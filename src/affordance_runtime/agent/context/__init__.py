"""Agent-owned, provider-neutral context boundary with a cycle-safe lazy facade."""

# ruff: noqa: F401 -- TYPE_CHECKING imports preserve the public facade's static API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from affordance_runtime.agent.context.action_candidate_projection import (
        ActionDeliveryFragment,
        ActionDeliveryPlan,
    )
    from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget
    from affordance_runtime.agent.context.context import (
        AgentContext,
        ContextIdentity,
    )
    from affordance_runtime.agent.context.context_builder import ContextBuilder
    from affordance_runtime.agent.context.contracts import (
        AgentActionOptionView,
        AgentActionPageView,
        AgentActionSpaceView,
        AgentDestinationView,
        AgentMaterialBindingView,
        AgentSuccessCriterionView,
        AgentTaskView,
        AgentTurnView,
    )
    from affordance_runtime.agent.context.failures import (
        ModelFailure,
        ModelFailureKind,
        ProviderAttemptOrigin,
    )
    from affordance_runtime.agent.context.projection import (
        project_action_page,
        project_action_space,
        project_parameter_schema_for_model,
    )
    from affordance_runtime.agent.context.source_projection import (
        ModelSemanticInventoryView,
        ObservationSourceSummary,
    )
    from affordance_runtime.agent.context.task_projection import project_task

_EXPORTS = {
    "ActionDeliveryFragment": (
        "affordance_runtime.agent.context.action_candidate_projection",
        "ActionDeliveryFragment",
    ),
    "ActionDeliveryPlan": (
        "affordance_runtime.agent.context.action_candidate_projection",
        "ActionDeliveryPlan",
    ),
    "AgentActionOptionView": ("affordance_runtime.agent.context.contracts", "AgentActionOptionView"),
    "AgentActionPageView": ("affordance_runtime.agent.context.contracts", "AgentActionPageView"),
    "AgentActionSpaceView": ("affordance_runtime.agent.context.contracts", "AgentActionSpaceView"),
    "AgentContext": ("affordance_runtime.agent.context.context", "AgentContext"),
    "AgentDestinationView": ("affordance_runtime.agent.context.contracts", "AgentDestinationView"),
    "AgentMaterialBindingView": ("affordance_runtime.agent.context.contracts", "AgentMaterialBindingView"),
    "AgentSuccessCriterionView": ("affordance_runtime.agent.context.contracts", "AgentSuccessCriterionView"),
    "AgentTaskView": ("affordance_runtime.agent.context.contracts", "AgentTaskView"),
    "AgentTurnView": ("affordance_runtime.agent.context.contracts", "AgentTurnView"),
    "BoundedSection": ("affordance_runtime.agent.context.budgets", "BoundedSection"),
    "ContextBuilder": ("affordance_runtime.agent.context.context_builder", "ContextBuilder"),
    "ContextIdentity": ("affordance_runtime.agent.context.context", "ContextIdentity"),
    "ContextProjectionBudget": ("affordance_runtime.agent.context.budgets", "ContextProjectionBudget"),
    "ModelFailure": ("affordance_runtime.agent.context.failures", "ModelFailure"),
    "ModelFailureKind": ("affordance_runtime.agent.context.failures", "ModelFailureKind"),
    "ProviderAttemptOrigin": (
        "affordance_runtime.agent.context.failures",
        "ProviderAttemptOrigin",
    ),
    "ModelSemanticInventoryView": (
        "affordance_runtime.agent.context.source_projection",
        "ModelSemanticInventoryView",
    ),
    "ObservationSourceSummary": (
        "affordance_runtime.agent.context.source_projection",
        "ObservationSourceSummary",
    ),
    "project_action_page": ("affordance_runtime.agent.context.projection", "project_action_page"),
    "project_action_space": ("affordance_runtime.agent.context.projection", "project_action_space"),
    "project_parameter_schema_for_model": (
        "affordance_runtime.agent.context.projection",
        "project_parameter_schema_for_model",
    ),
    "project_task": ("affordance_runtime.agent.context.task_projection", "project_task"),
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
