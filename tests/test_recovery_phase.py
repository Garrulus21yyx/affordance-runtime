from affordance_runtime.failure_envelope import (
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_command_dispatcher import RecoveryCommandDispatcher
from affordance_runtime.recovery_commands import RecoveryCommandKind
from affordance_runtime.recovery_coordinator import RecoveryCoordinator
from affordance_runtime.recovery_phase import RecoveryApplicationResult, RecoveryPhase
from affordance_runtime.recovery_protocol import FailureKind, RecoveryKind
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

    result = RecoveryPhase(
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

    assert isinstance(result, RecoveryApplicationResult)
    assert result.command_kind == RecoveryCommandKind.REOBSERVE
    assert result.decision.kind == RecoveryKind.REOBSERVE
    assert result.outcome is None
    assert state.phase == RuntimeStep.OBSERVING.value
    assert state.current_failure == failure
    assert state.current_recovery_decision == result.decision
    assert state.current_recovery_outcome is None
    assert state.attempted_recovery_strategy_ids == {result.decision.strategy_key}
    assert [node.kind for node in trace.nodes[-3:]] == [
        "FailureDetected",
        "RecoveryStrategySelected",
        "RecoveryCommandStarted",
    ]
    assert "decision" in trace.nodes[-2].payload
    assert "plan" not in trace.nodes[-2].payload
    assert result.parent.kind == "RecoveryCommandStarted"


def test_recovery_phase_records_immediate_terminal_outcome_without_pending_plan() -> None:
    state = StateKernel("task-1", "observe current page")
    failure = make_failure_envelope(
        run_id="task-1",
        phase=FailurePhase.OBSERVATION,
        failure_class=FailureClass.MISSING_EVIDENCE,
        error_code="observation_missing",
        message="current observation is unavailable",
        state_version=state.version,
        expected_effect="observe the page",
        remaining_budgets=RemainingRecoveryBudgets(recoveries=2, timeout_ms=10_000),
    )
    trace = TraceDag("task-1")
    state.transition(RuntimeStep.OBSERVING.value)
    parent = trace.add("Root", {"state": state.phase})

    result = RecoveryPhase(
        coordinator=RecoveryCoordinator(),
        command_dispatcher=RecoveryCommandDispatcher(),
    ).handle_phase_failure(
        failure=failure,
        state=state,
        trace=trace,
        parent=parent,
        available_commands=frozenset({RecoveryCommandKind.ABORT}),
        runtime_profile_digest="",
        loaded_profile_artifact_ids=(),
    )

    assert result.command_kind == RecoveryCommandKind.ABORT
    assert result.outcome is not None
    assert result.outcome.decision_id == result.decision.decision_id
    assert result.outcome.failure_id == failure.failure_id
    assert result.outcome.success
    assert result.outcome.next_phase.value == RuntimeStep.ABORTED.value
    assert state.current_recovery_decision == result.decision
    assert state.current_recovery_outcome == result.outcome


def test_recovery_phase_uses_typed_action_space_facts_for_planner_deferral() -> None:
    state = StateKernel("task-1", "choose next action")
    failure = make_failure_envelope(
        run_id="task-1",
        phase=FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
        error_code="planner_waiting_clarification",
        message="planner deferred despite available action choices",
        state_version=state.version,
        expected_effect="choose a bounded action",
        remaining_budgets=RemainingRecoveryBudgets(
            recoveries=2,
            replans=2,
            provider_switches=1,
            timeout_ms=10_000,
            model_calls=2,
            estimated_cost=10.0,
        ),
    )
    trace = TraceDag("task-1")
    state.transition(RuntimeStep.OBSERVING.value)
    parent = trace.add("Root", {"state": state.phase})

    result = RecoveryPhase(
        coordinator=RecoveryCoordinator(),
        command_dispatcher=RecoveryCommandDispatcher(),
    ).handle_phase_failure(
        failure=failure,
        state=state,
        trace=trace,
        parent=parent,
        available_commands=frozenset(
            {
                RecoveryCommandKind.COMPACT_CONTEXT,
                RecoveryCommandKind.ASK_USER,
                RecoveryCommandKind.ABORT,
            }
        ),
        runtime_profile_digest="",
        loaded_profile_artifact_ids=(),
        available_action_count=2,
    )

    assert result.classification.kind == FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE
    assert result.command_kind != RecoveryCommandKind.ASK_USER
