"""One immutable current-World delivery shared by one ActionPolicy call."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveryManifest,
    WorldDeliveryView,
    render_compact_actor_world,
)
from affordance_runtime.agent.context.context import AgentContext

_DELIVERY_ID = re.compile(r"^delivery:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ModelTurnDelivery:
    """The sole observation/manifest identity for one model turn.

    The object is a disposable projection.  It owns neither current World truth
    nor action legality; it only guarantees that prompt text, catalog exposure,
    resolver admission, and trace lineage refer to the same rendered delivery.
    """

    view: WorldDeliveryView
    delivery_id: str
    context_id: str
    world_observation_id: str
    includes_images: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.view, WorldDeliveryView):
            raise TypeError("model turn delivery requires a typed WorldDeliveryView")
        if _DELIVERY_ID.fullmatch(self.delivery_id) is None:
            raise ValueError("model turn delivery identity is invalid")
        if not self.context_id.startswith("context:"):
            raise ValueError("model turn delivery requires current Context identity")
        if self.view.manifest.world_observation_id != self.world_observation_id:
            raise ValueError("model turn delivery manifest belongs to another World")
        if type(self.includes_images) is not bool:
            raise TypeError("model turn delivery image selection must be boolean")

    @property
    def manifest(self) -> DeliveryManifest:
        return self.view.manifest


def build_model_turn_delivery(
    context: AgentContext,
    *,
    include_images: bool,
    max_rendered_bytes: int | None = None,
) -> ModelTurnDelivery:
    """Build the one selected delivery for one current ActionPolicy call."""

    search_action_refs = frozenset(
        item.target_ref
        for item in context.actions.options
        if context.actions.active_query or context.actions.active_target_filter
    )
    view = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=include_images,
        region_index=context.region_index,
        observation=context.current_observation,
        delivery_lens=context.delivery_lens,
        selected_region_keys=_selected_region_keys(context),
        selected_cursor=context.delivery_lens.page_cursor if context.delivery_lens is not None else "",
        search_action_refs=search_action_refs,
        action_options=context.complete_actions,
        preference_text=_delivery_preference_text(context),
        max_rendered_bytes=max_rendered_bytes,
    )
    payload = {
        "context_id": context.context_id,
        "world_observation_id": view.manifest.world_observation_id,
        "projection": view.projection,
        "includes_images": include_images,
        "text": view.text,
        "manifest": {
            "executable_refs": view.manifest.executable_refs,
            "readonly_refs": view.manifest.readonly_refs,
            "fact_refs": view.manifest.fact_refs,
            "region_refs": view.manifest.region_refs,
        },
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return ModelTurnDelivery(
        view,
        f"delivery:{digest}",
        context.context_id,
        view.manifest.world_observation_id,
        include_images,
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


def _delivery_preference_text(context: AgentContext) -> str:
    values = [context.task.instruction]
    values.extend(item.objective for item in context.goal_plan.items)
    if context.recent_steps.items:
        latest = context.recent_steps.items[-1]
        if latest.target is not None:
            values.extend((latest.target.role, latest.target.label, *latest.target.context))
        values.extend(str(value) for value in latest.transition.values())
    lens = context.delivery_lens
    if lens is not None and lens.query:
        values.append(lens.query)
    return " ".join(value for value in values if value)
