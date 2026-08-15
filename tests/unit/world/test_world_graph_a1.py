from __future__ import annotations

import io
from dataclasses import replace
from itertools import permutations

import pytest
from PIL import Image

from affordance_runtime.actions import ActionSpace
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.grounding_projection import GroundingProjection
from affordance_runtime.agent.context.world_projection import project_model_world
from affordance_runtime.world import (
    AcquisitionCost,
    CoverageState,
    EntityAlignmentBasis,
    EntityAlignmentDisposition,
    EntityAlignmentProposal,
    FusionStatus,
    ObservationAssurance,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationModality,
    ObservationSourceProfile,
    SemanticTarget,
    SourceEntityEndpoint,
    StateFact,
    SurfaceObservation,
    VerificationStrength,
    WorldFusion,
    WorldObservation,
)
from tests.support.world import manifest_for_sources


def _source(
    source_id: str,
    local_id: str,
    *,
    surface: str = "browser",
    profile: ObservationSourceProfile | None = None,
    value: object = True,
    proposals: tuple[EntityAlignmentProposal, ...] = (),
    media: tuple[ObservationMedia, ...] = (),
    targets: tuple[SemanticTarget, ...] = (),
) -> SurfaceObservation:
    retained = targets or (SemanticTarget(local_id, "button", "Save", {"enabled": value}),)
    facts = tuple(
        StateFact(f"fact:{source_id}:{target.target_id}", target.target_id, "enabled", value, source_id)
        for target in retained
    )
    return SurfaceObservation(
        source_id,
        surface,
        f"revision:{source_id}",
        profile or ObservationSourceProfile.dom(),
        retained,
        facts,
        coverage=CoverageState.COMPLETE,
        media=media,
        acquisition_root_id="capture:shared",
        alignment_proposals=proposals,
    )


def _proposal(
    proposal_id: str,
    source_id: str,
    source_target_id: str,
    candidate_id: str,
    candidate_target_id: str,
) -> EntityAlignmentProposal:
    return EntityAlignmentProposal(
        proposal_id,
        SourceEntityEndpoint(source_id, source_target_id),
        SourceEntityEndpoint(candidate_id, candidate_target_id),
        EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
        (f"evidence:{proposal_id}",),
        0.9,
    )


def _fused(*sources: SurfaceObservation) -> WorldObservation:
    result = WorldFusion().fuse(tuple(sources))
    assert result.status is FusionStatus.FUSED and result.observation is not None
    return result.observation


def test_source_permutation_preserves_links_conflicts_and_canonical_claims() -> None:
    dom = _source("dom:1", "dom-target", value=False)
    visual = _source(
        "visual:1",
        "visual-target",
        profile=ObservationSourceProfile.visual(),
        value=True,
        proposals=(_proposal("proposal:visual", "visual:1", "visual-target", "dom:1", "dom-target"),),
    )
    signatures = []
    for ordered in permutations((dom, visual)):
        world = _fused(*ordered)
        signatures.append((world.targets, world.facts, world.conflicts, world.entity_source_links))
        assert "enabled" not in world.targets[0].state
        assert not world.facts
    assert signatures[0] == signatures[1]


def test_canonical_id_uses_the_complete_sorted_endpoint_component() -> None:
    dom = _source("dom:component", "dom-target")
    first_visual = _source(
        "visual:first",
        "visual-target",
        profile=ObservationSourceProfile.visual(),
        proposals=(_proposal(
            "proposal:first", "visual:first", "visual-target",
            "dom:component", "dom-target",
        ),),
    )
    second_visual = replace(
        first_visual,
        observation_id="visual:second",
        revision="revision:visual:second",
        alignment_proposals=(_proposal(
            "proposal:second", "visual:second", "visual-target",
            "dom:component", "dom-target",
        ),),
    )

    first_id = _fused(dom, first_visual).targets[0].target_id
    second_id = _fused(dom, second_visual).targets[0].target_id
    assert first_id.startswith("entity:")
    assert second_id.startswith("entity:")
    assert first_id != second_id


def test_same_surface_instances_keep_distinct_manifest_coverage_and_links() -> None:
    first = replace(_source("dom:ax", "ax-target"), coverage=CoverageState.COMPLETE)
    second = replace(_source("dom:dom", "dom-target"), coverage=CoverageState.TRUNCATED)
    world = _fused(second, first)

    assert tuple(item.source_observation_id for item in world.source_manifest) == ("dom:ax", "dom:dom")
    assert tuple(item.coverage for item in world.source_manifest) == (
        CoverageState.COMPLETE,
        CoverageState.TRUNCATED,
    )
    assert len(world.targets) == 2
    assert len(world.entity_source_links) == sum(len(item.targets) for item in world.sources)


def test_duplicate_source_observation_id_fails_closed() -> None:
    result = WorldFusion().fuse((_source("duplicate", "one"), _source("duplicate", "two")))
    assert result.status is FusionStatus.INCONCLUSIVE
    assert result.reason_code == "duplicate_source_observation_id"


