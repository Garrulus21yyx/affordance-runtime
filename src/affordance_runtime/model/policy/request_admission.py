"""Final deterministic admission for one complete canonical provider envelope."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

from affordance_runtime.agent.context.budgets import (
    DEFAULT_MODEL_REQUEST_TOKEN_LIMIT,
    ModelRequestBudget,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.canonical_provider_envelope import (
    DETERMINISTIC_COUNTING_METHOD,
    CanonicalProviderEnvelope,
)

_PROVIDER_ENVELOPE_TOKENS = 64
_MESSAGE_OVERHEAD_TOKENS = 6
_TOOL_OVERHEAD_TOKENS = 12


@dataclass(frozen=True)
class ModelRequestBreakdown:
    """Conservative local count of every field in one physical request."""

    phase: str
    counting_method: str = DETERMINISTIC_COUNTING_METHOD
    system_tokens: int = 0
    actor_world_tokens: int = 0
    history_tokens: int = 0
    tool_schema_tokens: int = 0
    image_estimated_tokens: int = 0
    repair_tokens: int = 0
    provider_envelope_tokens: int = _PROVIDER_ENVELOPE_TOKENS
    model_settings_tokens: int = 0
    output_contract_tokens: int = 0
    estimated_input_tokens: int = 0
    provider_reported_prompt_tokens: int = 0
    effective_input_limit: int = DEFAULT_MODEL_REQUEST_TOKEN_LIMIT
    admission_action: str = "admitted"
    delivery_projection: str = "full"
    expanded_region_count: int = 0
    folded_region_count: int = 0
    direct_action_count: int = 0
    searchable_action_count: int = 0
    obligation_group_count: int = 0
    admitted_record_count: int = 0
    available_record_count: int = 0
    manifest_route_count: int = 0
    packing_backoff_count: int = 0
    rendered_request_bytes: int = 0
    tool_schema_bytes: int = 0
    media_bytes: int = 0
    output_reserve_tokens: int = 0
    complete_request_tokens: int = 0

    def __post_init__(self) -> None:
        if not self.phase.strip() or self.counting_method != DETERMINISTIC_COUNTING_METHOD:
            raise ValueError("model request breakdown counting contract is invalid")
        for name, value in self.__dict__.items():
            if name.endswith(("_tokens", "_count", "_bytes", "_limit")) and (
                isinstance(value, bool) or value < 0
            ):
                raise ValueError("model request counters must be non-negative")
        if self.admission_action not in {"admitted", "context_capacity"}:
            raise ValueError("model request admission action is invalid")

    def as_diagnostics(self) -> dict[str, object]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class AdmittedProviderEnvelope:
    envelope: CanonicalProviderEnvelope
    token_breakdown: ModelRequestBreakdown
    counting_method: str

    def __post_init__(self) -> None:
        if self.counting_method != self.envelope.counting_method:
            raise ValueError("admitted envelope counting method is inconsistent")
        if self.token_breakdown.admission_action != "admitted":
            raise ValueError("admitted envelope carries a rejection breakdown")


@dataclass(frozen=True)
class RejectedProviderEnvelope:
    reason: str
    token_breakdown: ModelRequestBreakdown
    counting_method: str

    def __post_init__(self) -> None:
        if self.reason != "context_capacity" or self.token_breakdown.admission_action != self.reason:
            raise ValueError("rejected envelope outcome is invalid")


@dataclass(frozen=True)
class InvalidProviderEnvelope:
    reason: str
    detail: str


ProviderEnvelopeAdmission = AdmittedProviderEnvelope | RejectedProviderEnvelope | InvalidProviderEnvelope


class ModelRequestCapacityError(ValueError):
    """TurnPacker control signal for a complete locally rejected envelope."""

    def __init__(self, breakdown: ModelRequestBreakdown) -> None:
        super().__init__("context_capacity")
        self.breakdown = breakdown


@dataclass(frozen=True)
class RequestAdmission:
    """The only final provider-request capacity authority."""

    def admit(
        self,
        envelope: CanonicalProviderEnvelope,
        *,
        budget: ModelRequestBudget,
    ) -> ProviderEnvelopeAdmission:
        if not isinstance(envelope, CanonicalProviderEnvelope):
            return InvalidProviderEnvelope("invalid_provider_envelope", "request is not canonical")
        try:
            breakdown = estimate_canonical_envelope(envelope, budget=budget)
        except (TypeError, ValueError) as error:
            return InvalidProviderEnvelope("invalid_provider_envelope", str(error)[:500])
        if breakdown.admission_action == "context_capacity":
            return RejectedProviderEnvelope(
                "context_capacity",
                breakdown,
                envelope.counting_method,
            )
        return AdmittedProviderEnvelope(envelope, breakdown, envelope.counting_method)


def estimate_canonical_envelope(
    envelope: CanonicalProviderEnvelope,
    *,
    budget: ModelRequestBudget | None = None,
) -> ModelRequestBreakdown:
    """Count the complete immutable envelope without consulting a provider."""

    active_budget = budget or ModelRequestBudget()
    system_tokens = _tokens_for(envelope.instructions)
    history_tokens = _tokens_for(
        {
            "history_messages": envelope.history_messages,
            "tool_result": envelope.tool_result,
        }
    ) if envelope.history_messages else 0
    actor_world_tokens = _tokens_for(envelope.user_text)
    tools_projection = tuple(
        {
            "name": item.name,
            "description": item.description,
            "parameters_json_schema": to_json_compatible(item.parameters_json_schema),
            "strict": item.strict,
            "return_mode": item.return_mode,
        }
        for item in envelope.function_tools
    )
    tool_schema_tokens = _tokens_for(tools_projection)
    image_tokens = sum(_media_tokens(item.data, item.dimensions) for item in envelope.media)
    settings_tokens = _tokens_for(envelope.model_settings)
    output_projection = {
        "output_mode": envelope.output_contract.output_mode,
        "allow_text_output": envelope.output_contract.allow_text_output,
        "allow_image_output": envelope.output_contract.allow_image_output,
        "output_tools": tuple(
            {
                "name": item.name,
                "description": item.description,
                "parameters_json_schema": to_json_compatible(item.parameters_json_schema),
                "strict": item.strict,
            }
            for item in envelope.output_contract.output_tools
        ),
    }
    output_contract_tokens = _tokens_for(output_projection)
    provider_envelope_tokens = (
        _PROVIDER_ENVELOPE_TOKENS
        + _MESSAGE_OVERHEAD_TOKENS * (len(envelope.history_messages) + 1)
        + len(envelope.function_tools) * _TOOL_OVERHEAD_TOKENS
    )
    input_total = (
        system_tokens
        + history_tokens
        + actor_world_tokens
        + tool_schema_tokens
        + image_tokens
        + settings_tokens
        + output_contract_tokens
        + provider_envelope_tokens
    )
    complete_total = input_total + envelope.output_token_reserve
    effective_input_limit = active_budget.effective_input_limit(envelope.output_token_reserve)
    action = (
        "admitted"
        if input_total <= effective_input_limit and complete_total <= active_budget.model_context_window
        else "context_capacity"
    )
    tool_bytes = len(_json(tools_projection).encode())
    media_bytes = sum(len(item.data) for item in envelope.media)
    request_bytes = (
        len(_json(envelope.physical_content()).encode())
        + media_bytes
    )
    return ModelRequestBreakdown(
        phase=envelope.attempt_phase,
        counting_method=envelope.counting_method,
        system_tokens=system_tokens,
        actor_world_tokens=actor_world_tokens,
        history_tokens=history_tokens,
        tool_schema_tokens=tool_schema_tokens,
        image_estimated_tokens=image_tokens,
        repair_tokens=(actor_world_tokens if envelope.attempt_phase == "representation_repair" else 0),
        provider_envelope_tokens=provider_envelope_tokens,
        model_settings_tokens=settings_tokens,
        output_contract_tokens=output_contract_tokens,
        estimated_input_tokens=input_total,
        effective_input_limit=effective_input_limit,
        admission_action=action,
        delivery_projection=envelope.delivery_projection,
        expanded_region_count=envelope.expanded_region_count,
        folded_region_count=envelope.folded_region_count,
        direct_action_count=envelope.direct_action_count,
        searchable_action_count=envelope.searchable_action_count,
        obligation_group_count=envelope.obligation_group_count,
        admitted_record_count=envelope.admitted_record_count,
        available_record_count=envelope.available_record_count,
        manifest_route_count=envelope.manifest_route_count,
        packing_backoff_count=envelope.packing_backoff_count,
        rendered_request_bytes=request_bytes,
        tool_schema_bytes=tool_bytes,
        media_bytes=media_bytes,
        output_reserve_tokens=envelope.output_token_reserve,
        complete_request_tokens=complete_total,
    )


def request_breakdown_diagnostics(
    breakdowns: Sequence[ModelRequestBreakdown],
    *,
    provider_reported_prompt_tokens: int = 0,
) -> dict[str, object]:
    records = tuple(item.as_diagnostics() for item in breakdowns)
    result: dict[str, object] = {
        "request_breakdowns": records,
        "provider_reported_prompt_tokens": provider_reported_prompt_tokens,
    }
    if records:
        result.update(records[-1])
    return result


def _tokens_for(value: object) -> int:
    if value in (None, "", (), [], {}):
        return 0
    text = value if isinstance(value, str) else _json(value)
    return max(1, math.ceil(len(text.encode("utf-8")) / 3))


def _media_tokens(data: bytes, dimensions: tuple[int, int]) -> int:
    width, height = dimensions
    tiles = max(1, math.ceil(width / 512) * math.ceil(height / 512))
    return 85 + tiles * 170 + math.ceil(len(data) / 4096)


def _json(value: object) -> str:
    return json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


__all__ = [
    "AdmittedProviderEnvelope",
    "InvalidProviderEnvelope",
    "ModelRequestBreakdown",
    "ModelRequestCapacityError",
    "ProviderEnvelopeAdmission",
    "RejectedProviderEnvelope",
    "RequestAdmission",
    "estimate_canonical_envelope",
    "request_breakdown_diagnostics",
]
