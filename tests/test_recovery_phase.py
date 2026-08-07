import pytest

from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_coordinator import RecoveryCoordinator
from affordance_runtime.recovery_owner_dispatcher import RecoveryOwnerDispatcher
from affordance_runtime.recovery_phase import RecoveryStage, RecoveryStageInput
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.runtime_state_projection import runtime_state_snapshot
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag


def _failure(state: StateKernel, *, phase: FailurePhase = FailurePhase.OBSERVATION, error_code: str = "observation_missing", failure_class: FailureClass = FailureClass.MISSING_EVIDENCE):
    return make_failure_envelope(
        run_id=state.task_id,
        phase=phase,
        failure_class=failure_class,
        error_code=error_code,
        message="recovery stage test",
        state_version=state.version,
        expected_effect=state.goal,
        remaining_budgets=RemainingRecoveryBudgets(
            recoveries=2,
            observations=2,
            replans=2,
            provider_switches=1,
            user_escalations=1,
            timeout_ms=10_000,
            model_calls=2,
            estimated_cost=10.0,
        ),
    )


def _stage() -> RecoveryStage:
    return RecoveryStage(RecoveryCoordinator(), RecoveryOwnerDispatcher())


def test_recovery_stage_returns_unified_result_and_committer_owns_writes() -> None:
    state = StateKernel("task-1", "observe current page")
    state.transition(RuntimeStep.OBSERVING.value)
    failure = _failure(state)
    trace = TraceDag(state.task_id)
    parent = trace.add("Root", {"state": state.phase})

    result = _stage().run(
        RecoveryStageInput(
            failure,
            runtime_state_snapshot(state),
            frozenset({RecoveryKind.REOBSERVE}),
        )
    )

    assert result.output is not None
    assert result.output.recovery_kind == RecoveryKind.REOBSERVE
    assert state.current_failure is None
    parent = RuntimeCommitter().commit(state, trace, parent, result)
    assert state.phase == RuntimeStep.OBSERVING.value
    assert state.current_failure == failure
    assert state.current_recovery_decision == result.output.decision
    assert state.current_recovery_outcome is None
    assert [node.kind for node in trace.nodes[-3:]] == [
        "FailureDetected",
        "RecoveryStrategySelected",
        "RecoveryDecisionStarted",
    ]
    assert parent.kind == "RecoveryDecisionStarted"


def test_recovery_stage_routes_exhausted_runtime_recovery_to_terminal() -> None:
    state = StateKernel("task-1", "observe current page")
    state.transition(RuntimeStep.OBSERVING.value)

    result = _stage().run(
        RecoveryStageInput(_failure(state), runtime_state_snapshot(state), frozenset())
    )

    assert result.terminal is not None
    assert result.terminal.reason_code == "runtime_recovery_exhausted"
    assert result.output is None


@pytest.mark.parametrize(
    ("available_action_count", "user_input_required"),
    [(2, False), (0, True)],
)
def test_recovery_stage_rejects_non_runtime_owner_before_writes(
    available_action_count: int, user_input_required: bool
) -> None:
    state = StateKernel("task-1", "choose next action")
    state.transition(RuntimeStep.OBSERVING.value)
    failure = _failure(
        state,
        phase=FailurePhase.STEP_PLANNING,
        error_code="planner_waiting_clarification",
        failure_class=FailureClass.PLANNING,
    )

    with pytest.raises(ValueError, match="RecoveryStage only accepts Runtime-owned failures"):
        _stage().run(
            RecoveryStageInput(
                failure,
                runtime_state_snapshot(state),
                frozenset({RecoveryKind.COMPACT_CONTEXT}),
                available_action_count=available_action_count,
                user_input_required=user_input_required,
            )
        )

    assert state.current_failure is None
    assert state.current_recovery_decision is None
