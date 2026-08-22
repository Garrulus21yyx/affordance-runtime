"""Deterministic milestone projection into the existing GoalPlan view."""

from __future__ import annotations

from affordance_runtime.goals.plan import GoalPlan, GoalPlanItem, Ready
from affordance_runtime.mission.contracts import Milestone
from affordance_runtime.task.contracts import TaskGoal


def milestone_goal_resolution(
    task: TaskGoal,
    contract: Milestone,
    *,
    plan_version: int = 1,
) -> Ready:
    """Project one bounded milestone into one non-authoritative GoalPlan item."""

    return Ready(
        task.revision,
        GoalPlan(
            task.revision,
            plan_version,
            (
                GoalPlanItem(
                    contract.id,
                    contract.outcome,
                    contract.done_when,
                    (),
                    contract.final,
                ),
            ),
        ),
    )
