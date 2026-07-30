"""Terminal decision helpers for Coordinator-controlled runtime stops."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.immutable import freeze_json, thaw_json_at_external_boundary
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport

PlannerTerminalStatus = Literal["not_terminal", "completed", "rejected"]


@dataclass(frozen=True)
class PlannerTerminalCommit:
    parent: TraceNode
    status: PlannerTerminalStatus
    message: str = ""

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @property
    def rejected(self) -> bool:
        return self.status == "rejected"


@dataclass(frozen=True)
class TaskTerminalCommit:
    parent: TraceNode


@dataclass(frozen=True)
class TaskCompletionResult:
    status: Literal["passed", "failed"]
    result: Mapping[str, object]
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", freeze_json(dict(self.result)))

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @classmethod
    def passed_with(cls, result: Mapping[str, object]) -> "TaskCompletionResult":
        return cls("passed", dict(result))

    @classmethod
    def failed(cls, reason: str) -> "TaskCompletionResult":
        return cls("failed", {}, reason)


class TaskCompletionVerifier:
    """Compatibility task-level completion verifier.

    For TaskSpec-backed tasks, completion requires an independent passed
    verification report. Legacy envelope-only tasks remain compatibility
    completions until their callers provide TaskSpec completion criteria.
    """

    def verify(
        self,
        *,
        task_spec: TaskSpec | None,
        state: StateKernel,
        verification: VerificationReport | None,
        result: Mapping[str, object],
    ) -> TaskCompletionResult:
        if task_spec is None:
            return TaskCompletionResult.passed_with(result)
        if verification is None and not state.receipts and state.effectful_action_count == 0:
            return TaskCompletionResult.passed_with(result)
        if verification is None or not verification.passed:
            return TaskCompletionResult.failed(
                "task completion requires an independent passed verification"
            )
        return TaskCompletionResult.passed_with(result)


def is_safe_incomplete_terminal(decision: PlannerDecision, state: StateKernel) -> bool:
    """Allow an evidence-explicit non-success stop without claiming completion."""

    status = str(decision.result.get("status") or "").casefold()
    return (
        status in {"blocked", "incomplete", "inconclusive", "unsupported"}
        and not state.receipts
        and state.effectful_action_count == 0
    )


def commit_task_terminal_success(
    *,
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    completion: TaskCompletionResult,
) -> TaskTerminalCommit:
    """Commit the single terminal success transition and TaskCompleted event."""

    if not completion.passed:
        raise ValueError("task completion verification did not pass")
    state.final_result = thaw_json_at_external_boundary(completion.result)
    state.transition("done")
    parent = trace.add(
        "TaskCompleted",
        {"state": state.phase, "result": state.final_result},
        parents=[parent.id],
    )
    return TaskTerminalCommit(parent)


def commit_planner_terminal_decision(
    *,
    decision: PlannerDecision,
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    completion: TaskCompletionResult | None = None,
) -> PlannerTerminalCommit:
    """Handle Planner-origin terminal requests without granting progress authority.

    A planner terminal request can only complete the run when no TaskPlan is
    active, when the TaskPlan is already verifier-backed complete, or when it is
    an explicit non-success stop before any effectful action. It never marks
    subgoals complete.
    """

    if not decision.done:
        return PlannerTerminalCommit(parent, "not_terminal")
    if state.task_plan is not None and not TaskPlanLifecycle.completed(state):
        if is_safe_incomplete_terminal(decision, state):
            parent = trace.add(
                "TaskPlanStoppedIncomplete",
                {
                    "state": state.phase,
                    "task_plan_id": state.task_plan.plan_id,
                    "result_status": str(decision.result.get("status") or ""),
                    "reason": decision.reason,
                },
                parents=[parent.id],
            )
            completion = TaskCompletionResult.passed_with(decision.result)
        else:
            message = "planner cannot finish before verifier-backed subgoal completion"
            parent = trace.add(
                "PlannerProposalRejected",
                {
                    "state": state.phase,
                    "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                    "reason": message,
                },
                parents=[parent.id],
            )
            return PlannerTerminalCommit(parent, "rejected", message)
    completion = completion or TaskCompletionResult.passed_with(decision.result)
    if not completion.passed:
        parent = trace.add(
            "PlannerProposalRejected",
            {
                "state": state.phase,
                "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                "reason": completion.reason,
            },
            parents=[parent.id],
        )
        return PlannerTerminalCommit(parent, "rejected", completion.reason)
    terminal = commit_task_terminal_success(
        state=state,
        trace=trace,
        parent=parent,
        completion=completion,
    )
    return PlannerTerminalCommit(terminal.parent, "completed")
