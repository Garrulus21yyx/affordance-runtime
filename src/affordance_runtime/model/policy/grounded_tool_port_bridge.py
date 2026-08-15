"""Grounded-tools v2 model bridge with one allowlisted workspace projection."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

from affordance_runtime.actions.schema_validation import validate_value_issue
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
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.contracts import (
    ModelDecisionRequest,
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
from affordance_runtime.model.policy.grounded_tool_compiler import CompiledGroundedTool
from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOL_CALL_ENVELOPE,
    GROUNDED_TOOLS_PROTOCOL,
    GroundedActionResolution,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model.policy.model_port_bridge import (
    DecisionPerceptionProfile,
    perception_uses_images,
)
from affordance_runtime.model.policy.provider_call_normalizer import (
    ProviderCallNormalizer,
    ToolCallIssueCode,
    ToolCallReconciliationResult,
    ToolCallReconciliationStatus,
)
from affordance_runtime.model.policy.spec import SCHEMA_VERSION
from affordance_runtime.model.policy.strict_json import validate_json_tree
from affordance_runtime.model.providers.port import (
    FallbackModelPort,
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
    StructuredOutputViolation,
    structured_output_repair_contract,
)
from affordance_runtime.model.providers.tool_transport import tool_transport_for_model
from affordance_runtime.model.providers.tool_transport_contracts import ToolCall, ToolSpec, ToolTransportKind


class _GroundedCommandPayloadBase(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    name: str
    arguments: dict[str, object] = Field(default_factory=dict)

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


_TOOL_INTENT_REPAIR_CODES = frozenset(
    {
        ToolCallIssueCode.UNKNOWN_TOOL,
        ToolCallIssueCode.TOOL_ARGUMENT_OWNER_MISMATCH,
        ToolCallIssueCode.AMBIGUOUS_TOOL_INTENT,
        ToolCallIssueCode.NON_EQUIVALENT_TOOL_INTENT,
    }
)


@dataclass(frozen=True)
class _GroundedAdapterBase:
    port: ModelPort
    config: ModelConfig
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    context_binder: GroundedPolicyContextBinder = field(default_factory=GroundedPolicyContextBinder)
    last_schema_repair_count: int = field(default=0, init=False, compare=False)
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_argument_repair_count: int = field(default=0, init=False, compare=False)
    last_tool_intent_repair_count: int = field(default=0, init=False, compare=False)
    last_resolution_code: GroundedToolResolutionCode | None = field(default=None, init=False, compare=False)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
    last_image_input_count: int = field(default=0, init=False, compare=False)
    last_argument_violation_code: str = field(default="", init=False, compare=False)
    last_argument_violation_paths: tuple[str, ...] = field(default=(), init=False, compare=False)
    last_selected_operation: str = field(default="", init=False, compare=False)
    last_repaired_operation_match: bool = field(default=False, init=False, compare=False)
    last_routing_normalization: str = field(default="", init=False, compare=False)
    last_routing_original_operation: str = field(default="", init=False, compare=False)
    last_routing_normalized_operation: str = field(default="", init=False, compare=False)
    last_structured_output_violations: tuple[StructuredOutputViolation, ...] = field(
        default=(), init=False, compare=False
    )
    last_structured_output_repair_attempted: bool = field(default=False, init=False, compare=False)
    last_structured_output_repair_failed: bool = field(default=False, init=False, compare=False)
    last_attempt_origin: ProviderAttemptOrigin = field(
        default=ProviderAttemptOrigin.UNKNOWN,
        init=False,
        compare=False,
    )
    transport_kind: ToolTransportKind = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.port, FallbackModelPort):
            raise ValueError("grounded-tools bridge does not admit provider fallback")
        if self.config.rate_limit_retries or self.config.transient_retries:
            raise ValueError("grounded-tools bridge requires a one-attempt transport")
        profile = DecisionPerceptionProfile(self.perception_profile)
        object.__setattr__(self, "perception_profile", profile)
        object.__setattr__(self, "transport_kind", tool_transport_for_model(self.port.provider, self.port.model))
        if not isinstance(self.context_binder, GroundedPolicyContextBinder):
            raise TypeError("grounded adapter requires one typed context binder")

    @property
    def interaction_protocol(self) -> str:
        return GROUNDED_TOOLS_PROTOCOL

    @property
    def requires_serialized_context(self) -> bool:
        return False

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

    def _reset_diagnostics(self) -> None:
        object.__setattr__(self, "last_schema_repair_count", 0)
        object.__setattr__(self, "last_model_call_count", 0)
        object.__setattr__(self, "last_argument_repair_count", 0)
        object.__setattr__(self, "last_tool_intent_repair_count", 0)
        object.__setattr__(self, "last_resolution_code", None)
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_bytes", 0)
        object.__setattr__(self, "last_image_input_count", 0)
        object.__setattr__(self, "last_argument_violation_code", "")
        object.__setattr__(self, "last_argument_violation_paths", ())
        object.__setattr__(self, "last_selected_operation", "")
        object.__setattr__(self, "last_repaired_operation_match", False)
        object.__setattr__(self, "last_routing_normalization", "")
        object.__setattr__(self, "last_routing_original_operation", "")
        object.__setattr__(self, "last_routing_normalized_operation", "")
        object.__setattr__(self, "last_structured_output_violations", ())
        object.__setattr__(self, "last_structured_output_repair_attempted", False)
        object.__setattr__(self, "last_structured_output_repair_failed", False)
        object.__setattr__(self, "last_attempt_origin", ProviderAttemptOrigin.UNKNOWN)

    def _compile_catalog(self, request: ModelDecisionRequest, expected_schema: str, catalog_builder):
        if request.schema_version != expected_schema or request.agent_context is None:
            raise ValueError("grounded tool request lacks canonical context")
        catalog = catalog_builder(request.agent_context)
        object.__setattr__(self, "last_catalog_count", len(catalog.specs))
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
        calls = await self._call(
            messages,
            catalog.specs,
            (),
            payload_base,
        )
        if not calls:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.ZERO_CALLS)
        if len(calls) != 1:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS)
        original_call = calls[0]
        call = original_call
        normalizer = ProviderCallNormalizer()
        reconciliation = normalizer.normalize(call, catalog)
        if reconciliation.status in {
            ToolCallReconciliationStatus.EXACT,
            ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT,
        }:
            assert reconciliation.exact_call is not None
            normalized = reconciliation.exact_call
            call = normalized
        else:
            normalized = call
        if reconciliation.status is ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT:
            normalization = (
                "redundant_grounding_to_constant"
                if normalized.arguments != original_call.arguments
                else "unique_same_operation_argument_owner"
            )
            object.__setattr__(self, "last_routing_normalization", normalization)
            object.__setattr__(self, "last_routing_original_operation", original_call.name)
            object.__setattr__(self, "last_routing_normalized_operation", normalized.name)
        elif reconciliation.issue_code in _TOOL_INTENT_REPAIR_CODES:
            object.__setattr__(self, "last_schema_repair_count", self.last_schema_repair_count + 1)
            object.__setattr__(self, "last_tool_intent_repair_count", 1)
            repaired = await self._repair_tool_intent(
                messages,
                catalog.specs,
                payload_base,
                original_call,
                reconciliation,
            )
            repaired_reconciliation = normalizer.normalize(repaired, catalog)
            if repaired_reconciliation.status not in {
                ToolCallReconciliationStatus.EXACT,
                ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT,
            }:
                raise GroundedToolResolutionError(
                    _resolution_code_for_reconciliation(repaired_reconciliation.issue_code)
                )
            assert repaired_reconciliation.exact_call is not None
            call = repaired_reconciliation.exact_call
            object.__setattr__(self, "last_routing_normalization", "bounded_model_reemission")
            object.__setattr__(self, "last_routing_original_operation", original_call.name)
            object.__setattr__(self, "last_routing_normalized_operation", call.name)
        elif (
            reconciliation.status
            not in {
                ToolCallReconciliationStatus.EXACT,
                ToolCallReconciliationStatus.NORMALIZED_EQUIVALENT,
            }
            and reconciliation.issue_code is not ToolCallIssueCode.INVALID_ARGUMENT
        ):
            raise GroundedToolResolutionError(
                _resolution_code_for_reconciliation(reconciliation.issue_code)
            )
        try:
            decision = resolver(
                catalog,
                call,
                expected_context_id=request.context_id,
                expected_catalog_id=catalog.catalog_id,
            )
        except GroundedToolResolutionError as exc:
            if (
                exc.code is not GroundedToolResolutionCode.INVALID_ARGUMENTS
                or self.last_argument_repair_count
                or self.last_tool_intent_repair_count
            ):
                raise
            spec = next((item for item in catalog.specs if item.name == call.name), None)
            if spec is None:
                raise
            binding = catalog.bindings[
                next(index for index, item in enumerate(catalog.specs) if item.name == call.name)
            ]
            issue = validate_value_issue(call.arguments, spec.input_schema, path="parameters")
            if issue is None:
                raise
            object.__setattr__(self, "last_argument_violation_code", issue.code.value)
            object.__setattr__(self, "last_argument_violation_paths", issue.public_field_paths)
            object.__setattr__(self, "last_selected_operation", spec.name)
            if _semantic_selector_violation(binding, issue.public_field_paths):
                # A different semantic/grounding selector is a different GUI decision.
                raise
            object.__setattr__(self, "last_schema_repair_count", self.last_schema_repair_count + 1)
            object.__setattr__(self, "last_argument_repair_count", 1)
            repaired = await self._repair_selected_operation(
                messages,
                spec,
                issue,
                payload_base,
                call,
                binding,
            )
            object.__setattr__(self, "last_repaired_operation_match", repaired.name == call.name)
            if repaired.name != call.name:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
            decision = resolver(
                catalog,
                repaired,
                expected_context_id=request.context_id,
                expected_catalog_id=catalog.catalog_id,
            )
        object.__setattr__(self, "last_resolution_code", GroundedToolResolutionCode.ACCEPTED)
        return decision, _metadata(
            self.port,
            self.transport_kind,
            self.perception_profile,
            include_record=True,
            prompt_version=self.context_binder.prompts.version,
        )

    async def _generate_structured(self, messages, output_schema):
        object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
        return await self.port.generate_structured(messages, output_schema, self.config)

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
        if isinstance(exc, (TypeError, ValueError, json.JSONDecodeError)):
            object.__setattr__(self, "last_resolution_code", GroundedToolResolutionCode.CATALOG_INVALID)
            return _failure(ModelFailureKind.INTERNAL_ERROR, "grounded workspace could not be built")
        raise exc

    async def _call(
        self,
        messages,
        specs,
        aliases=(),
        payload_base: type[_GroundedCommandPayloadBase] = GroundedToolCommandPayload,
    ) -> tuple[ToolCall, ...]:
        if self.transport_kind is ToolTransportKind.COMPACT_JSON:
            payload_type = _command_payload_type(specs, aliases, payload_base)
            try:
                payload = await self._generate_structured(messages, payload_type)
            except StructuredOutputError as exc:
                object.__setattr__(self, "last_schema_repair_count", self.last_schema_repair_count + 1)
                self._record_structured_output(exc, repair_attempted=True)
                try:
                    payload = await self._generate_structured(
                        _format_repair_messages(messages, exc),
                        payload_type,
                    )
                except StructuredOutputError as repair_exc:
                    self._record_structured_output(repair_exc, repair_failed=True)
                    raise
            alias_map = dict(aliases)
            operation_name = alias_map.get(payload.name, payload.name)
            spec = next((item for item in specs if item.name == operation_name), None)
            if spec is None and len(specs) == 1:
                spec = specs[0]
            operation = spec.name if spec is not None else payload.name
            return (ToolCall(operation, payload.command_arguments(spec)),)
        generate = getattr(self.port, "generate_tool_calls", None)
        if generate is None:
            raise ValueError("model port does not implement admitted native tool calls")
        try:
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            return await generate(
                messages,
                specs,
                self.config,
                require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
            )
        except StructuredOutputError as exc:
            object.__setattr__(self, "last_schema_repair_count", self.last_schema_repair_count + 1)
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            self._record_structured_output(exc, repair_attempted=True)
            try:
                return await generate(
                    _format_repair_messages(messages, exc),
                    specs,
                    self.config,
                    require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
                )
            except StructuredOutputError as repair_exc:
                self._record_structured_output(repair_exc, repair_failed=True)
                raise

    def _record_structured_output(
        self,
        error: StructuredOutputError,
        *,
        repair_attempted: bool = False,
        repair_failed: bool = False,
    ) -> None:
        combined = (*self.last_structured_output_violations, *error.violations)
        object.__setattr__(self, "last_structured_output_violations", combined[:8])
        object.__setattr__(
            self,
            "last_structured_output_repair_attempted",
            self.last_structured_output_repair_attempted or repair_attempted or repair_failed,
        )
        object.__setattr__(
            self,
            "last_structured_output_repair_failed",
            self.last_structured_output_repair_failed or repair_failed,
        )

    async def _repair_selected_operation(
        self,
        messages,
        spec: ToolSpec,
        issue,
        payload_base: type[_GroundedCommandPayloadBase],
        original_call: ToolCall,
        binding: object,
    ) -> ToolCall:
        repair_spec = _selector_fixed_repair_spec(spec, original_call, binding)
        repair_messages = _argument_repair_messages(messages, repair_spec, issue)
        if self.transport_kind is not ToolTransportKind.COMPACT_JSON:
            generate = getattr(self.port, "generate_tool_calls", None)
            if generate is None:
                raise ValueError("model port does not implement admitted native tool calls")
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            calls = await generate(
                repair_messages,
                (repair_spec,),
                self.config,
                require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
            )
            if not calls:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.ZERO_CALLS)
            if len(calls) != 1:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS)
            repaired = calls[0]
        else:
            payload_type = _command_payload_type((repair_spec,), payload_base=payload_base)
            payload = await self._generate_structured(repair_messages, payload_type)
            repaired = ToolCall(payload.name, payload.command_arguments(repair_spec))
        if _selector_changed(original_call, repaired, binding):
            raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
        return repaired

    async def _repair_tool_intent(
        self,
        messages,
        specs: tuple[ToolSpec, ...],
        payload_base: type[_GroundedCommandPayloadBase],
        original_call: ToolCall,
        reconciliation: ToolCallReconciliationResult,
    ) -> ToolCall:
        repair_messages = _tool_intent_repair_messages(
            messages,
            specs,
            original_call,
            reconciliation,
        )
        if self.transport_kind is ToolTransportKind.COMPACT_JSON:
            payload_type = _command_payload_type(specs, payload_base=payload_base)
            payload = await self._generate_structured(repair_messages, payload_type)
            return ToolCall(payload.name, payload.command_arguments())
        generate = getattr(self.port, "generate_tool_calls", None)
        if generate is None:
            raise ValueError("model port does not implement admitted native tool calls")
        object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
        calls = await generate(
            repair_messages,
            specs,
            self.config,
            require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
        )
        if not calls:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.ZERO_CALLS)
        if len(calls) != 1:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS)
        return calls[0]


@dataclass(frozen=True)
class GroundedActionAdapter(_GroundedAdapterBase):
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
                self.transport_kind.value,
                GROUNDED_TOOL_CALL_ENVELOPE,
            )
        )

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ResolvedModelDecision | ModelFailure:
        self._reset_diagnostics()
        try:
            catalog = self._compile_catalog(request, SCHEMA_VERSION, compile_grounded_action_catalog)
            context = request.agent_context
            if context is None:
                raise ValueError("grounded action requires one canonical AgentContext")
            messages = self.context_binder.action_messages(
                context,
                catalog.specs,
                request,
                supports_multimodal=self.port.supports_multimodal,
                perception_profile=self.perception_profile,
                include_tool_menu=self.transport_kind is ToolTransportKind.COMPACT_JSON,
            )
            resolution, metadata = await self._resolve_catalog(
                request,
                catalog,
                messages,
                resolve_grounded_action_call,
                GroundedToolCommandPayload,
            )
        except (
            GroundedToolResolutionError,
            ProviderModelError,
            StructuredModelError,
            TypeError,
            ValueError,
        ) as exc:
            return self._failure_from_exception(exc)
        if not isinstance(resolution, GroundedActionResolution):
            return _failure(ModelFailureKind.INTERNAL_ERROR, "action adapter resolved an objective")
        return ResolvedModelDecision(
            resolution.decision,
            metadata,
        )


def _command_payload_type(
    specs: tuple[ToolSpec, ...],
    aliases: tuple[tuple[str, str], ...] = (),
    payload_base: type[_GroundedCommandPayloadBase] = GroundedToolCommandPayload,
) -> type[_GroundedCommandPayloadBase]:
    """Constrain the wire envelope, leaving exact arguments to the selected ToolSpec."""

    names = (*tuple(item.name for item in specs), *(item[0] for item in aliases))
    if not names or len(names) != len(set(names)):
        raise ValueError("grounded operation menu is invalid")
    allowed_operation = Literal.__getitem__(names)
    return create_model(
        f"{payload_base.__name__}Envelope",
        __base__=payload_base,
        name=(allowed_operation, ...),
        arguments=(dict[str, object], ...),
    )


def _selector_names(binding: object) -> tuple[str, ...]:
    if not isinstance(binding, CompiledGroundedTool):
        return ()
    return tuple(item.public_name for item in binding.selector_fields)


def _resolution_code_for_reconciliation(
    code: ToolCallIssueCode | None,
) -> GroundedToolResolutionCode:
    if code is None:
        return GroundedToolResolutionCode.CATALOG_INVALID
    codes: dict[ToolCallIssueCode, GroundedToolResolutionCode] = {
        ToolCallIssueCode.UNKNOWN_TOOL: GroundedToolResolutionCode.UNKNOWN_TOOL,
        ToolCallIssueCode.INVALID_ARGUMENT: GroundedToolResolutionCode.INVALID_ARGUMENT,
        ToolCallIssueCode.TOOL_ARGUMENT_OWNER_MISMATCH: GroundedToolResolutionCode.TOOL_ARGUMENT_OWNER_MISMATCH,
        ToolCallIssueCode.AMBIGUOUS_TOOL_INTENT: GroundedToolResolutionCode.AMBIGUOUS_TOOL_INTENT,
        ToolCallIssueCode.NON_EQUIVALENT_TOOL_INTENT: GroundedToolResolutionCode.NON_EQUIVALENT_TOOL_INTENT,
        ToolCallIssueCode.STALE_CATALOG: GroundedToolResolutionCode.STALE_CATALOG,
    }
    return codes.get(code, GroundedToolResolutionCode.CATALOG_INVALID)


def _semantic_selector_violation(binding: object, field_paths: tuple[str, ...]) -> bool:
    names = _selector_names(binding)
    return any(
        path == f"parameters.{name}" or path.startswith(f"parameters.{name}.") for path in field_paths for name in names
    )


def _selector_fixed_repair_spec(
    spec: ToolSpec,
    original_call: ToolCall,
    binding: object,
) -> ToolSpec:
    names = _selector_names(binding)
    if not names or any(name not in original_call.arguments for name in names):
        return spec
    schema = to_json_compatible(spec.input_schema)
    if not isinstance(schema, dict):
        raise ValueError("grounded tool schema is invalid")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("grounded tool properties are invalid")
    for name in names:
        selector_schema = properties.get(name)
        if not isinstance(selector_schema, dict):
            raise ValueError("grounded selector schema is invalid")
        selector_schema["enum"] = [to_json_compatible(original_call.arguments[name])]
    return ToolSpec(spec.name, spec.description, schema)


def _selector_changed(original: ToolCall, repaired: ToolCall, binding: object) -> bool:
    return any(repaired.arguments.get(name) != original.arguments.get(name) for name in _selector_names(binding))


def _format_repair_messages(messages, error: StructuredOutputError):
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("grounded command repair requires text system message")
    return (
        ModelMessage(
            role="system",
            content=(
                system.content + "\n\nReturn exactly one JSON tool call with fields name and arguments. Copy one "
                "name exactly from the current tools list, and make arguments conform exactly to that tool's "
                "input_schema. Public validation contract: "
                + json.dumps(
                    structured_output_repair_contract(error),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        ),
        *messages[1:],
    )


def _argument_repair_messages(messages, spec, issue):
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("grounded argument repair requires a text system message")
    contract = {
        "repair_kind": "selected_grounded_operation_arguments",
        "selected_operation": spec.name,
        "input_schema": to_json_compatible(spec.input_schema),
        "violation": {
            "contract_owner": issue.contract_owner.value,
            "code": issue.code.value,
            "field_paths": list(issue.public_field_paths),
        },
        "recovery": {
            "operation_must_remain": spec.name,
            "only_arguments_may_change": True,
        },
    }
    return (
        ModelMessage(
            role="system",
            content=(
                system.content + "\n\nThe selected operation is fixed. Repair only its arguments, return one "
                "standard JSON tool call with fields name and arguments, and obey this public contract: "
                + json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            ),
        ),
        *messages[1:],
    )


def _tool_intent_repair_messages(
    messages,
    specs: tuple[ToolSpec, ...],
    original_call: ToolCall,
    reconciliation: ToolCallReconciliationResult,
):
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("grounded tool-intent repair requires a text system message")
    specs_by_name = {spec.name: spec for spec in specs}
    candidates = []
    for candidate in reconciliation.did_you_mean[:8]:
        spec = specs_by_name.get(candidate.tool_name)
        if spec is None:
            continue
        candidates.append(
            {
                "name": spec.name,
                "suggested_arguments": to_json_compatible(candidate.public_arguments),
                "input_schema": to_json_compatible(spec.input_schema),
            }
        )
    if not candidates:
        candidates = [
            {
                "name": spec.name,
                "suggested_arguments": {},
                "input_schema": to_json_compatible(spec.input_schema),
            }
            for spec in specs[:8]
        ]
    contract = {
        "repair_kind": "current_catalog_tool_intent",
        "issue_code": (
            reconciliation.issue_code.value
            if reconciliation.issue_code is not None
            else "catalog_invalid"
        ),
        "original_operation": original_call.name,
        "field_paths": list(reconciliation.field_paths),
        "argument_code": reconciliation.argument_code,
        "did_you_mean": candidates,
        "recovery": {
            "emit_one_complete_call": True,
            "copy_current_tool_name_exactly": True,
            "arguments_must_match_selected_input_schema": True,
            "runtime_will_not_rename_or_invent_business_arguments": True,
        },
    }
    return (
        ModelMessage(
            role="system",
            content=(
                system.content
                + "\n\nThe previous tool intent did not identify one exact current catalog row. "
                "Re-emit one complete standard JSON tool call with fields name and arguments. "
                "Use only the current tools and this bounded public repair contract: "
                + json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            ),
        ),
        *messages[1:],
    )


def _metadata(
    port,
    transport_kind,
    perception_profile,
    *,
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
        latency_ms=record.latency_ms if record is not None else 0.0,
        prompt_tokens=record.prompt_tokens if record is not None else 0,
        completion_tokens=record.completion_tokens if record is not None else 0,
        total_tokens=record.total_tokens if record is not None else 0,
        perception_profile=perception_profile.value,
        grounding_variant="grounded-tools",
        grounding_profile_version=GROUNDED_TOOLS_PROTOCOL,
        decision_schema_digest=transport_kind.value,
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
