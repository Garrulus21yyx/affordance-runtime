"""Route-free E-ref, media-selection, and screenshot-mark projection."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.agent.context.context import (
    AgentGroundingEntityView,
    AgentGroundingIndexView,
    AgentImageInput,
)
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind
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
        world,
        actions,
        *,
        selected_media_ids: tuple[str, ...] = (),
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
        region_order: dict[str, tuple[int, int, int, int]] = {}
        for _, media in candidates:
            for region in media.grounding_regions:
                region_order.setdefault(region.target_id, region.bbox)
        targets_by_id = {item.target_id: item for item in world.targets.items}
        options_by_target: dict[str, list[object]] = {}
        for option in actions.options:
            options_by_target.setdefault(option.target_id, []).append(option)
        ordered_targets = tuple(sorted(
            world.targets.items,
            key=lambda item: (
                0 if item.target_id in region_order else 1,
                region_order.get(item.target_id, (0, 0, 0, 0))[1],
                region_order.get(item.target_id, (0, 0, 0, 0))[0],
                _public_target_order_key(item, targets_by_id, options_by_target),
            ),
        ))
        target_refs: dict[str, str] = {}
        executable_index = 1
        readonly_index = 1
        for target in ordered_targets:
            if target.target_id in offered:
                target_refs[target.target_id] = PublicRefCodec.encode(PublicRefKind.EXECUTABLE, executable_index)
                executable_index += 1
            else:
                target_refs[target.target_id] = PublicRefCodec.encode(PublicRefKind.NODE, readonly_index)
                readonly_index += 1
        selected_regions = {
            region.target_id for _, media in candidates for region in media.grounding_regions
        }
        marked_targets = offered.intersection(target_refs).intersection(selected_regions)
        verbs: dict[str, list[str]] = {}
        for option in actions.options:
            verbs.setdefault(option.target_id, []).append(
                INTERACTION_CAPABILITY_REGISTRY.require(option.semantic_action).semantic_action
            )
        entities = []
        for target in ordered_targets:
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
                target_refs[target.target_id],
                target.role,
                target.label,
                target.state,
                tuple(hints),
                tuple(dict.fromkeys(verbs.get(target.target_id, ()))),
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


def _public_target_order_key(target, targets_by_id, options_by_target) -> str:
    def semantic(target_id: str) -> object:
        item = targets_by_id.get(target_id)
        return (
            (item.role, item.label, to_json_compatible(item.state))
            if item is not None
            else ("unknown", "", {})
        )

    relation_context: list[tuple[str, object]] = []
    for key, value in target.relations.items():
        normalized = str(key).casefold()
        if normalized.endswith("parent_id") and isinstance(value, str):
            relation_context.append((normalized, semantic(value)))
        elif normalized.endswith("child_ids") and isinstance(value, tuple | list):
            relation_context.append(
                (normalized, tuple(sorted((semantic(item) for item in value if isinstance(item, str)), key=repr)))
            )
        elif not normalized.endswith("_id") and not normalized.endswith("_ids"):
            relation_context.append((normalized, to_json_compatible(value)))
    routes = []
    for option in options_by_target.get(target.target_id, ()):
        routes.append(
            (
                option.semantic_action,
                to_json_compatible(option.parameter_schema),
                tuple(
                    sorted(
                        (semantic(item.destination_id) for item in option.destinations.items),
                        key=repr,
                    )
                ),
            )
        )
    return json.dumps(
        to_json_compatible(
            (
                target.role,
                target.label,
                target.state,
                tuple(sorted(relation_context, key=lambda item: item[0])),
                tuple(sorted(routes, key=repr)),
            )
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
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
