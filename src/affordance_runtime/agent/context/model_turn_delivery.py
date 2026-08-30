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
)
from affordance_runtime.agent.context.compact_world_renderer import (
    DeliveredActionRoute,
    DeliveryManifest,
    WorldDeliveryView,
    render_compact_actor_world,
)
from affordance_runtime.agent.context.context import (
    AgentContext,
    VisualEvidenceFragment,
)
from affordance_runtime.agent.tool_result_projection import (
    committed_tool_call_id,
    project_committed_tool_metadata,
    project_committed_tool_return,
)
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
        if any(not isinstance(item, DeliveredMediaMark) for item in marks) or len({item.ref for item in marks}) != len(
            marks
        ):
            raise ValueError("delivered media marks are invalid")
        object.__setattr__(self, "actual_marks", marks)


@dataclass(frozen=True)
class DeferredToolDelivery:
    """One admitted public return paired to its original external call."""

    tool_call_id: str
    tool_name: str
    return_value: Mapping[str, object]
    metadata: Mapping[str, object] = field(repr=False, compare=False, metadata={"serialize": False})
    failed: bool = False

    def __post_init__(self) -> None:
        if not self.tool_call_id.strip() or not self.tool_name.strip():
            raise ValueError("deferred tool delivery requires one call identity")
        object.__setattr__(self, "return_value", to_json_compatible(self.return_value))
        object.__setattr__(self, "metadata", to_json_compatible(self.metadata))


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
    tool_result: DeferredToolDelivery | None = None
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
        if any(not isinstance(item, DeliveredMedia) for item in media):
            raise TypeError("model turn media must contain exact admitted image records")
        if self.tool_result is not None and not isinstance(self.tool_result, DeferredToolDelivery):
            raise TypeError("model turn deferred result must be typed")
        route_refs = {
            ref for route in self.manifest.action_routes for ref in (route.source_ref, route.destination_ref) if ref
        }
        if set(self.manifest.executable_refs) != route_refs:
            raise ValueError("every delivered executable must participate in an exact action route")
        projected_routes = {
            fragment.public_route for fragment in self.action_candidates.route_fragments
        }
        manifested_routes = {
            (route.operation, route.source_ref, route.destination_ref)
            for route in self.manifest.action_routes
        }
        if not projected_routes.issubset(manifested_routes):
            raise ValueError("every projected capability must enter the same DeliveryManifest")
        projected_operations: dict[str, set[str]] = {}
        for operation, source_ref, _destination_ref in projected_routes:
            projected_operations.setdefault(source_ref, set()).add(operation)
        if any(
            candidate.operation not in projected_operations.get(candidate.target_ref, set())
            for candidate in self.action_candidates.candidates
        ):
            raise ValueError("every action candidate requires one exact delivered operation")
        tool_result_value = self.tool_result.return_value if self.tool_result is not None else {}
        visible_refs = (
            set(re.findall(rf"\b{PublicRefCodec.token_pattern()}\b", self.view.text))
            | {mark.ref for item in media for mark in item.actual_marks}
            | _typed_public_refs_in_value(tool_result_value)
        )
        manifest_refs = {
            *self.manifest.executable_refs,
            *self.manifest.readonly_refs,
            *self.manifest.fact_refs,
            *self.manifest.region_refs,
        }
        if not manifest_refs.issubset(visible_refs):
            raise ValueError("delivery Manifest contains a ref absent from admitted text/media/tool result")
        object.__setattr__(self, "media", media)


