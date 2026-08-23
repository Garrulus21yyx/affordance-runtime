"""One immutable current-World delivery shared by one ActionPolicy call."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from affordance_runtime.agent.context.action_candidate_projection import (
    ActionCandidateProjection,
    ActionDeliveryPlan,
    ActionRouteIssueFragment,
    WorldDeliveryRecord,
)
from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveryManifest,
    WorldDeliveryView,
    render_compact_actor_world,
)
from affordance_runtime.agent.context.context import AgentContext, AgentImageInput
from affordance_runtime.immutable import to_json_compatible

_DELIVERY_ID = re.compile(r"^delivery:[0-9a-f]{64}$")


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
    action_candidates: ActionCandidateProjection = field(
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    action_delivery_plan_id: str
    media: tuple[AgentImageInput, ...] = ()
    admitted_record_counts: tuple[tuple[str, int], ...] = ()
    packing_backoff_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.view, WorldDeliveryView):
            raise TypeError("model turn delivery requires a typed WorldDeliveryView")
        if _DELIVERY_ID.fullmatch(self.delivery_id) is None:
            raise ValueError("model turn delivery identity is invalid")
        if not self.context_id.startswith("context:"):
            raise ValueError("model turn delivery requires current Context identity")
        if not isinstance(self.action_candidates, ActionCandidateProjection):
            raise TypeError("model turn delivery requires typed action candidates")
        if not self.action_delivery_plan_id.startswith("action-delivery-plan:"):
            raise ValueError("model turn requires the sibling action delivery plan")
        admitted = dict(self.admitted_record_counts)
        if len(admitted) != len(self.admitted_record_counts):
            raise ValueError("model turn admitted obligation kinds must be unique")
        if any(type(value) is not int or value < 0 for value in admitted.values()):
            raise ValueError("model turn admitted obligation prefix is invalid")
        if self.packing_backoff_count < 0:
            raise ValueError("model turn packing backoff count is invalid")
        if any(item.target_ref not in self.manifest.executable_refs for item in self.action_candidates.candidates):
            raise ValueError("every action candidate must enter the same DeliveryManifest")
        if any(
            destination.target_ref not in self.manifest.executable_refs
            for item in self.action_candidates.candidates
            for destination in item.destinations
        ):
            raise ValueError("every candidate destination must enter the same DeliveryManifest")
        media = tuple(self.media)
        if any(not isinstance(item, AgentImageInput) for item in media):
            raise TypeError("model turn media must contain exact admitted image records")
        if any(ref not in self.manifest.executable_refs for item in media for ref, _ in item.marks):
            raise ValueError("attached actionable marks must belong to delivered action routes")
        object.__setattr__(self, "media", media)


def build_model_turn_delivery(
    context: AgentContext,
    *,
    include_images: bool,
    admitted_records: Mapping[str, int] | None = None,
    packing_backoff_count: int = 0,
) -> ModelTurnDelivery:
    """Build the one selected delivery for one current ActionPolicy call."""

    if context.action_delivery_plan is None:
        raise ValueError("AgentContext requires an ActionDeliveryPlan before model delivery")
    selected_counts = (
        context.action_delivery_plan.bounded_preview_counts()
        if admitted_records is None
        else dict(admitted_records)
    )
    selected_candidates = context.action_delivery_plan.projection(selected_counts)
    selected_records = _selected_records(context.action_delivery_plan, selected_counts)
    effect_indices = {
        item.record_index
        for item in selected_records
        if isinstance(item, WorldDeliveryRecord) and item.record_kind == "effect"
    }
    directory_indices = {
        item.record_index
        for item in selected_records
        if isinstance(item, WorldDeliveryRecord) and item.record_kind == "page_directory"
    }
    effect_record_total = sum(
        1
        for obligation in context.action_delivery_plan.obligations
        for item in obligation.records
        if isinstance(item, WorldDeliveryRecord) and item.record_kind == "effect"
    )
    selected_effect_header = context.observation_delivery.effect_header
    if selected_effect_header is not None:
        selected_effect_header = replace(
            selected_effect_header,
            continuation_available=len(effect_indices) < effect_record_total,
        )
    selected_observation_delivery = replace(
        context.observation_delivery,
        effect_header=selected_effect_header,
        latest_effect_values=tuple(
            item
            for index, item in enumerate(context.observation_delivery.latest_effect_values)
            if index in effect_indices
        ),
        recovery_directory=tuple(
            item
            for index, item in enumerate(context.observation_delivery.recovery_directory)
            if index in directory_indices
        ),
        page_outline=(),
        changed_regions=(),
    )
    selected_issues = tuple(
        item for item in selected_records if isinstance(item, ActionRouteIssueFragment)
    )
    rendered = render_compact_actor_world(
        context.actor_world,
        context.grounding,
        include_images=include_images,
        region_index=context.region_index,
        observation=context.current_observation,
        selected_region_keys=frozenset(),
        action_candidates=selected_candidates,
        action_route_issues=selected_issues,
        public_fact_bindings=context.private_fact_bindings,
        evidence_index=context.evidence_index,
        observation_delivery=selected_observation_delivery,
    )
    view = replace(
        rendered.view,
        coverage={
            **dict(rendered.view.coverage),
            "candidate_region_expansion_reason": "none",
            "admitted_obligations": tuple(sorted(selected_counts.items())),
            "continuation_available": any(
                selected_counts.get(item.kind.value, 0) < len(item.remaining)
                for item in context.action_delivery_plan.obligations
            ),
            "continuation_scopes": tuple(
                item.continuation_scope
                for item in context.action_delivery_plan.obligations
                if selected_counts.get(item.kind.value, 0) < len(item.remaining)
            ),
            "packing_backoff_count": packing_backoff_count,
        },
    )
    manifest = rendered.manifest
    routed_refs = {ref for route in manifest.action_routes for ref in (route.source_ref, route.destination_ref) if ref}
    media = (
        tuple(
            replace(
                item,
                marks=tuple(mark for mark in item.marks if mark[0] in routed_refs),
            )
            for item in context.image_inputs
        )
        if include_images
        else ()
    )
    payload = {
        "projection": view.projection,
        "text": view.text,
        "manifest": {
            "executable_refs": manifest.executable_refs,
            "readonly_refs": manifest.readonly_refs,
            "fact_refs": manifest.fact_refs,
            "region_refs": manifest.region_refs,
            "action_routes": to_json_compatible(manifest.action_routes),
        },
        "media": tuple(
            {
                "ref": item.evidence_ref,
                "mime": item.mime_type,
                "digest": item.sha256,
                "coordinate_space": item.coordinate_space_id,
                "marks": item.marks,
            }
            for item in media
        ),
        "action_candidates": selected_candidates.projection_id,
        "action_delivery_plan": context.action_delivery_plan.plan_id,
        "admitted_record_counts": tuple(sorted(selected_counts.items())),
        "packing_backoff_count": packing_backoff_count,
        "public_effect": tuple(to_json_compatible(item) for item in selected_observation_delivery.latest_effect_values),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return ModelTurnDelivery(
        view,
        manifest,
        f"delivery:{digest}",
        context.context_id,
        selected_candidates,
        context.action_delivery_plan.plan_id,
        media,
        tuple(sorted(selected_counts.items())),
        packing_backoff_count,
    )


def _selected_records(
    plan: ActionDeliveryPlan,
    admitted: Mapping[str, int],
) -> tuple[object, ...]:
    return tuple(
        record
        for obligation in plan.obligations
        for record in obligation.remaining[: admitted.get(obligation.kind.value, 0)]
    )
