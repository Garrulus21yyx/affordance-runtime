"""Terminal decision helpers for Coordinator-controlled runtime stops."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.trace import TraceDag, TraceNode

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
    result: Mapping[str, object],
) -> TaskTerminalCommit:
    """Commit the single terminal success transition and TaskCompleted event."""

    state.final_result = dict(result)
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
    terminal = commit_task_terminal_success(
        state=state,
        trace=trace,
        parent=parent,
        result=decision.result,
    )
    return PlannerTerminalCommit(terminal.parent, "completed")
