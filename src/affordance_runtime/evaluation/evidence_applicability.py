"""Deterministic evidence-to-criterion scope and assurance checks."""

from enum import StrEnum

from affordance_runtime.evaluation.contracts import CriterionEvaluation, CriterionEvaluationStatus
from affordance_runtime.evaluation.criterion_contracts import NormalizedCriterionSpec
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.world.source_profile import assurance_satisfies


class EvidenceApplicability(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


def assess_criterion_evidence(
    criterion: NormalizedCriterionSpec,
    evaluation: CriterionEvaluation,
    evidence_index: WorldEvidenceIndex,
) -> EvidenceApplicability:
    if evaluation.criterion_id != criterion.criterion_id:
        return EvidenceApplicability.REJECTED
    if not evaluation.evidence_refs:
        return EvidenceApplicability.UNKNOWN if evaluation.status == CriterionEvaluationStatus.UNKNOWN else EvidenceApplicability.REJECTED
    records = tuple(evidence_index.resolve_record(ref) for ref in evaluation.evidence_refs)
    if any(record is None for record in records):
        return EvidenceApplicability.REJECTED
    if any(not _record_applies(criterion, record) for record in records if record is not None):
        return EvidenceApplicability.REJECTED
    if any(not _status_matches(criterion, evaluation.status, record) for record in records if record is not None):
        return EvidenceApplicability.REJECTED
    return EvidenceApplicability.ACCEPTED


def _record_applies(criterion: NormalizedCriterionSpec, record) -> bool:
    if criterion.required_assurance and not assurance_satisfies(record.source_assurance, criterion.required_assurance):
        return False
    if criterion.evidence_scope_target_ids and record.subject_id not in criterion.evidence_scope_target_ids:
        return False
    if criterion.kind in {"fact_equals", "hybrid"}:
        return record.kind == "fact" and record.predicate == criterion.predicate and (
            not criterion.subject_id or record.subject_id == criterion.subject_id
        )
    if criterion.kind == "target_state_equals":
        return record.kind == "fact" and record.subject_id == criterion.subject_id and record.predicate == criterion.state_key
    if criterion.kind == "artifact_exists":
        return record.kind == "artifact" and record.artifact_kind == criterion.output_id
    if criterion.kind == "semantic_rubric":
        return record.kind in {"fact", "artifact"}
    return criterion.kind == "user_acceptance" and record.kind == "fact"


def _status_matches(criterion: NormalizedCriterionSpec, status: CriterionEvaluationStatus, record) -> bool:
    if criterion.kind in {"fact_equals", "target_state_equals", "hybrid"}:
        equals = record.value == criterion.expected_value
        return equals if status == CriterionEvaluationStatus.SATISFIED else not equals
    if criterion.kind == "artifact_exists":
        return status == CriterionEvaluationStatus.SATISFIED
    return True
