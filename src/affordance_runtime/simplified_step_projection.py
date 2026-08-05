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
    StepActivityStatus,
    StepProgressView,
    StepSpec,
    TaskPlanView,
)
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    SourcedTaskClaim,
    TaskObligationSpec,
    TaskSpec,
)
from affordance_runtime.task_planning import PlanProgress, SubgoalSpec, TaskPlan
from affordance_runtime.task_source_references import task_source_refs


class LegacyStepProjectionStatus(StrEnum):
    PROJECTED = "projected"
    NO_PLAN = "no_plan"
    STALE_PLAN = "stale_plan"
    PROJECTION_INVALID = "projection_invalid"
    UNSUPPORTED_EVIDENCE_POLICY = "unsupported_evidence_policy"


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

    if state.task_plan is None or state.task_progress is None:
        return LegacyStepProjectionResult(
            status=LegacyStepProjectionStatus.NO_PLAN,
            evaluated_at_state_version=state.version,
            reason="state has no installed TaskPlan",
        )
    return project_legacy_task_plan_to_step_view(
        task_spec=task_spec,
        plan=state.task_plan,
        progress=state.task_progress,
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
    progress_error = _validate_legacy_progress_ids(plan=plan, progress=progress)
    if progress_error:
        return LegacyStepProjectionResult(
            status=LegacyStepProjectionStatus.PROJECTION_INVALID,
            evaluated_at_state_version=evaluated_at_state_version,
            reason=progress_error,
        )
    steps: list[StepSpec] = []
    for subgoal in plan.subgoals:
        obligation = obligation_by_id.get(subgoal.subgoal_id)
        if obligation is None and obligation_by_id:
            return LegacyStepProjectionResult(
                status=LegacyStepProjectionStatus.PROJECTION_INVALID,
                evaluated_at_state_version=evaluated_at_state_version,
                reason=(
                    f"TaskPlan subgoal {subgoal.subgoal_id!r} does not match an "
                    "exact obligation id"
                ),
            )
        criterion = (
            _criterion_from_subgoal_and_obligation(
                subgoal=subgoal,
                obligation=obligation,
                claims_by_id=claims_by_id,
            )
            if obligation is not None
            else _criterion_from_accepted_subgoal(subgoal, task_spec)
        )
        if criterion is None:
            status = (
                LegacyStepProjectionStatus.UNSUPPORTED_EVIDENCE_POLICY
                if obligation is not None and not obligation.typed_evidence_requirements
                else LegacyStepProjectionStatus.PROJECTION_INVALID
            )
            return LegacyStepProjectionResult(
                status=status,
                evaluated_at_state_version=evaluated_at_state_version,
                reason=f"TaskPlan subgoal {subgoal.subgoal_id!r} has unsupported criterion shape",
            )
        try:
            steps.append(
                StepSpec(
                    step_id=subgoal.subgoal_id,
                    objective=subgoal.objective,
                    interaction=subgoal.interaction,
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

    active_step_id: str | None = progress.active_subgoal_id or None
    ready_step_ids: tuple[str, ...] = ()
    activity_status = StepActivityStatus.NO_PLAN
    if active_step_id is not None:
        activity_status = StepActivityStatus.ACTIVE
    else:
        ready_step_ids = tuple(progress.ready_subgoal_ids(plan))
        if ready_step_ids:
            activity_status = StepActivityStatus.READY_NOT_ACTIVATED
        elif set(progress.completed_subgoal_ids) == {item.subgoal_id for item in plan.subgoals}:
            activity_status = StepActivityStatus.COMPLETED
        else:
            return LegacyStepProjectionResult(
                status=LegacyStepProjectionStatus.PROJECTION_INVALID,
                evaluated_at_state_version=evaluated_at_state_version,
                reason="legacy progress has no active, ready, or completed step",
            )
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
            activity_status=activity_status,
            completed_step_ids=tuple(progress.completed_subgoal_ids),
            failed_step_ids=tuple(progress.failed_subgoal_ids),
            ready_step_ids=ready_step_ids,
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


def _criterion_from_accepted_subgoal(
    subgoal: SubgoalSpec,
    task_spec: TaskSpec,
) -> Criterion | None:
    """Project accepted TaskPlan outcome without consulting compatibility graphs."""

    if subgoal.outcome is None:
        subject = _interaction_subject(subgoal)
        relation = (
            StateCriterionRelation.IS_VISIBLE
            if subgoal.operation_class in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
            else StateCriterionRelation.IS_COMPLETED
        )
        expected_value = None
    else:
        subject = subgoal.outcome.subject
        relation = StateCriterionRelation(subgoal.outcome.relation)
        expected_value = subgoal.outcome.value or None
    source_refs = task_source_refs(task_spec)
    policy = CriterionEvidencePolicy(
        minimum_strength=EvidenceStrength.INDEPENDENT,
        allowed_source_kinds=("dom_state", "visual_state", "api_state", "device_state"),
    )
    values = {
        "criterion_id": f"criterion:{subgoal.subgoal_id}",
        "subject": subject,
        "relation": relation,
        "expected_value": expected_value,
        "evidence_policy": policy,
        "source_refs": source_refs,
    }
    if relation == StateCriterionRelation.IS_ABSENT:
        return AbsenceCriterion(**values)
    if relation in {StateCriterionRelation.IS_VISIBLE, StateCriterionRelation.IS_AVAILABLE}:
        return PresenceCriterion(**values)
    return StateCriterion(**values)


def _interaction_subject(subgoal: SubgoalSpec) -> str:
    interaction = subgoal.interaction
    if hasattr(interaction, "target"):
        return str(interaction.target)
    if hasattr(interaction, "collection"):
        return str(interaction.collection.target)
    if hasattr(interaction, "source"):
        return str(interaction.source.target)
    if hasattr(interaction, "region"):
        return str(interaction.region)
    return subgoal.objective


def _criterion_from_subgoal_and_obligation(
    *,
    subgoal: SubgoalSpec,
    obligation: TaskObligationSpec,
    claims_by_id: dict[str, SourcedTaskClaim],
) -> Criterion | None:
    relation = StateCriterionRelation(obligation.relation)
    if subgoal.outcome is not None:
        if subgoal.outcome.relation != relation:
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
    resolved_relation = relation or StateCriterionRelation(obligation.relation)
    source_refs = _source_refs_for_obligation(obligation, claims_by_id)
    if not source_refs:
        return None
    resolved_value = obligation.expected_value if expected_value is None else expected_value
    policy = _evidence_policy_for_obligation(obligation)
    if policy is None:
        return None
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


def _validate_legacy_progress_ids(*, plan: TaskPlan, progress: PlanProgress) -> str:
    plan_step_ids = {item.subgoal_id for item in plan.subgoals}
    completed = set(progress.completed_subgoal_ids)
    failed = set(progress.failed_subgoal_ids)
    unknown_completed = completed - plan_step_ids
    if unknown_completed:
        return f"unknown completed step ids: {sorted(unknown_completed)!r}"
    unknown_failed = failed - plan_step_ids
    if unknown_failed:
        return f"unknown failed step ids: {sorted(unknown_failed)!r}"
    active = progress.active_subgoal_id or ""
    if active and active not in plan_step_ids:
        return f"unknown active step id: {active!r}"
    if active and (active in completed or active in failed):
        return "active step cannot be completed or failed"
    evidence_keys = set(progress.evidence_by_subgoal)
    unknown_evidence = evidence_keys - completed
    if unknown_evidence:
        return f"evidence key is not a completed step id: {sorted(unknown_evidence)!r}"
    for step_id in progress.completed_subgoal_ids:
        if not tuple(progress.evidence_by_subgoal.get(step_id, ())):
            return f"completed step {step_id!r} without verifier evidence"
    return ""


def _evidence_policy_for_obligation(
    obligation: TaskObligationSpec,
) -> CriterionEvidencePolicy | None:
    if not obligation.typed_evidence_requirements:
        return None
    mapped_strengths: list[EvidenceStrength] = []
    for requirement in obligation.typed_evidence_requirements:
        strength = _map_evidence_strength(requirement.minimum_strength)
        if strength is None:
            return None
        mapped_strengths.append(strength)
    if not mapped_strengths:
        return None
    strongest = max(mapped_strengths, key=_evidence_strength_rank)
    source_kinds = tuple(
        dict.fromkeys(
            requirement.kind.value
            for requirement in obligation.typed_evidence_requirements
        )
    )
    if not source_kinds:
        return None
    return CriterionEvidencePolicy(
        minimum_strength=strongest,
        allowed_source_kinds=source_kinds,
    )


def _map_evidence_strength(value: str) -> EvidenceStrength | None:
    normalized = value.casefold()
    if normalized == EvidenceStrength.WEAK.value:
        return EvidenceStrength.WEAK
    if normalized in {EvidenceStrength.INDEPENDENT.value, "strong"}:
        return EvidenceStrength.INDEPENDENT
    if normalized == EvidenceStrength.AUTHORITATIVE.value:
        return EvidenceStrength.AUTHORITATIVE
    return None


def _evidence_strength_rank(value: EvidenceStrength | None) -> int:
    if value == EvidenceStrength.WEAK:
        return 0
    if value == EvidenceStrength.INDEPENDENT:
        return 1
    if value == EvidenceStrength.AUTHORITATIVE:
        return 2
    return -1


def _source_refs_for_obligation(
    obligation: TaskObligationSpec,
    claims_by_id: dict[str, SourcedTaskClaim],
) -> tuple[SourceReference, ...]:
    refs: list[SourceReference] = []
    for claim_id in obligation.claim_ids:
        claim = claims_by_id.get(claim_id)
        if claim is None:
            return ()
        if claim.source_unit_ids:
            refs.extend(
                SourceReference(
                    source_id=claim.source_ref,
                    source_unit_id=source_unit_id,
                    claim_id=claim.claim_id,
                )
                for source_unit_id in claim.source_unit_ids
            )
        else:
            refs.append(
                SourceReference(
                    source_id=claim.source_ref,
                    source_unit_id=f"compatibility:claim-only:{claim.claim_id}",
                    claim_id=claim.claim_id,
                    field_path=("compatibility_claim_only",),
                )
            )
    return tuple(refs)


def _project_evidence_by_step(
    progress: PlanProgress,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    entries: list[tuple[str, tuple[str, ...]]] = []
    for step_id in progress.completed_subgoal_ids:
        refs = tuple(dict.fromkeys(progress.evidence_by_subgoal.get(step_id, ())))
        if refs:
            entries.append((step_id, refs))
    return tuple(entries)
