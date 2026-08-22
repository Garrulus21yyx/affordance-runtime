"""PydanticAI bridge for one fresh-world grounded GUI decision.

PydanticAI owns provider adaptation, tool-call parsing, and call IDs.  Tools are
external/deferred because the GUI Runtime remains the only owner of binding,
execution, risk, observation, and evaluation.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlparse

from affordance_runtime.agent.context.context import AgentImageInput
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
from affordance_runtime.agent.decisions import (
    ProtocolFeedback,
    ProtocolFeedbackKind,
)
from affordance_runtime.immutable import to_json_compatible
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
    GROUNDED_TOOLS_PROTOCOL,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.grounded_tool_rejection import (
    grounded_tool_rejection_decision,
)
from affordance_runtime.model.policy.perception import DecisionPerceptionProfile
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.reasoning_policy import (
    ActionPolicyCallProfile,
    ActionPolicyReasoningPolicy,
)
from affordance_runtime.model.policy.request_admission import (
    ModelRequestBreakdown,
    ModelRequestCapacityError,
    request_breakdown_diagnostics,
)
from affordance_runtime.model.policy.tool_contracts import ToolCall

_MAX_PROVIDER_RETRIES = 1
_DEFAULT_PROVIDER_BACKOFF_S = 1.0
_MAX_PROVIDER_BACKOFF_S = 5.0


@dataclass(frozen=True)
class ConfiguredPydanticAIModel:
    model: object
    provider_id: str
    model_id: str
    endpoint_host: str
    supports_multimodal: bool


@dataclass(frozen=True)
class _ProviderFailureDetail:
    code: ProviderFailureCode
    retryable: bool
    reason: str
    exception_class: str
    status_code: int | None = None
    retry_after_s: float | None = None


class _ProviderCallExhausted(RuntimeError):
    def __init__(self, detail: _ProviderFailureDetail) -> None:
        super().__init__(detail.reason)
        self.detail = detail


def _action_model_settings(profile: ActionPolicyCallProfile) -> dict[str, object]:
    return {
        "thinking": profile.thinking_mode == "enabled",
        "max_tokens": profile.max_output_tokens,
        "temperature": 0.0,
        "parallel_tool_calls": False,
    }


@dataclass(frozen=True)
class PydanticAIGroundedDecisionPort:
    """Resolve exactly one current external tool call into a Runtime decision."""

    model: object
    provider_id: str
    model_id: str
    endpoint_host: str
    supports_multimodal: bool
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    transport_timeout_s: float = 85.0
    provider_retry_backoff_s: float = _DEFAULT_PROVIDER_BACKOFF_S
    max_provider_retry_delay_s: float = _MAX_PROVIDER_BACKOFF_S
    context_binder: GroundedPolicyContextBinder = field(default_factory=GroundedPolicyContextBinder)
    reasoning_policy: ActionPolicyReasoningPolicy = field(default_factory=ActionPolicyReasoningPolicy)
    consumed_recovery_events: frozenset[str] = field(default_factory=frozenset, init=False, compare=False)
    last_call_profile: ActionPolicyCallProfile | None = field(default=None, init=False, compare=False)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
    last_catalog_specs: tuple[object, ...] = field(default=(), init=False, compare=False)
    last_image_input_count: int = field(default=0, init=False, compare=False)
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_provider_retry_count: int = field(default=0, init=False, compare=False)
    last_generation_attempts: tuple[ModelGenerationAttempt, ...] = field(default=(), init=False, compare=False)
    last_request_breakdowns: tuple[ModelRequestBreakdown, ...] = field(default=(), init=False, compare=False)
    last_tool_resolution_code: GroundedToolResolutionCode | None = field(default=None, init=False, compare=False)
    last_tool_resolution_detail: str = field(default="", init=False, compare=False)
    last_invocation_result: ModelInvocationResult[ResolvedModelDecision] | None = field(
        default=None, init=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip() or not self.endpoint_host.strip():
            raise ValueError("PydanticAI model identity is required")
        if not 0 < self.transport_timeout_s <= 300:
            raise ValueError("PydanticAI transport timeout must be in (0, 300]")
        if not 0 <= self.provider_retry_backoff_s <= self.max_provider_retry_delay_s:
            raise ValueError("provider retry backoff must fit its bounded delay")
        if not 0 < self.max_provider_retry_delay_s <= _MAX_PROVIDER_BACKOFF_S:
            raise ValueError("provider retry delay must be in (0, 5]")
        object.__setattr__(self, "perception_profile", DecisionPerceptionProfile(self.perception_profile))

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return GROUNDED_ACTION_DECISION_CAPABILITIES

    @property
    def compatibility_key(self) -> str:
        return ":".join(
            (
                GROUNDED_TOOLS_PROTOCOL,
                "pydantic-ai",
                self.provider_id,
                self.model_id,
                self.endpoint_host,
                self.perception_profile.value,
            )
        )

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ModelInvocationResult[ResolvedModelDecision]:
        semantic_started = time.perf_counter()
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_bytes", 0)
        object.__setattr__(self, "last_catalog_specs", ())
        object.__setattr__(self, "last_image_input_count", 0)
        object.__setattr__(self, "last_model_call_count", 0)
        object.__setattr__(self, "last_provider_retry_count", 0)
        object.__setattr__(self, "last_generation_attempts", ())
        object.__setattr__(self, "last_request_breakdowns", ())
        object.__setattr__(self, "last_invocation_result", None)
        call_profile = self.reasoning_policy.select(
            request.agent_context,
            self.consumed_recovery_events,
        )
        object.__setattr__(self, "last_call_profile", call_profile)
        if call_profile.recovery_event_signature:
            object.__setattr__(
                self,
                "consumed_recovery_events",
                self.consumed_recovery_events | frozenset((call_profile.recovery_event_signature,)),
            )
        try:
            from pydantic_ai import (
                Agent,
                BinaryContent,
                DeferredToolRequests,
                ExternalToolset,
                ToolDefinition,
            )
            from pydantic_ai.exceptions import (
                ModelAPIError,
                UnexpectedModelBehavior,
                UsageLimitExceeded,
            )
            from pydantic_ai.usage import RunUsage, UsageLimits
        except ImportError:
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.INTERNAL_ERROR,
                    "PydanticAI optional dependency is not installed",
                ),
                request,
            )

        delivery = None
        try:
            delivery = self.context_binder.model_turn_delivery(
                request,
                supports_multimodal=self.supports_multimodal,
                perception_profile=self.perception_profile,
            )
            catalog = compile_grounded_action_catalog(request.agent_context, delivery)
            object.__setattr__(self, "last_catalog_count", len(catalog.specs))
            object.__setattr__(self, "last_catalog_bytes", catalog.serialized_bytes)
            object.__setattr__(self, "last_catalog_specs", tuple(catalog.specs))
            object.__setattr__(self, "last_image_input_count", len(request.image_inputs))
            object.__setattr__(self, "last_tool_resolution_code", None)
            object.__setattr__(self, "last_tool_resolution_detail", "")
            admitted = self.context_binder.action_request(
                request,
                catalog.specs,
                delivery,
                supports_multimodal=self.supports_multimodal,
                perception_profile=self.perception_profile,
                include_tool_menu=False,
            )
            self._append_request_breakdown(admitted.breakdown)
            messages = admitted.messages
            instructions, user_prompt = _pydantic_prompt(messages, request.image_inputs, BinaryContent)
            toolset = ExternalToolset(
                [
                    ToolDefinition(
                        name=spec.name,
                        description=spec.description,
                        parameters_json_schema=to_json_compatible(spec.input_schema),
                        strict=True,
                    )
                    for spec in admitted.tools
                ],
                id=catalog.catalog_id,
            )
            agent = Agent(
                self.model,
                name="action-policy",
                instructions=instructions,
                output_type=[str, DeferredToolRequests],
                retries=0,
            )
            usage = RunUsage()
            # One semantic decision may make one explicit transport retry.
            # SDK-level output/tool retry stays disabled so it cannot become
            # an implicit second policy call.
            limits = UsageLimits(request_limit=2)
            result = await self._run_provider_call(
                lambda: agent.run(
                    user_prompt,
                    toolsets=[toolset],
                    usage=usage,
                    usage_limits=limits,
                    model_settings=_action_model_settings(call_profile),
                ),
                phase=call_profile.phase.value,
                specs=catalog.specs,
                input_messages=_initial_input_transcript(instructions, user_prompt),
                provider_error_type=ModelAPIError,
            )
            resolution_error = None
            decision, resolution_error, initial_call = _resolve_deferred(result.output, catalog, request.context_id)
            self._set_tool_resolution(resolution_error, accepted=decision is not None)
            if resolution_error is not None and resolution_error.code is GroundedToolResolutionCode.MULTIPLE_CALLS:
                decision = _protocol_feedback_decision(
                    request.context_id,
                    result.output,
                    resolution_error,
                )
            elif decision is None and (resolution_error is None or initial_call is None):
                decision = ProtocolFeedback(
                    request.context_id,
                    ProtocolFeedbackKind.JSON_INVALID,
                    0,
                    (resolution_error.code.value if resolution_error is not None else "provider_envelope_invalid"),
                )
            if decision is None and resolution_error is not None and initial_call is not None:
                decision = grounded_tool_rejection_decision(
                    resolution_error,
                    initial_call,
                    request.context_id,
                    request.agent_context,
                )
            if decision is None:
                return self._invocation_failure(
                    _tool_resolution_failure(resolution_error),
                    request,
                    delivery,
                )
        except asyncio.CancelledError:
            self._invocation_failure(
                _failure(ModelFailureKind.TIMEOUT, "model invocation was cancelled"),
                request,
                delivery,
            )
            raise
        except UsageLimitExceeded:
            return self._protocol_feedback_invocation(
                request,
                delivery,
                semantic_started,
                "provider_request_limit_exhausted",
            )
        except UnexpectedModelBehavior as error:
            self._record_local_failure(error, "pydantic_ai_output_validation", catalog.specs)
            return self._protocol_feedback_invocation(
                request,
                delivery,
                semantic_started,
                "provider_envelope_invalid",
            )
        except _ProviderCallExhausted as error:
            detail = error.detail
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.PROVIDER_UNAVAILABLE,
                    detail.reason,
                    retryable=detail.retryable,
                    provider_code=detail.code,
                    retry_after_s=detail.retry_after_s,
                ),
                request,
                delivery,
            )
        except ModelRequestCapacityError as error:
            self._append_request_breakdown(error.breakdown)
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.CONTEXT_CAPACITY,
                    "context_capacity",
                    attempt_origin=ProviderAttemptOrigin.LOCAL_RUNTIME,
                ),
                request,
                delivery,
            )
        except GroundedToolResolutionError as exc:
            self._set_tool_resolution(exc, accepted=False)
            return self._invocation_failure(
                _tool_resolution_failure(exc),
                request,
                delivery,
            )
        except (ValueError, TypeError):
            return self._invocation_failure(
                _failure(ModelFailureKind.INVALID_TOOL_ARGUMENTS, "grounded tool response could not be resolved"),
                request,
                delivery,
            )
        except Exception as error:
            self._record_local_failure(error, "local_runtime", catalog.specs)
            return self._invocation_failure(
                _failure(
                    ModelFailureKind.INTERNAL_ERROR,
                    "PydanticAI decision adapter failed locally",
                ),
                request,
                delivery,
            )

        invocation_prompt_tokens = sum(item.prompt_tokens for item in self.last_generation_attempts)
        invocation_completion_tokens = sum(item.completion_tokens for item in self.last_generation_attempts)
        rate_limit_retries = sum(
            1
            for item in self.last_generation_attempts
            if isinstance(item.transcript, dict)
            and item.transcript.get("error.code") == ProviderFailureCode.RATE_LIMITED.value
        )
        metadata = ModelMetadata(
            provider_id=self.provider_id,
            model_id=self.model_id,
            endpoint_class="openai-compatible",
            prompt_version=self.context_binder.prompt_version(request.agent_context),
            schema_version=GROUNDED_TOOLS_PROTOCOL,
            latency_ms=(time.perf_counter() - semantic_started) * 1000,
            prompt_tokens=invocation_prompt_tokens,
            completion_tokens=invocation_completion_tokens,
            total_tokens=invocation_prompt_tokens + invocation_completion_tokens,
            rate_limit_retry_count=rate_limit_retries,
            transient_retry_count=max(0, self.last_provider_retry_count - rate_limit_retries),
            grounding_profile_version=GROUNDED_TOOLS_PROTOCOL,
            perception_profile=self.perception_profile.value,
            endpoint_host=self.endpoint_host,
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

    def _protocol_feedback_invocation(
        self,
        request: ModelDecisionRequest,
        delivery,
        semantic_started: float,
        detail: str,
    ) -> ModelInvocationResult[ResolvedModelDecision]:
        prompt_tokens = sum(item.prompt_tokens for item in self.last_generation_attempts)
        completion_tokens = sum(item.completion_tokens for item in self.last_generation_attempts)
        metadata = ModelMetadata(
            provider_id=self.provider_id,
            model_id=self.model_id,
            endpoint_class="openai-compatible",
            prompt_version=self.context_binder.prompt_version(request.agent_context),
            schema_version=GROUNDED_TOOLS_PROTOCOL,
            latency_ms=(time.perf_counter() - semantic_started) * 1000,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            transient_retry_count=self.last_provider_retry_count,
            grounding_profile_version=GROUNDED_TOOLS_PROTOCOL,
            perception_profile=self.perception_profile.value,
            endpoint_host=self.endpoint_host,
        )
        decision = ProtocolFeedback(
            request.context_id,
            ProtocolFeedbackKind.JSON_INVALID,
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
            attempts=self.last_generation_attempts,
            diagnostics=self._diagnostics(),
            lineage=self._lineage(request, delivery),
        )
        object.__setattr__(self, "last_invocation_result", invocation)
        return invocation

    def _lineage(self, request: ModelDecisionRequest, delivery=None) -> Mapping[str, object]:
        lineage = {
            "role": "ActionPolicy",
            "adapter": "pydantic-ai",
            "request_id": request.request_id,
            "context_id": request.context_id,
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
            "tool_transport": "pydantic-ai",
            "tool_catalog_count": self.last_catalog_count,
            "tool_catalog_bytes": self.last_catalog_bytes,
            "tool_catalog_specs": self.last_catalog_specs,
            "model_image_input_count": self.last_image_input_count,
            "policy_model_call_count": self.last_model_call_count,
            "provider_retry_count": self.last_provider_retry_count,
            "tool_resolution_code": (
                self.last_tool_resolution_code.value if self.last_tool_resolution_code is not None else ""
            ),
            "tool_resolution_detail": self.last_tool_resolution_detail,
            "reasoning_phase": (self.last_call_profile.phase.value if self.last_call_profile else ""),
            "reasoning_trigger": (self.last_call_profile.trigger.value if self.last_call_profile else ""),
            **request_breakdown_diagnostics(
                self.last_request_breakdowns,
                provider_reported_prompt_tokens=sum(item.prompt_tokens for item in self.last_generation_attempts),
            ),
        }

    def _append_request_breakdown(self, breakdown: ModelRequestBreakdown) -> None:
        object.__setattr__(self, "last_request_breakdowns", (*self.last_request_breakdowns, breakdown))

    def _set_tool_resolution(self, error: GroundedToolResolutionError | None, *, accepted: bool) -> None:
        if accepted:
            object.__setattr__(self, "last_tool_resolution_code", GroundedToolResolutionCode.ACCEPTED)
            object.__setattr__(self, "last_tool_resolution_detail", "")
            return
        if error is None:
            return
        object.__setattr__(self, "last_tool_resolution_code", error.code)
        object.__setattr__(self, "last_tool_resolution_detail", error.detail)

    async def _run_provider_call(
        self,
        call,
        *,
        phase: str,
        specs: tuple[object, ...],
        input_messages: object,
        provider_error_type: type[Exception],
    ) -> object:
        for retry_index in range(_MAX_PROVIDER_RETRIES + 1):
            attempt_phase = phase if retry_index == 0 else f"{phase}_provider_retry"
            if retry_index:
                object.__setattr__(
                    self,
                    "last_provider_retry_count",
                    self.last_provider_retry_count + 1,
                )
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            started = time.perf_counter()
            try:
                result = await call()
            except asyncio.CancelledError:
                self._record_cancelled_attempt(
                    attempt_phase,
                    specs,
                    input_messages,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                raise
            except provider_error_type as error:
                detail = _classify_provider_failure(error)
                self._record_provider_failure(
                    detail,
                    attempt_phase,
                    specs,
                    input_messages,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                if retry_index >= _MAX_PROVIDER_RETRIES or not detail.retryable:
                    raise _ProviderCallExhausted(detail) from error
                delay_s = min(
                    detail.retry_after_s
                    if detail.retry_after_s is not None
                    else self.provider_retry_backoff_s * (2**retry_index),
                    self.max_provider_retry_delay_s,
                )
                if delay_s:
                    await asyncio.sleep(delay_s)
                continue
            self._record_generation(
                result,
                attempt_phase,
                specs,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            return result
        raise AssertionError("bounded provider retry loop did not resolve")

    def _record_generation(
        self,
        result: object,
        phase: str,
        specs: tuple[object, ...],
        *,
        latency_ms: float = 0.0,
    ) -> None:
        messages = json.loads(result.new_messages_json())
        requests = [message for message in messages if message.get("kind") == "request"]
        responses = [message for message in messages if message.get("kind") == "response"]
        usage = result.usage
        response = responses[-1] if responses else {}
        attempt_prompt_tokens, raw_cumulative_prompt_tokens = _attempt_token_delta(
            self.last_generation_attempts,
            response,
            usage,
            "input_tokens",
        )
        attempt_completion_tokens, raw_cumulative_completion_tokens = _attempt_token_delta(
            self.last_generation_attempts,
            response,
            usage,
            "output_tokens",
        )
        attempt_cached_input_tokens = _response_usage_int(response, "cache_read_tokens")
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": requests,
            "llm.output_messages": responses,
            "llm.tools": [
                {
                    "tool.name": getattr(spec, "name", ""),
                    "tool.description": getattr(spec, "description", ""),
                    "tool.json_schema": to_json_compatible(getattr(spec, "input_schema", {})),
                }
                for spec in specs
            ],
            "llm.token_count.prompt": attempt_prompt_tokens,
            "llm.token_count.completion": attempt_completion_tokens,
            "llm.token_count.total": attempt_prompt_tokens + attempt_completion_tokens,
            "estimated_request_tokens": 0,
            "attempt_input_tokens": attempt_prompt_tokens,
            "attempt_cached_input_tokens": attempt_cached_input_tokens,
            "provider_raw_cumulative_input_tokens": raw_cumulative_prompt_tokens,
            "provider_raw_cumulative_output_tokens": raw_cumulative_completion_tokens,
            "response.id": str(response.get("provider_response_id") or ""),
            "status": "accepted",
            "error": "",
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts) + 1,
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="accepted",
            response_id=str(response.get("provider_response_id") or ""),
            latency_ms=latency_ms,
            prompt_tokens=attempt_prompt_tokens,
            completion_tokens=attempt_completion_tokens,
            total_tokens=attempt_prompt_tokens + attempt_completion_tokens,
            finish_reason=str(response.get("finish_reason") or "")[:80],
            max_output_tokens=(self.last_call_profile.max_output_tokens if self.last_call_profile else 0),
            final_content_present=bool(getattr(result.output, "calls", ())),
            reasoning_content_present=False,
            role="action_policy",
            mode="single_action",
            schema_version=GROUNDED_TOOLS_PROTOCOL,
            thinking_requested=(self.last_call_profile.thinking_mode if self.last_call_profile else "provider_default"),
            thinking_effective=(self.last_call_profile.thinking_mode if self.last_call_profile else "provider_default"),
            trigger=(self.last_call_profile.trigger.value if self.last_call_profile else "ordinary"),
            reasoning_tokens=0,
            final_content_tokens=attempt_completion_tokens,
            final_tool_call_present=bool(getattr(result.output, "calls", ())),
            transcript=transcript,
        )
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts, attempt),
        )

    def _record_cancelled_attempt(
        self,
        phase: str,
        specs: tuple[object, ...],
        input_messages: object,
        *,
        latency_ms: float,
    ) -> None:
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": input_messages,
            "llm.output_messages": [],
            "llm.tools": _tool_transcript(specs),
            "status": "cancelled",
            "network_dispatched": True,
            "error.code": "cancelled",
            "error.exception_class": "CancelledError",
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts) + 1,
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="cancelled",
            latency_ms=latency_ms,
            exception_class="CancelledError",
            **self._attempt_role_fields(),
            transcript=transcript,
        )
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts, attempt),
        )

    def _record_provider_failure(
        self,
        detail: _ProviderFailureDetail,
        phase: str,
        specs: tuple[object, ...],
        input_messages: object,
        *,
        latency_ms: float,
    ) -> None:
        transcript = {
            "openinference.span.kind": "LLM",
            "llm.system": self.provider_id,
            "llm.model_name": self.model_id,
            "llm.configured_endpoint_host": self.endpoint_host,
            "llm.input_messages": input_messages,
            "llm.output_messages": [],
            "llm.tools": _tool_transcript(specs),
            "status": "failed",
            "error.code": detail.code.value,
            "error.reason": detail.reason,
            "error.exception_class": detail.exception_class,
            "error.http_status": detail.status_code,
            "error.retryable": detail.retryable,
            "error.retry_after_s": detail.retry_after_s,
        }
        attempt = ModelGenerationAttempt(
            attempt=len(self.last_generation_attempts) + 1,
            phase=phase,
            schema_name=GROUNDED_TOOLS_PROTOCOL,
            status="failed",
            latency_ms=latency_ms,
            exception_class=detail.exception_class,
            **self._attempt_role_fields(),
            transcript=transcript,
        )
        object.__setattr__(
            self,
            "last_generation_attempts",
            (*self.last_generation_attempts, attempt),
        )

    def _attempt_role_fields(self) -> dict[str, object]:
        profile = self.last_call_profile
        return {
            "max_output_tokens": profile.max_output_tokens if profile else 0,
            "role": "action_policy",
            "mode": "single_action",
            "schema_version": GROUNDED_TOOLS_PROTOCOL,
            "thinking_requested": profile.thinking_mode if profile else "provider_default",
            "thinking_effective": profile.thinking_mode if profile else "provider_default",
            "trigger": profile.trigger.value if profile else "ordinary",
        }

    def _record_local_failure(
        self,
        error: Exception,
        phase: str,
        specs: tuple[object, ...],
    ) -> None:
        if self.last_generation_attempts and self.last_generation_attempts[-1].status == "failed":
            return
        detail = _ProviderFailureDetail(
            ProviderFailureCode.UNAVAILABLE,
            False,
            str(error)[:500] or "PydanticAI decision adapter failed locally",
            type(error).__name__,
        )
        self._record_provider_failure(detail, phase, specs, (), latency_ms=0.0)


def openai_compatible_pydantic_ai_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    """Build native-tool policy transport for supported OpenAI-compatible profiles."""

    if not 1 < call_timeout_s <= 300:
        raise ValueError("PydanticAI policy timeout must be in (1, 300]")
    env = os.environ if environment is None else environment
    configured = pydantic_ai_model_from_environment(env, call_timeout_s=call_timeout_s)
    selected_perception = DecisionPerceptionProfile(
        perception_profile or env.get("LLM_DECISION_PERCEPTION", DecisionPerceptionProfile.TEXT_ONLY.value)
    )
    retry_delay_budget_s = min(_MAX_PROVIDER_BACKOFF_S, max(0.1, call_timeout_s * 0.1))
    transport_timeout_s = (call_timeout_s - retry_delay_budget_s - 0.5) / 2
    if transport_timeout_s <= 0:
        raise ValueError("PydanticAI policy timeout cannot fit bounded provider recovery")
    port = PydanticAIGroundedDecisionPort(
        model=configured.model,
        provider_id=configured.provider_id,
        model_id=configured.model_id,
        endpoint_host=configured.endpoint_host,
        supports_multimodal=configured.supports_multimodal,
        perception_profile=selected_perception,
        transport_timeout_s=transport_timeout_s,
        provider_retry_backoff_s=min(_DEFAULT_PROVIDER_BACKOFF_S, retry_delay_budget_s),
        max_provider_retry_delay_s=retry_delay_budget_s,
        reasoning_policy=ActionPolicyReasoningPolicy(
            ordinary_max_tokens=_bounded_reasoning_tokens(
                env,
                "LLM_ACTION_POLICY_ORDINARY_MAX_TOKENS",
                1024,
                512,
                1024,
            ),
            deliberate_max_tokens=_bounded_reasoning_tokens(
                env,
                "LLM_ACTION_POLICY_DELIBERATE_MAX_TOKENS",
                2048,
                1024,
                2048,
            ),
            repair_max_tokens=_bounded_reasoning_tokens(
                env,
                "LLM_ACTION_POLICY_REPRESENTATION_REPAIR_MAX_TOKENS",
                512,
                256,
                512,
            ),
        ),
    )
    return ModelBackedAgentPolicy(port, call_timeout_s=call_timeout_s)


def pydantic_ai_model_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
) -> ConfiguredPydanticAIModel:
    """Build the one supported PydanticAI provider model configuration."""

    try:
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.models.zai import ZaiModel
        from pydantic_ai.providers.deepseek import DeepSeekProvider
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.providers.zai import ZaiProvider
    except ImportError as exc:
        raise RuntimeError("install the pydantic-ai project extra") from exc
    env = os.environ if environment is None else environment
    profile = env.get("LLM_ACTIVE_PROFILE", "").strip().casefold()
    if profile not in {"zhipu", "aliyun", "deepseek", "mistral", "gemini", "local"}:
        raise ValueError("PydanticAI model adapter requires a supported OpenAI-compatible profile")
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("PydanticAI model adapter forbids provider fallback")
    prefix = {
        "zhipu": "LLM_ZHIPU",
        "aliyun": "LLM_ALIYUN",
        "deepseek": "LLM_DEEPSEEK",
        "mistral": "LLM_MISTRAL",
        "gemini": "LLM_GEMINI",
        "local": "LLM_LOCAL",
    }[profile]
    if (
        profile == "local"
        and env.get("LLM_LOCAL_PROVIDER", "openai_compatible").strip().casefold() != "openai_compatible"
    ):
        raise ValueError("local PydanticAI ActionPolicy requires LLM_LOCAL_PROVIDER=openai_compatible")
    base_url = (
        env.get("LLM_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1").strip()
        if profile == "local"
        else _required(env, f"{prefix}_BASE_URL")
    )
    model_id = (
        (env.get("LLM_LOCAL_MODEL_ID") or env.get("LLM_LOCAL_MODEL") or "qwen2.5:7b").strip()
        if profile == "local"
        else _required(env, f"{prefix}_MODEL")
    )
    retry_delay_budget_s = min(_MAX_PROVIDER_BACKOFF_S, max(0.1, call_timeout_s * 0.1))
    transport_timeout_s = (call_timeout_s - retry_delay_budget_s - 0.5) / 2
    if transport_timeout_s <= 0:
        raise ValueError("PydanticAI policy timeout cannot fit bounded provider recovery")
    client = AsyncOpenAI(
        api_key=(env.get("LLM_LOCAL_API_KEY", "local") or "local")
        if profile == "local"
        else _required(env, f"{prefix}_API_KEY"),
        base_url=base_url,
        timeout=transport_timeout_s,
        max_retries=0,
    )
    if profile == "deepseek":
        model = OpenAIChatModel(model_id, provider=DeepSeekProvider(openai_client=client))
    elif profile in {"zhipu", "aliyun"}:
        model = ZaiModel(model_id, provider=ZaiProvider(openai_client=client))
    else:
        model = OpenAIChatModel(model_id, provider=OpenAIProvider(openai_client=client))
    return ConfiguredPydanticAIModel(
        model,
        profile,
        model_id,
        _endpoint_host(base_url),
        profile == "zhipu" and _zhipu_supports_multimodal(model_id),
    )


def _bounded_reasoning_tokens(
    environment: Mapping[str, str],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environment.get(key, "").strip()
    value = default if not raw else int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be within [{minimum}, {maximum}]")
    return value


def zhipu_pydantic_ai_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    """Compatibility entry point for existing Zhipu/Aliyun callers."""

    return openai_compatible_pydantic_ai_policy_from_environment(
        environment,
        call_timeout_s=call_timeout_s,
        perception_profile=perception_profile,
    )


def _endpoint_host(base_url: str) -> str:
    parsed = urlparse(base_url)
    return (parsed.netloc or parsed.path.split("/", 1)[0]).strip().casefold()


def _resolve_deferred(output, catalog, context_id: str):
    from pydantic_ai import DeferredToolRequests

    if not isinstance(output, DeferredToolRequests) or output.approvals:
        return None, None, None
    if len(output.calls) != 1:
        code = GroundedToolResolutionCode.ZERO_CALLS if not output.calls else GroundedToolResolutionCode.MULTIPLE_CALLS
        return None, GroundedToolResolutionError(code), None
    call = output.calls[0]
    parsed_call = None
    try:
        arguments = call.args_as_dict(raise_if_invalid=True)
        parsed_call = ToolCall(call.tool_name, arguments, call.tool_call_id)
        reconciliation = ProviderCallNormalizer().normalize(
            parsed_call,
            catalog,
        )
        if reconciliation.status is not ToolCallReconciliationStatus.EXACT:
            return None, _reconciliation_error(reconciliation), parsed_call
        assert reconciliation.exact_call is not None
        return (
            resolve_grounded_action_call(
                catalog,
                reconciliation.exact_call,
                expected_context_id=context_id,
                expected_delivery_id=catalog.delivery_id,
                expected_catalog_id=catalog.catalog_id,
            ).decision,
            None,
            reconciliation.exact_call,
        )
    except GroundedToolResolutionError as exc:
        return None, exc, parsed_call
    except (ValueError, TypeError):
        return None, GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS), parsed_call


def _reconciliation_error(reconciliation) -> GroundedToolResolutionError:
    code = (
        GroundedToolResolutionCode.UNKNOWN_OPERATION
        if str(reconciliation.issue_code) == "unknown_tool"
        else GroundedToolResolutionCode.STALE_CATALOG
        if str(reconciliation.issue_code) == "stale_catalog"
        else GroundedToolResolutionCode.INVALID_ARGUMENTS
    )
    detail = reconciliation.argument_code
    if reconciliation.field_paths:
        detail = f"{detail}:{','.join(reconciliation.field_paths)}" if detail else ",".join(reconciliation.field_paths)
    return GroundedToolResolutionError(code, detail)


def _tool_resolution_failure(error: GroundedToolResolutionError | None) -> ModelFailure:
    if error is None:
        return _failure(
            ModelFailureKind.SCHEMA_ERROR,
            "model did not produce one valid current tool call",
        )
    if error.code is GroundedToolResolutionCode.GROUNDING_GAP:
        return _failure(ModelFailureKind.TOOL_GROUNDING_GAP, str(error))
    return _failure(ModelFailureKind.INVALID_TOOL_ARGUMENTS, str(error))


def _protocol_feedback_decision(
    context_id: str,
    output,
    error: GroundedToolResolutionError,
) -> ProtocolFeedback:
    calls = getattr(output, "calls", ())
    return ProtocolFeedback(
        context_id,
        ProtocolFeedbackKind.MULTIPLE_TOOL_CALLS,
        min(len(calls), 32),
        error.code.value,
    )


def _pydantic_prompt(messages, image_inputs: Sequence[AgentImageInput], binary_content_type):
    if len(messages) != 2 or messages[0].role != "system" or messages[1].role != "user":
        raise ValueError("grounded PydanticAI prompt requires one system and one user message")
    instructions = messages[0].content
    if not isinstance(instructions, str):
        raise ValueError("grounded PydanticAI instructions must be text")
    content = messages[1].content
    if isinstance(content, str):
        return instructions, content
    text_parts = [part.text for part in content if part.type == "text"]
    if len(text_parts) != 1:
        raise ValueError("grounded PydanticAI prompt requires one public text projection")
    prompt: list[object] = [text_parts[0]]
    prompt.extend(binary_content_type(data=image.data, media_type=image.mime_type) for image in image_inputs)
    return instructions, prompt


def _initial_input_transcript(instructions: str, user_prompt: object) -> list[dict[str, object]]:
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": _safe_prompt_projection(user_prompt)},
    ]


def _safe_prompt_projection(value: object) -> object:
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        projected = []
        for item in value:
            data = getattr(item, "data", None)
            if isinstance(data, (bytes, bytearray)):
                projected.append(
                    {
                        "type": "binary",
                        "media_type": str(getattr(item, "media_type", "")),
                        "byte_count": len(data),
                    }
                )
            else:
                projected.append(to_json_compatible(item))
        return projected
    try:
        return to_json_compatible(value)
    except (TypeError, ValueError):
        return {"type": type(value).__name__}


def _attempt_token_delta(
    previous_attempts: tuple[ModelGenerationAttempt, ...],
    response: Mapping[str, object],
    usage: object,
    field_name: str,
) -> tuple[int, int]:
    response_value = _response_usage_int(response, field_name)
    raw_cumulative = _usage_int(usage, field_name)
    if response_value >= 0:
        return response_value, raw_cumulative
    previous = sum(
        (item.prompt_tokens if field_name == "input_tokens" else item.completion_tokens) for item in previous_attempts
    )
    return max(0, raw_cumulative - previous), raw_cumulative


def _response_usage_int(response: Mapping[str, object], field_name: str) -> int:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return -1
    value = usage.get(field_name)
    return value if type(value) is int and value >= 0 else -1


def _usage_int(usage: object, field_name: str) -> int:
    value = getattr(usage, field_name, 0)
    return value if type(value) is int and value >= 0 else 0


def _tool_transcript(specs: tuple[object, ...]) -> list[dict[str, object]]:
    return [
        {
            "tool.name": getattr(spec, "name", ""),
            "tool.description": getattr(spec, "description", ""),
            "tool.json_schema": to_json_compatible(getattr(spec, "input_schema", {})),
        }
        for spec in specs
    ]


def _classify_provider_failure(error: Exception) -> _ProviderFailureDetail:
    status_code = _provider_status_code(error)
    retry_after_s = _provider_retry_after_s(error)
    exception_class = type(error).__name__
    names = " ".join(type(item).__name__.casefold() for item in _exception_chain(error))
    if status_code == 429:
        return _ProviderFailureDetail(
            ProviderFailureCode.RATE_LIMITED,
            True,
            "model provider rate limited the decision request",
            exception_class,
            status_code,
            retry_after_s,
        )
    if status_code in {401, 403}:
        return _ProviderFailureDetail(
            ProviderFailureCode.AUTHENTICATION,
            False,
            "model provider authentication failed",
            exception_class,
            status_code,
        )
    if status_code is not None and 400 <= status_code < 500 and status_code not in {408, 409}:
        return _ProviderFailureDetail(
            ProviderFailureCode.INVALID_REQUEST,
            False,
            "model provider rejected the decision request",
            exception_class,
            status_code,
        )
    if status_code == 408 or "timeout" in names:
        return _ProviderFailureDetail(
            ProviderFailureCode.TIMEOUT,
            True,
            "model provider decision request timed out",
            exception_class,
            status_code,
            retry_after_s,
        )
    if "connection" in names or "transport" in names:
        return _ProviderFailureDetail(
            ProviderFailureCode.TRANSPORT,
            True,
            "model provider transport failed",
            exception_class,
            status_code,
            retry_after_s,
        )
    return _ProviderFailureDetail(
        ProviderFailureCode.UNAVAILABLE,
        status_code is None or status_code == 409 or status_code >= 500,
        "model provider is unavailable",
        exception_class,
        status_code,
        retry_after_s,
    )


def _exception_chain(error: Exception) -> tuple[BaseException, ...]:
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _provider_status_code(error: Exception) -> int | None:
    for item in _exception_chain(error):
        status = getattr(item, "status_code", None)
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None


def _provider_retry_after_s(error: Exception) -> float | None:
    for item in _exception_chain(error):
        headers = getattr(item, "headers", None)
        if not isinstance(headers, Mapping):
            response = getattr(item, "response", None)
            headers = getattr(response, "headers", None)
        if not isinstance(headers, Mapping):
            continue
        value = headers.get("retry-after") or headers.get("Retry-After")
        try:
            delay = float(value)
        except (TypeError, ValueError):
            continue
        if delay >= 0:
            return delay
    return None


def _failure(
    kind: ModelFailureKind,
    reason: str,
    *,
    retryable: bool = False,
    provider_code: ProviderFailureCode | None = None,
    retry_after_s: float | None = None,
    attempt_origin: ProviderAttemptOrigin = ProviderAttemptOrigin.NETWORK,
) -> ModelFailure:
    return ModelFailure(
        kind,
        reason,
        retryable,
        provider_code,
        retry_after_s,
        attempt_origin=attempt_origin,
    )


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"missing required model configuration: {name}")
    return value


def _enabled(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _zhipu_supports_multimodal(model_id: str) -> bool:
    return "v" in model_id.casefold().split("-", 2)[-1]


__all__ = [
    "PydanticAIGroundedDecisionPort",
    "openai_compatible_pydantic_ai_policy_from_environment",
    "zhipu_pydantic_ai_policy_from_environment",
]
