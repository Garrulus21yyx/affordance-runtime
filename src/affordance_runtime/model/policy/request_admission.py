"""Deterministic model-delivery request admission for one provider call."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Callable

from affordance_runtime.agent.context.budgets import (
    DEFAULT_MODEL_REQUEST_TOKEN_LIMIT,
    ModelRequestBudget,
)
from affordance_runtime.agent.workspace import DefaultWorkspaceReducer, WorkspaceCapacityError, WorkspaceReducer
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.tool_contracts import ToolSpec
from affordance_runtime.model.providers.port import ModelMessage

_PROVIDER_ENVELOPE_TOKENS = 64
_MESSAGE_OVERHEAD_TOKENS = 6
_TOOL_OVERHEAD_TOKENS = 12
_DEFAULT_IMAGE_WIDTH = 1280
_DEFAULT_IMAGE_HEIGHT = 720
_PRIVATE_PROVIDER_FIELD_MARKERS = (
    "capture_epoch",
    "next_cursor",
    "observation_id",
    "omitted_count",
    "omitted_total",
    "page_cursor",
    "private_cursor",
    "raw_delta_lineage",
    "source_observation_id",
)
_RUNTIME_CAPTURE_ID = re.compile(
    r"[a-z][a-z0-9_-]*:[0-9a-f]{8}-[0-9a-f-]{27,}:[0-9]+",
    re.IGNORECASE,
)


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
    obligation_group_count: int = 0
    admitted_record_count: int = 0
    available_record_count: int = 0
    manifest_route_count: int = 0
    packing_backoff_count: int = 0
    rendered_request_bytes: int = 0
    tool_schema_bytes: int = 0
    output_reserve_tokens: int = 0
    fixed_request_tokens: int = 0
    complete_request_tokens: int = 0

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
            self.obligation_group_count,
            self.admitted_record_count,
            self.available_record_count,
            self.manifest_route_count,
            self.packing_backoff_count,
            self.rendered_request_bytes,
            self.tool_schema_bytes,
            self.output_reserve_tokens,
            self.fixed_request_tokens,
            self.complete_request_tokens,
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
            "obligation_group_count": self.obligation_group_count,
            "admitted_record_count": self.admitted_record_count,
            "available_record_count": self.available_record_count,
            "manifest_route_count": self.manifest_route_count,
            "packing_backoff_count": self.packing_backoff_count,
            "rendered_request_bytes": self.rendered_request_bytes,
            "tool_schema_bytes": self.tool_schema_bytes,
            "output_reserve_tokens": self.output_reserve_tokens,
            "fixed_request_tokens": self.fixed_request_tokens,
            "complete_request_tokens": self.complete_request_tokens,
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


class ModelRequestPrivacyError(ValueError):
    """Raised when a would-be provider envelope contains Runtime-private lineage."""

    def __init__(self, markers: tuple[str, ...]) -> None:
        super().__init__("provider_request_privacy")
        self.markers = markers


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
        media: Sequence[object] = (),
        phase: str = "initial",
        full_candidate_tokens: int = 0,
    ) -> AdmittedModelRequest:
        candidate = serialize(request)
        validate_provider_request_privacy(candidate, request)
        breakdown = self._estimate(candidate, request, tools, budget, include_images, media, phase)
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
                validate_provider_request_privacy(candidate, request)
                breakdown = self._estimate(candidate, request, tools, budget, include_images, media, phase)
        diagnosed = _diagnostic_breakdown(breakdown, candidate, prefit, full_candidate_tokens)
        if diagnosed.admission_action == "context_capacity":
            raise ModelRequestCapacityError(diagnosed)
        return AdmittedModelRequest(candidate.messages, tools, diagnosed)

    @staticmethod
    def _estimate(candidate, request, tools, budget, include_images, media, phase) -> ModelRequestBreakdown:
        return estimate_model_request(
            messages=candidate.messages,
            tools=tools,
            budget=budget,
            phase=phase,
            component_payloads=candidate.component_payloads,
            image_inputs=media if include_images else (),
        )


def validate_provider_request_privacy(candidate: object, request: object) -> None:
    """Fail before admission for Runtime-owned private fields or lineage."""

    components = getattr(candidate, "component_payloads", {})
    runtime_components = {
        key: value
        for key, value in (components.items() if isinstance(components, Mapping) else ())
        if key != "task_plan"
    }
    runtime_payload = {
        "components": runtime_components,
        "tools": _tool_projection(getattr(candidate, "tools", ())),
    }
    payload = json.dumps(
        to_json_compatible(runtime_payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    folded = payload.casefold()
    field_names = _mapping_field_names(runtime_payload)
    markers = [item for item in _PRIVATE_PROVIDER_FIELD_MARKERS if item in field_names]
    for marker in ("private_cursor", "raw_delta_lineage"):
        if marker in folded and marker not in markers:
            markers.append(marker)
    if _RUNTIME_CAPTURE_ID.search(payload):
        markers.append("runtime_capture_id")
    observation = getattr(getattr(request, "agent_context", None), "current_observation", None)
    private_values: list[str] = []
    if observation is not None:
        private_values.append(str(getattr(observation, "observation_id", "")))
        for source in getattr(observation, "sources", ()):
            private_values.extend(
                (str(getattr(source, "observation_id", "")), str(getattr(source, "revision", "")))
            )
        for binding in getattr(observation, "bindings", ()):
            private_values.append(str(getattr(binding, "binding_id", "")))
            binding_payload = getattr(binding, "payload", {})
            if isinstance(binding_payload, Mapping):
                private_values.extend(str(value) for value in binding_payload.values() if isinstance(value, str))
    if any(
        value.casefold() in folded
        for value in private_values
        if len(value) >= 12 or any(marker in value for marker in (":", "#", "/"))
    ):
        markers.append("runtime_lineage_value")
    if markers:
        raise ModelRequestPrivacyError(tuple(dict.fromkeys(markers)))


def _mapping_field_names(value: object) -> frozenset[str]:
    names: set[str] = set()

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                names.add(str(key).casefold())
                visit(nested)
        elif isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            for nested in item:
                visit(nested)

    visit(to_json_compatible(value))
    return frozenset(names)


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
        obligation_group_count=int(getattr(candidate, "obligation_group_count", 0)),
        admitted_record_count=int(getattr(candidate, "admitted_record_count", 0)),
        available_record_count=int(getattr(candidate, "available_record_count", 0)),
        manifest_route_count=int(getattr(candidate, "manifest_route_count", 0)),
        packing_backoff_count=int(getattr(candidate, "packing_backoff_count", 0)),
        rendered_request_bytes=_candidate_request_bytes(candidate),
        tool_schema_bytes=_tool_schema_bytes(getattr(candidate, "tools", ())),
        output_reserve_tokens=int(getattr(candidate, "output_reserve_tokens", 0)),
        fixed_request_tokens=(
            breakdown.system_tokens
            + breakdown.task_plan_tokens
            + breakdown.history_tokens
            + breakdown.working_set_tokens
            + breakdown.evidence_tokens
            + breakdown.image_estimated_tokens
            + breakdown.provider_envelope_tokens
            + int(getattr(candidate, "output_reserve_tokens", 0))
        ),
        complete_request_tokens=(
            breakdown.estimated_total_tokens + int(getattr(candidate, "output_reserve_tokens", 0))
        ),
    )


def _candidate_request_bytes(candidate: object) -> int:
    payload = {
        "messages": to_json_compatible(getattr(candidate, "messages", ())),
        "tools": _tool_projection(getattr(candidate, "tools", ())),
    }
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def _tool_schema_bytes(tools: Sequence[ToolSpec]) -> int:
    return len(
        json.dumps(
            _tool_projection(tuple(tools)),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    )


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
        _PROVIDER_ENVELOPE_TOKENS + len(messages) * _MESSAGE_OVERHEAD_TOKENS + len(tools) * _TOOL_OVERHEAD_TOKENS
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
    return sum(_tokens_for_message(item) for item in messages if item.role == "system")


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
            length = int.from_bytes(data[index : index + 2], "big")
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            } and index + 7 < len(data):
                return int.from_bytes(data[index + 5 : index + 7], "big"), int.from_bytes(
                    data[index + 3 : index + 5], "big"
                )
            index += max(2, length)
    return _DEFAULT_IMAGE_WIDTH, _DEFAULT_IMAGE_HEIGHT


def _json(value: object) -> str:
    return __import__("json").dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
