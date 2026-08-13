"""Runtime routing from semantic evidence obligations to independent providers."""

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
from affordance_runtime.visual_predicate_classification import (
    VisualPredicateClassificationRequest,
)


async def resolve_visual_set_evidence(session) -> bool:
    """Resolve only visual leaves on a frozen, scope-closed candidate universe."""

    classifier = getattr(session.environment, "visual_predicate_classifier", None)
    if classifier is None:
        return False
    sequence = session.state.active_objective_sequence
    if sequence is not None and sequence.selector_resolution is not None:
        return await _resolve_selector_evidence(
            session,
            sequence.selector_resolution,
            lambda resolved: setattr(
                session.state,
                "active_objective_sequence",
                install_sequence_selector_resolution(sequence, resolved),
            ),
        )
    set_state = session.state.active_set_objective
    aggregate_state = session.state.active_aggregate_objective
    if (
        aggregate_state is not None
        and aggregate_state.disposition is AggregateDisposition.NEED_DESTINATION
        and aggregate_state.destination_resolution is not None
    ):
        return await _resolve_aggregate_destination_evidence(
            session,
            aggregate_state,
        )
    state = set_state or aggregate_state
    if state is None or state.universe.coverage is not ScopeCoverage.COMPLETE:
        return False
    predicate = set_state.objective.predicate if set_state is not None else aggregate_state.objective.member_predicate
    leaves = visual_predicate_leaves(predicate)
    if not leaves:
        return False
    media = next(
        (
            media
            for source in session.state.current_observation.sources
            for media in source.media
            if media.kind == "screenshot"
        ),
        None,
    )
    if media is None:
        return False
    regions = {item.target_id: item.bbox for item in media.grounding_regions}
    targets = {item.target_id: item for item in session.state.current_observation.targets}
    attempted = set(session.state.visual_evidence_attempt_keys)
    made_call = False
    try:
        with Image.open(BytesIO(media.data)) as image:
            size = image.size
        for leaf in leaves:
            current = (
                session.state.active_set_objective
                if set_state is not None
                else session.state.active_aggregate_objective
            )
            if current is None:
                break
            leaf_digest = predicate_digest(leaf)
            known_leaf = {(item.entity_id, item.predicate_digest) for item in current.semantic_leaf_assessments}
            unresolved = _unknown_entity_ids(current)
            ids = tuple(
                entity_id
                for entity_id in current.universe.entity_ids
                if entity_id in unresolved
                and (entity_id, leaf_digest) not in known_leaf
                and entity_id in targets
                and entity_id in regions
                and _attempt_key(current.universe.observation_epoch, leaf_digest, entity_id) not in attempted
            )
            for offset in range(0, len(ids), 32):
                batch_ids = ids[offset : offset + 32]
                candidates = tuple(
                    VisualCandidate(
                        f"E{index + 1}",
                        entity_id,
                        targets[entity_id].role,
                        targets[entity_id].label,
                        regions[entity_id],
                        targets[entity_id].state,
                    )
                    for index, entity_id in enumerate(batch_ids)
                )
                if not candidates:
                    continue
                request = VisualPredicateClassificationRequest(
                    f"{current.universe.observation_epoch}:{leaf_digest[:12]}:{offset // 32 + 1}",
                    media.data,
                    size,
                    json.dumps(
                        predicate_public_value(leaf),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ),
                    candidates,
                )
                returned = await asyncio.to_thread(classifier.classify, request)
                by_ref = {item.ref: item for item in returned}
                submitted = tuple((candidate.target_id, by_ref[candidate.ref].truth) for candidate in candidates)
                evaluator_id = (
                    f"{getattr(classifier, 'provider', 'visual')}:{getattr(classifier, 'model', 'classifier')}"
                )
                if isinstance(current, SetObjectiveState):
                    session.state.active_set_objective = install_visual_leaf_assessments(
                        current,
                        session.state.current_observation,
                        leaf,
                        submitted,
                        evaluator_id=evaluator_id,
                    )
                else:
                    assert isinstance(current, AggregateObjectiveState)
                    session.state.active_aggregate_objective = install_aggregate_visual_leaf_assessments(
                        current,
                        session.state.current_observation,
                        leaf,
                        submitted,
                        evaluator_id=evaluator_id,
                        enumerator=session.state.scope_enumerator,
                    )
                for entity_id in batch_ids:
                    attempted.add(_attempt_key(current.universe.observation_epoch, leaf_digest, entity_id))
                made_call = True
                if hasattr(session.environment, "visual_predicate_classifier_calls"):
                    session.environment.visual_predicate_classifier_calls += 1
                if hasattr(session.environment, "visual_predicate_assessment_count"):
                    session.environment.visual_predicate_assessment_count += len(returned)
    except Exception:
        if hasattr(session.environment, "visual_predicate_classification_failure_count"):
            session.environment.visual_predicate_classification_failure_count += 1
        return False
    if not made_call:
        return False
    session.state.visual_evidence_attempt_keys = tuple(sorted(attempted))[-1024:]
    session.state.progress_revision += 1
    return True


