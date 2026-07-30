"""Temporary SAR-8B adapter from RecoveryDecision to legacy recovery commands.

This module is intentionally one-way and must be removed in SAR-8C when the
Coordinator stores and dispatches RecoveryDecision/RecoveryOutcome directly.
"""

from __future__ import annotations

from uuid import uuid4

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.failure_envelope import EffectStatus, FailureEnvelope
from affordance_runtime.recovery_commands import (
    RecoveryBudgetCost as LegacyRecoveryBudgetCost,
)
from affordance_runtime.recovery_commands import (
    RecoveryChangeDimension,
    RecoveryCommand,
    RecoveryCommandKind,
    RecoveryPlan,
    RecoveryReentryPhase,
)
from affordance_runtime.recovery_protocol import (
    RecoveryBudgetCost,
    RecoveryDecision,
    RecoveryDimension,
    RecoveryKind,
    RuntimePhase,
)


def legacy_plan_from_recovery_decision(
    decision: RecoveryDecision,
    failure: FailureEnvelope,
    *,
    effect_status: EffectStatus,
    profile_digest: str = "",
    profile_artifact_id: str = "",
    gap_ids: tuple[str, ...] = (),
) -> RecoveryPlan:
    """Project one canonical decision to the legacy single-command shape."""

    command = RecoveryCommand(
        command_id=decision.decision_id.replace("recovery-decision-", "recovery-command-", 1),
        failure_id=decision.failure_id,
        based_on_state_version=decision.based_on_state_version,
        strategy_id=decision.strategy_key,
        kind=_legacy_kind(decision.kind),
        expected_change=f"apply {decision.kind.value} and change {decision.changed_dimensions[0].value}",
        changed_dimensions=tuple(_legacy_dimension(item) for item in decision.changed_dimensions),
        preconditions=decision.preconditions,
        budget_cost=_legacy_budget(decision.budget_cost),
        timeout_ms=decision.budget_cost.timeout_ms,
        risk=RiskLevel.LOW,
        reentry_phase=_legacy_reentry(decision.reentry_phase),
        effect_status=effect_status,
        candidate_id=decision.candidate_id,
        route_ref=decision.route_ref,
        provider_id=decision.provider_id,
        question=decision.question,
        idempotency_key=decision.idempotency_key,
        compensation_contract_id=decision.compensation_contract_id,
        gap_ids=gap_ids if decision.kind == RecoveryKind.ACTIVE_PERCEPTION else (),
        profile_artifact_id=profile_artifact_id,
    )
    return RecoveryPlan(
        plan_id=f"recovery-plan-{uuid4().hex}",
        failure_id=failure.failure_id,
        based_on_state_version=decision.based_on_state_version,
        semantic_family_key=failure.semantic_family_key,
        commands=(command,),
        stop_conditions=(
            "declared_change_applied",
            "effect_status_requires_inspection",
            "no_safe_changed_strategy",
            "recovery_budget_exhausted",
        ),
        profile_digest=profile_digest,
    )


def _legacy_kind(kind: RecoveryKind) -> RecoveryCommandKind:
    return RecoveryCommandKind(kind.value)


def _legacy_dimension(dimension: RecoveryDimension) -> RecoveryChangeDimension:
    return RecoveryChangeDimension(dimension.value)


def _legacy_reentry(phase: RuntimePhase) -> RecoveryReentryPhase:
    return RecoveryReentryPhase(phase.value)


def _legacy_budget(cost: RecoveryBudgetCost) -> LegacyRecoveryBudgetCost:
    return LegacyRecoveryBudgetCost(
        recoveries=cost.recoveries,
        observations=cost.observations,
        replans=cost.replans,
        provider_switches=cost.provider_switches,
        user_escalations=cost.user_escalations,
        timeout_ms=cost.timeout_ms,
        model_calls=cost.model_calls,
        estimated_cost=cost.estimated_cost,
    )
