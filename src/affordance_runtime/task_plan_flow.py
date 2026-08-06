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
from affordance_runtime.simplified_runtime_contracts import StepSpec
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_contracts import (
    TaskPlanDecisionStatus,
    TaskPlanIssue,
)
from affordance_runtime.task_plan_lifecycle import (
    TaskPlanBudgetLimits,
    TaskPlanLifecycle,
    TaskPlanReplacementDecision,
    TaskPlanTransition,
)
from affordance_runtime.task_planner import (
    TaskPlanningFailure,
    TaskPlanningGap,
    TaskPlanningNoPlan,
    task_planning_request_summary,
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
    validation_status: TaskPlanDecisionStatus | None = None
    issues: tuple[TaskPlanIssue, ...] = ()


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

    active_step: str
    completed_step_ids: tuple[str, ...] = ()


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
        decision = transition.decision
        return TaskPlanTraceProjection(
            "TaskPlanProposed",
            {
                "state": state_phase,
                "plan_id": task_plan.plan_id,
                "plan_version": task_plan.plan_version,
                "generated_by": task_plan.generated_by.value,
                "step_count": len(task_plan.steps),
                "supersedes_plan_id": task_plan.supersedes_plan_id,
                "planning_context": task_planning_request_summary(transition.request),
                "validation": decision.status.value,
                "issues": [vars(item) for item in decision.issues],
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
                "issues": [vars(item) for item in failure.issues],
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
                    "preserved_step_ids": list(committed.completed_step_ids),
                    "active_step": committed.active_step,
                    "planning_context": task_planning_request_summary(self.transition.request),
                },
            )
        return TaskPlanTraceProjection(
            "TaskPlanAccepted",
            {
                "state": state_phase,
                "plan_id": task_plan.plan_id,
                "plan_version": task_plan.plan_version,
                "supersedes_plan_id": task_plan.supersedes_plan_id,
                "active_step": committed.active_step,
            },
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
        return self._prepare_replacement(
            task_spec,
            state,
            snapshot,
            budget,
            replacement,
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
        if isinstance(transition, TaskPlanningNoPlan):
            return TaskPlanFlowResult()
        if isinstance(transition, (TaskPlanningGap, TaskPlanningFailure)):
            return _typed_planner_failure(transition, initial=True)
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
        if isinstance(transition, TaskPlanningNoPlan):
            return TaskPlanFlowResult()
        if isinstance(transition, (TaskPlanningGap, TaskPlanningFailure)):
            return _typed_planner_failure(
                transition,
                initial=False,
                replacement=replacement,
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


def _ready_replacement_step(
    state: StateKernel,
    replacement: TaskPlanReplacementDecision,
) -> StepSpec | None:
    if (
        state.task_plan is None
        or state.task_progress is None
        or state.task_progress.active_step_id
        or not replacement.step_id
    ):
        return None
    completed = set(state.task_progress.completed_step_ids)
    failed = set(state.task_progress.failed_step_ids)
    return next(
        (
            item
            for item in state.task_plan.steps
            if item.step_id == replacement.step_id
            and item.step_id not in completed | failed
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
    decision = transition.decision
    failure = None
    if decision.status != TaskPlanDecisionStatus.ACCEPTED:
        issue_codes = ",".join(dict.fromkeys(item.code for item in decision.issues))
        detail = f" [{issue_codes}]" if issue_codes else ""
        failure = TaskPlanFlowFailure(
            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
            failure_class=FailureClass.VALIDATION,
            message=f"task plan validation: {decision.status.value}{detail}"[:500],
            validation_status=decision.status,
            issues=decision.issues,
        )
    return TaskPlanFlowResult(
        kind=kind,
        transition=transition,
        replacement=replacement,
        failure=failure,
    )


def _invocation_failure(
    exc: Exception,
    *,
    initial: bool,
) -> TaskPlanFlowFailure:
    return TaskPlanFlowFailure(
        error_code=(RuntimeErrorCode.PLANNER_FAILED if initial else RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED),
        failure_class=FailureClass.PLANNING,
        message=f"{type(exc).__name__}: {exc}"[:500],
    )


def _typed_planner_failure(
    response: TaskPlanningGap | TaskPlanningFailure,
    *,
    initial: bool,
    replacement: TaskPlanReplacementDecision | None = None,
) -> TaskPlanFlowResult:
    message = (
        f"{response.gap_code}: {response.detail}".rstrip(": ")
        if isinstance(response, TaskPlanningGap)
        else f"{response.error_code}: {response.message}"
    )
    return TaskPlanFlowResult(
        kind=TaskPlanFlowKind.INITIAL if initial else TaskPlanFlowKind.REPLACEMENT,
        replacement=replacement,
        failure=TaskPlanFlowFailure(
            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
            failure_class=FailureClass.PLANNING,
            message=message[:500],
        ),
    )
