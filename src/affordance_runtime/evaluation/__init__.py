"""Independent action and task evaluation contracts."""

from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.evaluation.contracts import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    EvaluatedOutput,
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_records import EvidenceRecord

__all__ = [
    "ActionEvaluation",
    "ActionEvaluationStatus",
    "CriterionEvaluation",
    "CriterionEvaluationStatus",
    "EvaluatedOutput",
    "EvidenceRecord",
    "ProductionTaskEvaluator",
    "TaskEvaluation",
    "TaskEvaluationStatus",
    "TaskOutcomeFact",
    "TaskOutcomeKind",
    "WorldEvidenceIndex",
]
