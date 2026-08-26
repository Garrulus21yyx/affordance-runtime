"""Stable lazy facade for target task contracts."""

from __future__ import annotations

from importlib import import_module

_MODULE_EXPORTS = {
    "affordance_runtime.task.contracts": {
        "EvaluationSpec", "LoopBudget", "MaterialBinding", "RiskProfile", "TaskGoal",
    },
    "affordance_runtime.task.intent_context": {"IntentContext", "IntentExcerpt", "IntentSourceKind"},
    "affordance_runtime.task.intake": {
        "NaturalLanguageTaskRequest", "ReadyTask", "TaskBoundary", "TaskInputRequired", "TaskIntake",
        "TaskIntakeOutcome", "TaskIntakeStatus", "TaskPolicyRejected", "TaskUnsupported", "ThinTaskIntake",
    },
    "affordance_runtime.task.revision": {
        "RevisionFailed", "RevisionNeedsInput", "RevisionNewTaskSuggested", "RevisionNoChange",
        "RevisionReady", "RevisionUnsupported", "TaskRevisionBoundary", "TaskRevisionCompiler",
        "TaskRevisionCompilerOutcome", "TaskRevisionProposal", "TaskRevisionRequest",
        "UnavailableTaskRevisionCompiler", "revision_outcome_code",
    },
}

_EXPORTS = {name: module for module, names in _MODULE_EXPORTS.items() for name in names}
__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value
