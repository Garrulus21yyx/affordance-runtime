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
from affordance_runtime.agent.context.context import (
    AgentContext,
    VisualEvidenceFragment,
)
from affordance_runtime.agent.context.observation_delivery import DeliveryContinuationCapability
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

_DELIVERY_ID = re.compile(r"^delivery:[0-9a-f]{64}$")


@dataclass(frozen=True)
class DeliveredMediaMark:
    ref: str
    bbox: tuple[int, int, int, int]

    def __post_init__(self) -> None:
        if (
            not PublicRefCodec.accepts(self.ref)
            or self.ref[:1] not in {PublicRefKind.EXECUTABLE.value, PublicRefKind.NODE.value}
            or len(self.bbox) != 4
            or any(type(value) is not int for value in self.bbox)
        ):
            raise ValueError("delivered media mark is invalid")
        object.__setattr__(self, "bbox", tuple(self.bbox))


@dataclass(frozen=True)
class DeliveredMedia:
    """Exact attached visual evidence; never an action-authorization source."""

    evidence_ref: str
    mime_type: str
    data: bytes = field(repr=False)
    sha256: str
    coordinate_space_id: str = field(repr=False, compare=False)
    actual_marks: tuple[DeliveredMediaMark, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.evidence_ref.startswith("artifact:")
            or self.mime_type not in {"image/png", "image/jpeg"}
            or not isinstance(self.data, bytes)
            or not self.data
            or hashlib.sha256(self.data).hexdigest() != self.sha256
            or not self.coordinate_space_id.strip()
        ):
            raise ValueError("delivered media payload is invalid")
        marks = tuple(self.actual_marks)
        if (
            any(not isinstance(item, DeliveredMediaMark) for item in marks)
            or len({item.ref for item in marks}) != len(marks)
        ):
            raise ValueError("delivered media marks are invalid")
        object.__setattr__(self, "actual_marks", marks)


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
    media: tuple[DeliveredMedia, ...] = ()
    admitted_record_counts: tuple[tuple[str, int], ...] = ()
    packing_backoff_count: int = 0
    continuation_capabilities: tuple[DeliveryContinuationCapability, ...] = field(
        default=(), repr=False, compare=False, metadata={"serialize": False}
    )

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
        capabilities = tuple(self.continuation_capabilities)
        if (
            any(not isinstance(item, DeliveryContinuationCapability) for item in capabilities)
            or len({item.scope for item in capabilities}) != len(capabilities)
        ):
            raise ValueError("model turn continuation capabilities are invalid")
        object.__setattr__(self, "continuation_capabilities", capabilities)
        if any(item.target_ref not in self.manifest.executable_refs for item in self.action_candidates.candidates):
            raise ValueError("every action candidate must enter the same DeliveryManifest")
        if any(
            destination.target_ref not in self.manifest.executable_refs
            for item in self.action_candidates.candidates
            for destination in item.destinations
        ):
            raise ValueError("every candidate destination must enter the same DeliveryManifest")
        media = tuple(self.media)
        if any(not isinstance(item, DeliveredMedia) for item in media):
            raise TypeError("model turn media must contain exact admitted image records")
        route_refs = {
            ref
            for route in self.manifest.action_routes
            for ref in (route.source_ref, route.destination_ref)
            if ref
        }
        if set(self.manifest.executable_refs) != route_refs:
            raise ValueError("every delivered executable must participate in an exact action route")
        visible_refs = set(re.findall(r"\b[ENFR][1-9][0-9]*\b", self.view.text)) | {
            mark.ref for item in media for mark in item.actual_marks
        }
        manifest_refs = {
            *self.manifest.executable_refs,
            *self.manifest.readonly_refs,
            *self.manifest.fact_refs,
            *self.manifest.region_refs,
        }
        if not manifest_refs.issubset(visible_refs):
            raise ValueError("delivery Manifest contains a ref absent from admitted text/media")
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
    continuation_capabilities = context.delivery_store.continuation_capabilities(selected_counts)
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
    selected_effect_header = context.observation_delivery.effect_header
    if selected_effect_header is not None:
        selected_effect_header = replace(
            selected_effect_header,
            continuation_available=any(item.scope == "effect" for item in continuation_capabilities),
        )
    delivered_action_refs = {
        ref
        for candidate in selected_candidates.candidates
        for ref in (
            candidate.target_ref,
            *(item.target_ref for item in candidate.destinations),
        )
    }
    selected_observation_delivery = replace(
        context.observation_delivery,
        effect_header=selected_effect_header,
        latest_effect_values=tuple(
            replace(item, public_ref="")
            if item.public_ref.startswith("E") and item.public_ref not in delivered_action_refs
            else item
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
        canonical_world=context.canonical_world,
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
            "continuation_available": bool(continuation_capabilities),
            "continuation_scopes": tuple(item.scope for item in continuation_capabilities),
            "packing_backoff_count": packing_backoff_count,
        },
    )
    media = _delivered_media(context.image_inputs) if include_images else ()
    manifest = _manifest_with_media_evidence(rendered.manifest, media)
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
                "marks": tuple((mark.ref, mark.bbox) for mark in item.actual_marks),
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
        continuation_capabilities,
    )


def _delivered_media(
    images: tuple[VisualEvidenceFragment, ...],
) -> tuple[DeliveredMedia, ...]:
    """Preserve exact image bytes and marks without inferring action authority."""

    delivered = []
    for image in images:
        marks = tuple(
            DeliveredMediaMark(
                mark.ref,
                mark.bbox,
            )
            for mark in image.marks
        )
        delivered.append(
            DeliveredMedia(
                image.evidence_ref,
                image.mime_type,
                image.data,
                image.sha256,
                image.coordinate_space_id,
                marks,
            )
        )
    return tuple(delivered)


def _manifest_with_media_evidence(
    text_manifest: DeliveryManifest,
    media: tuple[DeliveredMedia, ...],
) -> DeliveryManifest:
    """Add visible read-only marks without allowing media to authorize actions."""

    readonly = list(text_manifest.readonly_refs)
    for item in media:
        for mark in item.actual_marks:
            if mark.ref.startswith("N") and mark.ref not in readonly:
                readonly.append(mark.ref)
    return DeliveryManifest(
        text_manifest.executable_refs,
        tuple(readonly),
        text_manifest.fact_refs,
        text_manifest.region_refs,
        text_manifest.action_routes,
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
