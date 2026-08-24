from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.actions import ActionBinding, ActionSpaceBuilder
from affordance_runtime.agent.context import ContextBuilder
from affordance_runtime.agent.context.canonical_world_projection import (
    CanonicalPublicWorldProjection,
    PublicGroundingAmbiguousError,
)
from affordance_runtime.agent.context.model_turn_delivery import build_model_turn_delivery
from affordance_runtime.agent.context.observation_paging import ObservationPager
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from affordance_runtime.world.public_refs import PublicRefCodec


def _task() -> TaskGoal:
    return TaskGoal(
        "canonical-world",
        "Activate the requested control",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )


def _binding(source_id: str, revision: str, target_id: str, token: str) -> ActionBinding:
    return ActionBinding(
        f"binding:{token}:{target_id}",
        source_id,
        source_id,
        revision,
        f"fingerprint:{token}:{target_id}",
        target_id,
        target_id,
        "browser",
        "browsergym",
        "activate",
        "click",
        "local_reversible",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"selector": f"private-{token}-{target_id}"},
    )


def _world(token: str, *, reverse: bool = False, duplicate: bool = False):
    source_id = f"source:{token}"
    revision = f"revision:{token}"
    target_ids = (f"target:{token}:alpha", f"target:{token}:beta")
    labels = ("Same", "Same") if duplicate else ("Alpha", "Beta")
    targets = tuple(
        SemanticTarget(target_id, "button", label, {"enabled": True})
        for target_id, label in zip(target_ids, labels, strict=True)
    )
    facts = tuple(
        StateFact(f"fact:{token}:{index}", target_id, "status", "ready", source_id)
        for index, target_id in enumerate(target_ids)
    )
    bindings = tuple(_binding(source_id, revision, target_id, token) for target_id in target_ids)
    if duplicate:
        structure = ()
    else:
        root_id = f"structure:{token}:root"
        child_ids = (f"structure:{token}:alpha", f"structure:{token}:beta")
        structure = (
            ObservationStructureNode(
                root_id,
                "document",
                "Page",
                child_structure_ids=child_ids,
            ),
            ObservationStructureNode(
                child_ids[0], "button", "Alpha", parent_structure_id=root_id,
                semantic_target_id=target_ids[0],
            ),
            ObservationStructureNode(
                child_ids[1], "button", "Beta", parent_structure_id=root_id,
                semantic_target_id=target_ids[1],
            ),
        )
    if reverse:
        targets = tuple(reversed(targets))
        facts = tuple(reversed(facts))
        bindings = tuple(reversed(bindings))
        structure = tuple(reversed(structure))
    fused = WorldFusion().fuse((
        SurfaceObservation(
            source_id,
            "browser",
            revision,
            ObservationSourceProfile.dom(),
            targets,
            facts,
            bindings,
            structure=structure,
            structure_total_count=len(structure),
        ),
    ))
    assert fused.observation is not None
    return fused.observation


def _projection(world):
    actions = ActionSpaceBuilder().build(_task(), world)
    index = WorldDeliveryIndex.from_observation(world, actions.options)
    return CanonicalPublicWorldProjection.build(world, index, actions), actions, index


def _multi_source_world(token: str, *, reverse: bool):
    sources = []
    for ordinal, label in enumerate(("Alpha", "Beta")):
        source_id = f"source:{token}:{ordinal}"
        revision = f"revision:{token}:{ordinal}"
        target_id = f"target:{token}:{ordinal}"
        structure_id = f"structure:{token}:{ordinal}"
        sources.append(SurfaceObservation(
            source_id,
            "browser",
            revision,
            ObservationSourceProfile.dom(),
            (SemanticTarget(target_id, "button", label, {"enabled": True}),),
            (StateFact(f"fact:{token}:{ordinal}", target_id, "status", "ready", source_id),),
            (_binding(source_id, revision, target_id, token),),
            structure=(ObservationStructureNode(
                structure_id, "button", label, semantic_target_id=target_id
            ),),
            structure_total_count=1,
        ))
    fused = WorldFusion().fuse(tuple(reversed(sources)) if reverse else tuple(sources))
    assert fused.observation is not None
    return fused.observation


