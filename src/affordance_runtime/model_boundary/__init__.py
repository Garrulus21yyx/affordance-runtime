"""Typed, provider-neutral model boundary contracts and projections."""

from affordance_runtime.model_boundary.budgets import BoundedSection, ContextProjectionBudget
from affordance_runtime.model_boundary.context import (
    AgentBudgetView,
    AgentContext,
    AgentPendingView,
    AgentProgressView,
    ContextIdentity,
    DecisionMode,
    IntentContextView,
)
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.model_boundary.contracts import (
    AgentActionOptionView,
    AgentActionPageView,
    AgentActionSpaceView,
    AgentDestinationView,
    AgentMaterialBindingView,
    AgentMilestoneView,
    AgentPlanView,
    AgentSuccessCriterionView,
    AgentTaskView,
    AgentTurnView,
)
from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
from affordance_runtime.model_boundary.projection import (
    project_action_page,
    project_action_space,
    project_parameter_schema_for_model,
    project_plan,
    project_task,
    project_turns,
)

__all__ = [
    "AgentActionOptionView",
    "AgentActionPageView",
    "AgentActionSpaceView",
    "AgentDestinationView",
    "AgentMaterialBindingView",
    "AgentMilestoneView",
    "AgentPlanView",
    "AgentSuccessCriterionView",
    "AgentTaskView",
    "AgentTurnView",
    "AgentBudgetView",
    "AgentContext",
    "AgentPendingView",
    "AgentProgressView",
    "BoundedSection",
    "ContextBuilder",
    "ContextIdentity",
    "ContextProjectionBudget",
    "DecisionMode",
    "IntentContextView",
    "ModelFailure",
    "ModelFailureKind",
    "project_action_space",
    "project_action_page",
    "project_parameter_schema_for_model",
    "project_plan",
    "project_task",
    "project_turns",
]
