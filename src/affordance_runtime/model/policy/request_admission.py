"""Deterministic model-delivery request admission for one provider call."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Callable

from affordance_runtime.agent.workspace import DefaultWorkspaceReducer, WorkspaceCapacityError, WorkspaceReducer
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.tool_contracts import ToolSpec
from affordance_runtime.model.providers.port import ModelMessage

DEFAULT_MODEL_REQUEST_TOKEN_LIMIT = 64_000
DEFAULT_MODEL_REQUEST_SOFT_TARGET = 16_000
_PROVIDER_ENVELOPE_TOKENS = 64
_MESSAGE_OVERHEAD_TOKENS = 6
_TOOL_OVERHEAD_TOKENS = 12
_DEFAULT_IMAGE_WIDTH = 1280
_DEFAULT_IMAGE_HEIGHT = 720


@dataclass(frozen=True)
class ModelRequestBudget:
    """Hard provider-call admission limit for disposable model delivery."""

    soft_target_tokens: int = DEFAULT_MODEL_REQUEST_SOFT_TARGET
    model_context_window: int = 67_000
    max_output_tokens: int = 1_024
    protocol_reserve_tokens: int = 2_048
    safety_margin_tokens: int = 1_024
    admission_limit: int = field(default_factory=lambda: _env_limit())

    def __post_init__(self) -> None:
        counters = (
            self.soft_target_tokens,
            self.model_context_window,
            self.max_output_tokens,
            self.protocol_reserve_tokens,
            self.safety_margin_tokens,
            self.admission_limit,
        )
        if any(isinstance(value, bool) or value < 0 for value in counters):
            raise ValueError("model request budget counters must be non-negative")
        if self.soft_target_tokens < 1 or self.model_context_window < 1:
            raise ValueError("model request admission limit must be positive")
        derived = self.model_context_window - self.max_output_tokens - self.protocol_reserve_tokens - self.safety_margin_tokens
        limit = min(self.admission_limit or derived, derived)
        object.__setattr__(self, "admission_limit", max(1, limit))


@dataclass(frozen=True)
class ModelRequestBreakdown:
    """Conservative token estimate for exactly one rendered provider request."""

    phase: str
    system_tokens: int = 0
    task_plan_tokens: int = 0
    actor_world_tokens: int = 0
    history_tokens: int = 0
    working_set_tokens: int = 0
    evidence_tokens: int = 0
    tool_schema_tokens: int = 0
    image_estimated_tokens: int = 0
    repair_tokens: int = 0
    provider_envelope_tokens: int = _PROVIDER_ENVELOPE_TOKENS
    estimated_total_tokens: int = 0
    provider_reported_prompt_tokens: int = 0
    admission_limit: int = DEFAULT_MODEL_REQUEST_TOKEN_LIMIT
    admission_action: str = "admitted"
    prefit_estimated_total_tokens: int = 0
    delivery_projection: str = "full"
    full_candidate_tokens: int = 0
    lens_candidate_tokens: int = 0
    expanded_region_count: int = 0
    folded_region_count: int = 0
    direct_action_count: int = 0
    searchable_action_count: int = 0

    def __post_init__(self) -> None:
        if not self.phase.strip():
            raise ValueError("model request breakdown requires a phase")
        counters = (
            self.system_tokens,
            self.task_plan_tokens,
            self.actor_world_tokens,
            self.history_tokens,
            self.working_set_tokens,
            self.evidence_tokens,
            self.tool_schema_tokens,
            self.image_estimated_tokens,
            self.repair_tokens,
            self.provider_envelope_tokens,
            self.estimated_total_tokens,
            self.provider_reported_prompt_tokens,
            self.admission_limit,
            self.prefit_estimated_total_tokens,
            self.full_candidate_tokens,
            self.lens_candidate_tokens,
            self.expanded_region_count,
            self.folded_region_count,
            self.direct_action_count,
            self.searchable_action_count,
        )
        if any(isinstance(value, bool) or value < 0 for value in counters):
            raise ValueError("model request token counters must be non-negative")
        if self.admission_action not in {"admitted", "context_capacity"}:
            raise ValueError("model request admission action is outside the closed vocabulary")
        if self.delivery_projection not in {"full", "region_lens", "page_map"}:
            raise ValueError("model request delivery projection is outside the closed vocabulary")

    def as_diagnostics(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "system_tokens": self.system_tokens,
            "task_plan_tokens": self.task_plan_tokens,
            "actor_world_tokens": self.actor_world_tokens,
            "history_tokens": self.history_tokens,
            "working_set_tokens": self.working_set_tokens,
            "evidence_tokens": self.evidence_tokens,
            "tool_schema_tokens": self.tool_schema_tokens,
            "image_estimated_tokens": self.image_estimated_tokens,
            "repair_tokens": self.repair_tokens,
            "provider_envelope_tokens": self.provider_envelope_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
            "provider_reported_prompt_tokens": self.provider_reported_prompt_tokens,
            "admission_limit": self.admission_limit,
            "admission_action": self.admission_action,
            "prefit_estimated_total_tokens": self.prefit_estimated_total_tokens,
            "delivery_projection": self.delivery_projection,
            "full_candidate_tokens": self.full_candidate_tokens,
            "lens_candidate_tokens": self.lens_candidate_tokens,
            "expanded_region_count": self.expanded_region_count,
            "folded_region_count": self.folded_region_count,
            "direct_action_count": self.direct_action_count,
            "searchable_action_count": self.searchable_action_count,
        }


@dataclass(frozen=True)
class AdmittedModelRequest:
    messages: tuple[ModelMessage, ...]
    tools: tuple[ToolSpec, ...]
    breakdown: ModelRequestBreakdown

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "tools", tuple(self.tools))
        if any(not isinstance(item, ModelMessage) for item in self.messages):
            raise TypeError("admitted model request messages must be typed")
        if any(not isinstance(item, ToolSpec) for item in self.tools):
            raise TypeError("admitted model request tools must be typed")


class ModelRequestCapacityError(ValueError):
    """Raised before provider dispatch when a rendered request exceeds budget."""

    def __init__(self, breakdown: ModelRequestBreakdown) -> None:
        super().__init__("context_capacity")
        self.breakdown = breakdown


@dataclass(frozen=True)
class RequestAdmission:
    """Sole owner of workspace fitting and complete provider-request capacity."""

    workspace_reducer: WorkspaceReducer = field(default_factory=DefaultWorkspaceReducer)

    def admit(
        self,
        *,
        request: object,
        tools: tuple[ToolSpec, ...],
        budget: ModelRequestBudget,
        serialize: Callable[[object], object],
        include_images: bool,
        phase: str = "initial",
        full_candidate_tokens: int = 0,
    ) -> AdmittedModelRequest:
        candidate = serialize(request)
        breakdown = self._estimate(candidate, request, tools, budget, include_images, phase)
        prefit = breakdown.estimated_total_tokens
        if breakdown.admission_action == "context_capacity":
            available_tokens = max(0, budget.admission_limit - (prefit - breakdown.history_tokens))
            try:
                context = getattr(request, "agent_context")
                fitted = self.workspace_reducer.fit(context.workspace, available_tokens * 3)
            except (AttributeError, WorkspaceCapacityError):
                raise ModelRequestCapacityError(
                    _diagnostic_breakdown(breakdown, candidate, prefit, full_candidate_tokens)
                ) from None
            if fitted != context.workspace:
                request = replace(request, agent_context=replace(context, workspace=fitted))
                candidate = serialize(request)
                breakdown = self._estimate(candidate, request, tools, budget, include_images, phase)
        diagnosed = _diagnostic_breakdown(breakdown, candidate, prefit, full_candidate_tokens)
        if diagnosed.admission_action == "context_capacity":
            raise ModelRequestCapacityError(diagnosed)
        return AdmittedModelRequest(candidate.messages, tools, diagnosed)

    @staticmethod
    def _estimate(candidate, request, tools, budget, include_images, phase) -> ModelRequestBreakdown:
        return estimate_model_request(
            messages=candidate.messages,
            tools=tools,
            budget=budget,
            phase=phase,
            component_payloads=candidate.component_payloads,
            image_inputs=getattr(request, "image_inputs", ()) if include_images else (),
        )


def _diagnostic_breakdown(
    breakdown: ModelRequestBreakdown,
    candidate: object,
    prefit: int,
    full_candidate_tokens: int,
) -> ModelRequestBreakdown:
    full_total = max(
        1,
        breakdown.estimated_total_tokens - breakdown.actor_world_tokens + full_candidate_tokens,
    )
    return replace(
        breakdown,
        prefit_estimated_total_tokens=prefit,
        delivery_projection=str(getattr(candidate, "delivery_projection", "full")),
        full_candidate_tokens=full_total,
        lens_candidate_tokens=breakdown.estimated_total_tokens,
        expanded_region_count=int(getattr(candidate, "expanded_region_count", 0)),
        folded_region_count=int(getattr(candidate, "folded_region_count", 0)),
        direct_action_count=int(getattr(candidate, "direct_action_count", 0)),
        searchable_action_count=int(getattr(candidate, "searchable_action_count", 0)),
    )


def admit_model_request(
    *,
    messages: tuple[ModelMessage, ...],
    tools: tuple[ToolSpec, ...],
    budget: ModelRequestBudget,
    phase: str,
    component_payloads: Mapping[str, object] | None = None,
    image_byte_count: int = 0,
    image_inputs: Sequence[object] = (),
    repair_payload: object | None = None,
) -> AdmittedModelRequest:
    breakdown = estimate_model_request(
        messages=messages,
        tools=tools,
        budget=budget,
        phase=phase,
        component_payloads=component_payloads,
        image_byte_count=image_byte_count,
        image_inputs=image_inputs,
        repair_payload=repair_payload,
    )
    if breakdown.admission_action == "context_capacity":
        raise ModelRequestCapacityError(breakdown)
    return AdmittedModelRequest(messages, tools, breakdown)


def estimate_model_request(
    *,
    messages: tuple[ModelMessage, ...],
    tools: tuple[ToolSpec, ...],
    budget: ModelRequestBudget | None = None,
    phase: str = "initial",
    component_payloads: Mapping[str, object] | None = None,
    image_byte_count: int = 0,
    image_inputs: Sequence[object] = (),
    repair_payload: object | None = None,
) -> ModelRequestBreakdown:
    active_budget = budget or ModelRequestBudget()
    components = component_payloads or {}
    system_tokens = _estimate_system_tokens(messages)
    task_plan_tokens = _tokens_for(components.get("task_plan", ()))
    actor_world_tokens = _tokens_for(components.get("actor_world", ()))
    history_tokens = _tokens_for(components.get("history", ()))
    working_set_tokens = _tokens_for(components.get("working_set", ()))
    evidence_tokens = _tokens_for(components.get("evidence", ()))
    tool_schema_tokens = _tokens_for(_tool_projection(tools))
    image_estimated_tokens = _image_tokens(image_inputs, fallback_byte_count=image_byte_count)
    repair_tokens = _tokens_for(repair_payload) if repair_payload is not None else 0
    if not components:
        total_text_tokens = sum(_tokens_for_message(item) for item in messages)
        component_sum = system_tokens + tool_schema_tokens + image_estimated_tokens + repair_tokens
        actor_world_tokens = max(0, total_text_tokens - component_sum)
    provider_envelope_tokens = (
        _PROVIDER_ENVELOPE_TOKENS
        + len(messages) * _MESSAGE_OVERHEAD_TOKENS
        + len(tools) * _TOOL_OVERHEAD_TOKENS
    )
    estimated_total = (
        system_tokens
        + task_plan_tokens
        + actor_world_tokens
        + history_tokens
        + working_set_tokens
        + evidence_tokens
        + tool_schema_tokens
        + image_estimated_tokens
        + repair_tokens
        + provider_envelope_tokens
    )
    action = "admitted" if estimated_total <= active_budget.admission_limit else "context_capacity"
    return ModelRequestBreakdown(
        phase=phase,
        system_tokens=system_tokens,
        task_plan_tokens=task_plan_tokens,
        actor_world_tokens=actor_world_tokens,
        history_tokens=history_tokens,
        working_set_tokens=working_set_tokens,
        evidence_tokens=evidence_tokens,
        tool_schema_tokens=tool_schema_tokens,
        image_estimated_tokens=image_estimated_tokens,
        repair_tokens=repair_tokens,
        provider_envelope_tokens=provider_envelope_tokens,
        estimated_total_tokens=estimated_total,
        admission_limit=active_budget.admission_limit,
        admission_action=action,
    )


def request_breakdown_diagnostics(
    breakdowns: Sequence[ModelRequestBreakdown],
    *,
    provider_reported_prompt_tokens: int = 0,
) -> dict[str, object]:
    records = tuple(item.as_diagnostics() for item in breakdowns)
    latest = records[-1] if records else {}
    result: dict[str, object] = {
        "request_breakdowns": records,
        "provider_reported_prompt_tokens": provider_reported_prompt_tokens,
    }
    for name in (
        "phase",
        "system_tokens",
        "task_plan_tokens",
        "actor_world_tokens",
        "history_tokens",
        "working_set_tokens",
        "evidence_tokens",
        "tool_schema_tokens",
        "image_estimated_tokens",
        "repair_tokens",
        "estimated_total_tokens",
        "admission_limit",
        "admission_action",
        "delivery_projection",
        "full_candidate_tokens",
        "lens_candidate_tokens",
        "expanded_region_count",
        "folded_region_count",
        "direct_action_count",
        "searchable_action_count",
    ):
        if name in latest:
            result[name] = latest[name]
    return result


def _tokens_for_message(message: ModelMessage) -> int:
    return _tokens_for({"role": message.role, "content": _message_content_projection(message.content)})


def _estimate_system_tokens(messages: tuple[ModelMessage, ...]) -> int:
    return sum(
        _tokens_for_message(item)
        for item in messages
        if item.role == "system"
    )


def _message_content_projection(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(
            {"type": "image_url", "byte_count": len(getattr(part, "image_url", ""))}
            if getattr(part, "type", "") == "image_url"
            else to_json_compatible(part)
            for part in value
        )
    return value


def _tool_projection(tools: tuple[ToolSpec, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "name": item.name,
            "description": item.description,
            "input_schema": to_json_compatible(item.input_schema),
        }
        for item in tools
    )


def _tokens_for(value: object) -> int:
    if value in (None, "", (), [], {}):
        return 0
    text = value if isinstance(value, str) else _json(value)
    return max(1, math.ceil(len(text.encode("utf-8")) / 3))


def _image_tokens(images: Sequence[object], *, fallback_byte_count: int = 0) -> int:
    count = len(tuple(images))
    if count <= 0 and fallback_byte_count <= 0:
        return 0
    if count <= 0:
        count = 1
    total = 0
    for image in images or (None,) * count:
        width, height = _image_dimensions(getattr(image, "data", b"") if image is not None else b"")
        tiles = max(1, math.ceil(width / 512) * math.ceil(height / 512))
        # Conservative provider-neutral high-detail estimate. This follows
        # model-visible dimensions instead of compressed file size.
        total += 85 + tiles * 170
    return total


def _image_dimensions(data: bytes) -> tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(data):
                break
            length = int.from_bytes(data[index:index + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and index + 7 < len(data):
                return int.from_bytes(data[index + 5:index + 7], "big"), int.from_bytes(data[index + 3:index + 5], "big")
            index += max(2, length)
    return _DEFAULT_IMAGE_WIDTH, _DEFAULT_IMAGE_HEIGHT


def _json(value: object) -> str:
    return __import__("json").dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _env_limit() -> int:
    raw = os.environ.get("AFFORDANCE_MODEL_REQUEST_TOKEN_LIMIT", "").strip()
    if not raw:
        return DEFAULT_MODEL_REQUEST_TOKEN_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MODEL_REQUEST_TOKEN_LIMIT
    return value if value > 0 else DEFAULT_MODEL_REQUEST_TOKEN_LIMIT
