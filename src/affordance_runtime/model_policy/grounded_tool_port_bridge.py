"""Grounded-tools v2 model bridge with one allowlisted workspace projection."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model, field_validator

from affordance_runtime.agent.decision_capability import (
    TOOL_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
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
from affordance_runtime.model_policy.grounded_tool_catalog import (
    compile_grounded_action_catalog,
    compile_grounded_objective_catalog,
    resolve_grounded_action_call,
    resolve_grounded_objective_call,
)
from affordance_runtime.model_policy.grounded_tool_contracts import (
    GROUNDED_TOOLS_PROTOCOL,
    GroundedToolResolutionCode,
    GroundedToolResolutionError,
)
from affordance_runtime.model_policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model_policy.objective_spec import OBJECTIVE_SCHEMA_VERSION
from affordance_runtime.model_policy.spec import SCHEMA_VERSION
from affordance_runtime.model_policy.strict_json import validate_json_tree
from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolTransportKind
from affordance_runtime.model_port import (
    FallbackModelPort,
    ModelConfig,
    ModelImageURLPart,
    ModelMessage,
    ModelPort,
    ModelTextPart,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
)
from affordance_runtime.model_tool_transport import tool_transport_for_model
from affordance_runtime.world.schema_validation import validate_value_issue

_ACTION_SYSTEM_PROMPT = """
Choose exactly one offered operation that advances the GUI task.
The marked screenshot and grounding_index use the same E* references. Copy operation and target exactly.
Choose only among actions in the current Runtime action page; those actions are already narrowed by the
active objective reducer.
Use current public state and the previous tool result: once a requested field is nonempty or satisfied, advance to the next required control.
When recovery forbids retry or requires a strategy change, never repeat the same operation, target, and arguments.
Respect prerequisites expressed by the instruction, state, roles, labels, and relations before choosing a submit/final action.
Return only the required command. Do not invent screen points, private selectors, IDs, tools, targets, or explanations.
The Runtime independently validates action authority, currentness, risk, execution, effects, and task completion.
""".strip()

_OBJECTIVE_SYSTEM_PROMPT = """
Resolve the optional LocalObjective phase with exactly one offered outcome.
Propose a bounded observation-resolvable objective only when it is useful; otherwise declare not_required,
request specific missing user input, or fail closed as unsupported.
Use semantic predicates over public facts or visual concepts. Never use E-refs, action IDs, DOM IDs,
bindings, private selectors, screen points, or coordinates. A sequence may contain future-resolvable
semantic steps when the instruction already determines them. Runtime owns admission, identity, scope
closure, evidence, action legality, binding, effects, and completion. Return only one offered outcome.
""".strip()


class GroundedToolCommandPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    op: str
    target: str = ""
    text: str | None = None
    value: object | None = None

    @field_validator("op")
    @classmethod
    def _operation(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("grounded operation is invalid")
        return value

    @field_validator("target")
    @classmethod
    def _target(cls, value: str) -> str:
        if value and (not value.startswith("E") or not value[1:].isdigit()):
            raise ValueError("grounded target ref is invalid")
        return value

    @field_validator("value")
    @classmethod
    def _value(cls, value: object | None) -> object | None:
        validate_json_tree(value)
        return value



@dataclass(frozen=True)
class _GroundedAdapterBase:
    port: ModelPort
    config: ModelConfig
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.SCREENSHOT_AX
    last_schema_repair_count: int = field(default=0, init=False, compare=False)
    last_argument_repair_count: int = field(default=0, init=False, compare=False)
    last_resolution_code: GroundedToolResolutionCode | None = field(default=None, init=False, compare=False)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
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
        if profile is not DecisionPerceptionProfile.SCREENSHOT_AX:
            raise ValueError("grounded-tools v2 requires screenshot+AX perception")
        object.__setattr__(self, "perception_profile", profile)
        object.__setattr__(self, "transport_kind", tool_transport_for_model(self.port.provider, self.port.model))

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

    async def _generate(
        self,
        request: ModelDecisionRequest,
        *,
        expected_schema: str,
        catalog_builder,
        resolver,
        system_prompt: str,
    ) -> tuple[object, ModelMetadata] | ModelFailure:
        object.__setattr__(self, "last_schema_repair_count", 0)
        object.__setattr__(self, "last_argument_repair_count", 0)
        object.__setattr__(self, "last_resolution_code", None)
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_bytes", 0)
        object.__setattr__(self, "last_attempt_origin", ProviderAttemptOrigin.UNKNOWN)
        if request.schema_version != expected_schema or request.policy_context is None:
            return _failure(ModelFailureKind.INTERNAL_ERROR, "grounded tool request lacks canonical context")
        try:
            catalog = catalog_builder(request.policy_context)
            object.__setattr__(self, "last_catalog_count", len(catalog.specs))
            object.__setattr__(self, "last_catalog_bytes", catalog.serialized_bytes)
            object.__setattr__(self, "last_attempt_origin", ProviderAttemptOrigin.NETWORK)
            messages = _messages(
                catalog.view,
                request,
                self.port.supports_multimodal,
                system_prompt,
            )
            calls = await self._call(
                messages,
                catalog.specs,
                _labeled_entity_operation_aliases(catalog),
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
                object.__setattr__(self, "last_schema_repair_count", self.last_schema_repair_count + 1)
                object.__setattr__(self, "last_argument_repair_count", 1)
                repaired = await self._repair_selected_operation(messages, spec, issue)
                if repaired.name != call.name:
                    raise GroundedToolResolutionError(GroundedToolResolutionCode.INVALID_ARGUMENTS)
                decision = resolver(
                    catalog,
                    repaired,
                    expected_context_id=request.context_id,
                    expected_catalog_id=catalog.catalog_id,
                )
        except GroundedToolResolutionError as exc:
            object.__setattr__(self, "last_resolution_code", exc.code)
            return _failure(ModelFailureKind.SCHEMA_ERROR, exc.code.value)
        except ProviderModelError as exc:
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
        except StructuredOutputError:
            return _failure(ModelFailureKind.SCHEMA_ERROR, "grounded command violated its flat schema")
        except StructuredModelError:
            return _failure(ModelFailureKind.INVALID_RESPONSE, "grounded command response was invalid")
        except (TypeError, ValueError, json.JSONDecodeError):
            object.__setattr__(self, "last_resolution_code", GroundedToolResolutionCode.CATALOG_INVALID)
            return _failure(ModelFailureKind.INTERNAL_ERROR, "grounded workspace could not be built")
        object.__setattr__(self, "last_resolution_code", GroundedToolResolutionCode.ACCEPTED)
        metadata = _metadata(self.port, self.transport_kind, include_record=True)
        return decision, metadata

    async def _call(self, messages, specs, aliases=()) -> tuple[ToolCall, ...]:
        if self.transport_kind is ToolTransportKind.COMPACT_JSON:
            payload_type = _command_payload_type(specs, aliases)
            try:
                payload = await self.port.generate_structured(messages, payload_type, self.config)
            except StructuredOutputError:
                object.__setattr__(self, "last_schema_repair_count", 1)
                payload = await self.port.generate_structured(
                    _format_repair_messages(messages),
                    payload_type,
                    self.config,
                )
            alias_map = dict(aliases)
            operation_name = alias_map.get(payload.op, payload.op)
            spec = next((item for item in specs if item.name == operation_name), None)
            if spec is None and len(specs) == 1:
                spec = specs[0]
            operation = spec.name if spec is not None else payload.op
            return (ToolCall(operation, _command_arguments(payload, spec)),)
        generate = getattr(self.port, "generate_tool_calls", None)
        if generate is None:
            raise ValueError("model port does not implement admitted native tool calls")
        try:
            return await generate(
                messages,
                specs,
                self.config,
                require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
            )
        except StructuredOutputError:
            object.__setattr__(self, "last_schema_repair_count", 1)
            return await generate(
                _format_repair_messages(messages),
                specs,
                self.config,
                require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
            )

    async def _repair_selected_operation(self, messages, spec, issue) -> ToolCall:
        payload_type = _command_payload_type((spec,))
        payload = await self.port.generate_structured(
            _argument_repair_messages(messages, spec, issue),
            payload_type,
            self.config,
        )
        return ToolCall(payload.op, _command_arguments(payload, spec))


@dataclass(frozen=True)
class GroundedActionAdapter(_GroundedAdapterBase):
    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return TOOL_ACTION_DECISION_CAPABILITIES

    @property
    def compatibility_key(self) -> str:
        return f"{GROUNDED_TOOLS_PROTOCOL}:action_selection:{self.transport_kind.value}"

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ResolvedModelDecision | ModelFailure:
        resolved = await self._generate(
            request,
            expected_schema=SCHEMA_VERSION,
            catalog_builder=compile_grounded_action_catalog,
            resolver=resolve_grounded_action_call,
            system_prompt=_ACTION_SYSTEM_PROMPT,
        )
        if isinstance(resolved, ModelFailure):
            return resolved
        decision, metadata = resolved
        from affordance_runtime.agent.decisions import AgentDecision

        if not isinstance(decision, AgentDecision):
            return _failure(ModelFailureKind.INTERNAL_ERROR, "action adapter resolved an objective")
        return ResolvedModelDecision(decision, metadata)


@dataclass(frozen=True)
class GroundedObjectiveAdapter(_GroundedAdapterBase):
    @property
    def compatibility_key(self) -> str:
        return f"{GROUNDED_TOOLS_PROTOCOL}:objective_proposal:{self.transport_kind.value}"

    async def generate(
        self,
        request: ModelDecisionRequest,
    ) -> ResolvedLocalObjectiveOutcome | ModelFailure:
        resolved = await self._generate(
            request,
            expected_schema=OBJECTIVE_SCHEMA_VERSION,
            catalog_builder=compile_grounded_objective_catalog,
            resolver=resolve_grounded_objective_call,
            system_prompt=_OBJECTIVE_SYSTEM_PROMPT,
        )
        if isinstance(resolved, ModelFailure):
            return resolved
        outcome, metadata = resolved
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


def _messages(view, request, supports_multimodal, system_prompt):
    if not supports_multimodal or not request.image_inputs:
        raise ValueError("grounded-tools v2 requires a marked screenshot")
    public = {
        "task_brief": to_json_compatible(view.task_brief),
        "grounding_index": to_json_compatible(view.grounding_index),
        "current_state": to_json_compatible(view.current_state),
        "previous_tool_result": to_json_compatible(view.previous_tool_result),
        "tool_menu": tuple(
            {
                "op": item.name,
                "description": item.description,
                "arguments": to_json_compatible(item.input_schema),
            }
            for item in view.tools
        ),
    }
    text = json.dumps(public, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    parts: list[ModelTextPart | ModelImageURLPart] = [ModelTextPart(text=text)]
    for image in request.image_inputs:
        encoded = base64.b64encode(image.data).decode("ascii")
        parts.append(ModelImageURLPart(image_url=f"data:{image.mime_type};base64,{encoded}"))
    return (
        ModelMessage(
            role="system",
            content=system_prompt,
        ),
        ModelMessage(role="user", content=tuple(parts)),
    )


def _command_payload_type(specs, aliases=()):
    names = (*tuple(item.name for item in specs), *(item[0] for item in aliases))
    if not names or len(names) != len(set(names)):
        raise ValueError("grounded operation menu is invalid")
    if len(names) == 1:
        return GroundedToolCommandPayload
    digest = hashlib.sha256("\0".join(names).encode()).hexdigest()[:12]
    allowed_operation = Literal.__getitem__(names)
    return create_model(
        f"GroundedToolCommand_{digest}",
        __base__=GroundedToolCommandPayload,
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


def _format_repair_messages(messages):
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("grounded command repair requires text system message")
    return (
        ModelMessage(
            role="system",
            content=(
                system.content + "\n\nReturn exactly one flat JSON object. Copy one op exactly from the "
                "current tool_menu and use only fields declared by that operation."
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
            "expected": to_json_compatible(issue.expected),
            "actual": to_json_compatible(issue.actual),
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


def _command_arguments(payload, spec=None):
    admitted = (
        set(spec.input_schema.get("properties", {}))
        if spec is not None
        else {"target", "text", "value"}
    )
    result = {}
    if payload.target and "target" in admitted:
        result["target"] = payload.target
    if payload.text is not None and "text" in admitted:
        result["text"] = payload.text
    if payload.value is not None and "value" in admitted:
        result["value"] = payload.value
    return result


def _metadata(port, transport_kind, *, include_record=True):
    record = port.last_call if include_record else None
    return ModelMetadata(
        provider_id=port.provider,
        model_id=port.model,
        response_id=record.response_id if record is not None else "",
        endpoint_class=port.endpoint_class,
        prompt_version=record.prompt_version if record is not None else "",
        schema_version=GROUNDED_TOOLS_PROTOCOL,
        latency_ms=record.latency_ms if record is not None else 0,
        prompt_tokens=record.prompt_tokens if record is not None else 0,
        completion_tokens=record.completion_tokens if record is not None else 0,
        total_tokens=record.total_tokens if record is not None else 0,
        perception_profile=DecisionPerceptionProfile.SCREENSHOT_AX.value,
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
