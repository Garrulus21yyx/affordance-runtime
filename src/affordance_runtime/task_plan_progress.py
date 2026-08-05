"""Authority-free TaskPlan progress reconciliation.

This module prepares verifier-backed current-state subgoal completion. It does
not mutate ``StateKernel``, write trace events, invoke planners, delete
subgoals, or accept task finish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from affordance_runtime.simplified_runtime_contracts import StateCriterion, StateCriterionRelation
from affordance_runtime.task_plan_contracts import TaskPlan
from affordance_runtime.task_planner import (
    PlanningAffordanceSummary,
    PlanningEnvironmentSummary,
)


@dataclass(frozen=True)
class VerifiedStepRecord:
    plan_id: str
    step_id: str
    step_digest: str
    verified_criterion_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    completed_at_state_version: int


@dataclass
class TaskProgress:
    """Verified execution facts that survive replacement independently of a plan graph."""

    active_step_id: str = ""
    verified_steps: list[VerifiedStepRecord] = field(default_factory=list)
    failed_step_ids: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)
    bindings: dict[str, object] = field(default_factory=dict)
    recent_action_outcome_refs: list[str] = field(default_factory=list)
    durable_evidence_refs: list[str] = field(default_factory=list)
    action_count_by_step: dict[str, int] = field(default_factory=dict)
    replan_count: int = 0

    @property
    def completed_step_ids(self) -> tuple[str, ...]:
        return tuple(record.step_id for record in self.verified_steps)

    def evidence_for_step(self, step_id: str) -> tuple[str, ...]:
        record = next(
            (item for item in reversed(self.verified_steps) if item.step_id == step_id),
            None,
        )
        return record.evidence_refs if record is not None else ()

    def ready_step_ids(self, plan: TaskPlan) -> tuple[str, ...]:
        completed = set(self.completed_step_ids)
        unavailable = completed | set(self.failed_step_ids)
        return tuple(
            step.step_id
            for step in plan.steps
            if step.step_id not in unavailable
            and set(step.depends_on).issubset(completed)
        )

    def activate_next(self, plan: TaskPlan) -> str:
        if self.active_step_id:
            return self.active_step_id
        ready = self.ready_step_ids(plan)
        self.active_step_id = ready[0] if ready else ""
        return self.active_step_id

    def complete(
        self,
        *,
        plan: TaskPlan,
        step_id: str,
        criterion_ids: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        state_version: int,
    ) -> None:
        import hashlib

        step = plan.step(step_id)
        if step is None:
            raise ValueError("unknown TaskPlan step")
        digest = "sha256:" + hashlib.sha256(repr(step).encode()).hexdigest()
        self.verified_steps = [item for item in self.verified_steps if item.step_id != step_id]
        self.verified_steps.append(
            VerifiedStepRecord(
                plan_id=plan.plan_id,
                step_id=step_id,
                step_digest=digest,
                verified_criterion_ids=criterion_ids,
                evidence_refs=tuple(dict.fromkeys(evidence_refs)),
                completed_at_state_version=state_version,
            )
        )
        if self.active_step_id == step_id:
            self.active_step_id = ""

    def record_action(self, step_id: str) -> None:
        self.action_count_by_step[step_id] = self.action_count_by_step.get(step_id, 0) + 1

    def action_budget_exhausted(self, plan: TaskPlan) -> bool:
        step = plan.step(self.active_step_id)
        return step is not None and self.action_count_by_step.get(step.step_id, 0) >= step.max_actions


@dataclass(frozen=True)
class TaskPlanProgressStateView:
    plan_id: str
    plan_version: int
    plan_based_on_state_version: int
    evaluated_at_state_version: int
    active_step_id: str
    completed_step_ids: tuple[str, ...]
    failed_step_ids: tuple[str, ...]


@dataclass(frozen=True)
class CurrentStateEvidence:
    snapshot_id: str
    page_revision: str
    environment_revision: str
    semantic_target_id: str
    relation: StateCriterionRelation
    observed_value: str | bool | int | float | None
    artifact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepCompletionPreparation:
    plan_id: str
    plan_version: int
    evaluated_at_state_version: int
    step_id: str
    criterion_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    evidence: tuple[CurrentStateEvidence, ...]
    source: Literal["current_observation"]


def current_state_evidence_refs(
    evidence: tuple[CurrentStateEvidence, ...],
) -> tuple[str, ...]:
    """Project typed current-state evidence into stable StateKernel refs."""

    return tuple(_evidence_ref(item) for item in evidence)


class CurrentStateStepCompletionEvaluator:
    """Prepare completion for a ready canonical StepSpec satisfied now."""

    _SUPPORTED_RELATIONS = {
        StateCriterionRelation.IS_AVAILABLE,
        StateCriterionRelation.IS_SELECTED,
        StateCriterionRelation.IS_VISIBLE,
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
    ) -> StepCompletionPreparation | None:
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
        step = next(
            (
                item
                for item in plan.steps
                if item.step_id == progress.active_step_id
            ),
            None,
        )
        if step is None:
            return None
        criterion = next(
            (item for item in step.completion_criteria if isinstance(item, StateCriterion)),
            None,
        )
        if criterion is None:
            return None
        if step.step_id in progress.completed_step_ids:
            return None
        if step.step_id in progress.failed_step_ids:
            return None
        if not set(step.depends_on).issubset(progress.completed_step_ids):
            return None
        if criterion.relation not in self._SUPPORTED_RELATIONS:
            return None
        match = _unique_target(criterion.subject, environment.affordances)
        if match is None:
            return None
        if not _relation_satisfied(
            criterion.relation,
            match,
            expected_value=("" if criterion.expected_value is None else str(criterion.expected_value)),
        ):
            return None
        evidence = CurrentStateEvidence(
            snapshot_id=environment.snapshot_id,
            page_revision=environment.page_revision,
            environment_revision=environment.environment_revision,
            semantic_target_id=match.semantic_target_id,
            relation=criterion.relation,
            observed_value=_observed_value(criterion.relation, match),
        )
        return StepCompletionPreparation(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            evaluated_at_state_version=progress.evaluated_at_state_version,
            step_id=step.step_id,
            criterion_ids=tuple(item.criterion_id for item in step.completion_criteria),
            requirement_ids=tuple(ref.source_unit_id for ref in step.source_refs),
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
    normalized_subject = subject.strip().casefold().replace("_", " ")
    if normalized_subject == "textarea":
        matches = tuple(
            item
            for item in affordances
            if item.role.casefold() in {"textbox", "searchbox"}
            and item.current_state.element_tag.casefold() == "textarea"
        )
        return matches[0] if len(matches) == 1 else None
    if normalized_subject in {"text box", "textbox"}:
        matches = tuple(
            item
            for item in affordances
            if item.role.casefold() in {"textbox", "searchbox"}
            and item.current_state.element_tag.casefold() != "textarea"
        )
        return matches[0] if len(matches) == 1 else None
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
    relation: StateCriterionRelation,
    affordance: PlanningAffordanceSummary,
    *,
    expected_value: str = "",
) -> bool:
    if relation == StateCriterionRelation.IS_VISIBLE:
        return affordance.current_state.visible is True
    if relation == StateCriterionRelation.IS_AVAILABLE:
        return (
            affordance.current_state.visible is True
            and affordance.current_state.enabled is True
        )
    if relation == StateCriterionRelation.IS_SELECTED:
        if expected_value:
            return expected_value in affordance.current_state.selected_options
        return (
            affordance.current_state.selected is True
            or bool(affordance.current_state.selected_options)
        )
    return False


def _observed_value(
    relation: StateCriterionRelation,
    affordance: PlanningAffordanceSummary,
) -> str | bool | None:
    if relation == StateCriterionRelation.IS_VISIBLE:
        return affordance.current_state.visible
    if relation == StateCriterionRelation.IS_AVAILABLE:
        return (
            affordance.current_state.visible is True
            and affordance.current_state.enabled is True
        )
    if relation == StateCriterionRelation.IS_SELECTED:
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
