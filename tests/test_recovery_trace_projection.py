from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_commands import RecoveryCommandKind
from affordance_runtime.recovery_coordinator import RecoveryCoordinator, RecoverySelectionContext
from affordance_runtime.recovery_trace_projection import recovery_protocol_projections


def test_protocol_projection_is_typed_and_does_not_write_runtime_state() -> None:
    failure = make_failure_envelope(
        run_id="projection-run",
        phase=FailurePhase.OBSERVATION,
        failure_class=FailureClass.MISSING_EVIDENCE,
        error_code="observation_missing",
        message="current observation is unavailable",
        state_version=3,
        expected_effect="obtain current observation",
        effect_status=EffectStatus.NOT_DISPATCHED,
        remaining_budgets=RemainingRecoveryBudgets(
            recoveries=2,
            observations=2,
            replans=2,
            provider_switches=0,
            user_escalations=1,
            timeout_ms=20_000,
            model_calls=2,
            estimated_cost=0.0,
        ),
    )
    plan = RecoveryCoordinator().plan(
        failure,
        RecoverySelectionContext(
            available_commands=frozenset({RecoveryCommandKind.REOBSERVE, RecoveryCommandKind.ABORT}),
            current_attempt_fingerprint="state:3",
        ),
        current_state_version=3,
    )

    projections = recovery_protocol_projections(
        state_phase="recovering",
        failure=failure,
        plan=plan,
    )

    assert [item.kind for item in projections] == [
        "FailureDetected",
        "RecoveryStrategySelected",
        "RecoveryCommandStarted",
    ]
    assert projections[0].payload["failure"]["failure_id"] == failure.failure_id  # type: ignore[index]
    assert projections[-1].payload["command"]["command_id"] == plan.commands[0].command_id  # type: ignore[index]
