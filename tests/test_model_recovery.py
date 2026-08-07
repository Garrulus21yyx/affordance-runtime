from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.generalist_planner import GeneralistLMPlanner
from affordance_runtime.model_port import FallbackModelPort
from affordance_runtime.model_recovery import recovery_dispatcher_for_model
from affordance_runtime.recovery_protocol import (
    RecoveryBudgetCost,
    RecoveryDecision,
    RecoveryDimension,
    RecoveryKind,
    RuntimePhase,
)


@dataclass
class _Port:
    provider: str
    model: str
    endpoint_class: str = "test"
    last_call: object | None = None


def _failure():
    return make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
        error_code="provider_failed",
        message="provider failed",
        state_version=2,
        expected_effect="choose a next action",
        effect_status=EffectStatus.NOT_DISPATCHED,
        remaining_budgets=RemainingRecoveryBudgets(recoveries=2, provider_switches=1, timeout_ms=500),
        progress_fingerprint="sha256:" + "1" * 64,
    )


def _decision(
    kind: RecoveryKind,
    *,
    provider_id: str = "",
    changed_dimensions: tuple[RecoveryDimension, ...] = (RecoveryDimension.CONTEXT,),
) -> RecoveryDecision:
    return RecoveryDecision(
        decision_id=f"decision:{kind.value}",
        failure_id="failure:provider",
        based_on_state_version=2,
        strategy_key=f"strategy:{kind.value}",
        kind=kind,
        reason_code=f"test_{kind.value}",
        reentry_phase=RuntimePhase.PLANNING,
        changed_dimensions=changed_dimensions,
        preconditions=("configured fallback provider exists",),
        budget_cost=RecoveryBudgetCost(recoveries=1, replans=1, provider_switches=1, timeout_ms=500),
        provider_id=provider_id,
    )


def test_fallback_provider_owner_switches_real_active_profile_with_evidence() -> None:
    model = FallbackModelPort((_Port("remote", "primary"), _Port("local", "secondary")))
    dispatcher = recovery_dispatcher_for_model(model)
    assert dispatcher.target_ref(RecoveryKind.SWITCH_PROVIDER) == "local:secondary"

    result = dispatcher.dispatch(
        _decision(
            RecoveryKind.SWITCH_PROVIDER,
            provider_id="local:secondary",
            changed_dimensions=(RecoveryDimension.PROVIDER,),
        ),
        failure=_failure(),
        previous_attempt_fingerprint="sha256:" + "1" * 64,
    )

    assert result.outcome.success
    assert result.state_before_ref == "remote:primary"
    assert result.state_after_ref == "local:secondary"
    assert model.active_profile_ref == "local:secondary"
    assert result.outcome.artifact_refs == ("model-profile-switch:remote:primary->local:secondary",)


def test_normal_model_without_configured_fallback_exposes_no_provider_owner() -> None:
    model = FallbackModelPort((_Port("local", "only"),))

    dispatcher = recovery_dispatcher_for_model(model)

    assert dispatcher.available_kinds == frozenset()
    unavailable = dispatcher.dispatch(
        _decision(
            RecoveryKind.SWITCH_PROVIDER,
            provider_id="local:secondary",
            changed_dimensions=(RecoveryDimension.PROVIDER,),
        ),
        failure=_failure(),
        previous_attempt_fingerprint="sha256:" + "2" * 64,
    )
    assert not unavailable.outcome.success
    assert unavailable.outcome.error_code == "owning_port_unavailable"


def test_context_owner_compacts_real_generalist_planner_state_with_evidence() -> None:
    model = _Port("local", "only")
    planner = GeneralistLMPlanner(
        model,  # type: ignore[arg-type]
        accepted_knowledge=("older", "newer"),
    )
    dispatcher = recovery_dispatcher_for_model(model, planner=planner)  # type: ignore[arg-type]

    assert dispatcher.target_ref(RecoveryKind.COMPACT_CONTEXT).endswith("affordances=80:artifacts=3:knowledge=2")
    result = dispatcher.dispatch(
        _decision(RecoveryKind.COMPACT_CONTEXT),
        failure=_failure(),
        previous_attempt_fingerprint="sha256:" + "3" * 64,
    )

    assert result.outcome.success
    assert planner.limits.max_affordances == 40
    assert planner.limits.max_artifact_refs == 1
    assert planner.accepted_knowledge == ("newer",)
    assert result.outcome.artifact_refs[0].startswith("planner-context-compacted:")


def test_schema_owner_switches_generalist_planner_to_target_bound_schema_with_evidence() -> None:
    model = _Port("local", "only")
    planner = GeneralistLMPlanner(model)  # type: ignore[arg-type]
    dispatcher = recovery_dispatcher_for_model(model, planner=planner)  # type: ignore[arg-type]

    before = dispatcher.target_ref(RecoveryKind.REPAIR_MODEL_SCHEMA)
    result = dispatcher.dispatch(
        _decision(RecoveryKind.REPAIR_MODEL_SCHEMA),
        failure=_failure(),
        previous_attempt_fingerprint="sha256:" + "4" * 64,
    )

    assert before.endswith("action-bound-initial")
    assert result.outcome.success
    assert planner.schema_recovery_generation == 1
    assert planner.planner_schema_ref().endswith("target-bound-repair")
    assert result.outcome.artifact_refs[0].startswith("planner-schema-repaired:")