def _public_records(projection):
    return (
        tuple(to_json_compatible(item.public_value) for item in projection.ordered_target_records),
        tuple(to_json_compatible(item.public_value) for item in projection.ordered_fact_records),
        tuple(to_json_compatible(item.public_value) for item in projection.ordered_region_records),
    )


@given(
    left=st.text(alphabet=st.characters(categories=("Ll", "Nd")), min_size=1, max_size=18),
    right=st.text(alphabet=st.characters(categories=("Ll", "Nd")), min_size=19, max_size=36),
)
def test_private_identity_and_enumeration_permutations_preserve_public_projection(
    left: str,
    right: str,
) -> None:
    first, _first_actions, _first_index = _projection(_world(left))
    second, _second_actions, _second_index = _projection(_world(right, reverse=True))

    assert _public_records(first) == _public_records(second)
    assert first.public_document_signature == second.public_document_signature
    assert tuple(item.ref for item in first.ordered_target_records) == tuple(
        item.ref for item in second.ordered_target_records
    )
    assert tuple(item.ref for item in first.ordered_fact_records) == tuple(
        item.ref for item in second.ordered_fact_records
    )
    assert tuple(item.ref for item in first.ordered_region_records) == tuple(
        item.ref for item in second.ordered_region_records
    )
    first_page = ObservationPager().begin(first, page_size=1, min_exploration_slots=1)
    second_page = ObservationPager().begin(second, page_size=1, min_exploration_slots=1)
    assert tuple(first.target_refs[item] for item in first_page.target_ids) == tuple(
        second.target_refs[item] for item in second_page.target_ids
    )


def test_duplicate_public_facts_preserve_multiplicity_and_unique_refs() -> None:
    world = _world("multiplicity")
    duplicate = replace(
        world.facts[0],
        fact_id="fact:multiplicity:duplicate",
    )
    projection, _actions, _index = _projection(
        replace(world, facts=(*world.facts, duplicate))
    )

    matching = tuple(
        item for item in projection.ordered_fact_records
        if item.predicate == "status" and item.value == "ready"
    )
    assert len(matching) == 3
    assert len({item.ref for item in matching}) == 3


def test_unique_semantic_structure_reuses_target_public_ref() -> None:
    world = _world("structure-alias")
    projection, _actions, _index = _projection(world)
    source = world.sources[0]
    canonical_by_local = {
        item.source_target_id: item.canonical_target_id
        for item in world.entity_source_links
        if item.source_observation_id == source.observation_id
    }

    for node in source.structure:
        structure_ref = projection.private_structure_refs[(source.observation_id, node.structure_id)]
        if node.semantic_target_id:
            assert structure_ref == projection.target_refs[canonical_by_local[node.semantic_target_id]]
        else:
            assert structure_ref not in projection.target_refs.values()


