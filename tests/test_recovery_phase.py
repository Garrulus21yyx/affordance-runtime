from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_command_dispatcher import RecoveryCommandDispatcher
from affordance_runtime.recovery_commands import RecoveryCommandKind
from affordance_runtime.recovery_coordinator import RecoveryCoordinator
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag


def test_recovery_phase_handles_phase_general_failure_through_decision_seam() -> None:
    state = StateKernel("task-1", "observe current page")
    failure = make_failure_envelope(
        run_id="task-1",
        phase=FailurePhase.OBSERVATION,
        failure_class=FailureClass.MISSING_EVIDENCE,
        error_code="observation_missing",
        message="current observation is unavailable",
        state_version=state.version,
        expected_effect="observe the page",
        remaining_budgets=RemainingRecoveryBudgets(
            recoveries=2,
            observations=2,
            replans=1,
            timeout_ms=10_000,
        ),
    )
    trace = TraceDag("task-1")
    state.transition(RuntimeStep.OBSERVING.value)
    parent = trace.add("Root", {"state": state.phase})

    command_kind, new_parent = RecoveryPhase(
        coordinator=RecoveryCoordinator(),
        command_dispatcher=RecoveryCommandDispatcher(),
    ).handle_phase_failure(
        failure=failure,
        state=state,
        trace=trace,
        parent=parent,
        available_commands=frozenset(
            {RecoveryCommandKind.REOBSERVE, RecoveryCommandKind.ABORT}
        ),
        runtime_profile_digest="",
        loaded_profile_artifact_ids=(),
    )

    assert command_kind == RecoveryCommandKind.REOBSERVE
    assert state.phase == RuntimeStep.OBSERVING.value
    assert state.current_failure == failure
    assert state.current_recovery_plan is not None
    assert state.current_recovery_plan.commands[0].kind == RecoveryCommandKind.REOBSERVE
    assert state.attempted_recovery_strategy_ids == {
        state.current_recovery_plan.commands[0].strategy_id
    }
    assert [node.kind for node in trace.nodes[-3:]] == [
        "FailureDetected",
        "RecoveryStrategySelected",
        "RecoveryCommandStarted",
    ]
    assert new_parent.kind == "RecoveryCommandStarted"
