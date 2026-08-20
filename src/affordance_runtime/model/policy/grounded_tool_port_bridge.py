"""Bounded compact-JSON adapter for models without native tool calls."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from affordance_runtime.agent.context.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
    ProviderFailureCode,
)
from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.agent.decisions import ProtocolFeedback, ProtocolFeedbackKind
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
    ModelGenerationAttempt,
    ModelInvocationResult,
    ModelMetadata,
    ResolvedModelDecision,
)
from affordance_runtime.model.policy.grounded_policy_context import (
    GroundedPolicyContextBinder,
)
from affordance_runtime.model.policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    resolve_grounded_action_call,
)
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOL_CALL_ENVELOPE,
    GROUNDED_TOOLS_PROTOCOL,
    GroundedActionResolution,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.grounded_tool_rejection import (
    grounded_tool_rejection_decision,
)
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
    perception_uses_images,
)
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallIssueCode,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.request_admission import (
    ModelRequestBreakdown,
    ModelRequestCapacityError,
    request_breakdown_diagnostics,
)
from affordance_runtime.model.policy.strict_json import validate_json_tree
from affordance_runtime.model.policy.tool_contracts import ToolCall, ToolSpec
from affordance_runtime.model.providers.port import (
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderFailureKind,
    ProviderModelError,
    ProviderTransportErrorCategory,
    StructuredModelError,
    StructuredOutputError,
    StructuredOutputFailureKind,
    StructuredOutputViolation,
)


class _GroundedCommandPayloadBase(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    name: str
    arguments: dict[str, object]

    @model_validator(mode="before")
    @classmethod
    def _normalize_tool_call_envelope(cls, value: object) -> object:
        """Accept equivalent provider wire shapes without changing argument values."""

        return ProviderCallNormalizer.normalize_wire_envelope(value)

    @field_validator("name")
    @classmethod
    def _operation(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("grounded operation is invalid")
        return value

    def command_arguments(self, spec: ToolSpec | None = None) -> dict[str, object]:
        del spec
        result = dict(self.arguments)
        validate_json_tree(result)
        return result


class GroundedToolCommandPayload(_GroundedCommandPayloadBase):
    """Compact action-selection command; retained as the public compatibility name."""


_NON_NORMALIZABLE_ISSUES = frozenset({ToolCallIssueCode.UNKNOWN_TOOL})


@dataclass(frozen=True)
class CompactJsonDecisionPort:
    port: ModelPort
    config: ModelConfig
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    context_binder: GroundedPolicyContextBinder = field(default_factory=GroundedPolicyContextBinder)
    truncated_retry_max_tokens: int = 512
    truncated_retry_thinking_mode: str | None = "disabled"
    timeout_fast_retry_timeout_s: float | None = None
    timeout_fast_retry_max_tokens: int = 512
    timeout_fast_retry_thinking_mode: str | None = "disabled"
    semantic_call_deadline_s: float | None = None
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_resolution_code: GroundedToolResolutionCode | None = field(default=None, init=False, compare=False)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_specs: tuple[object, ...] = field(default=(), init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
    last_image_input_count: int = field(default=0, init=False, compare=False)
    last_structured_output_violations: tuple[StructuredOutputViolation, ...] = field(
        default=(), init=False, compare=False
    )
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(
        default=(), init=False, compare=False
    )
    last_request_breakdowns: tuple[ModelRequestBreakdown, ...] = field(
        default=(), init=False, compare=False
    )
    last_invocation_result: ModelInvocationResult[ResolvedModelDecision] | None = field(
        default=None, init=False, compare=False
    )
    last_attempt_origin: ProviderAttemptOrigin = field(
        default=ProviderAttemptOrigin.UNKNOWN,
        init=False,
        compare=False,
    )
    def __post_init__(self) -> None:
        configured_timeout_retries = (
            self.config.transient_retries
            if self.config.timeout_retries is None
            else self.config.timeout_retries
        )
        if max(
            self.config.rate_limit_retries,
            self.config.transient_retries,
            configured_timeout_retries,
        ) > 1:
            raise ValueError("grounded-tools bridge allows at most one transport retry")
        profile = DecisionPerceptionProfile(self.perception_profile)
        object.__setattr__(self, "perception_profile", profile)
        if not isinstance(self.context_binder, GroundedPolicyContextBinder):
            raise TypeError("grounded adapter requires one typed context binder")
        if self.context_binder.request_budget.max_output_tokens != self.config.max_tokens:
            object.__setattr__(
                self,
                "context_binder",
                replace(
                    self.context_binder,
                    request_budget=replace(
                        self.context_binder.request_budget,
                        max_output_tokens=self.config.max_tokens,
                    ),
                ),
            )
        if not 64 <= self.truncated_retry_max_tokens <= 4_096:
            raise ValueError("truncated-output retry budget must be within [64, 4096]")
        if self.truncated_retry_thinking_mode not in {None, "enabled", "disabled"}:
            raise ValueError("truncated-output retry thinking mode is unsupported")
        if self.timeout_fast_retry_timeout_s is not None and self.timeout_fast_retry_timeout_s <= 0:
            raise ValueError("timeout fast-retry timeout must be positive")
        if not 64 <= self.timeout_fast_retry_max_tokens <= 4_096:
            raise ValueError("timeout fast-retry output budget must be within [64, 4096]")
        if self.timeout_fast_retry_thinking_mode not in {None, "enabled", "disabled"}:
            raise ValueError("timeout fast-retry thinking mode is unsupported")
        if self.semantic_call_deadline_s is not None:
            if self.semantic_call_deadline_s <= 0:
                raise ValueError("semantic call deadline must be positive")
            retry_timeout = self.timeout_fast_retry_timeout_s or 0.0
            if self.config.timeout_s + retry_timeout > self.semantic_call_deadline_s:
                raise ValueError("model attempt timeouts exceed the semantic call deadline")

    @property
    def interaction_protocol(self) -> str:
        return GROUNDED_TOOLS_PROTOCOL

    @property
    def provider_id(self) -> str:
        return self.port.provider

    @property
    def model_id(self) -> str:
        return self.port.model

    @property
    def grounding_profile_version(self) -> str:
        return GROUNDED_TOOLS_PROTOCOL

    @property
    def transport_timeout_s(self) -> float:
        return self.config.timeout_s

    @property
    def semantic_timeout_budget_s(self) -> float:
        return self.config.timeout_s + (self.timeout_fast_retry_timeout_s or 0.0)

    def _reset_diagnostics(self) -> None:
        object.__setattr__(self, "last_model_call_count", 0)
        object.__setattr__(self, "last_resolution_code", None)
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_specs", ())
        object.__setattr__(self, "last_catalog_bytes", 0)
        object.__setattr__(self, "last_image_input_count", 0)
        object.__setattr__(self, "last_structured_output_violations", ())
        object.__setattr__(self, "last_generation_attempts", ())
        object.__setattr__(self, "last_request_breakdowns", ())
        object.__setattr__(self, "last_invocation_result", None)
        object.__setattr__(self, "last_attempt_origin", ProviderAttemptOrigin.UNKNOWN)

    def _compile_catalog(self, request: ModelDecisionRequest, delivery):
        catalog = compile_grounded_action_catalog(request.agent_context, delivery)
        object.__setattr__(self, "last_catalog_count", len(catalog.specs))
        object.__setattr__(self, "last_catalog_specs", tuple(catalog.specs))
        object.__setattr__(self, "last_catalog_bytes", catalog.serialized_bytes)
        object.__setattr__(
            self,
            "last_image_input_count",
            len(request.image_inputs) if perception_uses_images(request, self.perception_profile) else 0,
        )
        object.__setattr__(self, "last_attempt_origin", ProviderAttemptOrigin.NETWORK)
        return catalog

    async def _resolve_catalog(
        self,
        request: ModelDecisionRequest,
        catalog,
        messages,
        resolver,
        payload_base: type[_GroundedCommandPayloadBase],
    ) -> tuple[object, ModelMetadata]:
        calls = await self._call(messages, catalog.specs, payload_base)
        if not calls:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.ZERO_CALLS)
        if len(calls) != 1:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS)
        original_call = _with_call_id(calls[0], request.request_id, "initial")
        call = original_call
        normalizer = ProviderCallNormalizer()
        reconciliation = normalizer.normalize(call, catalog)
        if reconciliation.status is ToolCallReconciliationStatus.EXACT:
            assert reconciliation.exact_call is not None
            call = reconciliation.exact_call
        if reconciliation.issue_code in _NON_NORMALIZABLE_ISSUES:
            # Unknown operation is not representation-equivalent. Preserve the
            # rejection and never make another provider call to choose a tool.
            error = GroundedToolResolutionError(
                _resolution_code_for_reconciliation(reconciliation.issue_code)
            )
            return self._rejection_resolution(request, original_call, error)
        elif (
            reconciliation.status is not ToolCallReconciliationStatus.EXACT
            and reconciliation.issue_code is not ToolCallIssueCode.INVALID_ARGUMENT
        ):
            error = GroundedToolResolutionError(
                _resolution_code_for_reconciliation(reconciliation.issue_code)
            )
            return self._rejection_resolution(request, original_call, error)
        try:
            decision = resolver(
                catalog,
                call,
                expected_context_id=request.context_id,
                expected_delivery_id=catalog.delivery_id,
                expected_catalog_id=catalog.catalog_id,
            )
        except GroundedToolResolutionError as exc:
            # Current target, grounding, stale-context, and semantic-argument
            # rejection are not repairable representations. Local catalog-aware
            # normalization already ran above; return the rejection unchanged.
            return self._rejection_resolution(request, original_call, exc)
        object.__setattr__(self, "last_resolution_code", GroundedToolResolutionCode.ACCEPTED)
        return decision, _metadata(
            self.port,
            self.perception_profile,
            attempts=self.last_generation_attempts,
            include_record=True,
            prompt_version=self.context_binder.prompt_version(request.agent_context),
        )

    def _rejection_resolution(
        self,
        request: ModelDecisionRequest,
        call: ToolCall,
        error: GroundedToolResolutionError,
    ) -> tuple[GroundedActionResolution, ModelMetadata]:
        object.__setattr__(self, "last_resolution_code", error.code)
        decision = grounded_tool_rejection_decision(
            error,
            call,
            request.context_id,
            request.agent_context,
        )
        return GroundedActionResolution(decision), _metadata(
            self.port,
            self.perception_profile,
            attempts=self.last_generation_attempts,
            include_record=True,
            prompt_version=self.context_binder.prompt_version(request.agent_context),
        )

    async def _generate_structured(
        self,
        messages,
        specs: tuple[ToolSpec, ...],
        output_schema,
        *,
        phase: str,
        config: ModelConfig | None = None,
    ):
        object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
        attempt = self.last_model_call_count
        try:
            result = await self.port.generate_structured(
                messages,
                output_schema,
                config or self.config,
            )
        except StructuredOutputError as exc:
            self._append_generation_attempt(
                _generation_attempt(
                    self.port,
                    attempt,
                    phase,
                    output_schema.__name__,
                    exc.kind.value,
                    violations=exc.violations,
                    exception_class=type(exc).__name__,
                    output_failure_kind=exc.kind,
                )
            )
            raise
        except ProviderModelError as exc:
            self._append_generation_attempt(
                _provider_failure_generation_attempt(
                    self.port,
                    attempt,
                    phase,
                    output_schema.__name__,
                    exc,
                )
            )
            raise
        except Exception as exc:
            self._append_generation_attempt(
                _generation_attempt(
                    self.port,
                    attempt,
                    phase,
                    output_schema.__name__,
                    "failed",
                    exception_class=type(exc).__name__,
                )
            )
            raise
        self._append_generation_attempt(
            _generation_attempt(
                self.port,
                attempt,
                phase,
                output_schema.__name__,
                "accepted",
            )
        )
        return result

    def _append_generation_attempt(self, attempt: ModelGenerationAttempt) -> None:
        object.__setattr__(self, "last_generation_attempts", (*self.last_generation_attempts, attempt))

    def _append_request_breakdown(self, breakdown: ModelRequestBreakdown) -> None:
        object.__setattr__(self, "last_request_breakdowns", (*self.last_request_breakdowns, breakdown))

    def _failure_from_exception(self, exc: Exception) -> ModelFailure:
        if isinstance(exc, GroundedToolResolutionError):
            object.__setattr__(self, "last_resolution_code", exc.code)
            return _failure(ModelFailureKind.SCHEMA_ERROR, exc.code.value)
        if isinstance(exc, ProviderModelError):
            if exc.kind is ProviderFailureKind.QUOTA_EXHAUSTED:
                return _failure(
                    ModelFailureKind.REFUSED,
                    "model provider quota is exhausted",
                    provider_code=ProviderFailureCode.QUOTA_EXHAUSTED,
                )
            if exc.error_category is ProviderTransportErrorCategory.TIMEOUT:
                return _failure(
                    ModelFailureKind.TIMEOUT,
                    "model provider timed out",
                    retryable=exc.resumable,
                    provider_code=ProviderFailureCode.TIMEOUT,
                    attempt_origin=(
                        ProviderAttemptOrigin.LOCAL_CIRCUIT
                        if exc.circuit_open
                        else ProviderAttemptOrigin.NETWORK
                    ),
                )
            provider_code = (
                ProviderFailureCode.RATE_LIMITED
                if exc.kind is ProviderFailureKind.RATE_LIMIT_TRANSIENT
                else ProviderFailureCode.UNAVAILABLE
            )
            return _failure(
                ModelFailureKind.PROVIDER_UNAVAILABLE,
                "model provider declined the grounded tool request",
                retryable=exc.resumable,
                provider_code=provider_code,
                retry_after_s=exc.retry_after_s,
                attempt_origin=(
                    ProviderAttemptOrigin.LOCAL_CIRCUIT if exc.circuit_open else ProviderAttemptOrigin.NETWORK
                ),
            )
        if isinstance(exc, StructuredOutputError):
            return _failure(
                ModelFailureKind.SCHEMA_ERROR,
                "grounded cognition violated its structured schema",
                attempt_origin=ProviderAttemptOrigin.NETWORK,
            )
        if isinstance(exc, StructuredModelError):
            return _failure(ModelFailureKind.INVALID_RESPONSE, "grounded cognition response was invalid")
        if isinstance(exc, ModelRequestCapacityError):
            self._append_request_breakdown(exc.breakdown)
            object.__setattr__(self, "last_attempt_origin", ProviderAttemptOrigin.LOCAL_RUNTIME)
            return _failure(
                ModelFailureKind.CONTEXT_CAPACITY,
                "context_capacity",
                attempt_origin=ProviderAttemptOrigin.LOCAL_RUNTIME,
            )
        if isinstance(exc, (TypeError, ValueError, json.JSONDecodeError)):
            object.__setattr__(self, "last_resolution_code", GroundedToolResolutionCode.CATALOG_INVALID)
            return _failure(ModelFailureKind.INTERNAL_ERROR, "grounded workspace could not be built")
        raise exc

    async def _call(
        self,
        messages,
        specs: tuple[ToolSpec, ...],
        payload_type: type[_GroundedCommandPayloadBase] = GroundedToolCommandPayload,
    ) -> tuple[ToolCall, ...]:
        try:
            payload = await self._generate_structured(
                messages,
                specs,
                payload_type,
                phase="initial",
            )
        except ProviderModelError as exc:
            if (
                exc.error_category is not ProviderTransportErrorCategory.TIMEOUT
                or self.timeout_fast_retry_timeout_s is None
                or exc.physical_attempt_count != 1
            ):
                raise
            retry_thinking = (
                self.timeout_fast_retry_thinking_mode
                if bool(getattr(self.port, "supports_thinking_control", False))
                else None
            )
            retry_config = self.config.model_copy(update={
                "max_tokens": self.timeout_fast_retry_max_tokens,
                "timeout_s": self.timeout_fast_retry_timeout_s,
                "provider_total_timeout_s": self.timeout_fast_retry_timeout_s,
                "rate_limit_retries": 0,
                "transient_retries": 0,
                "timeout_retries": 0,
                "thinking_mode": retry_thinking,
            })
            recovery_messages = (
                *messages,
                ModelMessage(
                    role="user",
                    content=(
                        "The prior request timed out before returning a command. "
                        "Using the same current World and tool catalog, return exactly one compact JSON command now."
                    ),
                ),
            )
            payload = await self._generate_structured(
                recovery_messages,
                specs,
                payload_type,
                phase="timeout_fast_retry",
                config=retry_config,
            )
        except StructuredOutputError as exc:
            self._record_structured_output(exc)
            if exc.kind is not StructuredOutputFailureKind.OUTPUT_TRUNCATED:
                raise
            retry_thinking = (
                self.truncated_retry_thinking_mode
                if bool(getattr(self.port, "supports_thinking_control", False))
                else None
            )
            retry_config = self.config.model_copy(update={
                "max_tokens": self.truncated_retry_max_tokens,
                "thinking_mode": retry_thinking,
            })
            recovery_messages = (
                *messages,
                ModelMessage(
                    role="user",
                    content=(
                        "The prior provider response exhausted its output budget before final content. "
                        "Return exactly one compact JSON command matching the current schema."
                    ),
                ),
            )
            try:
                payload = await self._generate_structured(
                    recovery_messages,
                    specs,
                    payload_type,
                    phase="truncated_output_retry",
                    config=retry_config,
                )
            except StructuredOutputError as retry_error:
                self._record_structured_output(retry_error)
                raise
        return (ToolCall(payload.name, payload.command_arguments()),)

    def _record_structured_output(
        self,
        error: StructuredOutputError,
    ) -> None:
        combined = (*self.last_structured_output_violations, *error.violations)
        object.__setattr__(self, "last_structured_output_violations", combined[:8])

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return GROUNDED_ACTION_DECISION_CAPABILITIES

    @property
    def compatibility_key(self) -> str:
        return ":".join(
            (
                GROUNDED_TOOLS_PROTOCOL,
                "action_selection",
                self.perception_profile.value,
                "compact_json",
                GROUNDED_TOOL_CALL_ENVELOPE,
            )
        )

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ModelInvocationResult[ResolvedModelDecision]:
        self._reset_diagnostics()
        delivery = None
        try:
            delivery = self.context_binder.model_turn_delivery(
                request,
                supports_multimodal=self.port.supports_multimodal,
                perception_profile=self.perception_profile,
            )
            catalog = self._compile_catalog(request, delivery)
            admitted = self.context_binder.action_request(
                request,
                catalog.specs,
                delivery,
                supports_multimodal=self.port.supports_multimodal,
                perception_profile=self.perception_profile,
                include_tool_menu=True,
            )
            self._append_request_breakdown(admitted.breakdown)
            resolution, metadata = await self._resolve_catalog(
                request,
                catalog,
                admitted.messages,
                resolve_grounded_action_call,
                GroundedToolCommandPayload,
            )
        except (
            GroundedToolResolutionError,
            ProviderModelError,
            StructuredModelError,
            ModelRequestCapacityError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, StructuredOutputError):
                return self._protocol_feedback_invocation(
                    request,
                    delivery,
                    ProtocolFeedbackKind(exc.kind.value),
                    exc.kind.value,
                )
            return self._invocation_failure(self._failure_from_exception(exc), request, delivery)
        if not isinstance(resolution, GroundedActionResolution):
            return self._invocation_failure(
                _failure(ModelFailureKind.INTERNAL_ERROR, "action adapter resolved an objective"),
                request,
                delivery,
            )
        invocation = ModelInvocationResult(
            output=ResolvedModelDecision(resolution.decision, metadata),
            metadata=metadata,
            attempts=self.last_generation_attempts,
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request, delivery),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _protocol_feedback_invocation(
        self,
        request,
        delivery,
        kind: ProtocolFeedbackKind,
        detail: str,
    ):
        metadata = _metadata(
            self.port,
            self.perception_profile,
            attempts=self.last_generation_attempts,
            include_record=True,
            prompt_version=self.context_binder.prompt_version(request.agent_context),
        )
        decision = ProtocolFeedback(
            request.context_id,
            kind,
            0,
            detail,
        )
        invocation = ModelInvocationResult(
            output=ResolvedModelDecision(decision, metadata),
            metadata=metadata,
            attempts=self.last_generation_attempts,
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request, delivery),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _invocation_failure(
        self,
        failure: ModelFailure,
        request: ModelDecisionRequest,
        delivery=None,
    ) -> ModelInvocationResult[ResolvedModelDecision]:
        invocation = ModelInvocationResult(
            failure=failure,
            metadata=_metadata(
                self.port,
                self.perception_profile,
                attempts=self.last_generation_attempts,
                include_record=False,
                prompt_version=self.context_binder.prompt_version(request.agent_context),
            ),
            attempts=self.last_generation_attempts,
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request, delivery),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _lineage(self, request: ModelDecisionRequest, delivery=None) -> Mapping[str, object]:
        lineage = {
            "role": "ActionPolicy",
            "adapter": "compact-json",
            "request_id": request.request_id,
            "context_id": request.context_id,
            "compatibility_shim": True,
        }
        if delivery is not None:
            lineage.update(
                {
                    "delivery_id": delivery.delivery_id,
                    "world_observation_id": delivery.world_observation_id,
                }
            )
        return lineage

    def _diagnostics(self) -> Mapping[str, object]:
        return {
            "interaction_protocol": GROUNDED_TOOLS_PROTOCOL,
            "tool_transport": "compact-json",
            "tool_resolution_code": self.last_resolution_code.value if self.last_resolution_code else "",
            "tool_catalog_count": self.last_catalog_count,
            "tool_catalog_bytes": self.last_catalog_bytes,
            "tool_catalog_specs": self.last_catalog_specs,
            "model_image_input_count": self.last_image_input_count,
            "policy_model_call_count": self.last_model_call_count,
            "provider_output_failures": tuple(
                item.output_failure_kind.value
                for item in self.last_generation_attempts
                if item.output_failure_kind is not None
            ),
            "provider_finish_reasons": tuple(
                item.finish_reason for item in self.last_generation_attempts
            ),
            "truncated_output_retry_count": sum(
                item.phase == "truncated_output_retry"
                for item in self.last_generation_attempts
            ),
            "timeout_fast_retry_count": sum(
                item.phase == "timeout_fast_retry"
                for item in self.last_generation_attempts
            ),
            "provider_retry_count": sum(
                _attempt_retry_count(item) for item in self.last_generation_attempts
            ) + sum(
                item.phase == "timeout_fast_retry"
                for item in self.last_generation_attempts
            ),
            "provider_physical_attempt_count": sum(
                _attempt_physical_count(item) for item in self.last_generation_attempts
            ),
            "structured_output_validation_stage": "provider_response_to_grounded_command",
            "structured_output_violations": self.last_structured_output_violations,
            "compatibility_shim": True,
            **request_breakdown_diagnostics(
                self.last_request_breakdowns,
                provider_reported_prompt_tokens=sum(item.prompt_tokens for item in self.last_generation_attempts),
            ),
        }


def _with_call_id(call: ToolCall, request_id: str, phase: str) -> ToolCall:
    if call.call_id:
        return call
    digest = hashlib.sha256(f"{request_id}:{phase}".encode()).hexdigest()[:24]
    return replace(call, call_id=f"call:{digest}")


def _generation_attempt(
    port,
    attempt: int,
    phase: str,
    schema_name: str,
    status: str,
    *,
    violations: tuple[StructuredOutputViolation, ...] = (),
    exception_class: str = "",
    output_failure_kind: StructuredOutputFailureKind | None = None,
) -> ModelGenerationAttempt:
    record = getattr(port, "last_call", None)
    return ModelGenerationAttempt(
        attempt,
        phase,
        schema_name,
        status,
        violations,
        response_id=str(getattr(record, "response_id", "")),
        latency_ms=float(getattr(record, "latency_ms", 0.0)),
        prompt_tokens=int(getattr(record, "prompt_tokens", 0)),
        completion_tokens=int(getattr(record, "completion_tokens", 0)),
        total_tokens=int(getattr(record, "total_tokens", 0)),
        exception_class=exception_class,
        output_failure_kind=output_failure_kind,
        finish_reason=str(getattr(record, "finish_reason", "")),
        max_output_tokens=int(getattr(record, "max_output_tokens", 0)),
        final_content_present=bool(getattr(record, "final_content_present", False)),
        reasoning_content_present=bool(
            getattr(record, "reasoning_content_present", False)
        ),
        response_fields=tuple(getattr(record, "response_fields", ())),
        transcript=getattr(port, "last_transcript", None),
    )


def _provider_failure_generation_attempt(
    port,
    attempt: int,
    phase: str,
    schema_name: str,
    error: ProviderModelError,
) -> ModelGenerationAttempt:
    return ModelGenerationAttempt(
        attempt,
        phase,
        schema_name,
        "failed",
        latency_ms=error.latency_ms,
        exception_class=error.exception_class or type(error).__name__,
        transcript=getattr(port, "last_transcript", None),
    )


def _attempt_transcript_int(attempt: ModelGenerationAttempt, key: str) -> int:
    transcript = attempt.transcript
    if not isinstance(transcript, Mapping):
        return 0
    value = transcript.get(key, 0)
    return value if type(value) is int and value >= 0 else 0


def _attempt_retry_count(attempt: ModelGenerationAttempt) -> int:
    return _attempt_transcript_int(
        attempt, "network.rate_limit_retry_count"
    ) + _attempt_transcript_int(attempt, "network.transient_retry_count")


def _attempt_physical_count(attempt: ModelGenerationAttempt) -> int:
    return _attempt_transcript_int(attempt, "network.physical_attempt_count")


def _resolution_code_for_reconciliation(
    code: ToolCallIssueCode | None,
) -> GroundedToolResolutionCode:
    if code is None:
        return GroundedToolResolutionCode.CATALOG_INVALID
    codes: dict[ToolCallIssueCode, GroundedToolResolutionCode] = {
        ToolCallIssueCode.UNKNOWN_TOOL: GroundedToolResolutionCode.UNKNOWN_TOOL,
        ToolCallIssueCode.INVALID_ARGUMENT: GroundedToolResolutionCode.INVALID_ARGUMENT,
        ToolCallIssueCode.STALE_CATALOG: GroundedToolResolutionCode.STALE_CATALOG,
    }
    return codes.get(code, GroundedToolResolutionCode.CATALOG_INVALID)


def _metadata(
    port,
    perception_profile,
    *,
    attempts: tuple[ModelGenerationAttempt, ...] = (),
    include_record=True,
    prompt_version="",
):
    record = port.last_call if include_record else None
    return ModelMetadata(
        provider_id=port.provider,
        model_id=port.model,
        response_id=record.response_id if record is not None else "",
        endpoint_class=port.endpoint_class,
        prompt_version=prompt_version or (record.prompt_version if record is not None else ""),
        schema_version=GROUNDED_TOOLS_PROTOCOL,
        latency_ms=(
            sum(item.latency_ms for item in attempts)
            if attempts
            else record.latency_ms if record is not None else 0.0
        ),
        prompt_tokens=(
            sum(item.prompt_tokens for item in attempts)
            if attempts
            else record.prompt_tokens if record is not None else 0
        ),
        completion_tokens=(
            sum(item.completion_tokens for item in attempts)
            if attempts
            else record.completion_tokens if record is not None else 0
        ),
        total_tokens=(
            sum(item.total_tokens for item in attempts)
            if attempts
            else record.total_tokens if record is not None else 0
        ),
        rate_limit_retry_count=sum(
            _attempt_transcript_int(item, "network.rate_limit_retry_count")
            for item in attempts
        ),
        transient_retry_count=sum(
            _attempt_transcript_int(item, "network.transient_retry_count")
            for item in attempts
        ),
        perception_profile=perception_profile.value,
        grounding_variant="grounded-tools",
        grounding_profile_version=GROUNDED_TOOLS_PROTOCOL,
    )


def _failure(
    kind,
    reason,
    *,
    retryable=False,
    provider_code=None,
    retry_after_s=None,
    attempt_origin=ProviderAttemptOrigin.UNKNOWN,
):
    return ModelFailure(kind, reason, retryable, provider_code, retry_after_s, attempt_origin)
