from __future__ import annotations

import hashlib
import io

import pytest
from PIL import Image

import affordance_runtime.agent.context.grounding_projection as grounding_projection_module
from affordance_runtime.actions import ActionSpace
from affordance_runtime.agent.context.budgets import ContextProjectionBudget
from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.grounding_projection import (
    GroundingProjection,
    visual_mark_candidate_set,
)
from affordance_runtime.agent.context.world_projection import project_model_world
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.world import (
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldFusion,
)
from affordance_runtime.world.visual_annotation import VisualAnnotationResult


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(output, format="PNG")
    return output.getvalue()


def _readonly_world(token: str, *, count: int, reverse: bool = False, out_of_frame: bool = False):
    target_ids = tuple(f"private:{token}:{index}" for index in range(count))
    targets = tuple(
        SemanticTarget(target_id, "note", f"Public note {index:03d}")
        for index, target_id in enumerate(target_ids)
    )
    regions = tuple(
        ObservationGroundingRegion(
            target_id,
            (80, 1, 4, 4) if out_of_frame else (index % 16, index // 16, 4, 4),
            coordinate_space_id="viewport:readonly",
        )
        for index, target_id in enumerate(target_ids)
    )
    if reverse:
        targets = tuple(reversed(targets))
        regions = tuple(reversed(regions))
    media = ObservationMedia(
        f"screenshot:{token}",
        "screenshot",
        "image/png",
        _png(),
        regions,
        f"capture:{token}",
        ObservationMediaVariant.RAW,
        (64, 64),
        "viewport:readonly",
    )
    fused = WorldFusion().fuse((
        SurfaceObservation(
            f"source:{token}",
            "dom",
            f"revision:{token}",
            ObservationSourceProfile.dom(),
            targets,
            media=(media,),
        ),
    ))
    assert fused.observation is not None
    world = fused.observation
    actions = ActionSpace(world.observation_id, ())
    index = WorldDeliveryIndex.from_observation(world, ())
    projection = CanonicalPublicWorldProjection.build(world, index, actions)
    return world, projection, world.media[0].media


def test_many_readonly_visual_candidates_are_bounded_and_private_permutation_invariant() -> None:
    first_world, first_projection, first_media = _readonly_world("short", count=40)
    second_world, second_projection, second_media = _readonly_world(
        "different-private-lineage", count=40, reverse=True
    )

    first = visual_mark_candidate_set(first_projection, first_media, limit=7)
    second = visual_mark_candidate_set(second_projection, second_media, limit=7)

    assert first.total_count == second.total_count == 40
    assert first.truncated and second.truncated
    assert tuple((item.ref, item.bbox) for item in first.items) == tuple(
        (item.ref, item.bbox) for item in second.items
    )
    assert tuple(item.ref for item in first.items) == tuple(f"N{index}" for index in range(1, 8))
    assert first_world.observation_id != second_world.observation_id
    first_grounding = GroundingProjection(max_marks_per_image=7).project(
        first_world,
        first_projection,
        project_model_world(
            first_world,
            ContextProjectionBudget(),
            lossless_public=True,
            canonical_projection=first_projection,
        ),
    )
    second_grounding = GroundingProjection(max_marks_per_image=7).project(
        second_world,
        second_projection,
        project_model_world(
            second_world,
            ContextProjectionBudget(),
            lossless_public=True,
            canonical_projection=second_projection,
        ),
    )
    assert tuple((mark.ref, mark.bbox) for mark in first_grounding.images[0].marks) == tuple(
        (mark.ref, mark.bbox) for mark in second_grounding.images[0].marks
    )
    assert first_grounding.images[0].sha256 == second_grounding.images[0].sha256


def test_out_of_frame_readonly_candidate_is_not_an_actual_mark() -> None:
    world, projection, media = _readonly_world("out-of-frame", count=1, out_of_frame=True)
    model_world = project_model_world(
        world,
        ContextProjectionBudget(),
        lossless_public=True,
        canonical_projection=projection,
    )

    grounded = GroundingProjection(max_marks_per_image=4).project(world, projection, model_world)

    candidates = visual_mark_candidate_set(projection, media, limit=4)
    assert candidates.items == ()
    assert candidates.total_count == 0
    assert grounded.images[0].marks == ()
    assert grounded.images[0].sha256 == media.sha256


def test_annotation_unavailable_does_not_claim_candidate_was_actually_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, projection, media = _readonly_world("annotation-unavailable", count=1)
    model_world = project_model_world(
        world,
        ContextProjectionBudget(),
        lossless_public=True,
        canonical_projection=projection,
    )

    monkeypatch.setattr(
        grounding_projection_module,
        "annotate_screenshot_result",
        lambda data, mime_type, marks: VisualAnnotationResult(
            data,
            mime_type,
            hashlib.sha256(data).hexdigest(),
            (),
            False,
        ),
    )
    grounded = GroundingProjection().project(world, projection, model_world)

    assert visual_mark_candidate_set(projection, media, limit=4).items[0].ref == "N1"
    assert grounded.images[0].marks == ()
    assert grounded.index.entities[0].marked is False
