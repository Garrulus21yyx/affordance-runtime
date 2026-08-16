"""Declared-minimum action-effect evidence applicability."""

from dataclasses import replace

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    VerificationFamily,
)
from affordance_runtime.evaluation.action_verification import (
    RuntimeVerificationObligation,
    VerificationObligationKind,
)
from affordance_runtime.evaluation.contracts import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_records import evidence_source_is_current
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.public_semantic_digest import target_semantics
from affordance_runtime.world.source_profile import ObservationAssurance, assurance_satisfies


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
    if any(record is None or not evidence_source_is_current(record, after) for record in records):
        return _unknown(evaluation, "action evidence is not current")
    definition = INTERACTION_CAPABILITY_REGISTRY.require(
        request.intent.semantic_action
    )
    if (
        VerificationFamily.NAVIGATION_CONTEXT in definition.verification_families
        and evaluation.evidence.get("verification_profile") == "visual_diff_v1"
    ):
        return _apply_activate_visual_profile(evaluation, request, before, after, records)
    if not after.sources:
        return _unknown(evaluation, "action verification scope or source profile is unavailable")
    if evaluation.status == ActionEvaluationStatus.EFFECT_CONFIRMED:
        self_supported = _self_supported_structural_effect(
            evaluation,
            records,
            before,
            after,
            request.intent.target_id,
        )
        if (
            evaluation.evidence.get("verification_profile") == "structural_target_diff_v1"
            and self_supported
        ):
            return evaluation
        if not obligations:
            return (
                evaluation
                if self_supported
                else _unknown(evaluation, "action verification scope is unavailable")
            )
        supported = any(_effect_supported(item, records, before, after) for item in obligations)
        return evaluation if supported else _unknown(evaluation, "current evidence does not satisfy a verification obligation")
    if not obligations:
        return _unknown(evaluation, "action verification scope is unavailable")
    complete = bool(after.source_manifest) and all(
        item.coverage == CoverageState.COMPLETE for item in after.source_manifest
    )
    checkable = not _has_relevant_conflict(after, obligations) and all(
        _no_effect_supported(item, records, before, after, after_index) for item in obligations
    )
    return evaluation if complete and checkable else _unknown(evaluation, "current evidence cannot close every no-effect obligation")


def _before_values(observation: WorldObservation, subject_id: str, predicate: str) -> tuple[object, ...]:
    matches = tuple(fact.value for fact in observation.facts if fact.subject_id == subject_id and fact.predicate == predicate)
    return matches


def _effect_supported(obligation, records, before, after) -> bool:
    if obligation.kind == VerificationObligationKind.STRUCTURAL_WORLD_CHANGE:
        return any(
            item is not None
            and item.kind == "fact"
            and item.predicate != "focused"
            and evidence_source_is_current(item, after)
            and _assurance(item.source_assurance, "structural")
            and _source_coverage_complete(item.source_observation_id, after)
            and _before_values(before, item.subject_id, item.predicate) != (item.value,)
            for item in records
        )
    if obligation.kind == VerificationObligationKind.ARTIFACT_CREATED:
        before_kinds = {str(key) for source in before.sources for key in source.artifacts}
        return obligation.output_id not in before_kinds and any(
            item is not None and evidence_source_is_current(item, after)
            and item.kind == "artifact" and item.artifact_kind == obligation.output_id
            for item in records
        )
    before_values = _before_values(before, obligation.subject_id, obligation.predicate)
    return len(before_values) == 1 and before_values[0] != obligation.expected_value and any(
        item is not None and item.kind == "fact" and item.subject_id == obligation.subject_id
        and item.predicate == obligation.predicate and item.value == obligation.expected_value
        and _assurance(item.source_assurance, obligation.required_assurance)
        for item in records
    )


