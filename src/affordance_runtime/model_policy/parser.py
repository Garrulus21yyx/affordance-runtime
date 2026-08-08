"""Strict conversion of raw structured model output into typed AgentDecision."""

from __future__ import annotations

from pydantic import ValidationError

from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.spec import AgentDecisionPayload, payload_to_decision
from affordance_runtime.model_policy.strict_json import StrictJsonError, strict_json_loads


def parse_agent_decision(raw_payload: str, expected_context_id: str) -> AgentDecision | ModelFailure:
    try:
        loaded = strict_json_loads(raw_payload)
    except StrictJsonError:
        return _failure(ModelFailureKind.INVALID_RESPONSE, "model response is invalid structured JSON")
    try:
        payload = AgentDecisionPayload.model_validate(loaded)
        return payload_to_decision(payload, expected_context_id)
    except (ValidationError, TypeError, ValueError):
        return _failure(ModelFailureKind.SCHEMA_ERROR, "model response violates the AgentDecision schema")


def _failure(kind: ModelFailureKind, reason: str) -> ModelFailure:
    return ModelFailure(kind, reason, False)
