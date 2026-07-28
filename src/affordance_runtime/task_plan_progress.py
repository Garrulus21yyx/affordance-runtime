"""Authority-free TaskPlan progress reconciliation.

This module prepares verifier-backed current-state subgoal completion. It does
not mutate ``StateKernel``, write trace events, invoke planners, delete
subgoals, or accept task finish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from affordance_runtime.task_planning import (
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
    SubgoalOutcomeRelation,
    TaskPlan,
)


@dataclass(frozen=True)
class TaskPlanProgressStateView:
    plan_id: str
    plan_version: int
    based_on_state_version: int
    active_subgoal_id: str
    completed_subgoal_ids: tuple[str, ...]
    failed_subgoal_ids: tuple[str, ...]


@dataclass(frozen=True)
class CurrentStateEvidence:
    snapshot_id: str
    page_revision: str
    environment_revision: str
    semantic_target_id: str
    relation: SubgoalOutcomeRelation
    observed_value: str | bool | int | float | None
    artifact_refs: tuple[str, ...]


@dataclass(frozen=True)
class SubgoalCompletionPreparation:
    plan_id: str
    plan_version: int
    based_on_state_version: int
    snapshot_id: str
    subgoal_id: str
    criterion_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    source: Literal["current_observation"]


class CurrentStateSubgoalCompletionEvaluator:
    """Prepare completion for ready read-only subgoals satisfied now."""

    _SUPPORTED_RELATIONS = {
        SubgoalOutcomeRelation.IS_AVAILABLE,
        SubgoalOutcomeRelation.IS_VISIBLE,
    }

    def evaluate(
        self,
        *,
        plan: TaskPlan,
        progress: TaskPlanProgressStateView,
        environment: PlanningEnvironmentSummary,
    ) -> SubgoalCompletionPreparation | None:
        if not _identity_current(plan, progress):
            return None
        subgoal = next(
            (
                item
                for item in plan.subgoals
                if item.subgoal_id == progress.active_subgoal_id
            ),
            None,
        )
        if subgoal is None or subgoal.outcome is None:
            return None
        if subgoal.subgoal_id in progress.completed_subgoal_ids:
            return None
        if subgoal.subgoal_id in progress.failed_subgoal_ids:
            return None
        if not set(subgoal.depends_on).issubset(progress.completed_subgoal_ids):
            return None
        if subgoal.outcome.relation not in self._SUPPORTED_RELATIONS:
            return None
        match = _unique_target(subgoal.outcome.subject, environment.affordances)
        if match is None:
            return None
        if not _relation_satisfied(subgoal.outcome.relation, match):
            return None
        evidence_ref = _evidence_ref(
            environment,
            match.semantic_target_id,
            subgoal.outcome.relation,
        )
        return SubgoalCompletionPreparation(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            based_on_state_version=plan.based_on_state_version,
            snapshot_id=environment.snapshot_id,
            subgoal_id=subgoal.subgoal_id,
            criterion_ids=tuple(
                f"task_plan:{subgoal.subgoal_id}:criterion:{index}"
                for index, _ in enumerate(subgoal.success_criteria)
            ),
            requirement_ids=tuple(
                f"task_plan:{subgoal.subgoal_id}:requirement:{index}"
                for index, _ in enumerate(subgoal.evidence_requirements)
            ),
            evidence_refs=(evidence_ref,),
            source="current_observation",
        )


def _identity_current(plan: TaskPlan, progress: TaskPlanProgressStateView) -> bool:
    return (
        progress.plan_id == plan.plan_id
        and progress.plan_version == plan.plan_version
        and progress.based_on_state_version == plan.based_on_state_version
    )


def _unique_target(
    subject: str,
    affordances: tuple[PlanningAffordanceSummary, ...],
) -> PlanningAffordanceSummary | None:
    normalized = subject.casefold().strip()
    matches = tuple(
        item
        for item in affordances
        if item.label.casefold().strip() == normalized
        or item.semantic_target_id.casefold().strip() == normalized
    )
    if len(matches) != 1:
        return None
    return matches[0]


def _relation_satisfied(
    relation: SubgoalOutcomeRelation,
    affordance: PlanningAffordanceSummary,
) -> bool:
    if relation == SubgoalOutcomeRelation.IS_VISIBLE:
        return affordance.current_state.visible is True
    if relation == SubgoalOutcomeRelation.IS_AVAILABLE:
        return (
            affordance.current_state.visible is True
            and affordance.current_state.enabled is True
        )
    return False


def _evidence_ref(
    environment: PlanningEnvironmentSummary,
    semantic_target_id: str,
    relation: SubgoalOutcomeRelation,
) -> str:
    return ":".join(
        (
            "current_observation",
            environment.snapshot_id,
            environment.page_revision,
            semantic_target_id,
            relation.value,
        )
    )
