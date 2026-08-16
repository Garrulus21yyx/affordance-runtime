"""Production mechanical action-effect evaluation from current public world state."""

from dataclasses import replace

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    ParameterContractKind,
    VerificationFamily,
)
from affordance_runtime.evaluation.contracts import ActionEvaluation, ActionEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_records import evidence_source_is_current
from affordance_runtime.world import CoverageState
from affordance_runtime.world.evidence_refs import canonical_artifact_ref
from affordance_runtime.world.public_semantic_digest import target_semantics
from affordance_runtime.world.source_profile import assurance_satisfies


class ProductionActionEvaluator:
    """Evaluate fill, select, and activate effects using public before/after evidence."""

    async def evaluate(self, task, before, request, result, after) -> ActionEvaluation:
        del task, result
        definition = INTERACTION_CAPABILITY_REGISTRY.require(
            request.intent.semantic_action
        )
        if VerificationFamily.NAVIGATION_CONTEXT in definition.verification_families:
            return _evaluate_activate(before, request, after)
        if definition.parameter_contract not in {
            ParameterContractKind.TEXT,
            ParameterContractKind.OPTION_VALUE,
        }:
            return _evaluation(request, before, after, ActionEvaluationStatus.UNKNOWN)
        parameter_name = definition.parameter_names[0]
        requested = request.intent.parameters.get(parameter_name)
        if not isinstance(requested, str):
            return _evaluation(request, before, after, ActionEvaluationStatus.UNKNOWN)
        current = _current_value_evidence(after, request.intent.target_id)
        if current is None:
            return _evaluation(request, before, after, ActionEvaluationStatus.UNKNOWN)
        after_value, evidence_ref = current
        before_value = _single_value(before, request.intent.target_id)
        if before_value is _MISSING:
            return _evaluation(request, before, after, ActionEvaluationStatus.UNKNOWN)
        if after_value == requested and before_value != requested:
            status = ActionEvaluationStatus.EFFECT_CONFIRMED
        elif after_value == before_value:
            status = ActionEvaluationStatus.NO_EFFECT_CONFIRMED
        else:
            status = ActionEvaluationStatus.UNKNOWN
        refs = (evidence_ref,) if status != ActionEvaluationStatus.UNKNOWN else ()
        return _evaluation(request, before, after, status, refs)


_MISSING = object()


def _single_value(observation, target_id: str):
    values = tuple(
        fact.value for fact in observation.facts
        if fact.subject_id == target_id and fact.predicate == "value"
    )
    return values[0] if len(values) == 1 else _MISSING


def _current_value_evidence(observation, target_id: str) -> tuple[object, str] | None:
    if target_id not in {item.target_id for item in observation.targets}:
        return None
    if any(
        item.subject_id == target_id and item.predicate == "value"
        for item in observation.conflicts
    ):
        return None
    index = WorldEvidenceIndex.from_observation(observation)
    records = tuple(
        item for item in index.records
        if item.kind == "fact" and item.subject_id == target_id and item.predicate == "value"
    )
    if len(records) != 1:
        return None
    record = records[0]
    source = next(
        (item for item in observation.sources if item.observation_id == record.source_observation_id),
        None,
    )
    if (
        source is None
        or source.coverage != CoverageState.COMPLETE
        or not any(
            item.source_observation_id == source.observation_id
            and item.coverage == CoverageState.COMPLETE
            for item in observation.source_manifest
        )
        or not evidence_source_is_current(record, observation)
        or not assurance_satisfies(record.source_assurance, "structural")
    ):
        return None
    return record.value, record.evidence_ref


def _evaluation(request, before, after, status, refs=()) -> ActionEvaluation:
    reason = {
        ActionEvaluationStatus.EFFECT_CONFIRMED: "public postcondition changed to requested value",
        ActionEvaluationStatus.NO_EFFECT_CONFIRMED: "public postcondition did not change",
        ActionEvaluationStatus.UNKNOWN: "public postcondition is not mechanically resolved",
    }[status]
    evidence: dict[str, object] = {}
    if status in {
        ActionEvaluationStatus.EFFECT_CONFIRMED,
        ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
    }:
        evidence["observed_effect"] = status.value
    changes = _fact_changes(before, after, tuple(refs))
    if changes:
        evidence["fact_changes"] = changes
    return ActionEvaluation(
        request.request_id, before.observation_id, after.observation_id,
        status, reason, tuple(refs), evidence,
    )


