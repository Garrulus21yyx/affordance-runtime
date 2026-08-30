"""Declared-minimum action-local evidence applicability."""

from dataclasses import replace

from affordance_runtime.evaluation.contracts import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_records import evidence_source_is_current
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.public_semantic_digest import public_subject_semantics_changed
from affordance_runtime.world.source_profile import assurance_satisfies
from affordance_runtime.world.state_semantics import VALUE_TRUNCATED_STATE_KEY


def apply_action_evidence_profile(
    evaluation: ActionOutcome,
    request,
    before: WorldObservation,
    after: WorldObservation,
    after_index: WorldEvidenceIndex,
) -> ActionOutcome:
    if evaluation.observed_change is ObservedChange.UNKNOWN and (
        evaluation.local_postcondition is LocalPostconditionStatus.UNKNOWN
    ):
        return evaluation
    records = tuple(after_index.resolve_record(ref) for ref in evaluation.evidence_refs)
    if any(record is None or not evidence_source_is_current(record, after) for record in records):
        return _unknown(evaluation, "action evidence is not current")
    method = evaluation.evidence_method
    if method is EvidenceMethod.NONE:
        return evaluation
    if method is EvidenceMethod.VISUAL_DIFF:
        return _apply_visual_profile(evaluation, request, before, after, records)
    if method in {EvidenceMethod.NATIVE, EvidenceMethod.STRUCTURAL}:
        if not after.sources:
            return _unknown(evaluation, "action verification source profile is unavailable")
        if (
            evaluation.observed_change is ObservedChange.UNKNOWN
            and evaluation.local_postcondition
            in {LocalPostconditionStatus.SATISFIED, LocalPostconditionStatus.UNSATISFIED}
        ):
            return (
                evaluation
                if _all_supported_target_value_postcondition(records, evaluation, request, after)
                else _unknown(evaluation, "current evidence does not support the claimed local postcondition")
            )
        if evaluation.observed_change is ObservedChange.CHANGED:
            return (
                evaluation
                if _any_supported_structural_change(records, request, before, after)
                else _unknown(evaluation, "current evidence does not support the claimed local change")
            )
        if evaluation.observed_change is ObservedChange.UNCHANGED:
            return (
                evaluation
                if _all_supported_structural_unchanged(
                    records,
                    evaluation,
                    request,
                    before,
                    after,
                )
                else _unknown(evaluation, "current evidence does not support the claimed local non-change")
            )
        return evaluation
    return _unknown(evaluation, "action verification method is unsupported")


def _any_supported_structural_change(records, request, before, after) -> bool:
    target = next(
        (item for item in after.targets if item.target_id == request.intent.target_id),
        None,
    )
    allow_truncated = bool(target is not None and target.role == "browser_context")
    return any(
        item is not None
        and item.kind == "fact"
        and item.predicate != "focused"
        and evidence_source_is_current(item, after)
        and assurance_satisfies(item.source_assurance, "structural")
        and _source_coverage_admits(
            item.source_observation_id,
            after,
            allow_truncated=(
                allow_truncated
                and item.subject_id == request.intent.target_id
            ) or _is_exact_requested_value(item, request, after),
        )
        and _before_values(before, item.subject_id, item.predicate) != (item.value,)
        for item in records
    )


def _before_values(observation: WorldObservation, subject_id: str, predicate: str) -> tuple[object, ...]:
    return tuple(
        fact.value for fact in observation.facts
        if fact.subject_id == subject_id and fact.predicate == predicate
    )


def _all_supported_target_value_postcondition(records, evaluation, request, after) -> bool:
    requested_values = tuple(request.intent.parameters.values())
    if len(requested_values) != 1 or not isinstance(requested_values[0], str):
        return False
    requested = requested_values[0]
    return bool(records) and all(
        record is not None
        and record.kind == "fact"
        and record.subject_id == request.intent.target_id
        and record.predicate == "value"
        and (
            (record.value == requested)
            == (evaluation.local_postcondition is LocalPostconditionStatus.SATISFIED)
        )
        and evidence_source_is_current(record, after)
        and assurance_satisfies(record.source_assurance, "structural")
        and _source_coverage_admits(
            record.source_observation_id,
            after,
            allow_truncated=(
                evaluation.local_postcondition is LocalPostconditionStatus.SATISFIED
                and _is_exact_requested_value(record, request, after)
            ),
        )
        for record in records
    )


def _all_supported_structural_unchanged(
    records,
    evaluation,
    request,
    before,
    after,
) -> bool:
    return bool(records) and all(
        item is not None
        and item.kind == "fact"
        and evidence_source_is_current(item, after)
        and assurance_satisfies(item.source_assurance, "structural")
        and _source_coverage_admits(
            item.source_observation_id,
            after,
            allow_truncated=(
                evaluation.local_postcondition is LocalPostconditionStatus.SATISFIED
                and _is_exact_requested_value(item, request, after)
            ),
        )
        and _before_values(before, item.subject_id, item.predicate) == (item.value,)
        for item in records
    )


def _is_exact_requested_value(record, request, after) -> bool:
    requested_values = tuple(request.intent.parameters.values())
    return bool(
        len(requested_values) == 1
        and isinstance(requested_values[0], str)
        and record is not None
        and record.kind == "fact"
        and record.subject_id == request.intent.target_id
        and record.predicate == "value"
        and record.value == requested_values[0]
        and not any(
            item.subject_id == request.intent.target_id
            and item.predicate == VALUE_TRUNCATED_STATE_KEY
            and item.value is True
            for item in after.facts
        )
        and not any(
            item.subject_id == request.intent.target_id
            and item.predicate in {"value", VALUE_TRUNCATED_STATE_KEY}
            for item in after.conflicts
        )
    )


def _source_coverage_complete(source_observation_id: str, observation) -> bool:
    return _source_coverage_admits(
        source_observation_id,
        observation,
        allow_truncated=False,
    )


def _source_coverage_admits(
    source_observation_id: str,
    observation,
    *,
    allow_truncated: bool,
) -> bool:
    source = next(
        (item for item in observation.sources if item.observation_id == source_observation_id),
        None,
    )
    admitted = (
        {CoverageState.COMPLETE, CoverageState.TRUNCATED}
        if allow_truncated
        else {CoverageState.COMPLETE}
    )
    return bool(
        source is not None
        and source.coverage in admitted
        and any(
            item.source_observation_id == source.observation_id
            and item.coverage in admitted
            for item in observation.source_manifest
        )
    )


def _unknown(evaluation: ActionOutcome, reason: str) -> ActionOutcome:
    return replace(
        evaluation,
        observed_change=ObservedChange.UNKNOWN,
        local_postcondition=LocalPostconditionStatus.UNKNOWN,
        evidence_method=EvidenceMethod.NONE,
        reason=reason,
        evidence_refs=(),
        evidence={},
    )


def _apply_visual_profile(evaluation, request, before, after, records):
    if not any(
        record is not None
        and record.kind == "artifact"
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
    target_changed = public_subject_semantics_changed(before, after, target_id)
    changed = screenshot_changed or target_changed
    if evaluation.observed_change is ObservedChange.CHANGED and changed:
        return evaluation
    if evaluation.observed_change is ObservedChange.UNCHANGED and not changed:
        return evaluation
    return _unknown(evaluation, "activation evaluation does not match public before/after state")


def _screenshot_digests(observation: WorldObservation) -> tuple[str, ...]:
    return tuple(sorted({
        media.sha256
        for source in observation.sources
        for media in source.media
        if media.kind == "screenshot"
    }))
