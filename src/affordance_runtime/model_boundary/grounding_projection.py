"""Route-free E-ref, media-selection, and screenshot-mark projection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from affordance_runtime.adapters.som import BoundingBox, VisualMark, annotate_screenshot
from affordance_runtime.model_boundary.context import (
    AgentGroundingEntityView,
    AgentGroundingIndexView,
    AgentImageInput,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref


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
        target_refs = {
            item.target_id: f"E{index}" for index, item in enumerate(world.targets.items, 1)
        }
        offered = {
            target_id
            for option in actions.options
            for target_id in (
                option.target_id,
                *(item.destination_id for item in option.destinations.items),
            )
        }
        raw_candidates = tuple(
            (source, media)
            for source in observation.sources
            for media in source.media
            if media.kind == "screenshot"
            and (not selected_media_ids or media.media_id in selected_media_ids)
        )
        candidates = _deduplicated_media(raw_candidates)[: self.max_images]
        selected_regions = {
            region.target_id for _, media in candidates for region in media.grounding_regions
        }
        marked_targets = offered.intersection(target_refs).intersection(selected_regions)
        verbs: dict[str, list[str]] = {}
        for option in actions.options:
            verbs.setdefault(option.target_id, []).append(_public_verb(option.semantic_action))
        entities = []
        for target in world.targets.items:
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
        for source, media in candidates:
            artifact_ref = canonical_artifact_ref(source.observation_id, media.media_id)
            marks = tuple(
                VisualMark(
                    target_refs[region.target_id],
                    target_refs[region.target_id],
                    BoundingBox(*region.bbox),
                    region.confidence,
                    artifact_ref,
                    observation.observation_id,
                    source.revision,
                    f"grounding:{region.target_id}",
                )
                for region in media.grounding_regions
                if region.target_id in marked_targets
            )
            data = annotate_screenshot(media.data, marks) if marks else media.data
            images.append(AgentImageInput(
                artifact_ref, media.mime_type, data, hashlib.sha256(data).hexdigest(),
            ))
            media_refs.append(artifact_ref)
        return GroundingProjectionResult(
            AgentGroundingIndexView(tuple(entities), target_refs),
            tuple(images),
            tuple(media_refs),
        )


def _public_verb(semantic_action: str) -> str:
    return {"activate": "click", "fill": "fill", "select": "select"}.get(
        semantic_action, semantic_action,
    )


def _deduplicated_media(candidates):
    """Keep one transmitted image per digest while retaining all public regions."""

    grouped = {}
    order = []
    for source, media in candidates:
        if media.sha256 not in grouped:
            grouped[media.sha256] = [source, media, {}]
            order.append(media.sha256)
        regions = grouped[media.sha256][2]
        for region in media.grounding_regions:
            regions.setdefault(region.target_id, region)
    return tuple(
        (
            grouped[digest][0],
            replace(
                grouped[digest][1],
                grounding_regions=tuple(grouped[digest][2].values()),
            ),
        )
        for digest in order
    )
