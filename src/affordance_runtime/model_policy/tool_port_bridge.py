"""Dynamic-tools facade over the existing provider-neutral model transport."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

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
    ResolvedModelDecision,
)
from affordance_runtime.model_policy.grounding import DecisionGroundingVariant
from affordance_runtime.model_policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model_policy.spec import SCHEMA_VERSION
from affordance_runtime.model_policy.strict_json import validate_json_tree
from affordance_runtime.model_policy.tool_catalog import compile_tool_catalog, resolve_tool_call
from affordance_runtime.model_policy.tool_contracts import (
    DYNAMIC_TOOLS_PROTOCOL,
    ToolCall,
    ToolResolutionCode,
    ToolResolutionError,
    ToolTransportKind,
)
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
    structured_output_repair_contract,
)
from affordance_runtime.model_tool_transport import tool_transport_for_model
from affordance_runtime.world.schema_validation import reject_private_parameter_values, validate_value_issue

_SYSTEM_PROMPT = """
Select exactly one currently offered tool that advances the public GUI task.
Return only the requested tool proposal. Tool names and argument enums are call-local and must be copied exactly.
Do not emit Runtime IDs, selectors, coordinates, credentials, hidden reasoning, objective operations, or explanations.
The Runtime independently validates the selected action, currentness, risk, confirmation, execution, effects, and task result.
""".strip()


class CompactToolCallPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    tool: str
    args: dict[str, Any]

    @field_validator("tool")
    @classmethod
    def _bounded_tool(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("tool name is invalid")
        return value

    @field_validator("args")
    @classmethod
    def _bounded_arguments(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_tree(value)
        reject_private_parameter_values(value, path="tool_args")
        return value


@dataclass(frozen=True)
class DynamicToolDecisionAdapter:
    port: ModelPort
    config: ModelConfig
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.TEXT_ONLY
    grounding_variant: DecisionGroundingVariant = DecisionGroundingVariant.FORMAT_ONLY
    last_schema_repair_count: int = field(default=0, init=False, compare=False)
    last_argument_repair_count: int = field(default=0, init=False, compare=False)
    last_resolution_code: ToolResolutionCode | None = field(default=None, init=False, compare=False)
    last_catalog_count: int = field(default=0, init=False, compare=False)
    last_catalog_bytes: int = field(default=0, init=False, compare=False)
    transport_kind: ToolTransportKind = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.port, FallbackModelPort):
            raise ValueError("dynamic-tools bridge does not admit provider fallback")
        if self.config.rate_limit_retries or self.config.transient_retries:
            raise ValueError("dynamic-tools bridge requires a one-attempt transport")
        object.__setattr__(self, "perception_profile", DecisionPerceptionProfile(self.perception_profile))
        object.__setattr__(self, "grounding_variant", DecisionGroundingVariant(self.grounding_variant))
        object.__setattr__(
            self,
            "transport_kind",
            tool_transport_for_model(self.port.provider, self.port.model),
        )

    @property
    def interaction_protocol(self) -> str:
        return DYNAMIC_TOOLS_PROTOCOL

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return TOOL_ACTION_DECISION_CAPABILITIES

    @property
    def provider_id(self) -> str:
        return self.port.provider

    @property
    def model_id(self) -> str:
        return self.port.model

    @property
    def grounding_profile_version(self) -> str:
        return "dynamic-tools-objective-neutral.v1"

    @property
    def compatibility_key(self) -> str:
        return ":".join((DYNAMIC_TOOLS_PROTOCOL, self.perception_profile.value, self.transport_kind.value))

    @property
    def transport_timeout_s(self) -> float:
        return self.config.timeout_s

    async def generate(self, request: ModelDecisionRequest) -> ResolvedModelDecision | ModelFailure:
        object.__setattr__(self, "last_schema_repair_count", 0)
        object.__setattr__(self, "last_argument_repair_count", 0)
        object.__setattr__(self, "last_resolution_code", None)
        object.__setattr__(self, "last_catalog_count", 0)
        object.__setattr__(self, "last_catalog_bytes", 0)
        if request.schema_version != SCHEMA_VERSION:
            return _failure(ModelFailureKind.INTERNAL_ERROR, "dynamic tool request schema is not canonical")
        try:
            catalog = compile_tool_catalog(request.serialized_context)
            object.__setattr__(self, "last_catalog_count", len(catalog.specs))
            object.__setattr__(self, "last_catalog_bytes", catalog.serialized_bytes)
            messages = _messages(request, catalog, self.perception_profile, self.port.supports_multimodal)
            calls = await self._call(messages, catalog.specs)
            if not calls:
                object.__setattr__(self, "last_resolution_code", ToolResolutionCode.ZERO_CALLS)
                return _failure(ModelFailureKind.SCHEMA_ERROR, "model returned zero tool calls")
            if len(calls) != 1:
                object.__setattr__(self, "last_resolution_code", ToolResolutionCode.MULTIPLE_CALLS)
                return _failure(ModelFailureKind.SCHEMA_ERROR, "model returned multiple tool calls")
            call = calls[0]
            try:
                decision = resolve_tool_call(
                    catalog,
                    call,
                    expected_context_id=catalog.context_id,
                    expected_catalog_id=catalog.catalog_id,
                )
            except ToolResolutionError as exc:
                if exc.code is not ToolResolutionCode.INVALID_ARGUMENTS or self.last_schema_repair_count:
                    raise
                spec = next((item for item in catalog.specs if item.name == call.name), None)
                if spec is None:
                    raise
                issue = validate_value_issue(call.arguments, spec.input_schema, path="parameters")
                if issue is None:
                    raise
                object.__setattr__(self, "last_schema_repair_count", 1)
                object.__setattr__(self, "last_argument_repair_count", 1)
                repaired = await self._repair_selected_tool_arguments(messages, spec, issue)
                if repaired.name != call.name:
                    raise ToolResolutionError(ToolResolutionCode.INVALID_ARGUMENTS)
                decision = resolve_tool_call(
                    catalog,
                    repaired,
                    expected_context_id=catalog.context_id,
                    expected_catalog_id=catalog.catalog_id,
                )
        except ToolResolutionError as exc:
            object.__setattr__(self, "last_resolution_code", exc.code)
            return _failure(ModelFailureKind.SCHEMA_ERROR, "dynamic tool proposal was rejected")
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
                "model provider declined the tool request",
                retryable=exc.resumable,
                provider_code=provider_code,
                retry_after_s=exc.retry_after_s,
                attempt_origin=(
                    ProviderAttemptOrigin.LOCAL_CIRCUIT if exc.circuit_open else ProviderAttemptOrigin.NETWORK
                ),
            )
        except StructuredOutputError:
            return _failure(ModelFailureKind.SCHEMA_ERROR, "model tool response violated its format")
        except StructuredModelError:
            return _failure(ModelFailureKind.INVALID_RESPONSE, "model tool response was invalid")
        except (TypeError, ValueError, json.JSONDecodeError):
            object.__setattr__(self, "last_resolution_code", ToolResolutionCode.CATALOG_INVALID)
            return _failure(ModelFailureKind.INTERNAL_ERROR, "dynamic tool catalog could not be built")
        object.__setattr__(self, "last_resolution_code", ToolResolutionCode.ACCEPTED)
        return ResolvedModelDecision(
            decision,
            _metadata(self.port, self.perception_profile, self.transport_kind),
        )

    async def _call(self, messages, specs) -> tuple[ToolCall, ...]:
        if self.transport_kind is ToolTransportKind.COMPACT_JSON:
            try:
                payload = await self.port.generate_structured(messages, CompactToolCallPayload, self.config)
            except StructuredOutputError as exc:
                object.__setattr__(self, "last_schema_repair_count", 1)
                payload = await self.port.generate_structured(
                    _format_repair_messages(messages, exc),
                    CompactToolCallPayload,
                    self.config,
                )
            return (ToolCall(payload.tool, payload.args),)
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
        except StructuredOutputError as exc:
            object.__setattr__(self, "last_schema_repair_count", 1)
            return await generate(
                _format_repair_messages(messages, exc),
                specs,
                self.config,
                require_one=self.transport_kind is ToolTransportKind.NATIVE_REQUIRED_ONE,
            )

    async def _repair_selected_tool_arguments(self, messages, spec, issue) -> ToolCall:
        payload = await self.port.generate_structured(
            _argument_repair_messages(messages, spec, issue),
            CompactToolCallPayload,
            self.config,
        )
        return ToolCall(payload.tool, payload.args)


def _messages(request, catalog, perception_profile, supports_multimodal):
    public_context = _tool_context(request.serialized_context)
    public_tools = [
        {
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        }
        for item in catalog.specs
    ]
    text = json.dumps(
        {"agent_context": public_context, "tools": public_tools},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    content: str | tuple[ModelTextPart | ModelImageURLPart, ...] = text
    if perception_profile is DecisionPerceptionProfile.SCREENSHOT_AX:
        if not supports_multimodal or not request.image_inputs:
            raise ValueError("screenshot dynamic-tools profile requires a model image input")
        parts: list[ModelTextPart | ModelImageURLPart] = [ModelTextPart(text=text)]
        for image in request.image_inputs:
            encoded = base64.b64encode(image.data).decode("ascii")
            parts.append(ModelImageURLPart(image_url=f"data:{image.mime_type};base64,{encoded}"))
        content = tuple(parts)
    return (
        ModelMessage(role="system", content=_SYSTEM_PROMPT),
        ModelMessage(role="user", content=content),
    )


def _format_repair_messages(
    messages: tuple[ModelMessage, ...],
    error: StructuredOutputError,
) -> tuple[ModelMessage, ...]:
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("tool repair requires a text system message")
    return (
        ModelMessage(
            role="system",
            content=(
                system.content + "\n\nThe previous proposal was malformed. Return exactly one JSON object with only "
                'the keys "tool" and "args". Copy one offered tool name exactly. The args object must '
                "satisfy that tool's input_schema, including every required property. Public validation contract: "
                + json.dumps(
                    structured_output_repair_contract(error),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        ),
        *messages[1:],
    )


def _argument_repair_messages(messages: tuple[ModelMessage, ...], spec, issue) -> tuple[ModelMessage, ...]:
    system = messages[0]
    if not isinstance(system.content, str):
        raise ValueError("tool argument repair requires a text system message")
    contract = {
        "repair_kind": "selected_tool_arguments",
        "selected_tool": spec.name,
        "input_schema": to_json_compatible(spec.input_schema),
        "violation": {
            "contract_owner": issue.contract_owner.value,
            "code": issue.code.value,
            "field_paths": list(issue.public_field_paths),
            "expected": to_json_compatible(issue.expected),
            "actual": to_json_compatible(issue.actual),
        },
        "recovery": {
            "tool_must_remain": spec.name,
            "only_args_may_change": True,
        },
    }
    return (
        ModelMessage(
            role="system",
            content=(
                system.content + "\n\nThe selected offered tool is fixed. Repair only its arguments according to this "
                "public contract, then return one object with exactly tool and args: "
                + json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            ),
        ),
        *messages[1:],
    )


def _tool_context(serialized_context: str) -> dict[str, object]:
    value = json.loads(serialized_context)
    if not isinstance(value, dict):
        raise ValueError("AgentContext must be an object")
    return _scrub_runtime_identity(value)


def _scrub_runtime_identity(value):
    hidden = {
        "context_id",
        "action_id",
        "target_id",
        "destination_id",
        "cursor",
        "next_cursor",
        "snapshot_id",
        "observation_id",
        "page_id",
    }
    if isinstance(value, dict):
        return {
            key: _scrub_runtime_identity(item) for key, item in value.items() if key not in hidden and key != "actions"
        }
    if isinstance(value, list):
        return [_scrub_runtime_identity(item) for item in value]
    return value


def _metadata(port, perception_profile, transport_kind) -> ModelMetadata:
    record = port.last_call
    return ModelMetadata(
        provider_id=port.provider,
        model_id=port.model,
        response_id=record.response_id if record is not None else "",
        endpoint_class=port.endpoint_class,
        prompt_version=record.prompt_version if record is not None else "",
        schema_version=DYNAMIC_TOOLS_PROTOCOL,
        latency_ms=record.latency_ms if record is not None else 0,
        prompt_tokens=record.prompt_tokens if record is not None else 0,
        completion_tokens=record.completion_tokens if record is not None else 0,
        total_tokens=record.total_tokens if record is not None else 0,
        perception_profile=perception_profile.value,
        grounding_variant="dynamic-tools",
        grounding_profile_version="dynamic-tools-objective-neutral.v1",
        decision_schema_digest=transport_kind.value,
    )


def _failure(
    kind: ModelFailureKind,
    reason: str,
    *,
    retryable: bool = False,
    provider_code: ProviderFailureCode | None = None,
    retry_after_s: float | None = None,
    attempt_origin: ProviderAttemptOrigin = ProviderAttemptOrigin.UNKNOWN,
) -> ModelFailure:
    return ModelFailure(kind, reason, retryable, provider_code, retry_after_s, attempt_origin)
