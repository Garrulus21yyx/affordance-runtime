"""Finite deterministic mechanical criterion evaluation."""

from dataclasses import dataclass

from affordance_runtime.evaluation.contracts import CriterionEvaluation, CriterionEvaluationStatus
from affordance_runtime.evaluation.criterion_contracts import CriterionAdjudicator, NormalizedCriterionSpec
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_records import evidence_source_is_current
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.source_profile import assurance_satisfies


@dataclass(frozen=True)
class MechanicalCriterionEvaluator:
    def evaluate(self, criterion: NormalizedCriterionSpec, observation: WorldObservation) -> CriterionEvaluation:
        if criterion.adjudicator not in {CriterionAdjudicator.MECHANICAL, CriterionAdjudicator.HYBRID}:
            return _unknown(criterion, "criterion is not mechanical")
        index = WorldEvidenceIndex.from_observation(observation)
        if criterion.kind in {"fact_equals", "target_state_equals", "hybrid"}:
            return _fact_equals(criterion, observation, index)
        if criterion.kind == "artifact_exists":
            matches = tuple(
                record for record in index.records
                if record.kind == "artifact" and record.artifact_kind == criterion.output_id
                and evidence_source_is_current(record, observation)
            )
            if len(matches) == 1:
                return CriterionEvaluation(criterion.criterion_id, CriterionEvaluationStatus.SATISFIED, (matches[0].evidence_ref,), "current artifact exists")
            return _unknown(criterion, "artifact presence is not established")
        return _unknown(criterion, "mechanical criterion kind is unsupported")


def _fact_equals(criterion, observation, index) -> CriterionEvaluation:
    predicate = criterion.state_key if criterion.kind == "target_state_equals" else criterion.predicate
    matches = tuple(
        record for record in index.records
        if record.kind == "fact" and evidence_source_is_current(record, observation)
        and record.predicate == predicate and (
            not criterion.subject_id or record.subject_id == criterion.subject_id
        )
    )
    conflict = any(
        item.predicate == predicate and (not criterion.subject_id or item.subject_id == criterion.subject_id)
        for item in observation.conflicts
    )
    if conflict or len(matches) != 1:
        return _unknown(criterion, "current fact evidence is ambiguous or conflicting")
    record = matches[0]
    if criterion.required_assurance and not assurance_satisfies(record.source_assurance, criterion.required_assurance):
        return _unknown(criterion, "current fact assurance is insufficient")
    status = CriterionEvaluationStatus.SATISFIED if record.value == criterion.expected_value else CriterionEvaluationStatus.UNSATISFIED
    if status == CriterionEvaluationStatus.UNSATISFIED and (
        not _coverage_complete(observation) or not assurance_satisfies(record.source_assurance, "structural")
    ):
        return _unknown(criterion, "current evidence cannot prove inequality")
    return CriterionEvaluation(criterion.criterion_id, status, (record.evidence_ref,), "current fact compared with expected value")


def _coverage_complete(observation: WorldObservation) -> bool:
    return bool(observation.coverage) and all(value == CoverageState.COMPLETE for value in observation.coverage.values())


def _unknown(criterion, reason: str) -> CriterionEvaluation:
    return CriterionEvaluation(criterion.criterion_id, CriterionEvaluationStatus.UNKNOWN, (), reason)