def test_rejected_and_conflicted_proposals_allocate_every_target_independently() -> None:
    rejected = _source(
        "visual:rejected",
        "visual-target",
        profile=ObservationSourceProfile.visual(),
        proposals=(_proposal(
            "proposal:missing", "visual:rejected", "visual-target", "missing", "target"
        ),),
    )
    rejected_world = _fused(_source("dom:retained", "dom-target"), rejected)
    rejected_link = next(
        item for item in rejected_world.entity_source_links
        if item.source_observation_id == rejected.observation_id
    )
    assert rejected_link.disposition is EntityAlignmentDisposition.PROPOSAL_REJECTED_ALLOCATED
    assert len(rejected_world.targets) == 2

    left = _source(
        "dom:left",
        "unused",
        targets=(
            SemanticTarget("left:1", "button", "Save"),
            SemanticTarget("left:2", "button", "Save"),
        ),
    )
    right = _source(
        "visual:right",
        "right:1",
        profile=ObservationSourceProfile.visual(),
        proposals=(
            _proposal("proposal:left-1", "visual:right", "right:1", "dom:left", "left:1"),
            _proposal("proposal:left-2", "visual:right", "right:1", "dom:left", "left:2"),
        ),
    )
    conflicted_world = _fused(left, right)
    assert len(conflicted_world.targets) == 3
    assert all(
        item.disposition is EntityAlignmentDisposition.CONFLICTED_ALLOCATED
        for item in conflicted_world.entity_source_links
    )


def test_world_rejects_mixed_source_and_canonical_identity_construction() -> None:
    source = _source("dom:local", "local")
    with pytest.raises(ValueError, match="exactly one entity source link"):
        WorldObservation(
            "world:mixed",
            (SemanticTarget("canonical", "button", "Save"),),
            (),
            (),
            manifest_for_sources((source,)),
            sources=(source,),
        )

    with pytest.raises(ValueError, match="cover exactly"):
        WorldObservation(
            "world:phantom-source",
            (),
            (),
            (),
            manifest_for_sources((source,)),
        )


def test_undeclared_source_profile_fails_closed() -> None:
    profile = ObservationSourceProfile(
        ObservationModality.STRUCTURAL,
        ObservationAssurance.STRUCTURAL,
        VerificationStrength.STRUCTURAL,
        AcquisitionCost.LOW,
        "undeclared-profile",
    )
    result = WorldFusion().fuse((_source("unknown:1", "target", profile=profile),))
    assert result.status is FusionStatus.INCONCLUSIVE
    assert result.reason_code == "undeclared_source_profile"


def _png(colour: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 10), colour).save(output, format="PNG")
    return output.getvalue()


def test_media_capture_variant_selection_is_deterministic_and_coordinate_scoped() -> None:
    region = ObservationGroundingRegion(
        "target", (1, 1, 4, 4), coordinate_space_id="viewport:1"
    )
    raw = ObservationMedia(
        "raw", "screenshot", "image/png", _png("white"), (region,), "capture:1",
        ObservationMediaVariant.RAW, (20, 10), "viewport:1",
    )
    annotated = ObservationMedia(
        "annotated", "screenshot", "image/png", _png("black"), (region,), "capture:1",
        ObservationMediaVariant.ANNOTATED, (20, 10), "viewport:1",
    )
    source = _source("visual:media", "target", profile=ObservationSourceProfile.visual(), media=(annotated, raw))
    world = _fused(source)
    model_world = project_model_world(world, ContextProjectionBudget())
    grounded = GroundingProjection().project(
        world, model_world, ActionSpace(world.observation_id, ())
    )
    assert len(grounded.images) == 1
    assert grounded.images[0].sha256 == raw.sha256

    with pytest.raises(ValueError, match="coordinate space"):
        ObservationMedia(
            "invalid", "screenshot", "image/png", _png("white"),
            (replace(region, coordinate_space_id="other"),), "capture:1",
            ObservationMediaVariant.RAW, (20, 10), "viewport:1",
        )


def test_alignment_across_untransformed_coordinate_spaces_is_rejected() -> None:
    left_region = ObservationGroundingRegion(
        "dom-target", (1, 1, 4, 4), coordinate_space_id="viewport:dom"
    )
    right_region = ObservationGroundingRegion(
        "visual-target", (1, 1, 4, 4), coordinate_space_id="viewport:visual"
    )
    dom = _source(
        "dom:coords",
        "dom-target",
        media=(ObservationMedia(
            "dom-shot", "screenshot", "image/png", _png("white"), (left_region,),
            "capture:1", ObservationMediaVariant.RAW, (20, 10), "viewport:dom",
        ),),
    )
    visual = _source(
        "visual:coords",
        "visual-target",
        profile=ObservationSourceProfile.visual(),
        proposals=(_proposal(
            "proposal:coords", "visual:coords", "visual-target",
            "dom:coords", "dom-target",
        ),),
        media=(ObservationMedia(
            "visual-shot", "screenshot", "image/png", _png("white"), (right_region,),
            "capture:1", ObservationMediaVariant.RAW, (20, 10), "viewport:visual",
        ),),
    )

    world = _fused(visual, dom)
    assert len(world.targets) == 2
    assert all(
        item.disposition is EntityAlignmentDisposition.PROPOSAL_REJECTED_ALLOCATED
        for item in world.entity_source_links
    )
