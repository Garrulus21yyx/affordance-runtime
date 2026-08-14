"""Generic screenshot-region projection for the BrowserGym source group."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from io import BytesIO

from PIL import Image

from affordance_runtime.benchmarks.external_smoke.browsergym_binding import BrowserGymVisualBinding
from affordance_runtime.surfaces.visual.contracts import (
    VisualFrame,
    VisualRegionBinding,
    VisualViewport,
    project_visual_semantic_state,
)
from affordance_runtime.surfaces.visual.interaction_profile import VISUAL_INTERACTION_CAPABILITIES
from affordance_runtime.task import TaskGoal
from affordance_runtime.visual_grounding import (
    VisualGrounderPort,
    VisualGroundingRequest,
    VisualProviderFailure,
    VisualProviderStage,
    VisualRegionProposalRequest,
    VisualRegionProposerPort,
    classify_visual_provider_failure,
    point_grounded_visual_regions,
)
from affordance_runtime.world import (
    ActionBinding,
    CoverageState,
    EntityCorrespondence,
    ObservationGroundingRegion,
    ObservationMedia,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
)
from affordance_runtime.world.action_classification import classify_surface_action
from affordance_runtime.world.interaction_capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    InteractionCapabilityError,
)

MAX_BROWSERGYM_VISUAL_REGIONS = 16
MIN_VISUAL_ACTION_CONFIDENCE = 0.5


@dataclass(frozen=True)
class BrowserGymVisualProjection:
    source: SurfaceObservation
    private_bindings: tuple[BrowserGymVisualBinding, ...]
    correspondence_decisions: tuple[VisualCorrespondenceDecision, ...]
    point_grounding_attempted: bool = False
    point_grounding_succeeded: bool = False
    provider_failure: VisualProviderFailure | None = None


class VisualCorrespondenceStatus(StrEnum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class VisualCorrespondenceDecision:
    source_target_id: str
    status: VisualCorrespondenceStatus
    canonical_target_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_target_id.strip():
            raise ValueError("visual correspondence decision requires source identity")
        if (self.status is VisualCorrespondenceStatus.MATCHED) != bool(
            self.canonical_target_id.strip()
        ):
            raise ValueError("only matched correspondence carries canonical identity")


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


def project_browsergym_screenshot_source(
    raw: dict[str, object],
    *,
    observation_id: str,
    acquisition_root_id: str,
) -> SurfaceObservation:
    """Publish the captured viewport as evidence without inventing semantics or actions."""

    frame = browsergym_visual_frame(raw, observation_id)
    return SurfaceObservation(
        observation_id,
        "browsergym_visual",
        frame.source_revision,
        ObservationSourceProfile.visual(),
        coverage=CoverageState.COMPLETE,
        artifacts={
            "screenshot_semantic_state": {
                "public_summary": "Current raw viewport screenshot; semantic interpretation remains open world.",
            },
        },
        media=(ObservationMedia(
            "visual-screenshot",
            "screenshot",
            "image/png",
            frame.image_bytes,
        ),),
        acquisition_root_id=acquisition_root_id,
    )


def project_browsergym_visual_source(
    raw: dict[str, object],
    *,
    observation_id: str,
    acquisition_root_id: str,
    page_identity: str,
    episode_identity: str,
    task: TaskGoal,
    proposer: VisualRegionProposerPort | None,
    point_grounder: VisualGrounderPort | None,
    structured_source: SurfaceObservation,
) -> BrowserGymVisualProjection:
    if proposer is None and point_grounder is None:
        raise ValueError("visual discovery requires a region or point provider")
    frame = browsergym_visual_frame(raw, observation_id)
    request = VisualRegionProposalRequest(
        observation_id,
        None,
        frame.image_bytes,
        (frame.image_width, frame.image_height),
        task.instruction,
        MAX_BROWSERGYM_VISUAL_REGIONS,
    )
    proposed = list(proposer.propose(request)) if proposer is not None else []
    if len(proposed) > request.max_regions:
        raise ValueError("visual proposer exceeded the BrowserGym region bound")
    proposed = [
        replace(region, primitive_action="observe_only", action_point_xy=None)
        for region in proposed
    ]
    point_succeeded = False
    provider_failure = None
    if point_grounder is not None:
        try:
            point = point_grounder.ground(VisualGroundingRequest(
                observation_id,
                None,
                frame.image_bytes,
                (frame.image_width, frame.image_height),
                _atomic_point_instruction(task.instruction),
            ))
            proposed = point_grounded_visual_regions(proposed, point, request.image_size)
            if len(proposed) > request.max_regions:
                proposed = [*proposed[: request.max_regions - 1], proposed[-1]]
            point_succeeded = True
        except Exception as exc:
            point_succeeded = False
            provider_failure = classify_visual_provider_failure(
                VisualProviderStage.POINT_GROUNDING,
                exc,
            )
    regions = tuple(
        VisualRegionBinding.from_region(frame, f"visual-region:{index}", region)
        for index, region in enumerate(proposed)
    )
    decisions = tuple(
        _correspondence_decision(region, structured_source) for region in regions
    )
    decision_by_id = {item.source_target_id: item for item in decisions}
    structured_targets = {item.target_id: item for item in structured_source.targets}
    targets = tuple(
        SemanticTarget(
            region.region_id,
            structured_targets[decision_by_id[region.region_id].canonical_target_id].role
            if decision_by_id[region.region_id].status is VisualCorrespondenceStatus.MATCHED
            else region.role,
            structured_targets[decision_by_id[region.region_id].canonical_target_id].label
            if decision_by_id[region.region_id].status is VisualCorrespondenceStatus.MATCHED
            else region.label,
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
        decision = decision_by_id[region.region_id]
        pair = _binding_pair(
            task,
            frame,
            region,
            correspondence=decision,
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
        if proposer is not None and bool(getattr(proposer, "acquisition_exhaustive", False))
        else CoverageState.TRUNCATED,
        {
            "unsupported_actions": unsupported,
            "screenshot_semantic_state": {
                "public_summary": "Current screenshot state for bounded before/after effect comparison.",
            },
        },
        media=(media,),
        acquisition_root_id=acquisition_root_id,
        correspondences=tuple(
            EntityCorrespondence(item.source_target_id, item.canonical_target_id)
            for item in decisions
            if item.status is VisualCorrespondenceStatus.MATCHED
        ),
        visual_only_target_ids=tuple(
            item.source_target_id
            for item in decisions
            if item.status is VisualCorrespondenceStatus.UNMATCHED
        ),
    )
    return BrowserGymVisualProjection(
        source,
        tuple(private),
        decisions,
        point_grounding_attempted=point_grounder is not None,
        point_grounding_succeeded=point_succeeded,
        provider_failure=provider_failure,
    )


def _atomic_point_instruction(overall_goal: str) -> str:
    return (
        "Select exactly one currently visible control for the next atomic interaction that "
        "advances the overall goal. If the final target is hidden behind a menu, dialog, or "
        "panel, select the visible control that reveals it first. Do not point to a hidden "
        "later target and do not solve multiple interactions at once. Overall goal: "
        + overall_goal
    )


def _binding_pair(
    task: TaskGoal,
    frame: VisualFrame,
    region: VisualRegionBinding,
    *,
    correspondence: VisualCorrespondenceDecision,
    page_identity: str,
    episode_identity: str,
) -> tuple[ActionBinding, BrowserGymVisualBinding] | None:
    if (
        correspondence.status is not VisualCorrespondenceStatus.UNMATCHED
        or
        region.primitive_action != "point_activate"
        or region.confidence < MIN_VISUAL_ACTION_CONFIDENCE
    ):
        return None
    try:
        translator = VISUAL_INTERACTION_CAPABILITIES.resolve_primitive(region.primitive_action)
        schema = INTERACTION_CAPABILITY_REGISTRY.parameter_schema(translator.semantic_action)
    except InteractionCapabilityError:
        return None
    classification = classify_surface_action(task, region.role, translator.semantic_action)
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
        translator.semantic_action,
        translator.primitive_action,
        classification.category.value,
        classification.semantic_effects,
        schema,
        {},
        classification.observation_barrier,
        confidence=region.confidence,
        risk=classification.risk,
    )
    return public, BrowserGymVisualBinding(binding_id, page_identity, episode_identity, region)


def _correspondence_decision(
    region: VisualRegionBinding,
    structured_source: SurfaceObservation,
) -> VisualCorrespondenceDecision:
    targets = {item.target_id: item for item in structured_source.targets}
    boxes = {
        item.target_id: (
            float(item.bbox[0]),
            float(item.bbox[1]),
            float(item.bbox[2]),
            float(item.bbox[3]),
        )
        for media in structured_source.media
        for item in media.grounding_regions
        if item.target_id in targets
    }
    geometric = []
    for target_id, bbox in boxes.items():
        score = _geometry_score(region.bbox_xywh, bbox)
        if score > 0:
            geometric.append((target_id, score))
    compatible = [
        (target_id, score)
        for target_id, score in geometric
        if _semantically_compatible(region, targets[target_id])
    ]
    if len(compatible) == 1:
        return VisualCorrespondenceDecision(
            region.region_id,
            VisualCorrespondenceStatus.MATCHED,
            compatible[0][0],
        )
    if len(compatible) > 1:
        return VisualCorrespondenceDecision(
            region.region_id,
            VisualCorrespondenceStatus.AMBIGUOUS,
        )
    if geometric:
        return VisualCorrespondenceDecision(
            region.region_id,
            VisualCorrespondenceStatus.CONFLICT,
        )

    exact_semantic = [
        target.target_id
        for target in targets.values()
        if _exact_semantic_match(region, target)
    ]
    if len(exact_semantic) == 1:
        return VisualCorrespondenceDecision(
            region.region_id,
            VisualCorrespondenceStatus.MATCHED,
            exact_semantic[0],
        )
    if len(exact_semantic) > 1:
        return VisualCorrespondenceDecision(
            region.region_id,
            VisualCorrespondenceStatus.AMBIGUOUS,
        )
    return VisualCorrespondenceDecision(
        region.region_id,
        VisualCorrespondenceStatus.UNMATCHED,
    )


def _geometry_score(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    intersection_width = max(
        0.0,
        min(left_x + left_width, right_x + right_width) - max(left_x, right_x),
    )
    intersection_height = max(
        0.0,
        min(left_y + left_height, right_y + right_height) - max(left_y, right_y),
    )
    intersection = intersection_width * intersection_height
    if intersection <= 0:
        return 0.0
    left_area = left_width * left_height
    right_area = right_width * right_height
    union = left_area + right_area - intersection
    iou = intersection / union if union > 0 else 0.0
    containment = intersection / min(left_area, right_area)
    if iou < 0.2 and containment < 0.6:
        return 0.0
    return max(iou, containment)


def _semantically_compatible(region: VisualRegionBinding, target: SemanticTarget) -> bool:
    if not _roles_compatible(region.role, target.role):
        return False
    visual_label = _normalized_text(region.label)
    structured_label = _normalized_text(target.label)
    if not visual_label or not structured_label:
        return True
    return (
        visual_label == structured_label
        or visual_label in structured_label
        or structured_label in visual_label
    )


def _exact_semantic_match(region: VisualRegionBinding, target: SemanticTarget) -> bool:
    return (
        _roles_compatible(region.role, target.role)
        and bool(_normalized_text(region.label))
        and _normalized_text(region.label) == _normalized_text(target.label)
    )


def _roles_compatible(left: str, right: str) -> bool:
    normalized_left, normalized_right = left.casefold().strip(), right.casefold().strip()
    if normalized_left == normalized_right:
        return True
    interactive = {
        "button", "link", "option", "cell", "gridcell", "shape", "img", "image",
    }
    return normalized_left in interactive and normalized_right in interactive


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE))


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
