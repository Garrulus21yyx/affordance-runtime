from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from affordance_runtime.agent.context.observation_delivery import (
    ObservationDeliveryStore,
    PublicEffectProjector,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import (
    PublicChangeKind,
    WorldTransitionProjector,
)
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.canonical_world import canonical_world


def _world(
    observation_id: str,
    *,
    target_id: str = "target:item",
    fact_values: tuple[str, ...] = ("one",),
    state_value: str = "ready",
    extra_target: bool = False,
):
    source_id = f"browsergym-observation:{observation_id}:987654"
    target = SemanticTarget(target_id, "button", "Go", {"status": state_value})
    targets = (
        target,
        *( (SemanticTarget(f"extra:{observation_id}", "button", "Extra"),) if extra_target else () ),
    )
    child_ids = (
        f"button:{observation_id}",
        *((f"extra:{observation_id}",) if extra_target else ()),
    )
    source = SurfaceObservation(
        source_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        tuple(
            StateFact(f"fact:{observation_id}:{index}", target_id, "value", value, source_id)
            for index, value in enumerate(fact_values)
        ),
        structure=(
            ObservationStructureNode(
                f"root:{observation_id}",
                "document",
                "Page",
                child_structure_ids=child_ids,
            ),
            ObservationStructureNode(
                f"button:{observation_id}",
                "button",
                "Go",
                parent_structure_id=f"root:{observation_id}",
                semantic_target_id=target_id,
            ),
            *(
                (ObservationStructureNode(
                    f"extra:{observation_id}",
                    "button",
                    "Extra",
                    parent_structure_id=f"root:{observation_id}",
                    semantic_target_id=f"extra:{observation_id}",
                ),)
                if extra_target
                else ()
            ),
        ),
        structure_total_count=2 + int(extra_target),
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return replace(result.observation, observation_id=observation_id)


def _project(before, after):
    delta = WorldTransitionProjector().project(before, after)
    inventory = PublicEffectProjector().project(
        delta,
        canonical_world(before),
        canonical_world(after),
    )
    return delta, inventory


def _external_step(before, after):
    return SimpleNamespace(
        before_world=before,
        after_world=after,
        before_public_world=canonical_world(before),
        after_public_world=canonical_world(after),
        public_world_delta=WorldTransitionProjector().project(before, after),
        execution_receipts=SimpleNamespace(
            receipts=(
                SimpleNamespace(
                    request=SimpleNamespace(
                        intent=SimpleNamespace(
                            semantic_action="activate",
                            target_id=before.targets[0].target_id,
                        )
                    ),
                    result=SimpleNamespace(dispatch_status=DispatchStatus.SENT),
                ),
            )
        ),
    )


def _two_fact_world(observation_id: str, values: tuple[str, str]):
    source_id = f"source:{observation_id}"
    targets = tuple(SemanticTarget(f"target:{observation_id}:{index}", "status", "Item") for index in range(2))
    source = SurfaceObservation(
        source_id,
        "browser",
        f"revision:{observation_id}",
        ObservationSourceProfile.dom(),
        targets,
        tuple(
            StateFact(f"fact:{observation_id}:{index}", target.target_id, "value", value, source_id)
            for index, (target, value) in enumerate(zip(targets, values, strict=True))
        ),
        structure=(
            ObservationStructureNode("root", "document", "Page", child_structure_ids=("a", "b")),
            ObservationStructureNode("a", "status", "Item", parent_structure_id="root", semantic_target_id=targets[0].target_id),
            ObservationStructureNode("b", "status", "Item", parent_structure_id="root", semantic_target_id=targets[1].target_id),
        ),
        structure_total_count=3,
    )
    result = WorldFusion().fuse((source,))
    assert result.observation is not None
    return replace(result.observation, observation_id=observation_id)


def _ambiguous_index(world):
    index = WorldDeliveryIndex.from_observation(world)
    contexts = {
        target_id: replace(context, public_order=0)
        for target_id, context in index.target_contexts.items()
    }
    return replace(index, target_contexts=contexts)


def test_full_identity_remount_with_equal_public_semantics_has_no_effect_atoms() -> None:
    before = _world("world:before", target_id="private:old")
    after = _world("world:after-with-a-much-longer-id", target_id="private:new")

    delta, inventory = _project(before, after)

    assert canonical_world(before).public_document_signature == (
        canonical_world(after).public_document_signature
    )
    assert delta.target_changes or delta.fact_changes
    assert inventory.atoms == ()
    assert inventory.transition != "new_document"
    assert inventory.changed_target_slot_keys == ()
    assert inventory.raw_delta_lineage


@pytest.mark.parametrize(
    ("before_values", "after_values", "expected"),
    [
        (("same",), ("same", "same"), PublicChangeKind.ADDED),
        (("same", "same"), ("same",), PublicChangeKind.REMOVED),
    ],
)
def test_duplicate_public_fact_multiplicity_changes_by_exactly_one_atom(
    before_values: tuple[str, ...],
    after_values: tuple[str, ...],
    expected: PublicChangeKind,
) -> None:
    _delta, inventory = _project(
        _world("world:before", fact_values=before_values),
        _world("world:after", fact_values=after_values),
    )

    fact_atoms = tuple(item for item in inventory.atoms if item.atom_kind == "fact")
    assert len(fact_atoms) == 1
    assert fact_atoms[0].change is expected


def test_stable_slot_single_value_change_is_one_modified_atom() -> None:
    _delta, inventory = _project(
        _world("world:before", fact_values=("old",)),
        _world("world:after", fact_values=("new",)),
    )

    fact_atoms = tuple(item for item in inventory.atoms if item.atom_kind == "fact")
    assert [(item.change, item.exact_value) for item in fact_atoms] == [
        (PublicChangeKind.MODIFIED, "new")
    ]


def test_one_public_target_add_and_remove_produce_exact_target_atom_and_tombstone() -> None:
    before = _world("world:before")
    after = _world("world:after", extra_target=True)

    _delta, added = _project(before, after)
    _delta, removed = _project(after, before)
    added_targets = tuple(item for item in added.atoms if item.atom_kind == "target")
    removed_targets = tuple(item for item in removed.atoms if item.atom_kind == "target")

    assert len(added_targets) == 1
    assert added_targets[0].change is PublicChangeKind.ADDED
    assert len(removed_targets) == 1
    assert removed_targets[0].change is PublicChangeKind.REMOVED
    assert not removed_targets[0].subject_id


def test_ambiguous_same_slot_pairing_remains_adds_and_removed_tombstones() -> None:
    before = _two_fact_world("world:before", ("old-a", "old-b"))
    after = _two_fact_world("world:after", ("new-a", "new-b"))
    delta = WorldTransitionProjector().project(before, after)
    inventory = PublicEffectProjector().project(
        delta,
        canonical_world(before, index=_ambiguous_index(before)),
        canonical_world(after, index=_ambiguous_index(after)),
    )

    fact_atoms = tuple(item for item in inventory.atoms if item.atom_kind == "fact")
    assert [item.change for item in fact_atoms].count(PublicChangeKind.ADDED) == 2
    assert [item.change for item in fact_atoms].count(PublicChangeKind.REMOVED) == 2
    assert all(not item.subject_id for item in fact_atoms if item.change is PublicChangeKind.REMOVED)


def test_public_effect_is_id_permutation_invariant_but_raw_lineage_remains_private() -> None:
    before_a = _world("world:a", target_id="private:short", fact_values=("old",))
    after_a = _world("world:b", target_id="private:next", fact_values=("new",))
    before_b = _world("world:before-with-long-id", target_id="private:xxxxxxxx", fact_values=("old",))
    after_b = _world("world:after-with-long-id", target_id="private:yyyyyyyy", fact_values=("new",))

    _delta_a, effect_a = _project(before_a, after_a)
    _delta_b, effect_b = _project(before_b, after_b)

    assert effect_a.inventory_id == effect_b.inventory_id
    assert tuple(item.public_value for item in effect_a.atoms) == tuple(
        item.public_value for item in effect_b.atoms
    )
    assert effect_a.raw_delta_lineage != effect_b.raw_delta_lineage
    public = json.dumps(to_json_compatible(tuple(item.public_value for item in effect_a.atoms)))
    assert "browsergym-observation:" not in public
    assert "private:" not in public


def test_latest_external_effect_survives_local_operations_and_supersedes_once() -> None:
    before = _world("world:before", state_value="before")
    after = _world("world:after", state_value="after")
    final = _world("world:final", state_value="final")
    store = ObservationDeliveryStore().advance(_external_step(before, after), step_index=1)
    assert store.latest_effect is not None
    first_identity = store.latest_effect.inventory.inventory_id

    for operation in ("read_region", "search_page_content", "find_controls"):
        local = SimpleNamespace(execution_receipts=None, public_world_delta=None)
        assert store.advance(local, step_index=2) is store
        assert store.latest_effect.inventory.inventory_id == first_identity

    replaced = store.advance(_external_step(after, final), step_index=3)
    assert replaced.latest_effect is not None
    assert replaced.latest_effect.step_index == 3
    assert replaced.latest_effect.inventory.inventory_id != first_identity
    assert replaced.active_read is None
