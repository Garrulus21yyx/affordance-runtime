"""Strict conversion of raw structured model output into typed AgentDecision."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.contracts import MAX_MODEL_RESPONSE_BYTES
from affordance_runtime.world.schema_validation import reject_private_parameter_values

_FIELDS = {
    "select_action": {"type", "context_id", "action_id", "parameters", "destination_id"},
    "request_observation": {"type", "context_id", "subject_id", "modality", "required_assurance", "reason"},
    "request_action_page": {"type", "context_id", "query", "target_id", "relevance_role", "cursor"},
    "ask_user": {"type", "context_id", "question", "requested_fields"},
    "propose_done": {
        "type", "context_id", "claimed_criteria", "evidence_refs", "result_summary", "unresolved_items"
    },
    "wait": {"type", "context_id", "reason", "max_wait_ms"},
    "abort": {"type", "context_id", "reason", "category"},
}


def parse_agent_decision(raw_payload: str, expected_context_id: str) -> AgentDecision | ModelFailure:
    if not isinstance(raw_payload, str) or len(raw_payload.encode()) > MAX_MODEL_RESPONSE_BYTES:
        return _failure(ModelFailureKind.INVALID_RESPONSE, "model response is not bounded JSON")
    try:
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeError):
        return _failure(ModelFailureKind.INVALID_RESPONSE, "model response is malformed JSON")
    try:
        return _parse_payload(payload, expected_context_id)
    except (KeyError, TypeError, ValueError):
        return _failure(ModelFailureKind.SCHEMA_ERROR, "model response violates the AgentDecision schema")


def _parse_payload(payload: object, expected_context_id: str) -> AgentDecision:
    if not isinstance(payload, Mapping) or not all(isinstance(key, str) for key in payload):
        raise TypeError("decision must be an object")
    kind = _string(payload, "type")
    if kind not in _FIELDS or set(payload) != _FIELDS[kind]:
        raise ValueError("decision fields do not exactly match a known variant")
    context_id = _string(payload, "context_id")
    if context_id != expected_context_id:
        raise ValueError("decision context is stale")
    constructors: dict[str, Callable[[Mapping[str, Any]], AgentDecision]] = {
        "select_action": _select,
        "request_observation": _observation,
        "request_action_page": _page,
        "ask_user": _ask,
        "propose_done": _done,
        "wait": _wait,
        "abort": _abort,
    }
    return constructors[kind](payload)


def _select(value: Mapping[str, Any]) -> SelectAction:
    parameters = value["parameters"]
    if not isinstance(parameters, Mapping) or not all(isinstance(key, str) for key in parameters):
        raise TypeError("parameters must be an object")
    reject_private_parameter_values(parameters)
    return SelectAction(_string(value, "context_id"), _string(value, "action_id"), dict(parameters), _string(value, "destination_id"))


def _observation(value: Mapping[str, Any]) -> RequestObservation:
    return RequestObservation(
        _string(value, "context_id"),
        _string(value, "subject_id"),
        _string(value, "modality"),
        _string(value, "required_assurance"),
        _string(value, "reason"),
    )


def _page(value: Mapping[str, Any]) -> RequestActionPage:
    return RequestActionPage(
        _string(value, "context_id"),
        _string(value, "query"),
        _string(value, "target_id"),
        _string(value, "relevance_role"),
        _string(value, "cursor"),
    )


def _ask(value: Mapping[str, Any]) -> AskUser:
    return AskUser(_string(value, "context_id"), _string(value, "question"), _strings(value, "requested_fields"))


def _done(value: Mapping[str, Any]) -> ProposeDone:
    return ProposeDone(
        _string(value, "context_id"),
        _strings(value, "claimed_criteria"),
        _strings(value, "evidence_refs"),
        _string(value, "result_summary"),
        _strings(value, "unresolved_items"),
    )


def _wait(value: Mapping[str, Any]) -> Wait:
    duration = value["max_wait_ms"]
    if not isinstance(duration, int) or isinstance(duration, bool):
        raise TypeError("wait duration must be an integer")
    return Wait(_string(value, "context_id"), _string(value, "reason"), duration)


def _abort(value: Mapping[str, Any]) -> Abort:
    return Abort(_string(value, "context_id"), _string(value, "reason"), _string(value, "category"))


def _string(value: Mapping[str, Any], key: str) -> str:
    item = value[key]
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


def _strings(value: Mapping[str, Any], key: str) -> tuple[str, ...]:
    items = value[key]
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise TypeError(f"{key} must be a string array")
    return tuple(items)


def _failure(kind: ModelFailureKind, reason: str) -> ModelFailure:
    return ModelFailure(kind, reason, False)
