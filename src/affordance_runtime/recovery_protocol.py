"""Unified SAR-8 recovery failure taxonomy.

This module is intentionally pure: it classifies an existing
``FailureEnvelope`` into the recovery protocol vocabulary, but does not choose
or execute recovery commands.
"""

from __future__ import annotations

from enum import StrEnum

from affordance_runtime.failure_envelope import FailureClass, FailureEnvelope, FailurePhase


class FailureKind(StrEnum):
    MODEL_DEFERRAL_WITH_ACTION_SPACE = "model_deferral_with_action_space"
    NO_FEASIBLE_ACTION = "no_feasible_action"
    GROUNDING_AMBIGUOUS = "grounding_ambiguous"
    MISSING_USER_INPUT = "missing_user_input"
    PLAN_OUTPUT_REJECTED = "plan_output_rejected"
    INTENT_COMPILATION_REJECTED = "intent_compilation_rejected"
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    CURRENT_STEP_ALREADY_SATISFIED = "current_step_already_satisfied"
    OBSERVATION_INSUFFICIENT = "observation_insufficient"
    PROVIDER_OR_SCHEMA_FAILURE = "provider_or_schema_failure"
    AUTHORITY_BLOCKED = "authority_blocked"
    UNKNOWN = "unknown"


def classify_failure_kind(failure: FailureEnvelope) -> FailureKind:
    """Return the SAR-8 recovery taxonomy for one failure envelope."""

    error_code = failure.error_code
    message = failure.message
    if error_code == "planner_waiting_clarification":
        return FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE
    if (
        error_code == "planner_proposal_rejected"
        and "entry_outcome_already_satisfied" in message
    ):
        return FailureKind.CURRENT_STEP_ALREADY_SATISFIED
    if error_code in {"missing_user_input", "clarification_required"}:
        return FailureKind.MISSING_USER_INPUT
    if error_code in {"no_feasible_action", "no_action_candidate"}:
        return FailureKind.NO_FEASIBLE_ACTION
    if error_code in {"grounding_ambiguous", "ambiguous_target"}:
        return FailureKind.GROUNDING_AMBIGUOUS
    if failure.failure_class == FailureClass.AUTHORITY:
        return FailureKind.AUTHORITY_BLOCKED
    if failure.phase == FailurePhase.INTAKE:
        return FailureKind.INTENT_COMPILATION_REJECTED
    if failure.phase == FailurePhase.PROPOSAL_VALIDATION:
        return FailureKind.PLAN_OUTPUT_REJECTED
    if failure.phase in {
        FailurePhase.EXECUTION_NOT_DISPATCHED,
        FailurePhase.EXECUTION_UNCERTAIN,
    }:
        return FailureKind.EXECUTION_FAILED
    if failure.phase == FailurePhase.VERIFICATION:
        return FailureKind.VERIFICATION_FAILED
    if failure.phase in {FailurePhase.OBSERVATION, FailurePhase.FUSION}:
        return FailureKind.OBSERVATION_INSUFFICIENT
    if failure.phase == FailurePhase.PROVIDER_CONTEXT:
        return FailureKind.PROVIDER_OR_SCHEMA_FAILURE
    if failure.phase == FailurePhase.PREFLIGHT:
        return FailureKind.NO_FEASIBLE_ACTION
    if failure.phase in {
        FailurePhase.TASK_PLANNING,
        FailurePhase.STEP_PLANNING,
        FailurePhase.SKILL_ACTIVATION,
    }:
        return FailureKind.PLAN_OUTPUT_REJECTED
    if failure.phase == FailurePhase.GROUNDING_BINDING:
        return FailureKind.NO_FEASIBLE_ACTION
    return FailureKind.UNKNOWN
