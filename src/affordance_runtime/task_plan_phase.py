"""Coordinator-facing TaskPlan phase seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.progress_phase import ProgressPhase
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec
from affordance_runtime.task_plan_flow import (
    TaskPlanCommitPreparation,
    TaskPlanCommitStateView,
    TaskPlanFlow,
    TaskPlanFlowFailure,
    TaskPlanFlowKind,
)
from affordance_runtime.task_plan_lifecycle import TaskPlanBudgetLimits
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class TaskPlanPhaseResult:
    parent: TraceNode
    failure: TaskPlanFlowFailure | None = None
    plan_committed: bool = False
    current_state_completion_committed: bool = False


def commit_task_plan_phase(
    task_spec: TaskSpec,
    state: StateKernel,
    snapshot: BrowserSnapshot,
    budget: TaskPlanBudgetLimits,
    trace: TraceDag,
    parent: TraceNode,
    *,
    task_plan_flow: TaskPlanFlow,
    recovery_phase: RecoveryPhase,
    progress_phase: ProgressPhase,
) -> TaskPlanPhaseResult:
    """Prepare and commit TaskPlan changes without keeping the logic in run_sync."""

    flow_result = task_plan_flow.prepare(
        task_spec,
        state,
        snapshot,
        budget,
    )
    plan_commit = TaskPlanCommitPreparation(flow_result)
    transition = plan_commit.transition
    pre_commit = plan_commit.pre_commit_projection(state_phase=state.phase)
    if pre_commit is not None:
        parent = trace.add(
            pre_commit.kind,
            pre_commit.payload,
            parents=[parent.id],
        )

    flow_failure = plan_commit.failure
    if plan_commit.accepted:
        assert transition is not None
        task_plan = transition.plan
        try:
            if flow_result.kind == TaskPlanFlowKind.REPLACEMENT:
                state.replace_task_plan(task_plan)
            else:
                state.install_task_plan(task_plan)
        except Exception as exc:
            plan_commit = plan_commit.with_commit_failure(exc)
            flow_failure = plan_commit.failure

    if flow_failure is not None:
        rejection = plan_commit.failure_projection(state_phase=state.phase)
        parent = trace.add(
            rejection.kind,
            rejection.payload,
            parents=[parent.id],
        )
        return TaskPlanPhaseResult(parent=parent, failure=flow_failure)

    if not plan_commit.accepted:
        return TaskPlanPhaseResult(parent=parent)

    assert transition is not None
    task_plan = transition.plan
    committed = TaskPlanCommitStateView(
        active_subgoal=state.activate_next_subgoal(),
        completed_subgoal_ids=(
            tuple(state.plan_progress.completed_subgoal_ids)
            if state.plan_progress is not None
            else ()
        ),
    )
    acceptance = plan_commit.acceptance_projection(
        state_phase=state.phase,
        committed=committed,
    )
    parent = trace.add(acceptance.kind, acceptance.payload, parents=[parent.id])
    parent = recovery_phase.complete_pending_plan_change(
        state,
        trace,
        parent,
        kind=RecoveryKind.REPLAN_TASK,
        plan_or_route_ref=task_plan.plan_id,
    )
    progress_result = progress_phase.commit_current_state(
        task_spec,
        state,
        snapshot,
        budget,
        trace,
        parent,
    )
    return TaskPlanPhaseResult(
        parent=progress_result.parent,
        plan_committed=True,
        current_state_completion_committed=progress_result.completion_committed,
    )