def build_model_turn_delivery(
    context: AgentContext,
    *,
    include_images: bool,
    admitted_records: Mapping[str, int] | None = None,
    packing_backoff_count: int = 0,
    committed_step: object | None = None,
    pending_tool_call_id: str = "",
    pending_tool_name: str = "",
) -> ModelTurnDelivery:
    """Build the one selected delivery for one current ActionPolicy call."""

    if context.action_delivery_plan is None:
        raise ValueError("AgentContext requires an ActionDeliveryPlan before model delivery")
    if admitted_records is None:
        selected_counts = context.action_delivery_plan.bounded_preview_counts()
        selected_counts.update(
            {
                obligation.kind.value: obligation.required_record_count
                for obligation in context.action_delivery_plan.obligations
                if obligation.required_record_count
            }
        )
    else:
        selected_counts = dict(admitted_records)
    selected_candidates = context.action_delivery_plan.projection(selected_counts)
    selected_records = _selected_records(context.action_delivery_plan, selected_counts)
    tool_result = _deferred_tool_delivery(
        committed_step,
        pending_tool_call_id,
        pending_tool_name,
    )
    selected_issues = tuple(item for item in selected_records if isinstance(item, ActionRouteIssueFragment))
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
    )
    view = replace(
        rendered.view,
        coverage={
            **dict(rendered.view.coverage),
            "candidate_region_expansion_reason": "none",
            "admitted_obligations": tuple(sorted(selected_counts.items())),
            "packing_backoff_count": packing_backoff_count,
        },
    )
    media = _delivered_media(context.image_inputs) if include_images else ()
    manifest = _manifest_with_media_evidence(rendered.manifest, media)
    manifest = _manifest_with_same_world_tool_grounding(manifest, tool_result, context)
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
        "tool_result": (
            {
                "tool_call_id": tool_result.tool_call_id,
                "tool_name": tool_result.tool_name,
                "return_value": tool_result.return_value,
                "failed": tool_result.failed,
            }
            if tool_result is not None
            else None
        ),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return ModelTurnDelivery(
        view=view,
        manifest=manifest,
        delivery_id=f"delivery:{digest}",
        context_id=context.context_id,
        action_candidates=selected_candidates,
        action_delivery_plan_id=context.action_delivery_plan.plan_id,
        media=media,
        tool_result=tool_result,
        admitted_record_counts=tuple(sorted(selected_counts.items())),
        packing_backoff_count=packing_backoff_count,
    )


