from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import EffectStatus
from affordance_runtime.generalist_planner import GeneralistLMPlanner
from affordance_runtime.model_port import FallbackModelPort
from affordance_runtime.model_recovery import recovery_dispatcher_for_model
from affordance_runtime.recovery_commands import (
    RecoveryBudgetCost,
    RecoveryChangeDimension,
    RecoveryCommand,
    RecoveryCommandKind,
    RecoveryReentryPhase,
)


@dataclass
class _Port:
    provider: str
    model: str
    endpoint_class: str = "test"
    last_call: object | None = None


def _provider_switch_command() -> RecoveryCommand:
    return RecoveryCommand(
        command_id="command:switch-provider",
        failure_id="failure:provider",
        based_on_state_version=2,
        strategy_id="strategy:switch-provider",
        kind=RecoveryCommandKind.SWITCH_PROVIDER,
        expected_change="select the configured fallback provider",
        changed_dimensions=(RecoveryChangeDimension.PROVIDER,),
        preconditions=("configured fallback provider exists",),
        budget_cost=RecoveryBudgetCost(recoveries=1, replans=1, provider_switches=1, timeout_ms=500),
        timeout_ms=500,
        reentry_phase=RecoveryReentryPhase.PLANNING,
        effect_status=EffectStatus.NOT_DISPATCHED,
        provider_id="local:secondary",
    )


def _context_compaction_command() -> RecoveryCommand:
    return RecoveryCommand(
        command_id="command:compact-context",
        failure_id="failure:planning",
        based_on_state_version=2,
        strategy_id="strategy:compact-context",
        kind=RecoveryCommandKind.COMPACT_CONTEXT,
        expected_change="reduce optional planner context",
        changed_dimensions=(RecoveryChangeDimension.CONTEXT,),
        preconditions=("planner owns compactable context",),
        budget_cost=RecoveryBudgetCost(recoveries=1, replans=1, timeout_ms=500),
        timeout_ms=500,
        reentry_phase=RecoveryReentryPhase.PLANNING,
        effect_status=EffectStatus.NOT_DISPATCHED,
    )


def _schema_repair_command() -> RecoveryCommand:
    return RecoveryCommand(
        command_id="command:repair-schema",
        failure_id="failure:proposal-validation",
        based_on_state_version=2,
        strategy_id="strategy:repair-schema",
        kind=RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
        expected_change="bind the next candidate schema to current targets",
        changed_dimensions=(RecoveryChangeDimension.CONTEXT,),
        preconditions=("planner model orchestration owns repair schema",),
        budget_cost=RecoveryBudgetCost(recoveries=1, replans=1, timeout_ms=500),
        timeout_ms=500,
        reentry_phase=RecoveryReentryPhase.PLANNING,
        effect_status=EffectStatus.NOT_DISPATCHED,
    )


def test_fallback_provider_owner_switches_real_active_profile_with_evidence() -> None:
    model = FallbackModelPort((_Port("remote", "primary"), _Port("local", "secondary")))
    dispatcher = recovery_dispatcher_for_model(model)
    assert dispatcher.target_ref(RecoveryCommandKind.SWITCH_PROVIDER) == "local:secondary"

    result = dispatcher.dispatch(
        _provider_switch_command(),
        previous_attempt_fingerprint="sha256:" + "1" * 64,
    )

    assert result.receipt.success
    assert result.delta is not None
    assert result.receipt.state_before == "remote:primary"
    assert result.receipt.state_after == "local:secondary"
    assert model.active_profile_ref == "local:secondary"
    assert result.receipt.artifact_refs == ("model-profile-switch:remote:primary->local:secondary",)


def test_normal_model_without_configured_fallback_exposes_no_provider_owner() -> None:
    model = FallbackModelPort((_Port("local", "only"),))

    dispatcher = recovery_dispatcher_for_model(model)

    assert dispatcher.available_commands == frozenset()
    unavailable = dispatcher.dispatch(
        _provider_switch_command(),
        previous_attempt_fingerprint="sha256:" + "2" * 64,
    )
    assert not unavailable.receipt.success
    assert unavailable.receipt.error_code == "owning_port_unavailable"


def test_context_owner_compacts_real_generalist_planner_state_with_evidence() -> None:
    model = _Port("local", "only")
    planner = GeneralistLMPlanner(
        model,  # type: ignore[arg-type]
        accepted_knowledge=("older", "newer"),
    )
    dispatcher = recovery_dispatcher_for_model(model, planner=planner)  # type: ignore[arg-type]

    assert dispatcher.target_ref(RecoveryCommandKind.COMPACT_CONTEXT).endswith("affordances=80:artifacts=3:knowledge=2")
    result = dispatcher.dispatch(
        _context_compaction_command(),
        previous_attempt_fingerprint="sha256:" + "3" * 64,
    )

    assert result.receipt.success
    assert result.delta is not None
    assert planner.limits.max_affordances == 40
    assert planner.limits.max_artifact_refs == 1
    assert planner.accepted_knowledge == ("newer",)
    assert result.receipt.artifact_refs[0].startswith("planner-context-compacted:")


def test_schema_owner_switches_generalist_planner_to_target_bound_schema_with_evidence() -> None:
    model = _Port("local", "only")
    planner = GeneralistLMPlanner(model)  # type: ignore[arg-type]
    dispatcher = recovery_dispatcher_for_model(model, planner=planner)  # type: ignore[arg-type]

    before = dispatcher.target_ref(RecoveryCommandKind.REPAIR_MODEL_SCHEMA)
    result = dispatcher.dispatch(
        _schema_repair_command(),
        previous_attempt_fingerprint="sha256:" + "4" * 64,
    )

    assert before.endswith("action-bound-initial")
    assert result.receipt.success
    assert result.delta is not None
    assert planner.schema_recovery_generation == 1
    assert planner.planner_schema_ref().endswith("target-bound-repair")
    assert result.receipt.artifact_refs[0].startswith("planner-schema-repaired:")
