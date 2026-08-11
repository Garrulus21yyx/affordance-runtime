"""Typed, provider-neutral model boundary with a cycle-safe lazy facade."""

# ruff: noqa: F401 -- TYPE_CHECKING imports preserve the public facade's static API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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
    from affordance_runtime.model_boundary.control_transition_projection import (
        project_control_transitions,
    )
    from affordance_runtime.model_boundary.failures import ModelFailure, ModelFailureKind
    from affordance_runtime.model_boundary.projection import (
        project_action_page,
        project_action_space,
        project_parameter_schema_for_model,
        project_plan,
        project_turns,
    )
    from affordance_runtime.model_boundary.source_projection import (
        ModelSemanticInventoryView,
        ObservationSourceSummary,
    )
    from affordance_runtime.model_boundary.task_projection import project_task

_EXPORTS = {
    "AgentActionOptionView": ("affordance_runtime.model_boundary.contracts", "AgentActionOptionView"),
    "AgentActionPageView": ("affordance_runtime.model_boundary.contracts", "AgentActionPageView"),
    "AgentActionSpaceView": ("affordance_runtime.model_boundary.contracts", "AgentActionSpaceView"),
    "AgentBudgetView": ("affordance_runtime.model_boundary.context", "AgentBudgetView"),
    "AgentContext": ("affordance_runtime.model_boundary.context", "AgentContext"),
    "AgentDestinationView": ("affordance_runtime.model_boundary.contracts", "AgentDestinationView"),
    "AgentMaterialBindingView": ("affordance_runtime.model_boundary.contracts", "AgentMaterialBindingView"),
    "AgentMilestoneView": ("affordance_runtime.model_boundary.contracts", "AgentMilestoneView"),
    "AgentPendingView": ("affordance_runtime.model_boundary.context", "AgentPendingView"),
    "AgentPlanView": ("affordance_runtime.model_boundary.contracts", "AgentPlanView"),
    "AgentProgressView": ("affordance_runtime.model_boundary.context", "AgentProgressView"),
    "AgentSuccessCriterionView": ("affordance_runtime.model_boundary.contracts", "AgentSuccessCriterionView"),
    "AgentTaskView": ("affordance_runtime.model_boundary.contracts", "AgentTaskView"),
    "AgentTurnView": ("affordance_runtime.model_boundary.contracts", "AgentTurnView"),
    "BoundedSection": ("affordance_runtime.model_boundary.budgets", "BoundedSection"),
    "ContextBuilder": ("affordance_runtime.model_boundary.context_builder", "ContextBuilder"),
    "ContextIdentity": ("affordance_runtime.model_boundary.context", "ContextIdentity"),
    "ContextProjectionBudget": ("affordance_runtime.model_boundary.budgets", "ContextProjectionBudget"),
    "DecisionMode": ("affordance_runtime.model_boundary.context", "DecisionMode"),
    "IntentContextView": ("affordance_runtime.model_boundary.context", "IntentContextView"),
    "ModelFailure": ("affordance_runtime.model_boundary.failures", "ModelFailure"),
    "ModelFailureKind": ("affordance_runtime.model_boundary.failures", "ModelFailureKind"),
    "ModelSemanticInventoryView": (
        "affordance_runtime.model_boundary.source_projection",
        "ModelSemanticInventoryView",
    ),
    "ObservationSourceSummary": (
        "affordance_runtime.model_boundary.source_projection",
        "ObservationSourceSummary",
    ),
    "project_action_page": ("affordance_runtime.model_boundary.projection", "project_action_page"),
    "project_action_space": ("affordance_runtime.model_boundary.projection", "project_action_space"),
    "project_control_transitions": (
        "affordance_runtime.model_boundary.control_transition_projection",
        "project_control_transitions",
    ),
    "project_parameter_schema_for_model": (
        "affordance_runtime.model_boundary.projection",
        "project_parameter_schema_for_model",
    ),
    "project_plan": ("affordance_runtime.model_boundary.projection", "project_plan"),
    "project_task": ("affordance_runtime.model_boundary.task_projection", "project_task"),
    "project_turns": ("affordance_runtime.model_boundary.projection", "project_turns"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
