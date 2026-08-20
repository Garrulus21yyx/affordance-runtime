"""Deterministic model projection for one executor episode's step history."""

from __future__ import annotations

import json
from collections.abc import Mapping

from affordance_runtime.agent.context.budgets import DEFAULT_MAX_HISTORY_SERIALIZED_BYTES
from affordance_runtime.agent.context.contracts import (
    AgentHistoricalTargetView,
    AgentTurnView,
    sanitize_history_value,
)
from affordance_runtime.agent.context.projection import project_public_value

DETAILED_HISTORY_STEPS = 4
_TRANSITION_SUMMARY_KEYS = (
    "role",
    "label",
    "observed_change",
    "evidence_method",
    "local_postcondition",
    "target_changed",
    "structural_world_changed",
)
_STATE_DELTA_KEYS = ("before_state", "after_state")
_MAX_STATE_DELTA_FIELDS = 8


class EpisodeHistoryCapacityError(ValueError):
    """The lossless compact episode history cannot fit its declared budget."""


def render_episode_history(
    items: tuple[AgentTurnView, ...],
    max_bytes: int = DEFAULT_MAX_HISTORY_SERIALIZED_BYTES,
) -> dict[str, object]:
    """Keep all older actions compact and the latest four actions detailed."""

    if max_bytes <= 0:
        raise ValueError("episode history byte budget must be positive")
    values = tuple(items)
    recent = values[-DETAILED_HISTORY_STEPS:]
    earlier = values[:-DETAILED_HISTORY_STEPS]
    payload = _payload(tuple(_earlier_action(item) for item in earlier), recent, len(values))
    if _serialized_size(payload) <= max_bytes:
        return payload
    folded = _fold_repeated_no_progress(tuple(_earlier_action(item) for item in earlier))
    payload = _payload(folded, recent, len(values))
    if _serialized_size(payload) <= max_bytes:
        return payload
    raise EpisodeHistoryCapacityError("episode history exceeds its deterministic compact budget")


def _payload(
    earlier: tuple[dict[str, object], ...],
    recent: tuple[AgentTurnView, ...],
    retained_count: int,
) -> dict[str, object]:
    return {
        "earlier_actions": earlier,
        "recent_trajectory": tuple(_turn(item) for item in recent),
        "retained_count": retained_count,
    }


def _earlier_action(item: AgentTurnView) -> dict[str, object]:
    result: dict[str, object] = {
        "operation": sanitize_history_value(item.semantic_action),
        "outcome": sanitize_history_value(item.reason),
    }
    if item.target is not None:
        result["target"] = _historical_target(item.target)
    return result


def _turn(item: AgentTurnView) -> dict[str, object]:
    action: dict[str, object] = {
        "kind": sanitize_history_value(item.decision_kind),
        "tool": sanitize_history_value(item.semantic_action),
        "arguments": sanitize_history_value(project_public_value(item.public_parameters)),
    }
    if item.target is not None:
        action["target"] = _historical_target(item.target)
    if item.destination is not None:
        action["destination"] = _historical_target(item.destination)
    if item.expected_outcome:
        action["expected_outcome"] = sanitize_history_value(item.expected_outcome)
    result_details = None
    if item.semantic_summary:
        details = sanitize_history_value(project_public_value(item.semantic_summary))
        if isinstance(details, Mapping):
            details = dict(details)
            result_details = details.pop("result", None)
        if details:
            action["details"] = details
    result: dict[str, object] = {
        "dispatch": sanitize_history_value(item.dispatch_status),
        "local_postcondition": sanitize_history_value(item.local_postcondition),
        "reason": sanitize_history_value(item.reason),
    }
    if item.task_evaluation_status not in {"", "unknown", "incomplete"}:
        result["task"] = sanitize_history_value(item.task_evaluation_status)
    transition = _compact_transition(item.transition)
    if transition:
        result["transition"] = transition
    if result_details is not None:
        result["details"] = result_details
    return {"action": action, "result": result}


def _historical_target(value: AgentHistoricalTargetView) -> dict[str, object]:
    result: dict[str, object] = {
        "role": sanitize_history_value(value.role),
        "label": sanitize_history_value(value.label),
    }
    if value.context:
        result["context"] = tuple(sanitize_history_value(item) for item in value.context)
    return result


def _compact_transition(
    transition: Mapping[str, object],
) -> dict[str, object]:
    public = sanitize_history_value(transition)
    if not isinstance(public, Mapping):
        return {}
    result = {
        key: public[key]
        for key in _TRANSITION_SUMMARY_KEYS
        if key in public and _small_history_value(public[key])
    }
    for key in _STATE_DELTA_KEYS:
        value = public.get(key)
        if isinstance(value, Mapping):
            compact = _compact_state_delta(value)
            if compact:
                result[key] = compact
    raw_fact_changes = transition.get("fact_changes")
    if isinstance(raw_fact_changes, tuple | list):
        result["fact_change_count"] = len(raw_fact_changes)
    return result


def _compact_state_delta(value: Mapping[str, object]) -> dict[str, object]:
    result = {}
    for key, item in value.items():
        if len(result) >= _MAX_STATE_DELTA_FIELDS:
            break
        if _small_history_value(item):
            result[str(key)] = item
    return result



def _small_history_value(value: object) -> bool:
    if isinstance(value, str):
        return len(value) <= 240
    if value is None or isinstance(value, bool | int | float):
        return True
    if isinstance(value, tuple | list):
        return len(value) <= _MAX_STATE_DELTA_FIELDS and all(_small_history_value(item) for item in value)
    if isinstance(value, Mapping):
        return len(value) <= _MAX_STATE_DELTA_FIELDS and all(
            isinstance(key, str) and len(key) <= 120 and _small_history_value(item)
            for key, item in value.items()
        )
    return False


def _fold_repeated_no_progress(
    items: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    folded: list[dict[str, object]] = []
    for item in items:
        if folded and _foldable(item) and _same_step(folded[-1], item):
            previous = dict(folded[-1])
            previous["repeat_count"] = int(previous.get("repeat_count", 1)) + 1
            folded[-1] = previous
        else:
            folded.append(item)
    return tuple(folded)


def _foldable(item: Mapping[str, object]) -> bool:
    tool = item.get("operation")
    outcome = str(item.get("outcome", "")).casefold()
    transition = item.get("transition")
    unchanged = isinstance(transition, Mapping) and transition.get("observed_change") in {
        "unchanged",
        "no_effect",
    }
    return tool in {
        "wait",
        "search_actions",
        "action_results_next_page",
        "read_region",
        "search_world",
        "list_regions",
        "read_next_page",
    } or unchanged or outcome in {
        "unchanged",
        "no_effect",
        "no effect",
    }


def _same_step(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return {key: value for key, value in left.items() if key != "repeat_count"} == right


def _serialized_size(value: object) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
