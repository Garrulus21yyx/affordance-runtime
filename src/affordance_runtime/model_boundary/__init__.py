"""Typed, provider-neutral model boundary contracts and projections."""

from affordance_runtime.model_boundary.contracts import (
    AgentActionOptionView,
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
    project_action_space,
    project_parameter_schema_for_model,
    project_plan,
    project_task,
    project_turns,
)

__all__ = [
    "AgentActionOptionView",
    "AgentActionSpaceView",
    "AgentDestinationView",
    "AgentMaterialBindingView",
    "AgentMilestoneView",
    "AgentPlanView",
    "AgentSuccessCriterionView",
    "AgentTaskView",
    "AgentTurnView",
    "ModelFailure",
    "ModelFailureKind",
    "project_action_space",
    "project_parameter_schema_for_model",
    "project_plan",
    "project_task",
    "project_turns",
]
