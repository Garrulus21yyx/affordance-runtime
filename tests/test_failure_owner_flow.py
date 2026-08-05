import pytest

from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    ProposalRejectionContext,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_protocol import FailureOwner, RecoveryKind, classify_failure
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.stage_protocol import (
    ProgressHandoff,
    StepPlannerHandoff,
    TaskPlannerHandoff,
    TerminalResult,
    UserInputRequest,
    build_failure_owner_handoff,
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
    error_code: str,
    failure_class: FailureClass = FailureClass.PLANNING,
    recoverable: bool = True,
    proposal_rejection: ProposalRejectionContext | None = None,
) -> object:
    return make_failure_envelope(
        run_id="run-1",
        phase=phase,
        failure_class=failure_class,
        error_code=error_code,
        message="failure owner handoff test",
        state_version=5,
        task_revision=1,
        plan_version=1,
        active_step_id="step-1",
        expected_effect="complete current step",
        proposal_rejection=proposal_rejection,
        attempted_strategy_ids=(),
        remaining_budgets=_budgets(),
        recoverable=recoverable,
        progress_fingerprint="fingerprint-1",
    )


@pytest.mark.parametrize(
    ("phase", "error_code", "failure_class", "expected_type", "expected_owner"),
    [
        (
            FailurePhase.PROPOSAL_VALIDATION,
            "planner_proposal_rejected",
            FailureClass.VERIFICATION,
            ProgressHandoff,
            FailureOwner.PROGRESS,
        ),
        (
            FailurePhase.PROPOSAL_VALIDATION,
            "planner_proposal_rejected",
            FailureClass.PLANNING,
            StepPlannerHandoff,
            FailureOwner.STEP_PLANNER,
        ),
        (
            FailurePhase.TASK_PLANNING,
            "task_plan_rejected",
            FailureClass.PLANNING,
            TaskPlannerHandoff,
            FailureOwner.TASK_PLANNER,
        ),
        (
            FailurePhase.INTAKE,
            "clarification_required",
            FailureClass.INVALID_INPUT,
            UserInputRequest,
            FailureOwner.USER,
        ),
    ],
)
def test_non_runtime_failure_owner_routes_to_typed_handoff(
    phase: FailurePhase,
    error_code: str,
    failure_class: FailureClass,
    expected_type: type[object],
    expected_owner: FailureOwner,
) -> None:
    rejection = (
        ProposalRejectionContext(
            code="already_satisfied",
            reason_code="entry_outcome_already_satisfied",
        )
        if expected_owner == FailureOwner.PROGRESS
        else None
    )
    failure = _failure(
        phase,
        error_code=error_code,
        failure_class=failure_class,
        proposal_rejection=rejection,
    )
    classification = classify_failure(failure)

    handoff = build_failure_owner_handoff(
        failure, classification.owner, classification.reason_code
    )

    assert classification.owner == expected_owner
    assert isinstance(handoff, expected_type)
    assert handoff.failure_id == failure.failure_id
    assert handoff.reason_code == classification.reason_code
    assert not hasattr(handoff, "compatibility_recovery_kind")
    assert not hasattr(handoff, "decision")


def test_user_input_request_contains_question_without_recovery_policy() -> None:
    failure = _failure(
        FailurePhase.INTAKE,
        error_code="clarification_required",
        failure_class=FailureClass.INVALID_INPUT,
    )

    classification = classify_failure(failure)
    handoff = build_failure_owner_handoff(
        failure, classification.owner, classification.reason_code
    )

    assert isinstance(handoff, UserInputRequest)
    assert handoff.question


def test_unrecoverable_failure_routes_directly_to_terminal_result() -> None:
    failure = _failure(
        FailurePhase.PROPOSAL_VALIDATION,
        error_code="planner_proposal_rejected",
        recoverable=False,
    )

    classification = classify_failure(failure)
    handoff = build_failure_owner_handoff(
        failure, classification.owner, classification.reason_code
    )

    assert isinstance(handoff, TerminalResult)
    assert handoff.owner == FailureOwner.TERMINAL
    assert handoff.status == RuntimeStep.ABORTED


def test_runtime_owner_is_rejected_by_non_runtime_router() -> None:
    failure = _failure(
        FailurePhase.OBSERVATION,
        error_code="no_feasible_action",
        failure_class=FailureClass.GROUNDING,
    )
    classification = classify_failure(failure)

    assert classification.owner == FailureOwner.RUNTIME_RECOVERY
    with pytest.raises(ValueError, match="non-runtime failure owner"):
        build_failure_owner_handoff(
            failure, classification.owner, classification.reason_code
        )


def test_recovery_kind_contains_runtime_mechanical_repair_only() -> None:
    forbidden = {
        "CLARIFY_INTENT",
        "REPLAN_TASK",
        "REPLAN_STEP",
        "REQUEST_APPROVAL",
        "ASK_USER",
        "ABORT",
    }

    assert forbidden.isdisjoint(RecoveryKind.__members__)
