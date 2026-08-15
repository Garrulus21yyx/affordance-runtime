"""Typed, provider-neutral model boundary with a cycle-safe lazy facade."""

# ruff: noqa: F401 -- TYPE_CHECKING imports preserve the public facade's static API.

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from affordance_runtime.model.context.budgets import BoundedSection, ContextProjectionBudget
    from affordance_runtime.model.context.context import (
        AgentBudgetView,
        AgentContext,
        AgentPendingView,
        AgentProgressView,
        ContextIdentity,
        DecisionMode,
        IntentContextView,
    )
    from affordance_runtime.model.context.context_builder import ContextBuilder
    from affordance_runtime.model.context.contracts import (
        AgentActionOptionView,
        AgentActionPageView,
        AgentActionSpaceView,
        AgentDestinationView,
        AgentMaterialBindingView,
        AgentSuccessCriterionView,
        AgentTaskView,
        AgentTurnView,
    )
    from affordance_runtime.model.context.control_feedback_projection import (
        AgentControlFeedbackView,
        project_control_feedback,
    )
    from affordance_runtime.model.context.control_transition_projection import (
        project_control_transitions,
    )
    from affordance_runtime.model.context.failures import (
        ModelFailure,
        ModelFailureKind,
        ProviderAttemptOrigin,
    )
    from affordance_runtime.model.context.projection import (
        project_action_page,
        project_action_space,
        project_parameter_schema_for_model,
        project_turns,
    )
    from affordance_runtime.model.context.source_projection import (
        ModelSemanticInventoryView,
        ObservationSourceSummary,
    )
    from affordance_runtime.model.context.task_projection import project_task
    from affordance_runtime.model.context.transition_digest_projection import (
        AgentTransitionDigestView,
        project_latest_transition,
    )

_EXPORTS = {
    "AgentControlFeedbackView": (
        "affordance_runtime.model.context.control_feedback_projection",
        "AgentControlFeedbackView",
    ),
    "AgentActionOptionView": ("affordance_runtime.model.context.contracts", "AgentActionOptionView"),
    "AgentActionPageView": ("affordance_runtime.model.context.contracts", "AgentActionPageView"),
    "AgentActionSpaceView": ("affordance_runtime.model.context.contracts", "AgentActionSpaceView"),
    "AgentBudgetView": ("affordance_runtime.model.context.context", "AgentBudgetView"),
    "AgentContext": ("affordance_runtime.model.context.context", "AgentContext"),
    "AgentDestinationView": ("affordance_runtime.model.context.contracts", "AgentDestinationView"),
    "AgentMaterialBindingView": ("affordance_runtime.model.context.contracts", "AgentMaterialBindingView"),
    "AgentPendingView": ("affordance_runtime.model.context.context", "AgentPendingView"),
    "AgentProgressView": ("affordance_runtime.model.context.context", "AgentProgressView"),
    "AgentSuccessCriterionView": ("affordance_runtime.model.context.contracts", "AgentSuccessCriterionView"),
    "AgentTaskView": ("affordance_runtime.model.context.contracts", "AgentTaskView"),
    "AgentTransitionDigestView": (
        "affordance_runtime.model.context.transition_digest_projection",
        "AgentTransitionDigestView",
    ),
    "AgentTurnView": ("affordance_runtime.model.context.contracts", "AgentTurnView"),
    "BoundedSection": ("affordance_runtime.model.context.budgets", "BoundedSection"),
    "ContextBuilder": ("affordance_runtime.model.context.context_builder", "ContextBuilder"),
    "ContextIdentity": ("affordance_runtime.model.context.context", "ContextIdentity"),
    "ContextProjectionBudget": ("affordance_runtime.model.context.budgets", "ContextProjectionBudget"),
    "DecisionMode": ("affordance_runtime.model.context.context", "DecisionMode"),
    "IntentContextView": ("affordance_runtime.model.context.context", "IntentContextView"),
    "ModelFailure": ("affordance_runtime.model.context.failures", "ModelFailure"),
    "ModelFailureKind": ("affordance_runtime.model.context.failures", "ModelFailureKind"),
    "ProviderAttemptOrigin": (
        "affordance_runtime.model.context.failures",
        "ProviderAttemptOrigin",
    ),
    "ModelSemanticInventoryView": (
        "affordance_runtime.model.context.source_projection",
        "ModelSemanticInventoryView",
    ),
    "ObservationSourceSummary": (
        "affordance_runtime.model.context.source_projection",
        "ObservationSourceSummary",
    ),
    "project_action_page": ("affordance_runtime.model.context.projection", "project_action_page"),
    "project_action_space": ("affordance_runtime.model.context.projection", "project_action_space"),
    "project_control_transitions": (
        "affordance_runtime.model.context.control_transition_projection",
        "project_control_transitions",
    ),
    "project_control_feedback": (
        "affordance_runtime.model.context.control_feedback_projection",
        "project_control_feedback",
    ),
    "project_parameter_schema_for_model": (
        "affordance_runtime.model.context.projection",
        "project_parameter_schema_for_model",
    ),
    "project_task": ("affordance_runtime.model.context.task_projection", "project_task"),
    "project_latest_transition": (
        "affordance_runtime.model.context.transition_digest_projection",
        "project_latest_transition",
    ),
    "project_turns": ("affordance_runtime.model.context.projection", "project_turns"),
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
