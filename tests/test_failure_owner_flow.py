import pytest

from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.failure_owner_flow import (
    FailureOwnerHandoff,
    FailureOwnerHandoffDecision,
    build_failure_owner_handoff,
    non_runtime_failure_owner_decision,
)
from affordance_runtime.recovery_protocol import (
    FailureOwner,
    RecoveryDimension,
    RecoveryKind,
    RuntimePhase,
    classify_failure,
)


def _budgets() -> RemainingRecoveryBudgets:
    return RemainingRecoveryBudgets(
        recoveries=3,
        observations=3,
        replans=3,
        provider_switches=1,
        user_escalations=1,
        timeout_ms=30_000,
        model_calls=3,
        estimated_cost=1.0,
    )


def _failure(
    phase: FailurePhase,
    *,
    error_code: str = "planner_waiting_clarification",
    recoverable: bool = True,
) -> object:
    return make_failure_envelope(
        run_id="run-1",
        phase=phase,
        failure_class=FailureClass.PLANNING,
        error_code=error_code,
        message="failure owner handoff test",
        state_version=5,
        task_revision=1,
        plan_version=1,
        active_subgoal_id="step-1",
        expected_effect="complete current step",
        attempted_strategy_ids=(),
        remaining_budgets=_budgets(),
        recoverable=recoverable,
        progress_fingerprint="fingerprint-1",
    )


def test_step_planner_handoff_is_structured_not_runtime_recovery() -> None:
    failure = _failure(FailurePhase.PROPOSAL_VALIDATION, error_code="planner_proposal_rejected")
    classification = classify_failure(failure)

    handoff = build_failure_owner_handoff(failure, classification)

    assert isinstance(handoff, FailureOwnerHandoff)
    assert handoff.owner == FailureOwner.STEP_PLANNER
    assert handoff.target_phase == RuntimePhase.PLANNING
    assert handoff.changed_dimensions == (RecoveryDimension.STEP_PLAN,)
    assert handoff.reason_code == classification.reason_code
    assert handoff.replan_scope == "step"
    assert handoff.user_question == ""


def test_user_handoff_preserves_question_without_runtime_policy() -> None:
    failure = _failure(FailurePhase.INTAKE, error_code="clarification_required")
    classification = classify_failure(failure)

    handoff = build_failure_owner_handoff(failure, classification)

    assert handoff.owner == FailureOwner.USER
    assert handoff.target_phase == RuntimePhase.WAITING_USER
    assert handoff.changed_dimensions == (RecoveryDimension.USER_INFORMATION,)
    assert handoff.user_question
    assert handoff.replan_scope == ""


def test_unrecoverable_owner_handoff_is_terminal_abort() -> None:
    failure = _failure(
        FailurePhase.PROPOSAL_VALIDATION,
        error_code="planner_proposal_rejected",
        recoverable=False,
    )
    classification = classify_failure(failure)

    handoff = build_failure_owner_handoff(failure, classification)
    decision = non_runtime_failure_owner_decision(
        failure,
        classification,
        current_state_version=7,
    )

    assert isinstance(handoff, FailureOwnerHandoff)
    assert isinstance(decision, FailureOwnerHandoffDecision)
    assert handoff.owner == FailureOwner.TERMINAL
    assert handoff.target_phase == RuntimePhase.ABORTED
    assert decision.kind == RecoveryKind.ABORT
    assert decision.changed_dimensions == (RecoveryDimension.TERMINAL,)
    assert decision.handoff.owner == FailureOwner.TERMINAL


def test_runtime_owner_handoff_is_rejected() -> None:
    failure = _failure(FailurePhase.OBSERVATION, error_code="no_feasible_action")
    classification = classify_failure(failure)

    assert classification.owner == FailureOwner.RUNTIME_RECOVERY
    with pytest.raises(ValueError, match="non-runtime failure owner"):
        build_failure_owner_handoff(failure, classification)
