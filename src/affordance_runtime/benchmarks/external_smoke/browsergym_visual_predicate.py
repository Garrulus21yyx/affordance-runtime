"""Project bounded visual predicate evidence onto existing DOM identities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from affordance_runtime.benchmarks.external_smoke.browsergym_visual_projection import browsergym_visual_frame
from affordance_runtime.visual_disambiguation import VisualCandidate
from affordance_runtime.visual_predicate_classification import (
    VisualPredicateClassificationRequest,
    VisualPredicateClassifierPort,
)
from affordance_runtime.world import (
    CoverageState,
    EntityCorrespondence,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)

MAX_VISUAL_PREDICATE_CANDIDATES = 32


@dataclass(frozen=True)
class BrowserGymVisualPredicateProjection:
    source: SurfaceObservation
    assessment_count: int


def project_browsergym_visual_predicate_source(
    raw: dict[str, object],
    *,
    observation_id: str,
    acquisition_root_id: str,
    instruction: str,
    structured_source: SurfaceObservation,
    classifier: VisualPredicateClassifierPort,
) -> BrowserGymVisualPredicateProjection:
    frame = browsergym_visual_frame(raw, observation_id)
    targets = {item.target_id: item for item in structured_source.targets}
    actionable_ids = {item.target_id for item in structured_source.bindings}
    boxes = {
        region.target_id: region.bbox
        for media in structured_source.media
        for region in media.grounding_regions
        if region.target_id in actionable_ids and region.target_id in targets
    }
    ordered_ids = tuple(sorted(
        boxes,
        key=lambda target_id: (
            boxes[target_id][1], boxes[target_id][0], boxes[target_id][3], boxes[target_id][2], target_id,
        ),
    ))
    candidate_ids = ordered_ids[:MAX_VISUAL_PREDICATE_CANDIDATES]
    if not candidate_ids:
        raise ValueError("visual predicate classification requires grounded DOM candidates")
    candidates = tuple(
        VisualCandidate(
            f"E{index}", target_id, targets[target_id].role, targets[target_id].label,
            boxes[target_id], dict(targets[target_id].state),
        )
        for index, target_id in enumerate(candidate_ids, 1)
    )
    assessments = classifier.classify(VisualPredicateClassificationRequest(
        observation_id,
        frame.image_bytes,
        (frame.image_width, frame.image_height),
        instruction,
        candidates,
    ))
    by_ref = {item.ref: item for item in assessments}
    instruction_digest = hashlib.sha256(instruction.encode()).hexdigest()
    projected_targets = tuple(
        SemanticTarget(
            f"visual-predicate:{item.ref}",
            targets[item.target_id].role,
            targets[item.target_id].label,
            {
                "task_predicate_truth": by_ref[item.ref].truth.value,
                "task_predicate_digest": instruction_digest,
                "task_predicate_confidence": by_ref[item.ref].confidence,
            },
        )
        for item in candidates
    )
    facts = tuple(
        StateFact(
            f"{observation_id}:visual-predicate:{item.ref}:{predicate}",
            f"visual-predicate:{item.ref}",
            predicate,
            value,
            observation_id,
        )
        for item in candidates
        for predicate, value in (
            ("task_predicate_truth", by_ref[item.ref].truth.value),
            ("task_predicate_digest", instruction_digest),
            ("task_predicate_confidence", by_ref[item.ref].confidence),
        )
    )
    correspondences = tuple(
        EntityCorrespondence(f"visual-predicate:{item.ref}", item.target_id)
        for item in candidates
    )
    media = ObservationMedia(
        "visual-predicate-screenshot",
        "screenshot",
        "image/png",
        frame.image_bytes,
        tuple(
            ObservationGroundingRegion(f"visual-predicate:{item.ref}", item.bbox)
            for item in candidates
        ),
    )
    source = SurfaceObservation(
        observation_id,
        "browsergym_visual",
        frame.source_revision,
        ObservationSourceProfile.visual(),
        projected_targets,
        facts,
        (),
        CoverageState.TRUNCATED if len(ordered_ids) > len(candidate_ids) else CoverageState.COMPLETE,
        {"visual_predicate": {"public_summary": "Supplied DOM candidates received three-valued visual predicate evidence."}},
        media=(media,),
        acquisition_root_id=acquisition_root_id,
        correspondences=correspondences,
    )
    return BrowserGymVisualPredicateProjection(source, len(assessments))
