"""Point-free E-ref disambiguation projection for current DOM candidates."""

from __future__ import annotations

from dataclasses import dataclass

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
    EntityAlignmentBasis,
    EntityAlignmentProposal,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationMediaVariant,
    ObservationSourceProfile,
    SemanticTarget,
    SourceEntityEndpoint,
    StateFact,
    SurfaceObservation,
    VisionEvidenceNeed,
)

MAX_VISUAL_DISAMBIGUATION_CANDIDATES = 32


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
    disambiguator: VisualCandidateDisambiguatorPort,
    evidence_need: VisionEvidenceNeed = VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION,
) -> BrowserGymVisualDisambiguationProjection:
    frame = browsergym_visual_frame(raw, observation_id)
    targets = {item.target_id: item for item in structured_source.targets}
    actionable_ids = {item.target_id for item in structured_source.bindings}
    boxes = {
        region.target_id: region.bbox
        for media in structured_source.media
        for region in media.grounding_regions
        if region.target_id in actionable_ids and region.target_id in targets
    }
    # E-ref numbering follows visual reading order instead of private identity
    # hashes.  This keeps dense SoM inventories legible and deterministic while
    # preserving the target ID exclusively inside the Runtime binding.
    ordered_ids = tuple(sorted(
        boxes,
        key=lambda target_id: (
            boxes[target_id][1],
            boxes[target_id][0],
            boxes[target_id][3],
            boxes[target_id][2],
            target_id,
        ),
    ))
    candidate_ids = ordered_ids[:MAX_VISUAL_DISAMBIGUATION_CANDIDATES]
    if len(candidate_ids) < 2:
        raise ValueError("visual disambiguation requires at least two grounded DOM candidates")
    candidates = tuple(
        VisualCandidate(
            f"E{index}",
            target_id,
            targets[target_id].role,
            targets[target_id].label,
            boxes[target_id],
            dict(targets[target_id].state),
        )
        for index, target_id in enumerate(candidate_ids, 1)
    )
    selected_ref = disambiguator.choose(VisualCandidateDisambiguationRequest(
        observation_id,
        frame.image_bytes,
        (frame.image_width, frame.image_height),
        instruction,
        candidates,
        evidence_need,
    ))
    selected = next((item for item in candidates if item.ref == selected_ref), None)
    projected_targets: tuple[SemanticTarget, ...] = ()
    facts: tuple[StateFact, ...] = ()
    alignment_proposals: tuple[EntityAlignmentProposal, ...] = ()
    grounding_regions: tuple[ObservationGroundingRegion, ...] = ()
    selected_target_id = ""
    if selected is not None:
        selected_target_id = selected.target_id
        local_id = f"visual-choice:{selected.ref}"
        target = targets[selected.target_id]
        projected_targets = (SemanticTarget(
            local_id,
            target.role,
            target.label,
            {"visually_selected": True},
        ),)
        facts = (StateFact(
            f"{observation_id}:{local_id}:visually_selected",
            local_id,
            "visually_selected",
            True,
            observation_id,
        ),)
        alignment_proposals = (EntityAlignmentProposal(
            f"proposal:{observation_id}:{local_id}",
            SourceEntityEndpoint(observation_id, local_id),
            SourceEntityEndpoint(structured_source.observation_id, selected.target_id),
            EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE,
            (f"media:{observation_id}:visual-disambiguation-screenshot:{local_id}",),
            1.0,
        ),)
        grounding_regions = (ObservationGroundingRegion(
            local_id, selected.bbox, coordinate_space_id="browsergym:viewport_pixels"
        ),)
    media = ObservationMedia(
        "visual-disambiguation-screenshot",
        "screenshot",
        "image/png",
        frame.image_bytes,
        grounding_regions,
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
        projected_targets,
        facts,
        (),
        CoverageState.TRUNCATED
        if len(ordered_ids) > len(candidate_ids)
        else CoverageState.COMPLETE,
        {
            "visual_disambiguation": {
                "public_summary": "Current marked candidates were visually disambiguated without coordinates."
            }
        },
        media=(media,),
        acquisition_root_id=acquisition_root_id,
        alignment_proposals=alignment_proposals,
    )
    return BrowserGymVisualDisambiguationProjection(source, selected_target_id)
