"""Independent action and task evaluation contracts."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ProductionActionEvaluator": (
        "affordance_runtime.evaluation.action_evaluator",
        "ProductionActionEvaluator",
    ),
    "ProductionTaskEvaluator": (
        "affordance_runtime.evaluation.composition",
        "ProductionTaskEvaluator",
    ),
    "WorldEvidenceIndex": (
        "affordance_runtime.evaluation.evidence",
        "WorldEvidenceIndex",
    ),
    "EvidenceRecord": (
        "affordance_runtime.evaluation.evidence_records",
        "EvidenceRecord",
    ),
}

for _name in (
    "ActionEvaluation",
    "ActionEvaluationStatus",
    "CriterionEvaluation",
    "CriterionEvaluationStatus",
    "EvaluatedOutput",
    "EvaluationOutcome",
    "EvaluationInterruption",
    "EvaluationInterruptionReason",
    "TaskEvaluation",
    "TaskEvaluationStatus",
    "TaskOutcomeFact",
    "TaskOutcomeKind",
):
    _EXPORTS[_name] = ("affordance_runtime.evaluation.contracts", _name)

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
