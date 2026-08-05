"""Stateless TaskPlan invocation and acceptance preparation.

The flow owns planner/lifecycle orchestration only.  It never mutates
``StateKernel``, writes trace events, selects recovery, or changes budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureClass
from affordance_runtime.immutable import freeze_json
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_lifecycle import (
    TaskPlanBudgetLimits,
    TaskPlanLifecycle,
    TaskPlanReplacementDecision,
    TaskPlanReplacementReason,
    TaskPlanTransition,
)
from affordance_runtime.task_planning import (
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlanValidationIssue,
    TaskPlanValidationReport,
    TaskPlanValidationStatus,
    task_planning_context_summary,
)
from affordance_runtime.unified_observation import UnifiedObservation


class TaskPlanFlowKind(StrEnum):
    NONE = "none"
    INITIAL = "initial"
    REPLACEMENT = "replacement"


@dataclass(frozen=True)
class TaskPlanFlowFailure:
    """Typed failure returned before any authoritative state mutation."""

    error_code: RuntimeErrorCode
    failure_class: FailureClass
    message: str
    validation_status: TaskPlanValidationStatus | None = None
    issues: tuple[TaskPlanValidationIssue, ...] = ()


@dataclass(frozen=True)
class TaskPlanFlowResult:
    """One authority-free planning preparation result."""

    kind: TaskPlanFlowKind = TaskPlanFlowKind.NONE
    transition: TaskPlanTransition | None = None
    replacement: TaskPlanReplacementDecision | None = None
    failure: TaskPlanFlowFailure | None = None

    @property
    def required(self) -> bool:
        return self.kind != TaskPlanFlowKind.NONE

    @property
    def accepted(self) -> bool:
        return self.required and self.transition is not None and self.failure is None


@dataclass(frozen=True)
class TaskPlanTraceProjection:
    """One event payload that the Coordinator may append after committing state."""

    kind: str
    payload: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_json(self.payload))


@dataclass(frozen=True)
class TaskPlanCommitStateView:
    """Post-commit facts projected without granting state mutation authority."""

    active_subgoal: str
    completed_subgoal_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskPlanCommitPreparation:
    """Translate TaskPlanFlow output into commit and trace projections only."""

    result: TaskPlanFlowResult

    @property
    def transition(self) -> TaskPlanTransition | None:
        return self.result.transition

    @property
    def failure(self) -> TaskPlanFlowFailure | None:
        return self.result.failure

    @property
    def accepted(self) -> bool:
        return self.result.accepted

    def pre_commit_projection(self, *, state_phase: str) -> TaskPlanTraceProjection | None:
        transition = self.transition
        if self.result.kind != TaskPlanFlowKind.INITIAL or transition is None:
            return None
        task_plan = transition.plan
        report = transition.validation
        return TaskPlanTraceProjection(
            "TaskPlanProposed",
            {
                "state": state_phase,
                "plan_id": task_plan.plan_id,
                "plan_version": task_plan.plan_version,
                "generated_by": task_plan.generated_by.value,
                "subgoal_count": len(task_plan.subgoals),
                "supersedes_plan_id": task_plan.supersedes_plan_id,
                "planning_context": task_planning_context_summary(transition.context),
                "validation": report.status.value,
                "issues": [item.model_dump(mode="json") for item in report.issues],
            },
        )

    def with_commit_failure(self, exc: Exception) -> "TaskPlanCommitPreparation":
        if not self.accepted:
            raise ValueError("only an accepted TaskPlanFlow result can fail during commit")
        return TaskPlanCommitPreparation(
            TaskPlanFlowResult(
                kind=self.result.kind,
                transition=self.transition,
                replacement=self.result.replacement,
                failure=TaskPlanFlowFailure(
                    error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                    failure_class=FailureClass.VALIDATION,
                    message=f"{type(exc).__name__}: {exc}"[:500],
                ),
            )
        )

    def failure_projection(self, *, state_phase: str) -> TaskPlanTraceProjection:
        failure = self.failure
        if failure is None:
            raise ValueError("a failure projection requires a TaskPlanFlow failure")
        replacement = self.result.replacement
        return TaskPlanTraceProjection(
            "TaskReplanRejected" if self.result.kind == TaskPlanFlowKind.REPLACEMENT else "TaskPlanRejected",
            {
                "state": state_phase,
                "error_code": failure.error_code.value,
                "reason": failure.message,
                "validation": failure.validation_status.value if failure.validation_status is not None else "",
                "issues": [item.model_dump(mode="json") for item in failure.issues],
                "replacement_reason": (
                    replacement.reason.value if replacement is not None and replacement.reason is not None else ""
                ),
            },
        )

    def acceptance_projection(
        self,
        *,
        state_phase: str,
        committed: TaskPlanCommitStateView,
    ) -> TaskPlanTraceProjection:
        if not self.accepted or self.transition is None:
            raise ValueError("an acceptance projection requires an accepted TaskPlanFlow result")
        task_plan = self.transition.plan
        if self.result.kind == TaskPlanFlowKind.REPLACEMENT:
            previous = self.transition.previous_plan
            replacement = self.result.replacement
            if previous is None or replacement is None or replacement.reason is None:
                raise ValueError("accepted replacement must retain previous-plan and replacement lineage")
            return TaskPlanTraceProjection(
                "TaskReplanned",
                {
                    "state": state_phase,
                    "reason": replacement.reason.value,
                    "previous_plan_id": previous.plan_id,
                    "supersedes_plan_id": task_plan.supersedes_plan_id,
                    "plan_id": task_plan.plan_id,
                    "plan_version": task_plan.plan_version,
                    "preserved_subgoal_ids": list(committed.completed_subgoal_ids),
                    "active_subgoal": committed.active_subgoal,
                    "planning_context": task_planning_context_summary(self.transition.context),
                },
            )
        return TaskPlanTraceProjection(
            "TaskPlanAccepted",
            {
                "state": state_phase,
                "plan_id": task_plan.plan_id,
                "plan_version": task_plan.plan_version,
                "supersedes_plan_id": task_plan.supersedes_plan_id,
                "active_subgoal": committed.active_subgoal,
            },
        )


_CURRENT_STATE_COMPLETABLE_RELATIONS = frozenset(
    {
        SubgoalOutcomeRelation.IS_AVAILABLE,
        SubgoalOutcomeRelation.IS_VISIBLE,
    }
)


@dataclass(frozen=True)
class TaskPlanFlow:
    """Prepare an initial plan or required replacement through one typed port."""

    lifecycle: TaskPlanLifecycle

    def prepare(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
    ) -> TaskPlanFlowResult:
        if state.task_plan is None:
            return self._prepare_initial(task_spec, state, snapshot, budget)
        replacement = self.lifecycle.evaluate_replacement(
            task_spec,
            state,
            snapshot,
            budget,
        )
        if not replacement.required:
            return TaskPlanFlowResult()
        if replacement.reason == TaskPlanReplacementReason.ACTIVE_SUBGOAL_OUTCOME_ALREADY_SATISFIED:
            discarded = self._prepare_current_state_discard(
                task_spec,
                state,
                snapshot,
                budget,
                replacement,
            )
            if discarded is not None:
                return discarded
        return self._prepare_replacement(
            task_spec,
            state,
            snapshot,
            budget,
            replacement,
        )

    def _prepare_current_state_discard(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
        replacement: TaskPlanReplacementDecision,
    ) -> TaskPlanFlowResult | None:
        assert replacement.reason is not None
        previous_plan = state.task_plan
        subgoal = self.lifecycle.active_subgoal_spec(state)
        if subgoal is None:
            subgoal = _ready_replacement_subgoal(state, replacement)
        if (
            previous_plan is None
            or subgoal is None
            or task_spec.obligations
            or subgoal.subgoal_id != replacement.subgoal_id
            or subgoal.outcome is None
            or subgoal.outcome.relation not in _CURRENT_STATE_COMPLETABLE_RELATIONS
        ):
            return None
        remaining = tuple(
            item for item in previous_plan.subgoals if item.subgoal_id != subgoal.subgoal_id
        )
        if not remaining:
            return None
        context = self.lifecycle.build_context(
            task_spec,
            state,
            snapshot,
            budget,
            reason=replacement.reason.value,
        )
        plan = previous_plan.model_copy(
            update={
                "plan_id": f"{previous_plan.plan_id}-current-state-discard",
                "plan_version": previous_plan.plan_version + 1,
                "supersedes_plan_id": previous_plan.plan_id,
                "based_on_state_version": state.version,
                "subgoals": remaining,
            }
        )
        transition = TaskPlanTransition(
            context=context,
            plan=plan,
            validation=self.lifecycle.validator.validate(
                plan,
                task_spec,
                state_version=state.version,
                previous_plan=previous_plan,
                planning_context=context,
            ),
            previous_plan=previous_plan,
        )
        return _validated_result(
            TaskPlanFlowKind.REPLACEMENT,
            transition,
            replacement=replacement,
        )

    def _prepare_initial(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
    ) -> TaskPlanFlowResult:
        try:
            transition = self.lifecycle.propose_initial(
                task_spec,
                state,
                snapshot,
                budget,
            )
        except Exception as exc:
            return TaskPlanFlowResult(
                kind=TaskPlanFlowKind.INITIAL,
                failure=_invocation_failure(exc, initial=True),
            )
        return _validated_result(TaskPlanFlowKind.INITIAL, transition)

    def _prepare_replacement(
        self,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: UnifiedObservation,
        budget: TaskPlanBudgetLimits,
        replacement: TaskPlanReplacementDecision,
    ) -> TaskPlanFlowResult:
        assert replacement.reason is not None
        try:
            transition = self.lifecycle.propose_replacement(
                task_spec,
                state,
                snapshot,
                budget,
                reason=replacement.reason.value,
            )
        except Exception as exc:
            return TaskPlanFlowResult(
                kind=TaskPlanFlowKind.REPLACEMENT,
                replacement=replacement,
                failure=_invocation_failure(exc, initial=False),
            )
        if transition.previous_plan is None:
            return TaskPlanFlowResult(
                kind=TaskPlanFlowKind.REPLACEMENT,
                transition=transition,
                replacement=replacement,
                failure=TaskPlanFlowFailure(
                    error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                    failure_class=FailureClass.PLANNING,
                    message="task replan transition is missing its previous plan",
                ),
            )
        return _validated_result(
            TaskPlanFlowKind.REPLACEMENT,
            transition,
            replacement=replacement,
        )


def _ready_replacement_subgoal(
    state: StateKernel,
    replacement: TaskPlanReplacementDecision,
) -> SubgoalSpec | None:
    if (
        state.task_plan is None
        or state.task_progress is None
        or state.task_progress.active_subgoal_id
        or not replacement.subgoal_id
    ):
        return None
    completed = set(state.task_progress.completed_subgoal_ids)
    failed = set(state.task_progress.failed_subgoal_ids)
    return next(
        (
            item
            for item in state.task_plan.subgoals
            if item.subgoal_id == replacement.subgoal_id
            and item.subgoal_id not in completed | failed
            and all(dependency in completed for dependency in item.depends_on)
        ),
        None,
    )


def _validated_result(
    kind: TaskPlanFlowKind,
    transition: TaskPlanTransition,
    *,
    replacement: TaskPlanReplacementDecision | None = None,
) -> TaskPlanFlowResult:
    report = transition.validation
    failure = None
    if report.status != TaskPlanValidationStatus.ACCEPT and not _current_state_precheck_only(
        report
    ):
        issue_codes = ",".join(dict.fromkeys(item.code for item in report.issues))
        detail = f" [{issue_codes}]" if issue_codes else ""
        failure = TaskPlanFlowFailure(
            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
            failure_class=FailureClass.VALIDATION,
            message=f"task plan validation: {report.status.value}{detail}"[:500],
            validation_status=report.status,
            issues=report.issues,
        )
    return TaskPlanFlowResult(
        kind=kind,
        transition=transition,
        replacement=replacement,
        failure=failure,
    )


def _current_state_precheck_only(report: TaskPlanValidationReport) -> bool:
    return (
        report.status == TaskPlanValidationStatus.REPAIRABLE
        and bool(report.issues)
        and all(item.code == "entry_outcome_already_satisfied" for item in report.issues)
    )


def _invocation_failure(
    exc: Exception,
    *,
    initial: bool,
) -> TaskPlanFlowFailure:
    return TaskPlanFlowFailure(
        error_code=(
            RuntimeErrorCode.PLANNER_FAILED
            if initial
            else RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
        ),
        failure_class=FailureClass.PLANNING,
        message=f"{type(exc).__name__}: {exc}"[:500],
    )
