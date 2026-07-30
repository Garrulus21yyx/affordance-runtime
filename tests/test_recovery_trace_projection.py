import pytest

from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_commands import RecoveryCommandKind
from affordance_runtime.recovery_coordinator import RecoveryCoordinator, RecoverySelectionContext
from affordance_runtime.recovery_decision_compatibility import legacy_plan_from_recovery_decision
from affordance_runtime.recovery_protocol import classify_failure
from affordance_runtime.recovery_trace_projection import RecoveryTraceProjection, recovery_protocol_projections


def test_recovery_trace_projection_payload_is_deeply_immutable_from_source_payload() -> None:
    payload = {"failure": {"code": "stale"}, "changed_dimensions": ["observation"]}

    projection = RecoveryTraceProjection("RecoveryStrategySelected", payload)
    payload["failure"]["code"] = "mutated"  # type: ignore[index]
    payload["changed_dimensions"].append("backend")  # type: ignore[union-attr]

    assert projection.payload["failure"] == {"code": "stale"}
    assert projection.payload["changed_dimensions"] == ("observation",)
    with pytest.raises(TypeError):
        projection.payload["failure"]["code"] = "mutated"  # type: ignore[index]


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
    context = RecoverySelectionContext(
        available_commands=frozenset({RecoveryCommandKind.REOBSERVE, RecoveryCommandKind.ABORT}),
        current_attempt_fingerprint="state:3",
    )
    classification = classify_failure(failure)
    decision = RecoveryCoordinator().decide(
        failure,
        classification,
        context,
        current_state_version=3,
    )
    plan = legacy_plan_from_recovery_decision(
        decision,
        failure,
        effect_status=failure.effect_status,
    )

    projections = recovery_protocol_projections(
        state_phase="recovering",
        failure=failure,
        decision=decision,
        command=plan.commands[0],
    )

    assert [item.kind for item in projections] == [
        "FailureDetected",
        "RecoveryStrategySelected",
        "RecoveryCommandStarted",
    ]
    assert projections[0].payload["failure"]["failure_id"] == failure.failure_id  # type: ignore[index]
    assert "decision" in projections[1].payload
    assert "plan" not in projections[1].payload
    assert projections[-1].payload["command"]["command_id"] == plan.commands[0].command_id  # type: ignore[index]
