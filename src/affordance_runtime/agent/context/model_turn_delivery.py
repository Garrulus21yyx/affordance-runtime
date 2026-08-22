"""One immutable current-World delivery shared by one ActionPolicy call."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from affordance_runtime.agent.context.action_candidate_projection import ActionCandidateProjection
from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveryManifest,
    WorldDeliveryView,
    render_compact_actor_world,
)
from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.immutable import to_json_compatible

_DELIVERY_ID = re.compile(r"^delivery:[0-9a-f]{64}$")
DEFAULT_MODEL_DELIVERY_MAX_RENDERED_BYTES = 10 * 1024


@dataclass(frozen=True)
class ModelTurnDelivery:
    """The sole observation/manifest identity for one model turn.

    The object is a disposable projection.  It owns neither current World truth
    nor action legality; it only guarantees that prompt text, catalog exposure,
    resolver admission, and trace lineage refer to the same rendered delivery.
    """

    view: WorldDeliveryView
    manifest: DeliveryManifest
    delivery_id: str
    context_id: str
    world_observation_id: str
    action_candidates: ActionCandidateProjection
    delivery_index: WorldDeliveryIndex
    includes_images: bool = False
    evidence_candidates: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.view, WorldDeliveryView):
            raise TypeError("model turn delivery requires a typed WorldDeliveryView")
        if _DELIVERY_ID.fullmatch(self.delivery_id) is None:
            raise ValueError("model turn delivery identity is invalid")
        if not self.context_id.startswith("context:"):
            raise ValueError("model turn delivery requires current Context identity")
        if self.manifest.world_observation_id != self.world_observation_id:
            raise ValueError("model turn delivery manifest belongs to another World")
        if not isinstance(self.action_candidates, ActionCandidateProjection):
            raise TypeError("model turn delivery requires typed action candidates")
        if self.action_candidates.world_observation_id != self.world_observation_id:
            raise ValueError("model turn candidates belong to another World")
        if (
            not isinstance(self.delivery_index, WorldDeliveryIndex)
            or self.delivery_index.world_observation_id != self.world_observation_id
        ):
            raise ValueError("model turn delivery requires the same current delivery index")
        if any(item.target_ref not in self.manifest.executable_refs for item in self.action_candidates.candidates):
            raise ValueError("every action candidate must enter the same DeliveryManifest")
        if any(
            destination.target_ref not in self.manifest.executable_refs
            for item in self.action_candidates.candidates
            for destination in item.destinations
        ):
            raise ValueError("every candidate destination must enter the same DeliveryManifest")
        if self.evidence_candidates is not None:
            from affordance_runtime.agent.context.evidence_candidate_projection import EvidenceCandidateProjection

            if not isinstance(self.evidence_candidates, EvidenceCandidateProjection):
                raise TypeError("model turn evidence candidates must be typed")
            if self.evidence_candidates.world_observation_id != self.world_observation_id:
                raise ValueError("model turn evidence candidates belong to another World")
            if any(item.fact_ref not in self.manifest.fact_refs for item in self.evidence_candidates.candidates):
                raise ValueError("every evidence candidate must enter the same DeliveryManifest")
        if type(self.includes_images) is not bool:
            raise TypeError("model turn delivery image selection must be boolean")


def build_model_turn_delivery(
    context: AgentContext,
    *,
    include_images: bool,
    max_rendered_bytes: int | None = DEFAULT_MODEL_DELIVERY_MAX_RENDERED_BYTES,
) -> ModelTurnDelivery:
    """Build the one selected delivery for one current ActionPolicy call."""

    if context.action_candidates is None:
        raise ValueError("AgentContext requires a candidate projection before model delivery")
    rendered = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=include_images,
        region_index=context.region_index,
        observation=context.current_observation,
        delivery_lens=context.delivery_lens,
        selected_region_keys=_selected_region_keys(context),
        selected_cursor=context.delivery_lens.page_cursor if context.delivery_lens is not None else "",
        action_candidates=context.action_candidates,
        evidence_candidates=context.evidence_candidates,
        public_fact_bindings=context.private_fact_bindings,
        evidence_index=context.evidence_index,
        max_rendered_bytes=max_rendered_bytes,
    )
    payload = {
        "context_id": context.context_id,
        "world_observation_id": rendered.manifest.world_observation_id,
        "projection": rendered.projection,
        "includes_images": include_images,
        "text": rendered.text,
        "manifest": {
            "executable_refs": rendered.manifest.executable_refs,
            "readonly_refs": rendered.manifest.readonly_refs,
            "fact_refs": rendered.manifest.fact_refs,
            "region_refs": rendered.manifest.region_refs,
        },
        "action_candidates": context.action_candidates.projection_id,
        "evidence_candidates": to_json_compatible(context.evidence_candidates),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return ModelTurnDelivery(
        rendered.view,
        rendered.manifest,
        f"delivery:{digest}",
        context.context_id,
        rendered.manifest.world_observation_id,
        context.action_candidates,
        context.region_index,
        include_images,
        context.evidence_candidates,
    )

def _selected_region_keys(context: AgentContext) -> frozenset[str]:
    selected: list[str] = []
    lens = context.delivery_lens
    if lens is not None and lens.selected_region_key:
        selected.append(lens.selected_region_key)
    if (
        context.region_index is not None
        and context.current_observation is not None
        and context.recent_steps.items
        and context.recent_steps.items[-1].target is not None
    ):
        historical = context.recent_steps.items[-1].target
        for target in context.current_observation.targets:
            if target.role == historical.role and target.label == historical.label:
                region = context.region_index.region_for_target(target.target_id)
                if region is not None:
                    selected.append(region.key)
                    break
    return frozenset(selected)
