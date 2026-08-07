"""Typed policy deciding whether an accepted TaskPlan is reused or replaced."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import TaskSpec


class TaskPlanningTriggerKind(StrEnum):
    INITIAL = "initial"
    REUSE_ACTIVE_PLAN = "reuse_active_plan"
    REPLAN_EXHAUSTED = "replan_exhausted"
    REPLAN_STEP_INFEASIBLE = "replan_step_infeasible"
    REPLAN_ASSUMPTION_DISPROVED = "replan_assumption_disproved"
    REPLAN_ENVIRONMENT_BOUNDARY = "replan_environment_boundary"
    REPLAN_TASK_REVISION = "replan_task_revision"


@dataclass(frozen=True)
class TaskPlanningTrigger:
    kind: TaskPlanningTriggerKind
    step_id: str = ""
    detail: str = ""

    @property
    def requires_planner(self) -> bool:
        return self.kind != TaskPlanningTriggerKind.REUSE_ACTIVE_PLAN


def evaluate_task_planning_trigger(
    task_spec: TaskSpec,
    state: StateKernel,
) -> TaskPlanningTrigger:
    """Inspect typed state only; observation epoch freshness is intentionally irrelevant."""

    plan = state.task_plan
    progress = state.task_progress
    if plan is None or progress is None:
        return TaskPlanningTrigger(TaskPlanningTriggerKind.INITIAL)
    if plan.task_revision != task_spec.revision:
        return TaskPlanningTrigger(
            TaskPlanningTriggerKind.REPLAN_TASK_REVISION,
            progress.active_step_id,
            "task revision changed",
        )
    if state.current_disproved_assumption and any(
        assumption in state.current_disproved_assumption or state.current_disproved_assumption in assumption
        for assumption in plan.assumptions
    ):
        return TaskPlanningTrigger(
            TaskPlanningTriggerKind.REPLAN_ASSUMPTION_DISPROVED,
            progress.active_step_id,
            state.current_disproved_assumption,
        )
    failure = state.current_failure
    if failure is not None and failure.error_code == "environment_boundary_changed":
        return TaskPlanningTrigger(
            TaskPlanningTriggerKind.REPLAN_ENVIRONMENT_BOUNDARY,
            progress.active_step_id,
            failure.message,
        )
    if progress.active_step_id:
        if progress.action_budget_exhausted(plan):
            return TaskPlanningTrigger(
                TaskPlanningTriggerKind.REPLAN_STEP_INFEASIBLE,
                progress.active_step_id,
                "active step action budget exhausted",
            )
        return TaskPlanningTrigger(
            TaskPlanningTriggerKind.REUSE_ACTIVE_PLAN,
            progress.active_step_id,
        )
    completed = set(progress.completed_step_ids)
    if all(step.step_id in completed for step in plan.steps):
        return TaskPlanningTrigger(
            TaskPlanningTriggerKind.REPLAN_EXHAUSTED,
            detail="accepted plan exhausted while task remains incomplete",
        )
    ready = progress.ready_step_ids(plan)
    if ready:
        return TaskPlanningTrigger(TaskPlanningTriggerKind.REUSE_ACTIVE_PLAN, ready[0])
    return TaskPlanningTrigger(
        TaskPlanningTriggerKind.REPLAN_STEP_INFEASIBLE,
        detail="no active or dependency-ready step remains",
    )
