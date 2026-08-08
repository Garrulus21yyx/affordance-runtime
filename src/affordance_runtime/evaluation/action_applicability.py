"""Declared-minimum action-effect evidence applicability."""

from dataclasses import replace

from affordance_runtime.evaluation.action_verification import (
    RuntimeVerificationObligation,
    VerificationObligationKind,
)
from affordance_runtime.evaluation.contracts import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.source_profile import assurance_satisfies


def apply_action_evidence_profile(
    evaluation: ActionEvaluation,
    task,
    request,
    before: WorldObservation,
    after: WorldObservation,
    after_index: WorldEvidenceIndex,
    obligations: tuple[RuntimeVerificationObligation, ...],
) -> ActionEvaluation:
    del task
    if evaluation.status not in {ActionEvaluationStatus.EFFECT_CONFIRMED, ActionEvaluationStatus.NO_EFFECT_CONFIRMED}:
        return evaluation
    records = tuple(after_index.resolve_record(ref) for ref in evaluation.evidence_refs)
    if any(record is None for record in records):
        return _unknown(evaluation, "action evidence is not current")
    if not obligations or not after.sources:
        return _unknown(evaluation, "action verification scope or source profile is unavailable")
    if evaluation.status == ActionEvaluationStatus.EFFECT_CONFIRMED:
        supported = any(_effect_supported(item, records, before) for item in obligations)
        return evaluation if supported else _unknown(evaluation, "current evidence does not satisfy a verification obligation")
    complete = bool(after.coverage) and all(value == CoverageState.COMPLETE for value in after.coverage.values())
    checkable = all(_no_effect_supported(item, records, before) for item in obligations)
    return evaluation if complete and checkable else _unknown(evaluation, "current evidence cannot close every no-effect obligation")


def _before_values(observation: WorldObservation, subject_id: str, predicate: str) -> tuple[object, ...]:
    matches = tuple(fact.value for fact in observation.facts if fact.subject_id == subject_id and fact.predicate == predicate)
    return matches


def _effect_supported(obligation, records, before) -> bool:
    if obligation.kind == VerificationObligationKind.ARTIFACT_CREATED:
        before_kinds = {str(key) for source in before.sources for key in source.artifacts}
        return obligation.output_id not in before_kinds and any(
            item is not None and item.kind == "artifact" and item.artifact_kind == obligation.output_id
            for item in records
        )
    before_values = _before_values(before, obligation.subject_id, obligation.predicate)
    return len(before_values) == 1 and before_values[0] != obligation.expected_value and any(
        item is not None and item.kind == "fact" and item.subject_id == obligation.subject_id
        and item.predicate == obligation.predicate and item.value == obligation.expected_value
        and _assurance(item.source_assurance, obligation.required_assurance)
        for item in records
    )


def _no_effect_supported(obligation, records, before) -> bool:
    if obligation.kind == VerificationObligationKind.ARTIFACT_CREATED:
        return False
    before_values = _before_values(before, obligation.subject_id, obligation.predicate)
    return len(before_values) == 1 and any(
        item is not None and item.kind == "fact" and item.subject_id == obligation.subject_id
        and item.predicate == obligation.predicate and item.value == before_values[0]
        and _assurance(item.source_assurance, obligation.required_assurance or "structural")
        for item in records
    )


def _assurance(actual: str, required: str) -> bool:
    return assurance_satisfies(actual, required) if required else True


def _unknown(evaluation: ActionEvaluation, reason: str) -> ActionEvaluation:
    return replace(evaluation, status=ActionEvaluationStatus.UNKNOWN, reason=reason, evidence_refs=())
