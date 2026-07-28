"""Authority-free TaskPlan progress reconciliation from current observation.

This module prepares typed progress only.  It does not mutate ``StateKernel``,
write trace events, call planners, create replacement plans, or accept finish.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_planning import (
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
)


@dataclass(frozen=True)
class TaskPlanProgressStateView:
    """Immutable state identity and TaskPlan progress visible to the evaluator."""

    plan_id: str
    plan_version: int
    based_on_state_version: int
    snapshot_id: str
    environment_revision: str
    page_revision: str
    active_subgoal_id: str
    completed_subgoal_ids: tuple[str, ...]
    failed_subgoal_ids: tuple[str, ...]

    @classmethod
    def from_state(
        cls,
        state: StateKernel,
        *,
        snapshot_id: str,
        environment_revision: str,
        page_revision: str,
    ) -> "TaskPlanProgressStateView":
        if state.task_plan is None or state.plan_progress is None:
            raise ValueError("cannot build TaskPlan progress view without an active TaskPlan")
        return cls(
            plan_id=state.task_plan.plan_id,
            plan_version=state.task_plan.plan_version,
            based_on_state_version=state.task_plan.based_on_state_version,
            snapshot_id=snapshot_id,
            environment_revision=environment_revision,
            page_revision=page_revision,
            active_subgoal_id=state.plan_progress.active_subgoal_id,
            completed_subgoal_ids=tuple(state.plan_progress.completed_subgoal_ids),
            failed_subgoal_ids=tuple(state.plan_progress.failed_subgoal_ids),
        )


@dataclass(frozen=True)
class CurrentStateEvidence:
    """One current-observation fact used to justify a progress preparation."""

    snapshot_id: str
    page_revision: str
    environment_revision: str
    semantic_target_id: str
    relation: SubgoalOutcomeRelation
    observed_value: str | bool | int | float | None
    artifact_refs: tuple[str, ...]


@dataclass(frozen=True)
class SubgoalCompletionPreparation:
    """Typed completion result for Coordinator-side authoritative commit."""

    plan_id: str
    plan_version: int
    based_on_state_version: int
    snapshot_id: str
    subgoal_id: str
    criterion_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    source: Literal["current_observation"] = "current_observation"


class CurrentStateSubgoalCompletionEvaluator:
    """Evaluate whether current observation completes one ready read-only subgoal."""

    _SUPPORTED_RELATIONS = frozenset(
        {
            SubgoalOutcomeRelation.IS_AVAILABLE,
            SubgoalOutcomeRelation.IS_VISIBLE,
        }
    )

    def evaluate(
        self,
        *,
        plan: TaskPlan,
        progress: TaskPlanProgressStateView,
        environment: PlanningEnvironmentSummary,
    ) -> SubgoalCompletionPreparation | None:
        if not _identity_matches(plan, progress, environment):
            return None
        completed = set(progress.completed_subgoal_ids)
        failed = set(progress.failed_subgoal_ids)
        candidates = tuple(
            subgoal
            for subgoal in plan.subgoals
            if subgoal.subgoal_id not in completed
            and subgoal.subgoal_id not in failed
            and all(dependency in completed for dependency in subgoal.depends_on)
            and (not progress.active_subgoal_id or progress.active_subgoal_id == subgoal.subgoal_id)
            and subgoal.outcome is not None
            and subgoal.outcome.relation in self._SUPPORTED_RELATIONS
        )
        for subgoal in candidates:
            evidence = _current_state_evidence_for(subgoal, environment)
            if evidence is None:
                continue
            return SubgoalCompletionPreparation(
                plan_id=progress.plan_id,
                plan_version=progress.plan_version,
                based_on_state_version=progress.based_on_state_version,
                snapshot_id=progress.snapshot_id,
                subgoal_id=subgoal.subgoal_id,
                criterion_ids=tuple(subgoal.success_criteria),
                requirement_ids=tuple(subgoal.evidence_requirements),
                evidence_refs=evidence.artifact_refs,
            )
        return None


def _identity_matches(
    plan: TaskPlan,
    progress: TaskPlanProgressStateView,
    environment: PlanningEnvironmentSummary,
) -> bool:
    return (
        plan.plan_id == progress.plan_id
        and plan.plan_version == progress.plan_version
        and plan.based_on_state_version == progress.based_on_state_version
        and bool(progress.snapshot_id)
        and environment.snapshot_id == progress.snapshot_id
        and environment.environment_revision == progress.environment_revision
        and environment.page_revision == progress.page_revision
    )


def _current_state_evidence_for(
    subgoal: SubgoalSpec,
    environment: PlanningEnvironmentSummary,
) -> CurrentStateEvidence | None:
    assert subgoal.outcome is not None
    matches = tuple(
        affordance
        for affordance in environment.affordances
        if _affordance_matches_subject(affordance, subgoal.outcome.subject)
        and _affordance_proves_relation(affordance, subgoal.outcome.relation)
    )
    if len(matches) != 1:
        return None
    matched = matches[0]
    observed_value: bool = (
        matched.current_state.visible is True
        if subgoal.outcome.relation == SubgoalOutcomeRelation.IS_VISIBLE
        else matched.current_state.visible is True and matched.current_state.enabled is not False
    )
    return CurrentStateEvidence(
        snapshot_id=environment.snapshot_id,
        page_revision=environment.page_revision,
        environment_revision=environment.environment_revision,
        semantic_target_id=matched.semantic_target_id,
        relation=subgoal.outcome.relation,
        observed_value=observed_value,
        artifact_refs=(
            "current_state:"
            f"{environment.snapshot_id}:"
            f"{matched.semantic_target_id}:"
            f"{subgoal.outcome.relation.value}",
        ),
    )


def _affordance_proves_relation(
    affordance: PlanningAffordanceSummary,
    relation: SubgoalOutcomeRelation,
) -> bool:
    state = affordance.current_state
    if relation == SubgoalOutcomeRelation.IS_VISIBLE:
        return state.visible is True
    if relation == SubgoalOutcomeRelation.IS_AVAILABLE:
        return state.visible is True and state.enabled is not False
    return False


def _affordance_matches_subject(
    affordance: PlanningAffordanceSummary,
    subject: str,
) -> bool:
    subject_tokens = _tokens(subject)
    if not subject_tokens:
        return False
    target_tokens = _tokens(" ".join((affordance.label, affordance.role, affordance.semantic_target_id)))
    return subject_tokens.issubset(target_tokens)


def _tokens(value: str) -> set[str]:
    return {item for item in re.split(r"[^a-z0-9]+", value.lower()) if item}