def _deferred_tool_delivery(
    committed_step: object | None,
    pending_tool_call_id: str,
    pending_tool_name: str,
) -> DeferredToolDelivery | None:
    if committed_step is None:
        return None
    if type(committed_step).__name__ != "StepResult":
        raise TypeError("deferred tool delivery requires one committed StepResult")
    call_id = committed_tool_call_id(committed_step)
    if not call_id:
        return None
    if call_id != pending_tool_call_id or not pending_tool_name:
        raise ValueError("committed step does not match the pending official call")
    admitted = project_committed_tool_return(committed_step)
    if admitted is None:
        raise ValueError("pending official call requires one projected result")
    return DeferredToolDelivery(
        call_id,
        pending_tool_name,
        admitted,
        project_committed_tool_metadata(committed_step),
        bool(getattr(committed_step, "runtime_failure", None)),
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


def _manifest_with_same_world_tool_grounding(
    manifest: DeliveryManifest,
    tool_result: DeferredToolDelivery | None,
    context: AgentContext,
) -> DeliveryManifest:
    """Admit exact live refs returned by a read tool into this same delivery.

    The ToolReturn is presentation, not action authority.  Its explicit
    ``executable_grounding`` contract may only select routes that still exist
    in the sibling current ActionSpace, and only while both sides of the local
    read identify the one fresh World used by this turn.
    """

    if tool_result is None or tool_result.failed or context.current_observation is None:
        return manifest
    current_world = context.current_observation.observation_id
    if (
        tool_result.metadata.get("before_world") != current_world
        or tool_result.metadata.get("after_world") != current_world
        or tool_result.return_value.get("executable_grounding") != "attached_to_returned_readable_targets"
    ):
        return manifest

    returned_refs = _typed_public_refs_in_value(tool_result.return_value)
    current_regions = set(context.canonical_world.region_refs.values())
    current_nodes = set(context.grounding.target_refs.values())
    current_facts = set(context.private_fact_bindings)
    readonly = [*manifest.readonly_refs]
    facts = [*manifest.fact_refs]
    regions = [*manifest.region_refs]
    for ref in sorted(returned_refs, key=_public_ref_order):
        if ref.startswith("N") and ref in current_nodes and ref not in readonly:
            readonly.append(ref)
        elif ref.startswith("F") and ref in current_facts and ref not in facts:
            facts.append(ref)
        elif ref.startswith("R") and ref in current_regions and ref not in regions:
            regions.append(ref)

    claimed_routes = _returned_read_routes(tool_result.return_value)
    current_routes = {
        (option.operation, option.target_ref, ""): option
        for option in context.complete_actions
        if option.destination_mode == "forbidden"
    }
    executable = [*manifest.executable_refs]
    routes = [*manifest.action_routes]
    existing = {(route.operation, route.source_ref, route.destination_ref) for route in routes}
    for route_key in sorted(claimed_routes):
        option = current_routes.get(route_key)
        if option is None or route_key in existing:
            continue
        _operation, source_ref, _destination_ref = route_key
        if source_ref not in executable:
            executable.append(source_ref)
        routes.append(
            DeliveredActionRoute(
                option.operation,
                source_ref,
                private_action_id=option.action_id,
                private_option=option,
            )
        )
        existing.add(route_key)

    return DeliveryManifest(
        tuple(executable),
        tuple(readonly),
        tuple(facts),
        tuple(regions),
        tuple(routes),
    )


def _returned_read_routes(value: object) -> frozenset[tuple[str, str, str]]:
    routes: set[tuple[str, str, str]] = set()

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            target_ref = str(item.get("target_ref", ""))
            verbs = item.get("verbs", ())
            if PublicRefCodec.accepts(target_ref, expected=PublicRefKind.EXECUTABLE) and isinstance(
                verbs, (tuple, list)
            ):
                routes.update(
                    (str(operation), target_ref, "")
                    for operation in verbs
                    if isinstance(operation, str) and operation.strip()
                )
            for child in item.values():
                visit(child)
        elif isinstance(item, (tuple, list)):
            for child in item:
                visit(child)

    visit(value)
    return frozenset(routes)


_TYPED_PUBLIC_REF_FIELDS = {
    "evidence_ref": PublicRefKind.FACT,
    "fact_ref": PublicRefKind.FACT,
    "node_ref": PublicRefKind.NODE,
    "region_ref": PublicRefKind.REGION,
    "target_ref": PublicRefKind.EXECUTABLE,
}
_TYPED_PUBLIC_REF_SEQUENCE_FIELDS = {
    "evidence_refs": PublicRefKind.FACT,
    "fact_refs": PublicRefKind.FACT,
    "node_refs": PublicRefKind.NODE,
    "region_refs": PublicRefKind.REGION,
    "target_refs": PublicRefKind.EXECUTABLE,
}


def _typed_public_refs_in_value(value: object) -> set[str]:
    """Read authority only from producer-defined public-ref fields."""

    refs: set[str] = set()

    def add(item: object, kind: PublicRefKind) -> None:
        if isinstance(item, str) and PublicRefCodec.accepts(item, expected=kind):
            refs.add(item)

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                raw_key = str(key)
                singular_kind = _TYPED_PUBLIC_REF_FIELDS.get(raw_key)
                sequence_kind = _TYPED_PUBLIC_REF_SEQUENCE_FIELDS.get(raw_key)
                if singular_kind is not None:
                    add(child, singular_kind)
                elif sequence_kind is not None and isinstance(child, tuple | list):
                    for value_item in child:
                        add(value_item, sequence_kind)
                else:
                    visit(child)
        elif isinstance(item, (tuple, list)):
            for child in item:
                visit(child)

    visit(value)
    return refs


def _public_ref_order(ref: str) -> tuple[str, int]:
    decoded = PublicRefCodec.decode(ref)
    return decoded.kind.value, decoded.index


def _selected_records(
    plan: ActionDeliveryPlan,
    admitted: Mapping[str, int],
) -> tuple[object, ...]:
    return tuple(
        record
        for obligation in plan.obligations
        for record in obligation.remaining[: admitted.get(obligation.kind.value, 0)]
    )
