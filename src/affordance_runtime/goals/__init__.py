"""Public non-authoritative GoalPlan guidance boundary."""

from affordance_runtime.goals.compiler import (
    GoalCompiler,
    GoalCompilerRequest,
    GoalCompileTrigger,
    GoalPlanBoundary,
    InvalidGoalProposal,
    NotRequiredGoalCompiler,
    TaskSemanticsBoundary,
    UnavailableGoalCompiler,
)
from affordance_runtime.goals.contracts import (
    GoalPredicateValueType,
    GoalSemanticContract,
    merge_goal_semantic_contracts,
)
from affordance_runtime.goals.plan import (
    AgentGoalPlanView,
    Failed,
    GoalCompilerOutcome,
    GoalPlan,
    GoalPlanItem,
    GoalPlanProposal,
    GoalPlanResolution,
    NeedsInput,
    NotRequired,
    Ready,
    Unsupported,
)
from affordance_runtime.goals.projection import project_agent_goal_plan

__all__ = [
    "AgentGoalPlanView",
    "Failed",
    "GoalCompiler",
    "GoalCompilerOutcome",
    "GoalCompilerRequest",
    "GoalCompileTrigger",
    "GoalPlan",
    "GoalPlanBoundary",
    "GoalPlanItem",
    "GoalPlanProposal",
    "GoalPlanResolution",
    "GoalPredicateValueType",
    "GoalSemanticContract",
    "InvalidGoalProposal",
    "NeedsInput",
    "NotRequired",
    "NotRequiredGoalCompiler",
    "Ready",
    "TaskSemanticsBoundary",
    "UnavailableGoalCompiler",
    "Unsupported",
    "merge_goal_semantic_contracts",
    "project_agent_goal_plan",
]
