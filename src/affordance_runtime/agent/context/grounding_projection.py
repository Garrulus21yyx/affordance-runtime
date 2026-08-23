"""Bounded public visual evidence selection and executable route binding."""

from __future__ import annotations

from dataclasses import dataclass, replace

from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.context import (
    AgentGroundingEntityView,
    AgentGroundingIndexView,
    AgentImageActionRoute,
    AgentImageInput,
    AgentImageMark,
    AgentImageOperandRole,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref
from affordance_runtime.world.public_refs import PublicRefCodec
from affordance_runtime.world.visual_annotation import (
    BoundingBox,
    VisualMark,
    annotate_screenshot_result,
)


@dataclass(frozen=True)
class VisualMarkCandidate:
    ref: str
    bbox: tuple[int, int, int, int]
    confidence: float

    def __post_init__(self) -> None:
        x, y, width, height = self.bbox if len(self.bbox) == 4 else (0, 0, 0, 0)
        if (
            not PublicRefCodec.accepts(self.ref)
            or self.ref[:1] not in {"E", "N"}
            or len(self.bbox) != 4
            or any(type(value) is not int for value in self.bbox)
            or x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("visual mark candidate is invalid")
        object.__setattr__(self, "bbox", tuple(self.bbox))


@dataclass(frozen=True)
class VisualMarkCandidateSet:
    items: tuple[VisualMarkCandidate, ...]
    total_count: int
    limit: int

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if (
            self.limit < 1
            or self.total_count < len(items)
            or len(items) > self.limit
            or len({item.ref for item in items}) != len(items)
            or any(not isinstance(item, VisualMarkCandidate) for item in items)
        ):
            raise ValueError("visual mark candidate set is invalid")
        object.__setattr__(self, "items", items)

    @property
    def truncated(self) -> bool:
        return len(self.items) < self.total_count


@dataclass(frozen=True)
class GroundingProjectionResult:
    index: AgentGroundingIndexView
    images: tuple[AgentImageInput, ...]
    selected_media_refs: tuple[str, ...]


@dataclass(frozen=True)
class GroundingProjection:
    max_images: int = 2
    max_marks_per_image: int = 32

    def __post_init__(self) -> None:
        if self.max_images < 1 or self.max_marks_per_image < 1:
            raise ValueError("grounding projection bounds must be positive")

    def project(
        self,
        observation: WorldObservation,
        projection: CanonicalPublicWorldProjection,
        world,
        *,
        selected_media_ids: tuple[str, ...] = (),
    ) -> GroundingProjectionResult:
        raw_candidates = tuple(
            (item.source_observation_id, item.media)
            for item in observation.media
            for media in (item.media,)
            if media.kind == "screenshot"
            and (not selected_media_ids or media.media_id in selected_media_ids)
        )
        candidates = _deduplicated_media(raw_candidates)[: self.max_images]
        visible = {item.target_id: item for item in world.targets.items}
        ordered_records = tuple(
            item for item in projection.ordered_target_records if item.target_id in visible
        )
        target_refs = {item.target_id: item.ref for item in ordered_records}
        candidate_sets = tuple(
            (
                source_observation_id,
                media,
                visual_mark_candidate_set(
                    projection,
                    media,
                    limit=self.max_marks_per_image,
                ),
            )
            for source_observation_id, media in candidates
        )
        marked_refs = {
            item.ref
            for _source_observation_id, _media, mark_candidates in candidate_sets
            for item in mark_candidates.items
        }
        entities = []
        for record in ordered_records:
            target = visible[record.target_id]
            hints: list[str] = []
            parent = target.relations.get("parent_id")
            if isinstance(parent, str) and parent in target_refs:
                hints.append(f"parent:{target_refs[parent]}")
            children = target.relations.get("child_ids")
            if isinstance(children, tuple | list):
                refs = tuple(
                    target_refs[item]
                    for item in children
                    if isinstance(item, str) and item in target_refs
                )
                if refs:
                    hints.append("children:" + ",".join(refs[:8]))
            entities.append(AgentGroundingEntityView(
                record.ref,
                target.role,
                target.label,
                target.state,
                tuple(hints),
                record.verbs,
                record.ref in marked_refs,
            ))
        images = []
        media_refs = []
        source_by_id = {item.observation_id: item for item in observation.sources}
        for source_observation_id, media, mark_candidates in candidate_sets:
            artifact_ref = canonical_artifact_ref(source_observation_id, media.media_id)
            marks = tuple(
                VisualMark(
                    candidate.ref,
                    candidate.ref,
                    BoundingBox(*candidate.bbox),
                    candidate.confidence,
                    artifact_ref,
                    observation.observation_id,
                    source_by_id[source_observation_id].revision,
                    f"grounding:{candidate.ref}",
                )
                for candidate in mark_candidates.items
            )
            annotation = annotate_screenshot_result(media.data, media.mime_type, marks)
            images.append(AgentImageInput(
                artifact_ref,
                annotation.mime_type,
                annotation.data,
                annotation.sha256,
                media.coordinate_space_id,
                tuple(
                    AgentImageMark(mark.mark_id, mark.bbox.xywh)
                    for mark in annotation.marks
                ),
            ))
            media_refs.append(artifact_ref)
        return GroundingProjectionResult(
            AgentGroundingIndexView(tuple(entities), target_refs),
            tuple(images),
            tuple(media_refs),
        )


def visual_mark_candidate_set(
    projection: CanonicalPublicWorldProjection,
    media,
    *,
    limit: int,
) -> VisualMarkCandidateSet:
    """Select E/N visual evidence in canonical public order, independent of ActionSpace operands."""

    if limit < 1:
        raise ValueError("visual mark candidate limit must be positive")
    regions = {item.target_id: item for item in media.grounding_regions}
    available = tuple(
        VisualMarkCandidate(record.ref, region.bbox, region.confidence)
        for record in projection.ordered_target_records
        if (region := regions.get(record.target_id)) is not None
        and _intersects_media(region.bbox, media.dimensions)
    )
    return VisualMarkCandidateSet(available[:limit], len(available), limit)


def _intersects_media(
    bbox: tuple[int, int, int, int],
    dimensions: tuple[int, int],
) -> bool:
    x, y, width, height = bbox
    media_width, media_height = dimensions
    return x < media_width and y < media_height and x + width > 0 and y + height > 0


def bind_image_action_routes(
    images: tuple[AgentImageInput, ...],
    actions,
) -> tuple[AgentImageInput, ...]:
    """Close actual annotation fragments over exact current public action routes."""

    delivered = []
    for image in images:
        actual_refs = frozenset(mark.ref for mark in image.marks)
        routes = tuple(
            AgentImageActionRoute(
                option.operation,
                option.target_ref,
                destination.grounding_ref if destination is not None else "",
                option.action_id,
                option,
            )
            for option in actions
            for destination in (
                option.destinations.items if option.destination_required else (None,)
            )
            if option.target_ref in actual_refs
            or (destination is not None and destination.grounding_ref in actual_refs)
        )
        marks = tuple(
            AgentImageMark(
                mark.ref,
                mark.bbox,
                tuple(
                    role
                    for role, matched in (
                        (
                            AgentImageOperandRole.SOURCE,
                            any(route.source_ref == mark.ref for route in routes),
                        ),
                        (
                            AgentImageOperandRole.DESTINATION,
                            any(route.destination_ref == mark.ref for route in routes),
                        ),
                    )
                    if matched
                ),
            )
            for mark in image.marks
        )
        delivered.append(replace(image, marks=marks, route_deltas=routes))
    return tuple(delivered)


def _deduplicated_media(candidates):
    """Select one deterministic full-frame capture variant after fusion alignment."""

    grouped = {}
    for source_observation_id, media in sorted(
        candidates,
        key=lambda item: (
            item[1].capture_group_id,
            0 if str(item[1].variant) == "raw" else 1,
            item[0],
            item[1].media_id,
        ),
    ):
        key = (media.capture_group_id, media.dimensions, media.coordinate_space_id)
        if key not in grouped:
            grouped[key] = [source_observation_id, media, {}]
        regions = grouped[key][2]
        for region in media.grounding_regions:
            regions.setdefault(region.target_id, region)
    return tuple(
        (
            grouped[key][0],
            replace(
                grouped[key][1],
                grounding_regions=tuple(grouped[key][2].values()),
            ),
        )
        for key in sorted(grouped)
    )
