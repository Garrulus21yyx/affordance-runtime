"""Human-readable, bounded semantic confirmation summaries."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.execution.contracts import ActionIntent
from affordance_runtime.risk.contracts import RiskAssessment
from affordance_runtime.world.view import AgentWorldView

_SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "credential",
    "authorization",
    "api_key",
    "apikey",
)
_MAX_ITEMS = 8
_MAX_STRING = 120
_MAX_DEPTH = 2


def build_confirmation_request(
    intent: ActionIntent,
    assessment: RiskAssessment,
    world: AgentWorldView,
) -> ConfirmationRequest:
    target = _display_target(world, intent.target_id)
    destination = _display_target(world, intent.destination_id) if intent.destination_id else ""
    parameters = json.dumps(_bounded(intent.parameters), sort_keys=True, ensure_ascii=False)
    effects = ", ".join(assessment.semantic_effects) or "no declared effect"
    consequences = ", ".join(assessment.consequences)
    destination_part = f" Destination: {destination}." if destination else ""
    summary = (
        f"Confirm {intent.semantic_action}. Target: {target}.{destination_part} "
        f"Parameters: {parameters}. Effects: {effects}. Risk: {assessment.risk.value}. "
        f"Consequences: {consequences}."
    )
    return ConfirmationRequest(
        f"confirmation:{uuid.uuid4().hex}",
        assessment.subject_id,
        intent,
        assessment.semantic_effects,
        assessment.risk,
        assessment.consequences,
        summary,
        assessment.subject,
    )


def _display_target(world: AgentWorldView, target_id: str) -> str:
    target = next((item for item in world.targets if item.target_id == target_id), None)
    return f"{target.label} ({target_id})" if target is not None else target_id


def _bounded(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "…"
    if value is None or isinstance(value, bool | int | float):
        return value
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:_MAX_ITEMS]:
            name = str(key)
            result[name] = "[REDACTED]" if _secret_key(name) else _bounded(item, depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_bounded(item, depth + 1) for item in list(value)[:_MAX_ITEMS]]
    return str(value)[:_MAX_STRING]


def _secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _SECRET_MARKERS)
