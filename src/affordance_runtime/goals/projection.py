"""Direct bounded projection of static GoalPlan guidance."""

from __future__ import annotations

from affordance_runtime.goals.plan import (
    AgentGoalPlanView,
    Failed,
    NotRequired,
    Ready,
    Unsupported,
)


def project_agent_goal_plan(
    resolution: Ready | NotRequired | Failed | Unsupported,
    *,
    max_items: int = 8,
) -> AgentGoalPlanView:
    if max_items < 1:
        raise ValueError("goal plan view bound must be positive")
    if isinstance(resolution, NotRequired):
        return AgentGoalPlanView(resolution.task_revision, "not_required")
    if isinstance(resolution, (Failed, Unsupported)):
        return AgentGoalPlanView(resolution.task_revision, "unavailable")
    plan = resolution.accepted_plan
    return AgentGoalPlanView(
        resolution.task_revision,
        "ready",
        plan.plan_version,
        plan.digest,
        plan.items[:max_items],
    )
