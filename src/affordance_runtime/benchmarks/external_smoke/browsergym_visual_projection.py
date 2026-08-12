"""Generic screenshot-region projection for the BrowserGym source group."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from affordance_runtime.benchmarks.external_smoke.browsergym_binding import BrowserGymVisualBinding
from affordance_runtime.surfaces.visual.contracts import (
    VisualFrame,
    VisualRegionBinding,
    VisualViewport,
    project_visual_semantic_state,
)
from affordance_runtime.task import TaskGoal
from affordance_runtime.visual_grounding import VisualRegionProposalRequest, VisualRegionProposerPort
from affordance_runtime.world import (
    ActionBinding,
    CoverageState,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)
from affordance_runtime.world.action_classification import classify_surface_action
from affordance_runtime.world.action_vocabulary import action_metadata

MAX_BROWSERGYM_VISUAL_REGIONS = 16


@dataclass(frozen=True)
class BrowserGymVisualProjection:
    source: SurfaceObservation
    private_bindings: tuple[BrowserGymVisualBinding, ...]


def browsergym_visual_frame(raw: dict[str, object], observation_id: str) -> VisualFrame:
    image_bytes, width, height = _encoded_screenshot(raw)
    digest = "sha256:" + hashlib.sha256(image_bytes).hexdigest()
    viewport = VisualViewport(
        width,
        height,
        0.0,
        0.0,
        1.0,
        1.0,
        "landscape" if width >= height else "portrait",
    )
    return VisualFrame(
        observation_id,
        f"browsergym-screenshot:{observation_id}",
        digest,
        width,
        height,
        viewport,
        image_bytes,
    )


def project_browsergym_visual_source(
    raw: dict[str, object],
    *,
    observation_id: str,
    acquisition_root_id: str,
    page_identity: str,
    episode_identity: str,
    task: TaskGoal,
    proposer: VisualRegionProposerPort,
) -> BrowserGymVisualProjection:
    frame = browsergym_visual_frame(raw, observation_id)
    request = VisualRegionProposalRequest(
        observation_id,
        None,
        frame.image_bytes,
        (frame.image_width, frame.image_height),
        task.instruction,
        MAX_BROWSERGYM_VISUAL_REGIONS,
    )
    proposed = tuple(proposer.propose(request))
    if len(proposed) > request.max_regions:
        raise ValueError("visual proposer exceeded the BrowserGym region bound")
    regions = tuple(
        VisualRegionBinding.from_region(frame, f"visual-region:{index}", region)
        for index, region in enumerate(proposed)
    )
    targets = tuple(
        SemanticTarget(
            region.region_id,
            region.role,
            region.label,
            project_visual_semantic_state(dict(region.state)),
        )
        for region in regions
    )
    facts = tuple(
        StateFact(
            f"{observation_id}:{target.target_id}:{key}",
            target.target_id,
            key,
            value,
            observation_id,
        )
        for target in targets
        for key, value in target.state.items()
    )
    public: list[ActionBinding] = []
    private: list[BrowserGymVisualBinding] = []
    for region in regions:
        pair = _binding_pair(
            task,
            frame,
            region,
            page_identity=page_identity,
            episode_identity=episode_identity,
        )
        if pair is not None:
            public.append(pair[0])
            private.append(pair[1])
    grounding_regions = tuple(
        ObservationGroundingRegion(
            region.region_id,
            _integer_bbox(region, frame.image_width, frame.image_height),
            region.confidence,
        )
        for region in regions
    )
    media = ObservationMedia(
        "visual-screenshot",
        "screenshot",
        "image/png",
        frame.image_bytes,
        grounding_regions,
    )
    unsupported = tuple(
        region.primitive_action for region in regions if region.primitive_action != "point_activate"
    )
    source = SurfaceObservation(
        observation_id,
        "browsergym_visual",
        frame.source_revision,
        ObservationSourceProfile.visual(),
        targets,
        facts,
        tuple(public),
        CoverageState.COMPLETE
        if bool(getattr(proposer, "acquisition_exhaustive", False))
        else CoverageState.TRUNCATED,
        {"unsupported_actions": unsupported},
        media=(media,),
        acquisition_root_id=acquisition_root_id,
    )
    return BrowserGymVisualProjection(source, tuple(private))


def _binding_pair(
    task: TaskGoal,
    frame: VisualFrame,
    region: VisualRegionBinding,
    *,
    page_identity: str,
    episode_identity: str,
) -> tuple[ActionBinding, BrowserGymVisualBinding] | None:
    if region.primitive_action != "point_activate":
        return None
    try:
        metadata = action_metadata("visual", region.primitive_action)
    except ValueError:
        return None
    classification = classify_surface_action(task, region.role, metadata.semantic_action)
    binding_id = f"binding:{frame.observation_id}:{region.region_id}:{region.primitive_action}"
    public = ActionBinding(
        binding_id,
        frame.observation_id,
        frame.observation_id,
        frame.source_revision,
        region.region_fingerprint,
        region.region_id,
        region.region_id,
        "browsergym_visual",
        "browsergym",
        metadata.semantic_action,
        metadata.primitive_action,
        classification.category.value,
        classification.semantic_effects,
        dict(metadata.parameter_schema),
        {},
        classification.observation_barrier,
        confidence=region.confidence,
        risk=classification.risk,
    )
    return public, BrowserGymVisualBinding(binding_id, page_identity, episode_identity, region)


def _encoded_screenshot(raw: dict[str, object]) -> tuple[bytes, int, int]:
    screenshot = raw.get("screenshot")
    if screenshot is None:
        raise ValueError("BrowserGym visual source requires a screenshot")
    try:
        image = Image.fromarray(screenshot)  # type: ignore[arg-type]
        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue(), image.width, image.height
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        raise ValueError("BrowserGym visual screenshot could not be encoded") from exc


def _integer_bbox(
    region: VisualRegionBinding,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    x, y, width, height = region.bbox_xywh
    left = max(0, min(image_width - 1, round(x)))
    top = max(0, min(image_height - 1, round(y)))
    right = max(left + 1, min(image_width, round(x + width)))
    bottom = max(top + 1, min(image_height, round(y + height)))
    return left, top, right - left, bottom - top
