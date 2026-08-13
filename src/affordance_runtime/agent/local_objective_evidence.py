"""Route local-objective evidence obligations to source-specific providers."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO

from PIL import Image

from affordance_runtime.task.aggregate_objective import (
    AggregateDisposition,
    AggregateObjectiveState,
    install_aggregate_destination_visual_leaf_assessments,
    install_aggregate_visual_leaf_assessments,
)
from affordance_runtime.task.objective_sequence import (
    ObjectiveSequenceState,
    install_sequence_selector_resolution,
)
from affordance_runtime.task.selector_resolution import (
    SelectorResolutionDisposition,
    SelectorResolutionState,
    install_selector_visual_leaf_assessments,
)
from affordance_runtime.task.set_objective import (
    PredicateTruth,
    ScopeCoverage,
    predicate_digest,
    predicate_public_value,
    visual_predicate_leaves,
)
from affordance_runtime.task.set_objective_state import (
    SetObjectiveState,
    install_visual_leaf_assessments,
)
from affordance_runtime.visual_disambiguation import VisualCandidate
from affordance_runtime.visual_predicate_classification import VisualPredicateClassificationRequest


async def resolve_visual_local_objective_evidence(session) -> bool:
    """Resolve visual leaves without giving the provider scope or action authority."""

    classifier = getattr(session.environment, "visual_predicate_classifier", None)
    if classifier is None:
        return False
    execution = session.state.local_objective_state
    if isinstance(execution, ObjectiveSequenceState) and execution.selector_resolution is not None:
        return await _resolve_selector(
            session,
            execution.selector_resolution,
            lambda resolved: setattr(
                session.state,
                "local_objective_state",
                install_sequence_selector_resolution(execution, resolved),
            ),
        )
    if (
        isinstance(execution, AggregateObjectiveState)
        and execution.disposition is AggregateDisposition.NEED_DESTINATION
        and execution.destination_resolution is not None
    ):
        return await _resolve_aggregate_destination(session, execution)
    if not isinstance(execution, SetObjectiveState | AggregateObjectiveState):
        return False
    if execution.universe.coverage is not ScopeCoverage.COMPLETE:
        return False
    predicate = (
        execution.objective.predicate
        if isinstance(execution, SetObjectiveState)
        else execution.objective.member_predicate
    )
    leaves = visual_predicate_leaves(predicate)
    frame = _visual_frame(session)
    if not leaves or frame is None:
        return False
    media, size, regions, targets = frame
    attempted = set(session.state.visual_evidence_attempt_keys)
    made_call = False
    try:
        for leaf in leaves:
            current = session.state.local_objective_state
            if not isinstance(current, SetObjectiveState | AggregateObjectiveState):
                break
            leaf_digest = predicate_digest(leaf)
            known = {(item.entity_id, item.predicate_digest) for item in current.semantic_leaf_assessments}
            unknown = _unknown_entity_ids(current)
            entity_ids = tuple(
                entity_id
                for entity_id in current.universe.entity_ids
                if entity_id in unknown
                and (entity_id, leaf_digest) not in known
                and entity_id in targets
                and entity_id in regions
                and _attempt_key(current.universe.observation_epoch, leaf_digest, entity_id) not in attempted
            )
            for offset in range(0, len(entity_ids), 32):
                batch = entity_ids[offset : offset + 32]
                candidates = _candidates(batch, targets, regions)
                if not candidates:
                    continue
                returned = await asyncio.to_thread(
                    classifier.classify,
                    _request(current.universe.observation_epoch, leaf, offset, media.data, size, candidates),
                )
                by_ref = {item.ref: item for item in returned}
                assessments = tuple((item.target_id, by_ref[item.ref].truth) for item in candidates)
                evaluator_id = _evaluator_id(classifier)
                if isinstance(current, SetObjectiveState):
                    session.state.local_objective_state = install_visual_leaf_assessments(
                        current,
                        session.state.current_observation,
                        leaf,
                        assessments,
                        evaluator_id=evaluator_id,
                    )
                else:
                    session.state.local_objective_state = install_aggregate_visual_leaf_assessments(
                        current,
                        session.state.current_observation,
                        leaf,
                        assessments,
                        evaluator_id=evaluator_id,
                        enumerator=session.state.scope_enumerator,
                    )
                attempted.update(
                    _attempt_key(current.universe.observation_epoch, leaf_digest, entity_id)
                    for entity_id in batch
                )
                made_call = True
                _record_success(session.environment, len(returned))
    except Exception:
        _record_failure(session.environment)
        return False
    return _commit_attempts(session, attempted) if made_call else False


async def _resolve_selector(session, resolution: SelectorResolutionState, install) -> bool:
    if (
        resolution.universe.coverage is not ScopeCoverage.COMPLETE
        or resolution.disposition is not SelectorResolutionDisposition.NEED_EVIDENCE
    ):
        return False
    leaves = visual_predicate_leaves(resolution.predicate)
    frame = _visual_frame(session)
    if not leaves or frame is None:
        return False
    media, size, regions, targets = frame
    attempted = set(session.state.visual_evidence_attempt_keys)
    current = resolution
    made_call = False
    try:
        for leaf in leaves:
            leaf_digest = predicate_digest(leaf)
            known = {(item.entity_id, item.predicate_digest) for item in current.semantic_leaf_assessments}
            entity_ids = tuple(
                entity_id
                for entity_id in current.unknown_entity_ids
                if (entity_id, leaf_digest) not in known
                and entity_id in targets
                and entity_id in regions
                and _attempt_key(current.universe.observation_epoch, leaf_digest, entity_id) not in attempted
            )
            for offset in range(0, len(entity_ids), 32):
                batch = entity_ids[offset : offset + 32]
                candidates = _candidates(batch, targets, regions)
                if not candidates:
                    continue
                returned = await asyncio.to_thread(
                    session.environment.visual_predicate_classifier.classify,
                    _request(current.universe.observation_epoch, leaf, offset, media.data, size, candidates),
                )
                by_ref = {item.ref: item for item in returned}
                current = install_selector_visual_leaf_assessments(
                    current,
                    session.state.current_observation,
                    leaf,
                    tuple((item.target_id, by_ref[item.ref].truth) for item in candidates),
                    evaluator_id=_evaluator_id(session.environment.visual_predicate_classifier),
                    enumerator=session.state.scope_enumerator,
                )
                attempted.update(
                    _attempt_key(current.universe.observation_epoch, leaf_digest, entity_id)
                    for entity_id in batch
                )
                made_call = True
                _record_success(session.environment, len(returned))
    except Exception:
        _record_failure(session.environment)
        return False
    if not made_call:
        return False
    install(current)
    return _commit_attempts(session, attempted)


async def _resolve_aggregate_destination(session, state: AggregateObjectiveState) -> bool:
    installed: list[SelectorResolutionState] = []
    assert state.destination_resolution is not None
    if not await _resolve_selector(session, state.destination_resolution, installed.append):
        return False
    current = state
    for leaf in visual_predicate_leaves(current.objective.destination_selector):
        digest = predicate_digest(leaf)
        assessments = tuple(
            (item.entity_id, item.truth)
            for item in installed[0].semantic_leaf_assessments
            if item.predicate_digest == digest
        )
        if not assessments:
            continue
        current = install_aggregate_destination_visual_leaf_assessments(
            current,
            session.state.current_observation,
            leaf,
            assessments,
            evaluator_id=next(
                item.evaluator_id
                for item in installed[0].semantic_leaf_assessments
                if item.predicate_digest == digest
            ),
            enumerator=session.state.scope_enumerator,
        )
    session.state.local_objective_state = current
    return True


def _visual_frame(session):
    media = next(
        (
            item
            for source in session.state.current_observation.sources
            for item in source.media
            if item.kind == "screenshot"
        ),
        None,
    )
    if media is None:
        return None
    with Image.open(BytesIO(media.data)) as image:
        size = image.size
    return (
        media,
        size,
        {item.target_id: item.bbox for item in media.grounding_regions},
        {item.target_id: item for item in session.state.current_observation.targets},
    )


def _candidates(entity_ids, targets, regions):
    return tuple(
        VisualCandidate(
            f"E{index + 1}",
            entity_id,
            targets[entity_id].role,
            targets[entity_id].label,
            regions[entity_id],
            targets[entity_id].state,
        )
        for index, entity_id in enumerate(entity_ids)
    )


def _request(epoch, leaf, offset, screenshot, size, candidates):
    digest = predicate_digest(leaf)
    return VisualPredicateClassificationRequest(
        f"{epoch}:{digest[:12]}:{offset // 32 + 1}",
        screenshot,
        size,
        json.dumps(predicate_public_value(leaf), sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        candidates,
    )


def _unknown_entity_ids(state):
    if isinstance(state, SetObjectiveState):
        return {item.entity_id for item in state.assessments if item.truth is PredicateTruth.UNKNOWN}
    return {entity_id for entity_id, truth in state.member_truth if truth is PredicateTruth.UNKNOWN}


def _attempt_key(epoch, leaf_digest, entity_id):
    return f"{epoch}:{leaf_digest}:{entity_id}"


def _evaluator_id(classifier):
    return f"{getattr(classifier, 'provider', 'visual')}:{getattr(classifier, 'model', 'classifier')}"


def _record_success(environment, count):
    if hasattr(environment, "visual_predicate_classifier_calls"):
        environment.visual_predicate_classifier_calls += 1
    if hasattr(environment, "visual_predicate_assessment_count"):
        environment.visual_predicate_assessment_count += count


def _record_failure(environment):
    if hasattr(environment, "visual_predicate_classification_failure_count"):
        environment.visual_predicate_classification_failure_count += 1


def _commit_attempts(session, attempted):
    session.state.visual_evidence_attempt_keys = tuple(sorted(attempted))[-1024:]
    session.state.progress_revision += 1
    return True
