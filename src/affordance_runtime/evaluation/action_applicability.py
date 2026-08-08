"""Declared-minimum action-effect evidence applicability."""

from dataclasses import replace

from affordance_runtime.evaluation.contracts import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.source_profile import assurance_satisfies


def apply_action_evidence_profile(
    evaluation: ActionEvaluation,
    request,
    before: WorldObservation,
    after: WorldObservation,
    after_index: WorldEvidenceIndex,
) -> ActionEvaluation:
    if evaluation.status not in {ActionEvaluationStatus.EFFECT_CONFIRMED, ActionEvaluationStatus.NO_EFFECT_CONFIRMED}:
        return evaluation
    records = tuple(after_index.resolve_record(ref) for ref in evaluation.evidence_refs)
    subjects = {request.intent.target_id, request.intent.destination_id} - {""}
    if any(record is None for record in records):
        return _unknown(evaluation, "action evidence is not current")
    fact_records = tuple(record for record in records if record is not None and record.kind == "fact" and record.subject_id in subjects)
    if evaluation.status == ActionEvaluationStatus.EFFECT_CONFIRMED:
        changed = any(_changed_from_before(before, item.subject_id, item.predicate, item.value) for item in fact_records)
        artifact_created = any(_artifact_created(before, item, request) for item in records if item is not None)
        if not changed and not artifact_created:
            return _unknown(evaluation, "current evidence does not prove a relevant state transition")
        return evaluation
    strong_unchanged = any(
        _unchanged_from_before(before, item.subject_id, item.predicate, item.value)
        and assurance_satisfies(item.source_assurance, "structural")
        for item in fact_records
    )
    complete = bool(after.coverage) and all(value == CoverageState.COMPLETE for value in after.coverage.values())
    return evaluation if strong_unchanged and complete else _unknown(evaluation, "current evidence cannot prove no effect")


def _before_values(observation: WorldObservation, subject_id: str, predicate: str) -> tuple[object, ...]:
    matches = tuple(fact.value for fact in observation.facts if fact.subject_id == subject_id and fact.predicate == predicate)
    return matches


def _changed_from_before(observation: WorldObservation, subject_id: str, predicate: str, value: object) -> bool:
    values = _before_values(observation, subject_id, predicate)
    return len(values) == 1 and values[0] != value


def _unchanged_from_before(observation: WorldObservation, subject_id: str, predicate: str, value: object) -> bool:
    values = _before_values(observation, subject_id, predicate)
    return len(values) == 1 and values[0] == value


def _artifact_created(before: WorldObservation, record, request) -> bool:
    if record.kind != "artifact":
        return False
    expected = request.intent.expected_outcome.get("output_id") or request.intent.expected_outcome.get("artifact_kind")
    before_kinds = {str(key) for source in before.sources for key in source.artifacts}
    return expected == record.artifact_kind and record.artifact_kind not in before_kinds


def _unknown(evaluation: ActionEvaluation, reason: str) -> ActionEvaluation:
    return replace(evaluation, status=ActionEvaluationStatus.UNKNOWN, reason=reason, evidence_refs=())
