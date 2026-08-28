"""Point-free E-ref disambiguation projection for current DOM candidates."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.surfaces.browsergym.capture_frame import BrowserGymCaptureFrame
from affordance_runtime.surfaces.browsergym.visual_projection import (
    browsergym_visual_frame,
)
from affordance_runtime.surfaces.visual.disambiguation import (
    VisualCandidate,
    VisualCandidateDisambiguationRequest,
    VisualCandidateDisambiguatorPort,
)
from affordance_runtime.world import (
    CoverageState,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationSourceProfile,
    SurfaceObservation,
    VisionEvidenceNeed,
)

MAX_VISUAL_DISAMBIGUATION_CANDIDATES = 32
_VIEWPORT_COORDINATE_SPACE = "browsergym:viewport_pixels"


class BrowserGymVisualDisambiguationProjectionError(ValueError):
    """The current structured source cannot form a valid specialist request."""

    reason_code = "visual_candidate_projection_invalid"


class BrowserGymVisualDisambiguationUnavailable(BrowserGymVisualDisambiguationProjectionError):
    """The current screenshot cannot represent a valid candidate choice."""

    reason_code = "visual_candidate_set_unavailable"


@dataclass(frozen=True)
class BrowserGymVisualDisambiguationProjection:
    source: SurfaceObservation
    selected_target_id: str = ""


def project_browsergym_visual_disambiguation_source(
    raw: dict[str, object],
    *,
    observation_id: str,
    acquisition_root_id: str,
    instruction: str,
    structured_source: SurfaceObservation,
    candidate_ids: tuple[str, ...],
    disambiguator: VisualCandidateDisambiguatorPort,
    evidence_need: VisionEvidenceNeed = VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,
    capture_frame: BrowserGymCaptureFrame | None = None,
) -> BrowserGymVisualDisambiguationProjection:
    try:
        frame = browsergym_visual_frame(raw, observation_id, capture_frame=capture_frame)
    except ValueError as exc:
        raise BrowserGymVisualDisambiguationProjectionError(
            "visual disambiguation screenshot projection is invalid"
        ) from exc
    targets = {item.target_id: item for item in structured_source.targets}
    boxes = {
        region.target_id: clipped
        for media in structured_source.media
        for region in media.grounding_regions
        if region.coordinate_space_id == _VIEWPORT_COORDINATE_SPACE
        if (clipped := _clip_to_viewport(
            region.bbox,
            frame.image_width,
            frame.image_height,
        )) is not None
        if region.target_id in candidate_ids and region.target_id in targets
    }
    visible_candidate_ids = tuple(item for item in candidate_ids if item in boxes)[
        :MAX_VISUAL_DISAMBIGUATION_CANDIDATES
    ]
    if len(visible_candidate_ids) < 2:
        raise BrowserGymVisualDisambiguationUnavailable(
            "visual disambiguation requires at least two current viewport candidates"
        )
    try:
        candidates = tuple(
            VisualCandidate(
                f"E{index}",
                target_id,
                targets[target_id].role,
                targets[target_id].label,
                boxes[target_id],
                dict(targets[target_id].state),
            )
            for index, target_id in enumerate(visible_candidate_ids, 1)
        )
        provider_request = VisualCandidateDisambiguationRequest(
            observation_id,
            frame.image_bytes,
            (frame.image_width, frame.image_height),
            instruction,
            candidates,
            evidence_need,
        )
    except ValueError as exc:
        raise BrowserGymVisualDisambiguationProjectionError(
            "visual disambiguation candidate projection is invalid"
        ) from exc
    selected_ref = disambiguator.choose(provider_request)
    selected = next((item for item in candidates if item.ref == selected_ref), None)
    selected_target_id = ""
    if selected is not None:
        selected_target_id = selected.target_id
    media = ObservationMedia(
        "visual-disambiguation-screenshot",
        "screenshot",
        "image/png",
        frame.image_bytes,
        (),
        capture_group_id=acquisition_root_id,
        variant=ObservationMediaVariant.RAW,
        dimensions=(frame.image_width, frame.image_height),
        coordinate_space_id="browsergym:viewport_pixels",
    )
    source = SurfaceObservation(
        observation_id,
        "browsergym_visual",
        frame.source_revision,
        ObservationSourceProfile.visual(),
        (),
        (),
        (),
        CoverageState.COMPLETE,
        {
            "visual_disambiguation": {
                "public_summary": "Current marked candidates were visually disambiguated without coordinates."
            }
        },
        media=(media,),
        acquisition_root_id=acquisition_root_id,
    )
    return BrowserGymVisualDisambiguationProjection(source, selected_target_id)


def _clip_to_viewport(
    bbox: tuple[int, int, int, int],
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int] | None:
    """Project one structural region into the current screenshot coordinate space."""

    x, y, width, height = bbox
    left = max(0, x)
    top = max(0, y)
    right = min(image_width, x + width)
    bottom = min(image_height, y + height)
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top
