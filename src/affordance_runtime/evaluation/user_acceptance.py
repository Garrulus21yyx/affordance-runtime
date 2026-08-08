"""Explicit authoritative user-evidence criterion profile."""

from dataclasses import dataclass

from affordance_runtime.evaluation.contracts import CriterionEvaluation, CriterionEvaluationStatus
from affordance_runtime.evaluation.criterion_contracts import NormalizedCriterionSpec
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex


@dataclass(frozen=True)
class UserAcceptanceCriterionEvaluator:
    def evaluate(self, criterion: NormalizedCriterionSpec, evidence_index: WorldEvidenceIndex) -> CriterionEvaluation:
        subject = criterion.subject_id or criterion.criterion_id
        matches = tuple(
            record for record in evidence_index.records
            if record.kind == "fact" and record.source_modality == "user"
            and record.source_assurance == "authoritative" and record.subject_id == subject
            and record.predicate == "accepted" and type(record.value) is bool
        )
        if len(matches) != 1:
            return CriterionEvaluation(criterion.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), "explicit user acceptance is unavailable")
        record = matches[0]
        status = CriterionEvaluationStatus.SATISFIED if record.value else CriterionEvaluationStatus.UNSATISFIED
        return CriterionEvaluation(criterion.criterion_id, status, (record.evidence_ref,), "explicit user acceptance evaluated")
