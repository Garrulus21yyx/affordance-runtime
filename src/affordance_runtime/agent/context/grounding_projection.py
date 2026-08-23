"""Route-free E-ref, media-selection, and screenshot-mark projection."""

from __future__ import annotations

from dataclasses import dataclass, replace

from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.context import (
    AgentGroundingEntityView,
    AgentGroundingIndexView,
    AgentImageInput,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref
from affordance_runtime.world.visual_annotation import (
    BoundingBox,
    VisualMark,
    annotate_screenshot_result,
)


@dataclass(frozen=True)
class GroundingProjectionResult:
    index: AgentGroundingIndexView
    images: tuple[AgentImageInput, ...]
    selected_media_refs: tuple[str, ...]


@dataclass(frozen=True)
class GroundingProjection:
    max_images: int = 2

    def project(
        self,
        observation: WorldObservation,
        projection: CanonicalPublicWorldProjection,
        world,
        actions,
        *,
        selected_media_ids: tuple[str, ...] = (),
        selected_target_ids: tuple[str, ...] = (),
    ) -> GroundingProjectionResult:
        offered = {
            target_id
            for option in actions.options
            for target_id in (
                option.target_id,
                *(item.destination_id for item in option.destinations.items),
            )
        }
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
        selected_regions = {
            region.target_id for _, media in candidates for region in media.grounding_regions
        }
        selected = set(selected_target_ids) if selected_target_ids else offered
        marked_targets = offered.intersection(selected).intersection(target_refs).intersection(selected_regions)
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
                target.target_id in marked_targets,
            ))
        images = []
        media_refs = []
        source_by_id = {item.observation_id: item for item in observation.sources}
        for source_observation_id, media in candidates:
            artifact_ref = canonical_artifact_ref(source_observation_id, media.media_id)
            marks = tuple(
                VisualMark(
                    target_refs[region.target_id],
                    target_refs[region.target_id],
                    BoundingBox(*region.bbox),
                    region.confidence,
                    artifact_ref,
                    observation.observation_id,
                    source_by_id[source_observation_id].revision,
                    f"grounding:{region.target_id}",
                )
                for region in media.grounding_regions
                if region.target_id in marked_targets
            )
            annotation = annotate_screenshot_result(media.data, media.mime_type, marks)
            images.append(AgentImageInput(
                artifact_ref,
                annotation.mime_type,
                annotation.data,
                annotation.sha256,
                media.coordinate_space_id,
                tuple((mark.mark_id, mark.bbox.xywh) for mark in annotation.marks),
            ))
            media_refs.append(artifact_ref)
        return GroundingProjectionResult(
            AgentGroundingIndexView(tuple(entities), target_refs),
            tuple(images),
            tuple(media_refs),
        )


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
