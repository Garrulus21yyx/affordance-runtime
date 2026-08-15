from __future__ import annotations

from dataclasses import asdict
from itertools import permutations

from affordance_runtime.actions import ActionSpace
from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldNodeView,
    project_actor_world_snapshot,
)
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.grounding_projection import GroundingProjection
from affordance_runtime.agent.context.world_projection import project_model_world
from affordance_runtime.world import (
    EntityAlignmentBasis,
    EntityAlignmentProposal,
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticTarget,
    SourceEntityEndpoint,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)


def _source(
    source_id: str,
    local_id: str,
    *,
    profile: ObservationSourceProfile,
    structure_prefix: str,
    proposal: EntityAlignmentProposal | None = None,
    novel: bool = False,
) -> SurfaceObservation:
    targets = [SemanticTarget(local_id, "button", "Save", {"enabled": True})]
    structure = [
        ObservationStructureNode(
            f"{structure_prefix}:root",
            "document",
            "Document",
            child_structure_ids=(f"{structure_prefix}:target",),
        ),
        ObservationStructureNode(
            f"{structure_prefix}:target",
            "button",
            "Save",
            parent_structure_id=f"{structure_prefix}:root",
            semantic_target_id=local_id,
        ),
    ]
    if novel:
        targets.append(SemanticTarget(f"{local_id}:novel", "note", "Visual-only note"))
        structure[0] = ObservationStructureNode(
            f"{structure_prefix}:root",
            "document",
            "Document",
            child_structure_ids=(f"{structure_prefix}:target", f"{structure_prefix}:novel"),
        )
        structure.append(ObservationStructureNode(
            f"{structure_prefix}:novel",
            "note",
            "Visual-only note",
            parent_structure_id=f"{structure_prefix}:root",
            semantic_target_id=f"{local_id}:novel",
        ))
    return SurfaceObservation(
        source_id,
        "browser",
        f"revision:{source_id}",
        profile,
        tuple(targets),
        (StateFact(f"fact:{source_id}", local_id, "enabled", True, source_id),),
        acquisition_root_id="capture:shared",
        alignment_proposals=(proposal,) if proposal else (),
        structure=tuple(structure),
        structure_total_count=len(structure),
    )


def _snapshot(sources: tuple[SurfaceObservation, ...], *, bound: int = 128):
    fused = WorldFusion().fuse(sources)
    assert fused.observation is not None
    world = fused.observation
    model_world = project_model_world(world, ContextProjectionBudget())
    grounding = GroundingProjection().project(
        world, model_world, ActionSpace(world.observation_id, ())
    )
    return world, project_actor_world_snapshot(
        world, model_world, grounding.index, grounding.images, max_structure_nodes=bound
    )


def _walk(node: ActorWorldNodeView):
    yield node
    for child in node.children:
        yield from _walk(child)


def _nodes(snapshot):
    return tuple(
        node
        for document in snapshot.documents
        for root in document.roots
        for node in _walk(root)
    )


def test_corresponded_structure_retains_one_canonical_entity_with_all_source_refs() -> None:
    dom = _source(
        "dom:1", "dom-target", profile=ObservationSourceProfile.dom(), structure_prefix="dom"
    )
    proposal = EntityAlignmentProposal(
        "proposal:visual",
        SourceEntityEndpoint("visual:1", "visual-target"),
        SourceEntityEndpoint("dom:1", "dom-target"),
        EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
        ("evidence:visual",),
        1.0,
    )
    visual = _source(
        "visual:1", "visual-target", profile=ObservationSourceProfile.visual(),
        structure_prefix="visual", proposal=proposal,
    )
    world, snapshot = _snapshot((visual, dom))

    entity_nodes = tuple(item for item in _nodes(snapshot) if item.ref.startswith("E"))
    assert len(world.targets) == len(entity_nodes) == 1
    assert entity_nodes[0].state == {"enabled": True}
    assert entity_nodes[0].state_evidence
    assert entity_nodes[0].source_refs == ("S1", "S2")
    assert len(snapshot.documents) == 1


def test_actor_semantic_payload_is_source_permutation_invariant() -> None:
    dom = _source(
        "dom:1", "dom-target", profile=ObservationSourceProfile.dom(), structure_prefix="dom"
    )
    visual = _source(
        "visual:1",
        "visual-target",
        profile=ObservationSourceProfile.visual(),
        structure_prefix="visual",
        proposal=EntityAlignmentProposal(
            "proposal:visual",
            SourceEntityEndpoint("visual:1", "visual-target"),
            SourceEntityEndpoint("dom:1", "dom-target"),
            EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
            ("evidence:visual",),
            1.0,
        ),
    )
    payloads = [asdict(_snapshot(tuple(items))[1]) for items in permutations((dom, visual))]
    assert payloads[0] == payloads[1]


def test_complementary_lens_does_not_repeat_primary_tree_and_bounds_are_truthful() -> None:
    dom = _source(
        "dom:1", "dom-target", profile=ObservationSourceProfile.dom(), structure_prefix="dom"
    )
    visual = _source(
        "visual:1",
        "visual-target",
        profile=ObservationSourceProfile.visual(),
        structure_prefix="visual",
        proposal=EntityAlignmentProposal(
            "proposal:visual",
            SourceEntityEndpoint("visual:1", "visual-target"),
            SourceEntityEndpoint("dom:1", "dom-target"),
            EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
            ("evidence:visual",),
            1.0,
        ),
        novel=True,
    )
    _, snapshot = _snapshot((dom, visual), bound=3)

    assert len(snapshot.documents) == 2
    primary, complementary = snapshot.documents
    assert primary.retained_node_count == primary.total_node_count == 2
    assert not primary.truncated
    assert complementary.retained_node_count == 1
    assert complementary.total_node_count == 2
    assert complementary.truncated
    assert all(not item.ref.startswith("E") for item in _nodes(type("S", (), {"documents": (complementary,)})()))


def test_primary_lens_bound_preserves_ancestor_closure_and_native_child_order() -> None:
    source = SurfaceObservation(
        "dom:out-of-order",
        "browser",
        "revision:1",
        ObservationSourceProfile.dom(),
        targets=(
            SemanticTarget("child:one", "button", "One"),
            SemanticTarget("child:two", "button", "Two"),
        ),
        structure=(
            ObservationStructureNode(
                "node:one", "button", "One",
                parent_structure_id="node:root", semantic_target_id="child:one",
            ),
            ObservationStructureNode(
                "node:root", "document", "Document",
                child_structure_ids=("node:two", "node:one"),
            ),
            ObservationStructureNode(
                "node:two", "button", "Two",
                parent_structure_id="node:root", semantic_target_id="child:two",
            ),
        ),
        structure_total_count=3,
    )

    _, snapshot = _snapshot((source,), bound=2)
    document = snapshot.documents[0]
    assert document.retained_node_count == 2
    assert document.total_node_count == 3
    assert document.truncated
    assert len(document.roots) == 1
    assert document.roots[0].label == "Document"
    assert tuple(item.label for item in document.roots[0].children) == ("Two",)
