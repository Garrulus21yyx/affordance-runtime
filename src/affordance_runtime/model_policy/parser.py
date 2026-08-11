"""Strict conversion of raw structured model output into typed AgentDecision."""

from __future__ import annotations

from pydantic import ValidationError

from affordance_runtime.agent.decisions import AgentDecision, AgentDecisionPackage
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_policy.spec import (
    AgentDecisionPackagePayload,
    AgentDecisionPayload,
    payload_to_decision,
    payload_to_package,
)
from affordance_runtime.model_policy.strict_json import StrictJsonError, strict_json_loads
from affordance_runtime.task.frontier_contracts import NoObjectiveOperation


def parse_agent_decision(
    raw_payload: str,
    expected_context_id: str,
) -> AgentDecision | AgentDecisionPackage | ModelFailure:
    try:
        loaded = strict_json_loads(raw_payload)
    except StrictJsonError:
        return _failure(ModelFailureKind.INVALID_RESPONSE, "model response is invalid structured JSON")
    try:
        if isinstance(loaded, dict) and "objective_operation" in loaded:
            payload = AgentDecisionPackagePayload.model_validate(loaded)
            package = payload_to_package(payload, expected_context_id)
            return (
                package.decision
                if isinstance(package.objective_operation, NoObjectiveOperation)
                else package
            )
        # Compatibility is limited to deterministic/recorded v1 payloads. The
        # production response schema is package.v2 and cannot emit this branch.
        payload = AgentDecisionPayload.model_validate(loaded)
        return payload_to_decision(payload, expected_context_id)
    except (ValidationError, TypeError, ValueError):
        return _failure(ModelFailureKind.SCHEMA_ERROR, "model response violates the AgentDecision schema")


def _failure(kind: ModelFailureKind, reason: str) -> ModelFailure:
    return ModelFailure(kind, reason, False)