def test_duplicate_semantic_structure_occurrences_keep_unique_refs() -> None:
    source_id = "source:duplicate-structure"
    revision = "revision:duplicate-structure"
    target_id = "target:duplicate-structure"
    source = SurfaceObservation(
        source_id,
        "browser",
        revision,
        ObservationSourceProfile.dom(),
        (SemanticTarget(target_id, "heading", "Repeated"),),
        structure=(
            ObservationStructureNode("first", "heading", "Repeated", semantic_target_id=target_id),
            ObservationStructureNode("second", "heading", "Repeated", semantic_target_id=target_id),
        ),
        structure_total_count=2,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None

    projection, _actions, _index = _projection(fused.observation)

    refs = tuple(
        projection.private_structure_refs[(source_id, structure_id)]
        for structure_id in ("first", "second")
    )
    assert len(set(refs)) == 2


def test_linked_structure_does_not_double_public_reference_capacity(monkeypatch) -> None:
    monkeypatch.setattr(PublicRefCodec, "max_index", 9)
    count = PublicRefCodec.max_index // 2 + 1
    source_id = "source:large-linked-structure"
    revision = "revision:large-linked-structure"
    target_ids = tuple(f"target:{index}" for index in range(count))
    source = SurfaceObservation(
        source_id,
        "browser",
        revision,
        ObservationSourceProfile.dom(),
        tuple(
            SemanticTarget(target_id, "StaticText", f"Item {index}")
            for index, target_id in enumerate(target_ids)
        ),
        structure=tuple(
            ObservationStructureNode(
                f"structure:{index}",
                "StaticText",
                f"Item {index}",
                semantic_target_id=target_id,
            )
            for index, target_id in enumerate(target_ids)
        ),
        structure_total_count=count,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None

    projection, _actions, _index = _projection(fused.observation)

    assert len(projection.ordered_target_records) == count
    assert len(projection.private_structure_refs) == count
    assert set(projection.private_structure_refs.values()) == set(projection.target_refs.values())


def test_source_enumeration_permutation_preserves_public_projection() -> None:
    first_world = _multi_source_world("sources-a", reverse=False)
    second_world = _multi_source_world("sources-b-long", reverse=True)
    first, first_actions, first_index = _projection(first_world)
    second, second_actions, second_index = _projection(second_world)

    assert _public_records(first) == _public_records(second)
    assert first.public_document_signature == second.public_document_signature
    contexts = tuple(
        ContextBuilder().build(
            _task(),
            world,
            actions,
            TaskEvaluation(
                _task().task_id,
                world.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "ongoing",
            ),
            region_index=index,
            canonical_world=projection,
        )
        for world, actions, index, projection in (
            (first_world, first_actions, first_index, first),
            (second_world, second_actions, second_index, second),
        )
    )
    assert to_json_compatible(contexts[0].actor_world) == to_json_compatible(contexts[1].actor_world)


def test_hash_seed_does_not_change_public_projection() -> None:
    code = (
        "import json; "
        "from tests.unit.agent.test_canonical_public_world_projection import "
        "_projection,_public_records,_world; "
        "p=_projection(_world('hash-seed'))[0]; "
        "print(json.dumps((_public_records(p),p.public_document_signature),sort_keys=True))"
    )
    outputs = []
    for seed in ("1", "777"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONPATH"] = "src:."
        outputs.append(subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=os.fspath(Path(__file__).resolve().parents[3]),
            env=environment,
            text=True,
        ))
    assert outputs[0] == outputs[1]


def test_indistinguishable_executable_targets_fail_closed_before_context_or_provider() -> None:
    world = _world("ambiguous", duplicate=True)
    actions = ActionSpaceBuilder().build(_task(), world)
    index = WorldDeliveryIndex.from_observation(world, actions.options)

    with pytest.raises(PublicGroundingAmbiguousError, match="public_grounding_ambiguous"):
        CanonicalPublicWorldProjection.build(world, index, actions)


def test_context_consumers_share_one_supplied_projection_and_create_no_unknown_refs() -> None:
    world = _world("consumer-identity")
    projection, actions, index = _projection(world)
    evaluation = TaskEvaluation(
        _task().task_id,
        world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    context = ContextBuilder().build(
        _task(),
        world,
        actions,
        evaluation,
        region_index=index,
        canonical_world=projection,
    )

    consumer_refs = {
        *(item.ref for item in context.grounding.entities),
        *(item.target_ref for item in context.action_candidates.candidates),
        *(item.region_ref for item in context.action_candidates.candidates),
        *re.findall(
            r"\b[ENFR][1-9][0-9]*\b",
            json.dumps(to_json_compatible(context.actor_world), ensure_ascii=False),
        ),
    }
    assert context.canonical_world is projection
    assert consumer_refs <= projection.public_refs
    assert set(context.private_fact_bindings) <= projection.public_refs
    delivery = build_model_turn_delivery(context, include_images=False)
    assert delivery.manifest.exact_refs <= projection.public_refs
    assert set(delivery.manifest.region_refs) <= projection.public_refs
