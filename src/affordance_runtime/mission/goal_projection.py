"""Deterministic subtask projection into the existing GoalPlan view."""

from __future__ import annotations

from affordance_runtime.goals.plan import GoalPlan, GoalPlanItem, Ready
from affordance_runtime.mission.contracts import SubtaskContract
from affordance_runtime.task.contracts import TaskGoal


def subtask_goal_resolution(
    task: TaskGoal,
    contract: SubtaskContract,
    *,
    plan_version: int = 1,
) -> Ready:
    """Project one bounded subtask into one non-authoritative GoalPlan item."""

    return Ready(
        task.revision,
        GoalPlan(
            task.revision,
            plan_version,
            (
                GoalPlanItem(
                    "active_subtask",
                    contract.objective,
                    contract.done_when,
                    (),
                    False,
                ),
            ),
        ),
    )