def _self_supported_structural_effect(
    evaluation,
    records,
    before,
    after,
    target_id: str,
) -> bool:
    """Preserve a closed positive structural proof when no task minimum exists."""

    profile = evaluation.evidence.get("verification_profile")
    if profile not in {"structural_target_diff_v1", "structural_world_diff_v1"}:
        return False
    return any(
        item is not None
        and item.kind == "fact"
        and (profile != "structural_target_diff_v1" or item.subject_id == target_id)
        and item.predicate != "focused"
        and evidence_source_is_current(item, after)
        and _assurance(item.source_assurance, "structural")
        and _source_coverage_complete(item.source_observation_id, after)
        and _before_values(before, item.subject_id, item.predicate) != (item.value,)
        for item in records
    )


def _no_effect_supported(obligation, records, before, after, index) -> bool:
    if obligation.kind in {
        VerificationObligationKind.ARTIFACT_CREATED,
        VerificationObligationKind.STRUCTURAL_WORLD_CHANGE,
    }:
        return False
    before_values = _before_values(before, obligation.subject_id, obligation.predicate)
    relevant = tuple(
        item for item in index.records
        if item.kind == "fact" and item.subject_id == obligation.subject_id
        and item.predicate == obligation.predicate and evidence_source_is_current(item, after)
    )
    submitted = {item.evidence_ref for item in records if item is not None}
    values = {repr(item.value) for item in relevant}
    required = no_effect_assurance_floor(obligation.required_assurance)
    return (
        len(before_values) == 1 and bool(relevant) and len(values) == 1
        and all(item.value == before_values[0] for item in relevant)
        and all(item.evidence_ref in submitted for item in relevant)
        and any(_assurance(item.source_assurance, required) for item in relevant)
    )


def no_effect_assurance_floor(required: str) -> ObservationAssurance:
    if not required:
        return ObservationAssurance.STRUCTURAL
    value = ObservationAssurance(required)
    return (
        ObservationAssurance.AUTHORITATIVE
        if value == ObservationAssurance.AUTHORITATIVE
        else ObservationAssurance.STRUCTURAL
    )


def _has_relevant_conflict(after, obligations) -> bool:
    keys = {
        (item.subject_id, item.predicate) for item in obligations
        if item.kind not in {
            VerificationObligationKind.ARTIFACT_CREATED,
            VerificationObligationKind.STRUCTURAL_WORLD_CHANGE,
        }
    }
    return any((item.subject_id, item.predicate) in keys for item in after.conflicts)


def _assurance(actual: str, required: str) -> bool:
    return assurance_satisfies(actual, required) if required else True


def _source_coverage_complete(source_observation_id: str, observation) -> bool:
    source = next(
        (item for item in observation.sources if item.observation_id == source_observation_id),
        None,
    )
    return bool(
        source is not None
        and source.coverage == CoverageState.COMPLETE
        and any(
            item.source_observation_id == source.observation_id
            and item.coverage == CoverageState.COMPLETE
            for item in observation.source_manifest
        )
    )


def _unknown(evaluation: ActionEvaluation, reason: str) -> ActionEvaluation:
    return replace(evaluation, status=ActionEvaluationStatus.UNKNOWN, reason=reason, evidence_refs=())


def _apply_activate_visual_profile(evaluation, request, before, after, records):
    if not any(
        record is not None and record.kind == "artifact"
        and record.artifact_kind == "screenshot_semantic_state"
        for record in records
    ):
        return _unknown(evaluation, "activation requires current screenshot-state evidence")
    before_digests = _screenshot_digests(before)
    after_digests = _screenshot_digests(after)
    if not before_digests or not after_digests:
        return _unknown(evaluation, "activation screenshot state is unavailable")
    target_id = request.intent.target_id
    screenshot_changed = before_digests != after_digests
    target_changed = _target_semantics(before, target_id) != _target_semantics(after, target_id)
    changed = screenshot_changed or target_changed
    if evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED and changed:
        return evaluation
    if evaluation.status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED and not changed:
        return evaluation
    return _unknown(evaluation, "activation evaluation does not match public before/after state")


def _screenshot_digests(observation: WorldObservation) -> tuple[str, ...]:
    return tuple(sorted({
        media.sha256
        for source in observation.sources
        for media in source.media
        if media.kind == "screenshot"
    }))


def _target_semantics(observation: WorldObservation, target_id: str):
    target = next((item for item in observation.targets if item.target_id == target_id), None)
    return None if target is None else target_semantics(target)