def _unknown_entity_ids(state: SetObjectiveState | AggregateObjectiveState) -> set[str]:
    if isinstance(state, SetObjectiveState):
        return {item.entity_id for item in state.assessments if item.truth is PredicateTruth.UNKNOWN}
    return {entity_id for entity_id, truth in state.member_truth if truth is PredicateTruth.UNKNOWN}


def _attempt_key(observation_epoch: str, leaf_digest: str, entity_id: str) -> str:
    return f"{observation_epoch}:{leaf_digest}:{entity_id}"


async def _resolve_selector_evidence(
    session,
    resolution: SelectorResolutionState,
    install,
) -> bool:
    classifier = session.environment.visual_predicate_classifier
    if (
        resolution.universe.coverage is not ScopeCoverage.COMPLETE
        or resolution.disposition is not SelectorResolutionDisposition.NEED_EVIDENCE
    ):
        return False
    leaves = visual_predicate_leaves(resolution.predicate)
    if not leaves:
        return False
    media = next(
        (
            media
            for source in session.state.current_observation.sources
            for media in source.media
            if media.kind == "screenshot"
        ),
        None,
    )
    if media is None:
        return False
    regions = {item.target_id: item.bbox for item in media.grounding_regions}
    targets = {item.target_id: item for item in session.state.current_observation.targets}
    attempted = set(session.state.visual_evidence_attempt_keys)
    with Image.open(BytesIO(media.data)) as image:
        size = image.size
    current = resolution
    made_call = False
    try:
        for leaf in leaves:
            leaf_digest = predicate_digest(leaf)
            known = {(item.entity_id, item.predicate_digest) for item in current.semantic_leaf_assessments}
            ids = tuple(
                entity_id
                for entity_id in current.unknown_entity_ids
                if (entity_id, leaf_digest) not in known
                and entity_id in targets
                and entity_id in regions
                and _attempt_key(
                    current.universe.observation_epoch,
                    leaf_digest,
                    entity_id,
                )
                not in attempted
            )
            for offset in range(0, len(ids), 32):
                batch_ids = ids[offset : offset + 32]
                candidates = tuple(
                    VisualCandidate(
                        f"E{index + 1}",
                        entity_id,
                        targets[entity_id].role,
                        targets[entity_id].label,
                        regions[entity_id],
                        targets[entity_id].state,
                    )
                    for index, entity_id in enumerate(batch_ids)
                )
                if not candidates:
                    continue
                request = VisualPredicateClassificationRequest(
                    f"{current.universe.observation_epoch}:{leaf_digest[:12]}:{offset // 32 + 1}",
                    media.data,
                    size,
                    json.dumps(
                        predicate_public_value(leaf),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ),
                    candidates,
                )
                returned = await asyncio.to_thread(classifier.classify, request)
                by_ref = {item.ref: item for item in returned}
                current = install_selector_visual_leaf_assessments(
                    current,
                    session.state.current_observation,
                    leaf,
                    tuple((candidate.target_id, by_ref[candidate.ref].truth) for candidate in candidates),
                    evaluator_id=(
                        f"{getattr(classifier, 'provider', 'visual')}:{getattr(classifier, 'model', 'classifier')}"
                    ),
                    enumerator=session.state.scope_enumerator,
                )
                for entity_id in batch_ids:
                    attempted.add(
                        _attempt_key(
                            current.universe.observation_epoch,
                            leaf_digest,
                            entity_id,
                        )
                    )
                made_call = True
                _record_classifier_success(session.environment, len(returned))
    except Exception:
        if hasattr(session.environment, "visual_predicate_classification_failure_count"):
            session.environment.visual_predicate_classification_failure_count += 1
        return False
    if not made_call:
        return False
    install(current)
    session.state.visual_evidence_attempt_keys = tuple(sorted(attempted))[-1024:]
    session.state.progress_revision += 1
    return True


async def _resolve_aggregate_destination_evidence(
    session,
    state: AggregateObjectiveState,
) -> bool:
    resolution = state.destination_resolution
    assert resolution is not None
    installed: list[SelectorResolutionState] = []
    resolved = await _resolve_selector_evidence(session, resolution, installed.append)
    if not resolved:
        return False
    current = state
    for assessment_digest in {item.predicate_digest for item in installed[0].semantic_leaf_assessments}:
        leaf = next(
            (
                item
                for item in visual_predicate_leaves(current.objective.destination_selector)
                if predicate_digest(item) == assessment_digest
            ),
            None,
        )
        if leaf is None:
            continue
        same_leaf = tuple(
            (item.entity_id, item.truth)
            for item in installed[0].semantic_leaf_assessments
            if item.predicate_digest == assessment_digest
        )
        current = install_aggregate_destination_visual_leaf_assessments(
            current,
            session.state.current_observation,
            leaf,
            same_leaf,
            evaluator_id=next(
                item.evaluator_id
                for item in installed[0].semantic_leaf_assessments
                if item.predicate_digest == assessment_digest
            ),
            enumerator=session.state.scope_enumerator,
        )
    session.state.active_aggregate_objective = current
    return True


def _record_classifier_success(environment, count: int) -> None:
    if hasattr(environment, "visual_predicate_classifier_calls"):
        environment.visual_predicate_classifier_calls += 1
    if hasattr(environment, "visual_predicate_assessment_count"):
        environment.visual_predicate_assessment_count += count
