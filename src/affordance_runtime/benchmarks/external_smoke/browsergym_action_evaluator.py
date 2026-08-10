"""Mechanical fill/select effect evaluation from public current world state."""

from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    WorldEvidenceIndex,
)
from affordance_runtime.evaluation.evidence_records import evidence_source_is_current
from affordance_runtime.world import CoverageState
from affordance_runtime.world.source_profile import assurance_satisfies


class BrowserGymMechanicalActionEvaluator:
    async def evaluate(self, task, before, request, result, after) -> ActionEvaluation:
        del task, result
        semantic = request.intent.semantic_action
        requested = request.intent.parameters.get("value")
        if semantic not in {"fill", "select"} or not isinstance(requested, str):
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
        or observation.coverage.get(source.surface) != CoverageState.COMPLETE
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
    return ActionEvaluation(
        request.request_id, before.observation_id, after.observation_id,
        status, reason, tuple(refs),
    )
