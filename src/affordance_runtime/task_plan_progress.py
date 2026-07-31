"""Authority-free TaskPlan progress reconciliation.

This module prepares verifier-backed current-state subgoal completion. It does
not mutate ``StateKernel``, write trace events, invoke planners, delete
subgoals, or accept task finish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from affordance_runtime.criteria import criterion_id, evidence_requirement_id
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
    plan_based_on_state_version: int
    evaluated_at_state_version: int
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
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubgoalCompletionPreparation:
    plan_id: str
    plan_version: int
    evaluated_at_state_version: int
    subgoal_id: str
    criterion_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    evidence: tuple[CurrentStateEvidence, ...]
    source: Literal["current_observation"]


def current_state_evidence_refs(
    evidence: tuple[CurrentStateEvidence, ...],
) -> tuple[str, ...]:
    """Project typed current-state evidence into stable StateKernel refs."""

    return tuple(_evidence_ref(item) for item in evidence)


class CurrentStateSubgoalCompletionEvaluator:
    """Prepare completion for ready read-only subgoals satisfied now."""

    _SUPPORTED_RELATIONS = {
        SubgoalOutcomeRelation.IS_AVAILABLE,
        SubgoalOutcomeRelation.IS_SELECTED,
        SubgoalOutcomeRelation.IS_VISIBLE,
    }

    def evaluate(
        self,
        *,
        plan: TaskPlan,
        progress: TaskPlanProgressStateView,
        environment: PlanningEnvironmentSummary,
        evaluated_at_state_version: int | None = None,
        snapshot_id: str = "",
        page_revision: str = "",
        environment_revision: str = "",
    ) -> SubgoalCompletionPreparation | None:
        if not _identity_current(plan, progress):
            return None
        if (
            evaluated_at_state_version is not None
            and progress.evaluated_at_state_version != evaluated_at_state_version
        ):
            return None
        if not _observation_identity_current(
            environment,
            snapshot_id=snapshot_id,
            page_revision=page_revision,
            environment_revision=environment_revision,
        ):
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
        if not _relation_satisfied(
            subgoal.outcome.relation,
            match,
            expected_value=subgoal.outcome.value,
        ):
            return None
        evidence = CurrentStateEvidence(
            snapshot_id=environment.snapshot_id,
            page_revision=environment.page_revision,
            environment_revision=environment.environment_revision,
            semantic_target_id=match.semantic_target_id,
            relation=subgoal.outcome.relation,
            observed_value=_observed_value(subgoal.outcome.relation, match),
        )
        return SubgoalCompletionPreparation(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            evaluated_at_state_version=progress.evaluated_at_state_version,
            subgoal_id=subgoal.subgoal_id,
            criterion_ids=tuple(
                criterion_id("subgoal", subgoal.subgoal_id, index)
                for index, _ in enumerate(subgoal.success_criteria)
            ),
            requirement_ids=tuple(
                evidence_requirement_id("subgoal", subgoal.subgoal_id, index)
                for index, _ in enumerate(subgoal.evidence_requirements)
            ),
            evidence=(evidence,),
            source="current_observation",
        )


def _identity_current(plan: TaskPlan, progress: TaskPlanProgressStateView) -> bool:
    return (
        progress.plan_id == plan.plan_id
        and progress.plan_version == plan.plan_version
        and progress.plan_based_on_state_version == plan.based_on_state_version
    )


def _observation_identity_current(
    environment: PlanningEnvironmentSummary,
    *,
    snapshot_id: str,
    page_revision: str,
    environment_revision: str,
) -> bool:
    return (
        (not snapshot_id or snapshot_id == environment.snapshot_id)
        and (not page_revision or page_revision == environment.page_revision)
        and (
            not environment_revision
            or environment_revision == environment.environment_revision
        )
    )


def _unique_target(
    subject: str,
    affordances: tuple[PlanningAffordanceSummary, ...],
) -> PlanningAffordanceSummary | None:
    if subject.strip().casefold() in {"combobox", "dropdown", "list", "select"}:
        matches = tuple(
            item
            for item in affordances
            if item.role.casefold() in {"combobox", "listbox", "select"}
        )
        return matches[0] if len(matches) == 1 else None
    subject_tokens = _label_tokens(subject)
    if not subject_tokens:
        return None
    matches = tuple(
        item
        for item in affordances
        if subject_tokens.issubset(
            _label_tokens(item.label)
            | _label_tokens(item.semantic_target_id)
            | _label_tokens(item.role)
        )
    )
    if len(matches) != 1:
        return None
    return matches[0]


def _relation_satisfied(
    relation: SubgoalOutcomeRelation,
    affordance: PlanningAffordanceSummary,
    *,
    expected_value: str = "",
) -> bool:
    if relation == SubgoalOutcomeRelation.IS_VISIBLE:
        return affordance.current_state.visible is True
    if relation == SubgoalOutcomeRelation.IS_AVAILABLE:
        return (
            affordance.current_state.visible is True
            and affordance.current_state.enabled is True
        )
    if relation == SubgoalOutcomeRelation.IS_SELECTED:
        if expected_value:
            return expected_value in affordance.current_state.selected_options
        return (
            affordance.current_state.selected is True
            or bool(affordance.current_state.selected_options)
        )
    return False


def _observed_value(
    relation: SubgoalOutcomeRelation,
    affordance: PlanningAffordanceSummary,
) -> str | bool | None:
    if relation == SubgoalOutcomeRelation.IS_VISIBLE:
        return affordance.current_state.visible
    if relation == SubgoalOutcomeRelation.IS_AVAILABLE:
        return (
            affordance.current_state.visible is True
            and affordance.current_state.enabled is True
        )
    if relation == SubgoalOutcomeRelation.IS_SELECTED:
        selected = affordance.current_state.selected_options
        return selected[0] if len(selected) == 1 else affordance.current_state.selected
    return None


def _evidence_ref(evidence: CurrentStateEvidence) -> str:
    return ":".join(
        (
            "current_observation",
            evidence.snapshot_id,
            evidence.page_revision,
            evidence.semantic_target_id,
            evidence.relation.value,
        )
    )


def _label_tokens(value: str) -> set[str]:
    normalized = "".join(
        character.casefold() if character.isalnum() else " " for character in value
    )
    return {item for item in normalized.split() if item}
