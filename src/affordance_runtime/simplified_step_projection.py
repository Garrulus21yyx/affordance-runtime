"""Read-only legacy TaskPlan to simplified active-step projection.

S2 foundation only: this module projects current TaskPlan/PlanProgress state
into simplified Step contracts for compatibility diagnostics. It does not
mutate StateKernel, write trace, invoke planners, or change production
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.simplified_runtime_contracts import (
    AbsenceCriterion,
    Criterion,
    CriterionEvidencePolicy,
    EvidenceStrength,
    PresenceCriterion,
    SourceReference,
    StateCriterion,
    StateCriterionRelation,
    StepProgressView,
    StepSpec,
    TaskPlanView,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    SourcedTaskClaim,
    TaskObligationRelation,
    TaskObligationSpec,
    TaskSpec,
)
from affordance_runtime.task_planning import PlanProgress, SubgoalSpec, TaskPlan


class LegacyStepProjectionStatus(StrEnum):
    PROJECTED = "projected"
    NO_PLAN = "no_plan"
    STALE_PLAN = "stale_plan"
    PROJECTION_INVALID = "projection_invalid"


class TaskCompletionProjectionStatus(StrEnum):
    PROJECTED = "projected"
    PENDING = "pending"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class LegacyStepProjectionResult:
    status: LegacyStepProjectionStatus
    evaluated_at_state_version: int
    task_plan_view: TaskPlanView | None = None
    step_progress_view: StepProgressView | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, LegacyStepProjectionStatus):
            raise ValueError("unsupported legacy step projection status")
        if self.evaluated_at_state_version < 0:
            raise ValueError("evaluated state version cannot be negative")
        if self.status == LegacyStepProjectionStatus.PROJECTED:
            if self.task_plan_view is None or self.step_progress_view is None:
                raise ValueError("projected result requires task and progress views")
        elif self.task_plan_view is not None or self.step_progress_view is not None:
            raise ValueError("non-projected result cannot carry projected views")


@dataclass(frozen=True)
class TaskCompletionCriterionProjectionResult:
    status: TaskCompletionProjectionStatus
    criterion: Criterion | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaskCompletionProjectionStatus):
            raise ValueError("unsupported task completion projection status")
        if self.status == TaskCompletionProjectionStatus.PROJECTED:
            if self.criterion is None:
                raise ValueError("projected task completion requires a criterion")
        elif self.criterion is not None:
            raise ValueError("non-projected task completion cannot carry a criterion")


def project_state_legacy_task_plan_to_step_view(
    *,
    task_spec: TaskSpec,
    state: StateKernel,
) -> LegacyStepProjectionResult:
    """Project the currently installed legacy plan without changing state."""

    if state.task_plan is None or state.plan_progress is None:
        return LegacyStepProjectionResult(
            status=LegacyStepProjectionStatus.NO_PLAN,
            evaluated_at_state_version=state.version,
            reason="state has no installed TaskPlan",
        )
    return project_legacy_task_plan_to_step_view(
        task_spec=task_spec,
        plan=state.task_plan,
        progress=state.plan_progress,
        evaluated_at_state_version=state.version,
    )


def project_task_completion_criterion(
    task_spec: TaskSpec,
) -> TaskCompletionCriterionProjectionResult:
    """Project an unambiguous task-level completion criterion from TaskSpec."""

    terminal_obligations = tuple(item for item in task_spec.obligations if item.terminal)
    if not terminal_obligations:
        return TaskCompletionCriterionProjectionResult(
            status=TaskCompletionProjectionStatus.PENDING,
            reason="TaskSpec has no terminal obligation",
        )
    if len(terminal_obligations) > 1:
        return TaskCompletionCriterionProjectionResult(
            status=TaskCompletionProjectionStatus.UNSUPPORTED,
            reason="multiple terminal obligations cannot be projected unambiguously",
        )
    claims_by_id = {item.claim_id: item for item in task_spec.source_claims}
    criterion = _criterion_from_obligation(
        obligation=terminal_obligations[0],
        claims_by_id=claims_by_id,
    )
    if criterion is None:
        return TaskCompletionCriterionProjectionResult(
            status=TaskCompletionProjectionStatus.UNSUPPORTED,
            reason="terminal obligation has unsupported criterion shape",
        )
    return TaskCompletionCriterionProjectionResult(
        status=TaskCompletionProjectionStatus.PROJECTED,
        criterion=criterion,
    )


def project_legacy_task_plan_to_step_view(
    *,
    task_spec: TaskSpec,
    plan: TaskPlan,
    progress: PlanProgress,
    evaluated_at_state_version: int,
) -> LegacyStepProjectionResult:
    """Project a legacy TaskPlan by exact canonical obligation identity only."""

    if evaluated_at_state_version < 0:
        return LegacyStepProjectionResult(
            status=LegacyStepProjectionStatus.PROJECTION_INVALID,
            evaluated_at_state_version=0,
            reason="evaluated state version cannot be negative",
        )
    if plan.task_id != task_spec.task_id or plan.task_revision != task_spec.revision:
        return LegacyStepProjectionResult(
            status=LegacyStepProjectionStatus.STALE_PLAN,
            evaluated_at_state_version=evaluated_at_state_version,
            reason="TaskPlan task identity does not match TaskSpec",
        )

    obligation_by_id = {item.obligation_id: item for item in task_spec.obligations}
    claims_by_id = {item.claim_id: item for item in task_spec.source_claims}
    steps: list[StepSpec] = []
    for subgoal in plan.subgoals:
        obligation = obligation_by_id.get(subgoal.subgoal_id)
        if obligation is None:
            return LegacyStepProjectionResult(
                status=LegacyStepProjectionStatus.PROJECTION_INVALID,
                evaluated_at_state_version=evaluated_at_state_version,
                reason=(
                    f"TaskPlan subgoal {subgoal.subgoal_id!r} does not match an "
                    "exact obligation id"
                ),
            )
        criterion = _criterion_from_subgoal_and_obligation(
            subgoal=subgoal,
            obligation=obligation,
            claims_by_id=claims_by_id,
        )
        if criterion is None:
            return LegacyStepProjectionResult(
                status=LegacyStepProjectionStatus.PROJECTION_INVALID,
                evaluated_at_state_version=evaluated_at_state_version,
                reason=f"TaskPlan subgoal {subgoal.subgoal_id!r} has unsupported criterion shape",
            )
        try:
            steps.append(
                StepSpec(
                    step_id=subgoal.subgoal_id,
                    objective=subgoal.objective,
                    completion_criteria=(criterion,),
                    source_refs=criterion.source_refs,
                    depends_on=subgoal.depends_on,
                )
            )
        except ValueError as exc:
            return LegacyStepProjectionResult(
                status=LegacyStepProjectionStatus.PROJECTION_INVALID,
                evaluated_at_state_version=evaluated_at_state_version,
                reason=str(exc),
            )

    active_step_id = progress.active_subgoal_id
    if not active_step_id:
        ready = progress.ready_subgoal_ids(plan)
        active_step_id = ready[0] if ready else plan.subgoals[-1].subgoal_id
    try:
        task_plan_view = TaskPlanView(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            steps=tuple(steps),
            active_step_id=active_step_id,
        )
        step_progress_view = StepProgressView(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            active_step_id=active_step_id,
            completed_step_ids=tuple(progress.completed_subgoal_ids),
            failed_step_ids=tuple(progress.failed_subgoal_ids),
            evidence_by_step_id=_project_evidence_by_step(progress),
        )
    except ValueError as exc:
        return LegacyStepProjectionResult(
            status=LegacyStepProjectionStatus.PROJECTION_INVALID,
            evaluated_at_state_version=evaluated_at_state_version,
            reason=str(exc),
        )

    return LegacyStepProjectionResult(
        status=LegacyStepProjectionStatus.PROJECTED,
        evaluated_at_state_version=evaluated_at_state_version,
        task_plan_view=task_plan_view,
        step_progress_view=step_progress_view,
    )


def _criterion_from_subgoal_and_obligation(
    *,
    subgoal: SubgoalSpec,
    obligation: TaskObligationSpec,
    claims_by_id: dict[str, SourcedTaskClaim],
) -> Criterion | None:
    relation = _map_relation(obligation.relation)
    if relation is None:
        return None
    if subgoal.outcome is not None:
        outcome_relation = _map_relation(
            TaskObligationRelation(subgoal.outcome.relation.value)
        )
        if outcome_relation != relation:
            return None
        if subgoal.outcome.subject != obligation.subject:
            return None
    expected_value = obligation.expected_value
    if subgoal.outcome is not None and subgoal.outcome.value:
        expected_value = subgoal.outcome.value
    return _criterion_from_obligation(
        obligation=obligation,
        claims_by_id=claims_by_id,
        relation=relation,
        expected_value=expected_value,
    )


def _criterion_from_obligation(
    *,
    obligation: TaskObligationSpec,
    claims_by_id: dict[str, SourcedTaskClaim],
    relation: StateCriterionRelation | None = None,
    expected_value: str | None = None,
) -> Criterion | None:
    resolved_relation = relation or _map_relation(obligation.relation)
    if resolved_relation is None:
        return None
    source_refs = _source_refs_for_obligation(obligation, claims_by_id)
    if not source_refs:
        return None
    resolved_value = obligation.expected_value if expected_value is None else expected_value
    policy = CriterionEvidencePolicy(
        minimum_strength=EvidenceStrength.INDEPENDENT,
        allowed_source_kinds=("task_obligation",),
    )
    if resolved_relation == StateCriterionRelation.IS_ABSENT:
        return AbsenceCriterion(
            criterion_id=obligation.obligation_id,
            subject=obligation.subject,
            relation=resolved_relation,
            expected_value=resolved_value or None,
            evidence_policy=policy,
            source_refs=source_refs,
        )
    if resolved_relation in {
        StateCriterionRelation.IS_VISIBLE,
        StateCriterionRelation.IS_AVAILABLE,
    }:
        return PresenceCriterion(
            criterion_id=obligation.obligation_id,
            subject=obligation.subject,
            relation=resolved_relation,
            expected_value=resolved_value or None,
            evidence_policy=policy,
            source_refs=source_refs,
        )
    return StateCriterion(
        criterion_id=obligation.obligation_id,
        subject=obligation.subject,
        relation=resolved_relation,
        expected_value=resolved_value or None,
        evidence_policy=policy,
        source_refs=source_refs,
    )


def _source_refs_for_obligation(
    obligation: TaskObligationSpec,
    claims_by_id: dict[str, SourcedTaskClaim],
) -> tuple[SourceReference, ...]:
    refs: list[SourceReference] = []
    for claim_id in obligation.claim_ids:
        claim = claims_by_id.get(claim_id)
        if claim is None:
            return ()
        refs.append(
            SourceReference(
                source_id=claim.source_ref,
                source_unit_id=claim.claim_id,
            )
        )
    return tuple(refs)


def _map_relation(
    relation: TaskObligationRelation,
) -> StateCriterionRelation | None:
    try:
        return StateCriterionRelation(relation.value)
    except ValueError:
        return None


def _project_evidence_by_step(
    progress: PlanProgress,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    entries: list[tuple[str, tuple[str, ...]]] = []
    for step_id in progress.completed_subgoal_ids:
        refs = tuple(dict.fromkeys(progress.evidence_by_subgoal.get(step_id, ())))
        if refs:
            entries.append((step_id, refs))
    return tuple(entries)