def _evaluate_activate(before, request, after) -> ActionEvaluation:
    target_changed = _target_semantics(before, request.intent.target_id) != _target_semantics(
        after, request.intent.target_id,
    )
    target_refs = _changed_target_fact_refs(
        before,
        after,
        request.intent.target_id,
    )
    structural_refs = target_refs or _changed_world_fact_refs(before, after)
    if structural_refs:
        fact_changes = _fact_changes(before, after, structural_refs)
        return ActionEvaluation(
            request.request_id,
            before.observation_id,
            after.observation_id,
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            (
                "public target semantics changed with current structural evidence"
                if target_refs
                else "public structural world facts changed after interaction"
            ),
            structural_refs,
            {
                "verification_profile": (
                    "structural_target_diff_v1"
                    if target_refs
                    else "structural_world_diff_v1"
                ),
                "expected_effects": request.selection.semantic_effects,
                "observed_effect": ActionEvaluationStatus.EFFECT_CONFIRMED.value,
                "target_changed": bool(target_refs),
                "structural_world_changed": True,
                "fact_changes": fact_changes,
            },
        )
    before_digests = _screenshot_digests(before)
    after_digests = _screenshot_digests(after)
    evidence_ref = _screenshot_evidence_ref(after)
    if not before_digests or not after_digests or evidence_ref is None:
        return _evaluation(request, before, after, ActionEvaluationStatus.UNKNOWN)
    screenshot_changed = before_digests != after_digests
    status = (
        ActionEvaluationStatus.EFFECT_CONFIRMED
        if screenshot_changed or target_changed
        else ActionEvaluationStatus.NO_EFFECT_CONFIRMED
    )
    reason = (
        "public screenshot or target semantics changed after activation"
        if status is ActionEvaluationStatus.EFFECT_CONFIRMED
        else "public screenshot and target semantics did not change after activation"
    )
    return ActionEvaluation(
        request.request_id,
        before.observation_id,
        after.observation_id,
        status,
        reason,
        (evidence_ref,),
        {
            "verification_profile": "visual_diff_v1",
            "expected_effects": request.selection.semantic_effects,
            "observed_effect": status.value,
            "screenshot_changed": screenshot_changed,
            "target_changed": target_changed,
        },
    )


def _changed_target_fact_refs(before, after, target_id: str) -> tuple[str, ...]:
    before_values = {
        fact.predicate: fact.value
        for fact in before.facts
        if fact.subject_id == target_id
    }
    if not before_values:
        return ()
    index = WorldEvidenceIndex.from_observation(after)
    refs = tuple(
        record.evidence_ref
        for record in index.records
        if record.kind == "fact"
        and record.subject_id == target_id
        and record.predicate != "focused"
        and record.predicate in before_values
        and record.value != before_values[record.predicate]
        and evidence_source_is_current(record, after)
        and assurance_satisfies(record.source_assurance, "structural")
        and _source_coverage_complete(record.source_observation_id, after)
    )
    return tuple(dict.fromkeys(refs))


def _changed_world_fact_refs(before, after) -> tuple[str, ...]:
    before_values: dict[tuple[str, str], tuple[object, ...]] = {}
    for fact in before.facts:
        before_values.setdefault((fact.subject_id, fact.predicate), ())
        before_values[(fact.subject_id, fact.predicate)] += (fact.value,)
    conflicted = {(item.subject_id, item.predicate) for item in after.conflicts}
    index = WorldEvidenceIndex.from_observation(after)
    refs = tuple(
        record.evidence_ref
        for record in index.records
        if record.kind == "fact"
        and record.predicate != "focused"
        and (record.subject_id, record.predicate) not in conflicted
        and before_values.get((record.subject_id, record.predicate), ()) != (record.value,)
        and evidence_source_is_current(record, after)
        and assurance_satisfies(record.source_assurance, "structural")
        and _source_coverage_complete(record.source_observation_id, after)
    )
    return tuple(dict.fromkeys(refs))


def _fact_changes(before, after, evidence_refs: tuple[str, ...]) -> tuple[dict[str, object], ...]:
    """Describe public fact transitions already proved by current after evidence."""

    index = WorldEvidenceIndex.from_observation(after)
    changes: list[dict[str, object]] = []
    for evidence_ref in evidence_refs:
        record = index.resolve_record(evidence_ref)
        if record is None or record.kind != "fact":
            continue
        before_values = tuple(
            fact.value
            for fact in before.facts
            if fact.subject_id == record.subject_id and fact.predicate == record.predicate
        )
        if before_values == (record.value,):
            continue
        change: dict[str, object] = {
            "subject_id": record.subject_id,
            "predicate": record.predicate,
            "after": record.value,
        }
        if len(before_values) == 1:
            change["before"] = before_values[0]
        else:
            change["before_values"] = before_values
        changes.append(change)
    return tuple(changes)


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


def _screenshot_digests(observation) -> tuple[str, ...]:
    return tuple(sorted({
        media.sha256
        for source in observation.sources
        for media in source.media
        if media.kind == "screenshot"
    }))


def _screenshot_evidence_ref(observation) -> str | None:
    source = next(
        (
            source for source in observation.sources
            if "screenshot_semantic_state" in source.artifacts and source.media
        ),
        None,
    )
    return (
        canonical_artifact_ref(source.observation_id, "screenshot_semantic_state")
        if source is not None
        else None
    )


def _target_semantics(observation, target_id: str):
    target = next((item for item in observation.targets if item.target_id == target_id), None)
    if target is None:
        return None
    state = {key: value for key, value in target.state.items() if key != "focused"}
    return target_semantics(replace(target, state=state))
