"""Legacy terminal readiness projection for immutable planner admission.

TPA-3.2C foundation: this module is the migration owner that may read legacy
TaskPlan/PlanProgress and BrowserSnapshot terminal-grounding details. It only
returns immutable PlanningRequest admission contracts. It does not mutate
StateKernel, write trace, invoke planners, or decide task completion.
"""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.planning_request import (
    PlannerAdmissionSource,
    PlannerAdmissionView,
    TargetAdmissionDecision,
    TargetAdmissionStatus,
)
from affordance_runtime.task_planning import PlanProgress, TaskPlan
from affordance_runtime.terminal_readiness import (
    TaskObligationViewCompiler,
    TerminalCandidateDecision,
    TerminalEffectBindingResolver,
    TerminalReadinessEvaluator,
    TerminalReadinessStatus,
)


@dataclass(frozen=True)
class LegacyPlannerAdmissionProjector:
    """Project existing terminal readiness into a request-safe admission view."""

    def project(
        self,
        *,
        task_revision: int,
        task_plan: TaskPlan | None,
        plan_progress: PlanProgress | None,
        snapshot: BrowserSnapshot,
    ) -> PlannerAdmissionView | None:
        if task_revision < 1:
            raise ValueError("planner admission projection requires task revision")
        if task_plan is None or plan_progress is None:
            return None
        if not snapshot.unified_affordances:
            return None
        resolution = TerminalEffectBindingResolver().resolve(
            plan=task_plan,
            progress=plan_progress,
            unified_affordances=snapshot.unified_affordances,
            observation=snapshot.observation,
        )
        decisions: list[TargetAdmissionDecision] = [
            TargetAdmissionDecision(
                target_id=target_id,
                status=TargetAdmissionStatus.UNRESOLVED,
                reason_code="terminal_grounding_unresolved",
            )
            for target_id in resolution.unresolved_target_ids
        ]
        if resolution.bindings:
            view = TaskObligationViewCompiler().compile(
                plan=task_plan,
                progress=plan_progress,
                bindings=resolution.bindings,
                task_revision=task_revision,
                observation_epoch_id=snapshot.observation.snapshot_id,
                target_fingerprints=snapshot.observation.target_fingerprints,
            )
            terminal_decision = TerminalReadinessEvaluator().evaluate(
                task_revision=task_revision,
                observation_epoch_id=snapshot.observation.snapshot_id,
                candidates=view.candidates,
                obligations=view.obligations,
            )
            decisions.extend(
                _target_admission_decision(item)
                for item in terminal_decision.candidates
            )
        if not decisions:
            return PlannerAdmissionView(
                source=PlannerAdmissionSource.LEGACY_TERMINAL_READINESS,
                task_revision=task_revision,
                snapshot_id=snapshot.observation.snapshot_id,
            )
        decisions_tuple = tuple(_dedupe_decisions(decisions))
        excluded = tuple(
            item.target_id
            for item in decisions_tuple
            if item.status != TargetAdmissionStatus.ALLOWED
        )
        return PlannerAdmissionView(
            source=PlannerAdmissionSource.LEGACY_TERMINAL_READINESS,
            task_revision=task_revision,
            snapshot_id=snapshot.observation.snapshot_id,
            target_decisions=decisions_tuple,
            excluded_target_ids=excluded,
        )


def _target_admission_decision(
    decision: TerminalCandidateDecision,
) -> TargetAdmissionDecision:
    target_id = str(decision.semantic_target_id)
    status = decision.status
    blocking_ids = tuple(str(item) for item in decision.blocking_obligation_ids)
    unknown_ids = tuple(str(item) for item in decision.unknown_obligation_ids)
    if status == TerminalReadinessStatus.READY:
        return TargetAdmissionDecision(
            target_id=target_id,
            status=TargetAdmissionStatus.ALLOWED,
            reason_code="terminal_ready",
        )
    if status == TerminalReadinessStatus.BLOCKED and blocking_ids:
        return TargetAdmissionDecision(
            target_id=target_id,
            status=TargetAdmissionStatus.BLOCKED,
            reason_code="terminal_dependency_blocked",
            blocking_step_ids=blocking_ids,
        )
    if status == TerminalReadinessStatus.UNKNOWN and unknown_ids:
        return TargetAdmissionDecision(
            target_id=target_id,
            status=TargetAdmissionStatus.UNKNOWN,
            reason_code="terminal_dependency_unknown",
            unknown_step_ids=unknown_ids,
        )
    return TargetAdmissionDecision(
        target_id=target_id,
        status=TargetAdmissionStatus.UNRESOLVED,
        reason_code="terminal_readiness_unresolved",
    )


def _dedupe_decisions(
    decisions: list[TargetAdmissionDecision],
) -> tuple[TargetAdmissionDecision, ...]:
    by_target: dict[str, TargetAdmissionDecision] = {}
    for decision in decisions:
        existing = by_target.get(decision.target_id)
        if existing is None or _admission_rank(decision.status) > _admission_rank(existing.status):
            by_target[decision.target_id] = decision
    return tuple(by_target[target_id] for target_id in sorted(by_target))


def _admission_rank(status: TargetAdmissionStatus) -> int:
    return {
        TargetAdmissionStatus.ALLOWED: 0,
        TargetAdmissionStatus.UNKNOWN: 1,
        TargetAdmissionStatus.BLOCKED: 2,
        TargetAdmissionStatus.UNRESOLVED: 3,
    }[status]
