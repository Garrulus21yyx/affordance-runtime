"""Grounded-tools v2 model bridge with one allowlisted workspace projection."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model, field_validator

from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.agent.working_memory import (
    MAX_WORKING_MEMORY_BLOCKERS,
    MAX_WORKING_MEMORY_DERIVED_FACTS,
    MAX_WORKING_MEMORY_DESCRIPTION_CHARS,
    MAX_WORKING_MEMORY_GOAL_CHARS,
    MAX_WORKING_MEMORY_ITEMS,
    MAX_WORKING_MEMORY_NEXT_STEP_CHARS,
    AgentWorkingMemory,
    WorkingMemoryItem,
    WorkingMemoryItemStatus,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.failures import (
    ModelFailure,
    ModelFailureKind,
    ProviderAttemptOrigin,
    ProviderFailureCode,
)
from affordance_runtime.model_policy.contracts import (
    ModelDecisionRequest,
    ModelMetadata,
    ResolvedLocalObjectiveOutcome,
    ResolvedModelDecision,
)
from affordance_runtime.model_policy.grounded_policy_context import (
    GroundedPolicyContextBinder,
)
from affordance_runtime.model_policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    compile_grounded_objective_catalog,
    resolve_grounded_action_call,
    resolve_grounded_objective_call,
)
from affordance_runtime.model_policy.grounded_tool_contracts import (
    GROUNDED_TOOLS_PROTOCOL,
    GroundedActionResolution,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model_policy.model_port_bridge import (
    DecisionPerceptionProfile,
    perception_uses_images,
)
from affordance_runtime.model_policy.objective_spec import OBJECTIVE_SCHEMA_VERSION
from affordance_runtime.model_policy.spec import SCHEMA_VERSION
from affordance_runtime.model_policy.strict_json import validate_json_tree
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolSpec, ToolTransportKind
from affordance_runtime.model_port import (
    FallbackModelPort,
    ModelConfig,
    ModelMessage,
    ModelPort,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
    structured_output_repair_contract,
)
from affordance_runtime.model_tool_transport import tool_transport_for_model
from affordance_runtime.world.schema_validation import validate_value_issue


class _GroundedCommandPayloadBase(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    op: str
    value: object | None = None

    @field_validator("op")
    @classmethod
    def _operation(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("grounded operation is invalid")
        return value

    @field_validator("value")
    @classmethod
    def _value(cls, value: object | None) -> object | None:
        validate_json_tree(value)
        return value

    def command_arguments(self, spec: ToolSpec | None = None) -> dict[str, object]:
        admitted = _admitted_properties(spec, {"value"})
        return {"value": self.value} if self.value is not None and "value" in admitted else {}


class GroundedWorkingMemoryItemPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    description: str
    status: Literal["pending", "in_progress", "completed"]

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        if not value.strip() or len(value) > MAX_WORKING_MEMORY_DESCRIPTION_CHARS:
            raise ValueError("working-memory description is invalid")
        return value


class GroundedWorkingMemoryPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    items: list[GroundedWorkingMemoryItemPayload]

    @field_validator("items")
    @classmethod
    def _items(
        cls,
        value: list[GroundedWorkingMemoryItemPayload],
    ) -> list[GroundedWorkingMemoryItemPayload]:
        if len(value) > MAX_WORKING_MEMORY_ITEMS:
            raise ValueError("working memory exceeds its item bound")
        return value


class GroundedTaskStatePayload(GroundedWorkingMemoryPayload):
    """Complete advisory task state produced before action selection."""

    goal: str
    derived_facts: list[str]
    next_step: str
    ready_to_finalize: bool
    blockers: list[str]

    @field_validator("goal")
    @classmethod
    def _goal(cls, value: str) -> str:
        if not value.strip() or len(value) > MAX_WORKING_MEMORY_GOAL_CHARS:
            raise ValueError("task-state goal is invalid")
        return value

    @field_validator("next_step")
    @classmethod
    def _next_step(cls, value: str) -> str:
        if len(value) > MAX_WORKING_MEMORY_NEXT_STEP_CHARS:
            raise ValueError("task-state next step is invalid")
        return value

    @field_validator("derived_facts")
    @classmethod
    def _derived_facts(cls, value: list[str]) -> list[str]:
        return _bounded_task_state_statements(value, MAX_WORKING_MEMORY_DERIVED_FACTS)

    @field_validator("blockers")
    @classmethod
    def _blockers(cls, value: list[str]) -> list[str]:
        return _bounded_task_state_statements(value, MAX_WORKING_MEMORY_BLOCKERS)


class GroundedToolCommandPayload(_GroundedCommandPayloadBase):
    """Compact action-selection command; retained as the public compatibility name."""

    target: str = ""
    text: str | None = None

    @field_validator("target")
    @classmethod
    def _target(cls, value: str) -> str:
        if value and (not value.startswith("E") or not value[1:].isdigit()):
            raise ValueError("grounded target ref is invalid")
        return value

    def command_arguments(self, spec: ToolSpec | None = None) -> dict[str, object]:
        result = super().command_arguments(spec)
        admitted = _admitted_properties(spec, {"target", "text", "value"})
        if self.target and "target" in admitted:
            result["target"] = self.target
        if self.text is not None and "text" in admitted:
            result["text"] = self.text
        return result


class GroundedObjectiveCommandPayload(_GroundedCommandPayloadBase):
    """Compact objective-proposal command with no action-selection fields."""


def _bounded_task_state_statements(value: list[str], limit: int) -> list[str]:
    if len(value) > limit or any(
        not item.strip() or len(item) > MAX_WORKING_MEMORY_DESCRIPTION_CHARS
        for item in value
    ):
        raise ValueError("task-state statements are invalid")
    return value


def _admitted_properties(spec: ToolSpec | None, default: set[str]) -> set[str]:
    if spec is None:
        return set(default)
    properties = spec.input_schema.get("properties")
    return set(properties) if isinstance(properties, Mapping) else set()


@dataclass(frozen=True)
class _GroundedAdapterBase:
    port: ModelPort
    config: ModelConfig
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    context_binder: GroundedPolicyContextBinder = field(default_factory=GroundedPolicyContextBinder)
    last_schema_repair_count: int = field(default=0, init=False, compare=False)
    last_model_call_count: int = field(default=0, init=False, compare=False)
    last_task_state_schema_repair_count: int = field(default=0, init=False, compare=False)
    last_task_state_call_record: object | None = field(default=None, init=False, compare=False, repr=False)
    last_argument_repair_count: int = field(default=0, init=False, compare=False)
    last_resolution_code: GroundedToolResolutionCode | None = field(default=None, init=False, compare=False)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
    last_image_input_count: int = field(default=0, init=False, compare=False)
    last_argument_violation_code: str = field(default="", init=False, compare=False)
    last_argument_violation_paths: tuple[str, ...] = field(default=(), init=False, compare=False)
    last_selected_operation: str = field(default="", init=False, compare=False)
    last_repaired_operation_match: bool = field(default=False, init=False, compare=False)
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
        object.__setattr__(self, "last_task_state_schema_repair_count", 0)
        object.__setattr__(self, "last_task_state_call_record", None)
        object.__setattr__(self, "last_argument_repair_count", 0)
        object.__setattr__(self, "last_resolution_code", None)
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_bytes", 0)
        object.__setattr__(self, "last_image_input_count", 0)
        object.__setattr__(self, "last_argument_violation_code", "")
        object.__setattr__(self, "last_argument_violation_paths", ())
        object.__setattr__(self, "last_selected_operation", "")
        object.__setattr__(self, "last_repaired_operation_match", False)
        object.__setattr__(self, "last_attempt_origin", ProviderAttemptOrigin.UNKNOWN)

    def _compile_catalog(self, request: ModelDecisionRequest, expected_schema: str, catalog_builder):
        if request.schema_version != expected_schema or request.policy_context is None:
            raise ValueError("grounded tool request lacks canonical context")
        catalog = catalog_builder(request.policy_context)
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
            _labeled_entity_operation_aliases(catalog),
            payload_base,
        )
        if not calls:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.ZERO_CALLS)
        if len(calls) != 1:
            raise GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS)
        call = calls[0]
        try:
            decision = resolver(
                catalog,
                call,
                expected_context_id=request.context_id,
                expected_catalog_id=catalog.catalog_id,
            )
        except GroundedToolResolutionError as exc:
            if exc.code is not GroundedToolResolutionCode.INVALID_ARGUMENTS or self.last_argument_repair_count:
                raise
            spec = next((item for item in catalog.specs if item.name == call.name), None)
            if spec is None:
                raise
            issue = validate_value_issue(call.arguments, spec.input_schema, path="parameters")
            if issue is None:
                raise
            object.__setattr__(self, "last_argument_violation_code", issue.code.value)
            object.__setattr__(self, "last_argument_violation_paths", issue.public_field_paths)
            object.__setattr__(self, "last_selected_operation", spec.name)
            object.__setattr__(self, "last_schema_repair_count", self.last_schema_repair_count + 1)
            object.__setattr__(self, "last_argument_repair_count", 1)
            repaired = await self._repair_selected_operation(messages, spec, issue, payload_base)
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
            prior_record=self.last_task_state_call_record,
        )

    async def _update_task_state(self, catalog, request: ModelDecisionRequest) -> AgentWorkingMemory:
        messages = self.context_binder.task_state_messages(
            catalog.view,
            request,
            supports_multimodal=self.port.supports_multimodal,
            perception_profile=self.perception_profile,
        )
        try:
            payload = await self._generate_structured(messages, GroundedTaskStatePayload)
        except StructuredOutputError as exc:
            object.__setattr__(self, "last_schema_repair_count", self.last_schema_repair_count + 1)
            object.__setattr__(self, "last_task_state_schema_repair_count", 1)
            payload = await self._generate_structured(
                _task_state_repair_messages(messages, exc),
                GroundedTaskStatePayload,
            )
        object.__setattr__(self, "last_task_state_call_record", self.port.last_call)
        return _task_state_from_payload(payload)

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
            return _failure(ModelFailureKind.SCHEMA_ERROR, "grounded cognition violated its structured schema")
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
                payload = await self._generate_structured(
                    _format_repair_messages(messages, exc),
                    payload_type,
                )
            alias_map = dict(aliases)
            operation_name = alias_map.get(payload.op, payload.op)
            spec = next((item for item in specs if item.name == operation_name), None)
            if spec is None and len(specs) == 1:
                spec = specs[0]
            operation = spec.name if spec is not None else payload.op
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
            return await generate(
                _format_repair_messages(messages, exc),
                specs,
                self.config,
                require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
            )

    async def _repair_selected_operation(
        self,
        messages,
        spec: ToolSpec,
        issue,
        payload_base: type[_GroundedCommandPayloadBase],
    ) -> ToolCall:
        repair_messages = _argument_repair_messages(messages, spec, issue)
        if self.transport_kind is not ToolTransportKind.COMPACT_JSON:
            generate = getattr(self.port, "generate_tool_calls", None)
            if generate is None:
                raise ValueError("model port does not implement admitted native tool calls")
            object.__setattr__(self, "last_model_call_count", self.last_model_call_count + 1)
            calls = await generate(
                repair_messages,
                (spec,),
                self.config,
                require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
            )
            if not calls:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.ZERO_CALLS)
            if len(calls) != 1:
                raise GroundedToolResolutionError(GroundedToolResolutionCode.MULTIPLE_CALLS)
            return calls[0]
        payload_type = _command_payload_type((spec,), payload_base=payload_base)
        payload = await self._generate_structured(repair_messages, payload_type)
        return ToolCall(payload.op, payload.command_arguments(spec))


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
            )
        )

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ResolvedModelDecision | ModelFailure:
        self._reset_diagnostics()
        try:
            catalog = self._compile_catalog(request, SCHEMA_VERSION, compile_grounded_action_catalog)
            task_state = await self._update_task_state(catalog, request)
            messages = self.context_binder.actor_messages(
                catalog.view,
                request,
                task_state,
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
            task_state,
        )


@dataclass(frozen=True)
class GroundedObjectiveAdapter(_GroundedAdapterBase):
    @property
    def compatibility_key(self) -> str:
        return ":".join(
            (
                GROUNDED_TOOLS_PROTOCOL,
                "objective_proposal",
                self.perception_profile.value,
                self.transport_kind.value,
            )
        )

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ResolvedLocalObjectiveOutcome | ModelFailure:
        self._reset_diagnostics()
        try:
            catalog = self._compile_catalog(
                request,
                OBJECTIVE_SCHEMA_VERSION,
                compile_grounded_objective_catalog,
            )
            messages = self.context_binder.objective_messages(
                catalog.view,
                request,
                supports_multimodal=self.port.supports_multimodal,
                perception_profile=self.perception_profile,
                include_tool_menu=self.transport_kind is ToolTransportKind.COMPACT_JSON,
            )
            outcome, metadata = await self._resolve_catalog(
                request,
                catalog,
                messages,
                resolve_grounded_objective_call,
                GroundedObjectiveCommandPayload,
            )
        except (
            GroundedToolResolutionError,
            ProviderModelError,
            StructuredModelError,
            TypeError,
            ValueError,
        ) as exc:
            return self._failure_from_exception(exc)
        from affordance_runtime.agent.local_objective_proposal import (
            LocalObjectiveNeedsInput,
            LocalObjectiveNotRequired,
            LocalObjectiveProposal,
            LocalObjectiveUnsupported,
        )

        if not isinstance(
            outcome,
            (
                LocalObjectiveProposal,
                LocalObjectiveNotRequired,
                LocalObjectiveNeedsInput,
                LocalObjectiveUnsupported,
            ),
        ):
            return _failure(ModelFailureKind.INTERNAL_ERROR, "objective adapter resolved an action")
        return ResolvedLocalObjectiveOutcome(outcome, metadata)


# Temporary name compatibility. The old name now denotes action selection only;
# it has no phase field and cannot be cast into an objective port.
GroundedToolDecisionAdapter = GroundedActionAdapter


def _command_payload_type(
    specs: tuple[ToolSpec, ...],
    aliases: tuple[tuple[str, str], ...] = (),
    payload_base: type[_GroundedCommandPayloadBase] = GroundedToolCommandPayload,
) -> type[_GroundedCommandPayloadBase]:
    names = (*tuple(item.name for item in specs), *(item[0] for item in aliases))
    if not names or len(names) != len(set(names)):
        raise ValueError("grounded operation menu is invalid")
    digest = hashlib.sha256("\0".join(names).encode()).hexdigest()[:12]
    allowed_operation = Literal.__getitem__(names)
    return create_model(
        f"GroundedToolCommand_{digest}",
        __base__=payload_base,
        op=(allowed_operation, ...),
    )


def _labeled_entity_operation_aliases(catalog) -> tuple[tuple[str, str], ...]:
    """Accept familiar verb names only when every selectable entity has a public label."""

    labels = {str(item.get("ref", "")): str(item.get("label", "")).strip() for item in catalog.view.grounding_index}
    proposed: dict[str, list[str]] = {}
    for spec in catalog.specs:
        match = re.fullmatch(r"establish_(.+?)_entity_objective(?:_\d+)?", spec.name)
        if match is None:
            continue
        target = spec.input_schema.get("properties", {}).get("target")
        refs = tuple(target.get("enum", ())) if isinstance(target, Mapping) else ()
        if refs and all(labels.get(str(ref), "") for ref in refs):
            proposed.setdefault(match.group(1), []).append(spec.name)
    return tuple(
        (verb, names[0])
        for verb, names in sorted(proposed.items())
        if len(names) == 1 and verb not in {item.name for item in catalog.specs}
    )


def _task_state_from_payload(payload: GroundedTaskStatePayload) -> AgentWorkingMemory:
    return AgentWorkingMemory(
        items=tuple(
            WorkingMemoryItem(
                item.description,
                WorkingMemoryItemStatus(item.status),
            )
            for item in payload.items
        ),
        goal=payload.goal,
        derived_facts=tuple(payload.derived_facts),
        next_step=payload.next_step,
        ready_to_finalize=payload.ready_to_finalize,
        blockers=tuple(payload.blockers),
    )


def _task_state_repair_messages(messages, error: StructuredOutputError):
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("task-state repair requires text system message")
    return (
        ModelMessage(
            role="system",
            content=(
                system.content
                + "\n\nRepair only the task-state response. Return exactly one object matching the supplied "
                "task-state JSON schema. Do not select or describe a tool call. Public validation contract: "
                + json.dumps(
                    structured_output_repair_contract(error),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        ),
        *messages[1:],
    )


def _format_repair_messages(messages, error: StructuredOutputError):
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("grounded command repair requires text system message")
    return (
        ModelMessage(
            role="system",
            content=(
                system.content + "\n\nReturn exactly one flat JSON object. Copy one op exactly from the "
                "current tool_menu and use only fields declared by that operation. Public validation contract: "
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
                system.content + "\n\nThe selected operation is fixed. Repair only its arguments, return one flat "
                "command, and obey this public contract: "
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
    prior_record=None,
):
    record = port.last_call if include_record else None
    return ModelMetadata(
        provider_id=port.provider,
        model_id=port.model,
        response_id=record.response_id if record is not None else "",
        endpoint_class=port.endpoint_class,
        prompt_version=prompt_version or (record.prompt_version if record is not None else ""),
        schema_version=GROUNDED_TOOLS_PROTOCOL,
        latency_ms=sum(item.latency_ms for item in (prior_record, record) if item is not None),
        prompt_tokens=sum(item.prompt_tokens for item in (prior_record, record) if item is not None),
        completion_tokens=sum(item.completion_tokens for item in (prior_record, record) if item is not None),
        total_tokens=sum(item.total_tokens for item in (prior_record, record) if item is not None),
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
