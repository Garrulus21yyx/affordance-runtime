"""Close current actions over complete bounded public candidate semantics."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    DestinationMode,
)
from affordance_runtime.actions.paging import ActionDiscoveryResult, ActionReranker
from affordance_runtime.actions.space_contracts import ActionSpaceIssue
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context import AgentGroundingEntityView, AgentGroundingIndexView
from affordance_runtime.agent.context.contracts import (
    AgentActionOptionView,
    AgentActionPageView,
    AgentDestinationView,
)
from affordance_runtime.agent.context.observation_delivery import (
    DeliveryInventorySnapshot,
    ObservationDelivery,
    ObservationDeliveryStore,
    PublicEffectInventory,
)
from affordance_runtime.agent.context.world_region_index import (
    FunctionalContainerKind,
    WorldDeliveryIndex,
)
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

_FOCUS_CONTAINER_SOURCE_ROLES = frozenset(
    {
        "checkbox",
        "combobox",
        "listbox",
        "radio",
        "searchbox",
        "spinbutton",
        "switch",
        "textbox",
    }
)


@dataclass(frozen=True)
class ActionCandidateDestination:
    """One current public destination required or offered by a candidate."""

    target_ref: str
    label: str
    role: str
    functional_path: tuple[str, ...]
    region_ref: str
    public_state: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not PublicRefCodec.accepts(self.target_ref, expected=PublicRefKind.EXECUTABLE)
            or not self.role
            or not PublicRefCodec.accepts(self.region_ref, expected=PublicRefKind.REGION)
        ):
            raise ValueError("action candidate destination requires current public identity")
        object.__setattr__(self, "functional_path", tuple(self.functional_path))
        object.__setattr__(self, "public_state", freeze_json(dict(self.public_state)))


@dataclass(frozen=True)
class ActionCandidate:
    """Disposable public ranking of one existing current ActionOption."""

    action_id: str
    target_ref: str
    operation: str
    label: str
    role: str
    functional_path: tuple[str, ...]
    region_ref: str
    public_state: Mapping[str, object] = field(default_factory=dict)
    rank: int = 1
    reasons: tuple[str, ...] = ()
    destination_required: bool = False
    destinations: tuple[ActionCandidateDestination, ...] = ()
    private_option: object | None = field(
        default=None, repr=False, compare=False, metadata={"serialize": False}
    )

    def __post_init__(self) -> None:
        if (
            not self.action_id
            or not PublicRefCodec.accepts(self.target_ref, expected=PublicRefKind.EXECUTABLE)
            or not self.operation
            or not self.role
            or not PublicRefCodec.accepts(self.region_ref, expected=PublicRefKind.REGION)
            or self.rank < 1
        ):
            raise ValueError("action candidate requires current public identity")
        object.__setattr__(self, "functional_path", tuple(self.functional_path))
        object.__setattr__(self, "public_state", freeze_json(dict(self.public_state)))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "destinations", tuple(self.destinations))
        if self.destination_required and not self.destinations:
            raise ValueError("destination-required candidate must close current destinations")
        if len({item.target_ref for item in self.destinations}) != len(self.destinations):
            raise ValueError("candidate destination refs must be unique")
        if self.private_option is None:
            raise ValueError("action candidate requires its private resolver row")


@dataclass(frozen=True)
class ActionCandidateProjection:
    action_space_id: str
    world_observation_id: str
    candidates: tuple[ActionCandidate, ...]
    scope: str = "automatic"
    projection_id: str = ""

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        if not self.action_space_id.strip() or not self.world_observation_id.strip():
            raise ValueError("candidate projection requires current authority identities")
        if self.scope not in {"automatic", "search", "delivery"}:
            raise ValueError("candidate projection scope is invalid")
        if self.scope == "automatic" and len(candidates) > 5:
            raise ValueError("automatic action candidates are bounded to Top-5")
        identities = tuple(
            (
                item.target_ref,
                item.operation,
                tuple(destination.target_ref for destination in item.destinations),
            )
            for item in candidates
        )
        if len(set(identities)) != len(identities):
            raise ValueError("candidate projection route fragments must be unique")
        payload = {
            "scope": self.scope,
            "candidates": tuple(
                {key: value for key, value in to_json_compatible(item).items() if key != "action_id"}
                for item in candidates
            ),
        }
        expected = (
            "action-candidates:"
            + hashlib.sha256(
                json.dumps(
                    to_json_compatible(payload),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
        )
        if self.projection_id and self.projection_id != expected:
            raise ValueError("candidate projection identity does not bind its ranking")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "projection_id", expected)


@dataclass(frozen=True)
class ActionDeliveryFragment:
    """One atomic public route/context fragment proposed for this turn."""

    candidate: ActionCandidate
    inclusion_reason: str
    public_provenance: tuple[str, ...] = ()
    rendered_cost_bytes: int = 0

    def __post_init__(self) -> None:
        if (
            not self.inclusion_reason.strip()
            or self.rendered_cost_bytes < 0
        ):
            raise ValueError("action delivery fragment metadata is invalid")
        object.__setattr__(self, "public_provenance", tuple(self.public_provenance))

    @property
    def route_deltas(self) -> tuple[tuple[str, str, str], ...]:
        if self.candidate.destination_required:
            return tuple(
                (self.candidate.operation, self.candidate.target_ref, item.target_ref)
                for item in self.candidate.destinations
            )
        return ((self.candidate.operation, self.candidate.target_ref, ""),)


@dataclass(frozen=True)
class ActionRouteIssueFragment:
    """One model-visible why-not fact for an atomically unavailable route."""

    code: str
    operation: str
    source_ref: str
    destination_refs: tuple[str, ...]
    conflicting_contract_fields: tuple[str, ...]
    provenance: str = "action_space"
    rendered_cost_bytes: int = 0

    def __post_init__(self) -> None:
        if (
            self.code != "action_route_conflict"
            or not self.operation.strip()
            or not PublicRefCodec.accepts(self.source_ref)
            or any(not PublicRefCodec.accepts(item) for item in self.destination_refs)
            or not self.conflicting_contract_fields
            or not self.provenance.strip()
            or self.rendered_cost_bytes < 0
        ):
            raise ValueError("action route issue fragment is invalid")
        object.__setattr__(self, "destination_refs", tuple(self.destination_refs))
        object.__setattr__(
            self,
            "conflicting_contract_fields",
            tuple(sorted(set(self.conflicting_contract_fields))),
        )


class DeliveryObligationKind(StrEnum):
    EXPLICIT_QUERY = "query"
    PUBLIC_EFFECT = "effect_actions"
    INTERACTION = "interaction"
    BASE_ACTIONS = "base"
    PAGE_DIRECTORY = "page_directory"
    DESTINATION_ROUTES = "destinations"
    ROUTE_ISSUES = "issues"


@dataclass(frozen=True)
class WorldDeliveryRecord:
    """One atomic record already owned by ObservationDelivery."""

    record_kind: str
    record_index: int
    rendered_cost_bytes: int
    route_fragments: tuple[ActionDeliveryFragment, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.record_kind not in {"effect", "page_directory"}
            or type(self.record_index) is not int
            or self.record_index < 0
            or self.rendered_cost_bytes < 0
        ):
            raise ValueError("World delivery record is invalid")
        object.__setattr__(self, "route_fragments", tuple(self.route_fragments))


DeliveryAtomicRecord = ActionDeliveryFragment | ActionRouteIssueFragment | WorldDeliveryRecord


@dataclass(frozen=True)
class DeliveryObligation:
    """One bounded protocol group over a complete deterministic inventory."""

    kind: DeliveryObligationKind
    records: tuple[DeliveryAtomicRecord, ...]
    priority: int
    inventory: DeliveryInventorySnapshot = field(
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )
    continuation_scope: str = ""
    source_coverage: str = "complete"
    result_coverage: str = "complete"
    public_provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.records)
        if (
            not isinstance(self.kind, DeliveryObligationKind)
            or self.priority < 0
            or not isinstance(self.inventory, DeliveryInventorySnapshot)
            or self.inventory.kind != self.kind.value
            or self.inventory.records != records
            or self.source_coverage not in {"complete", "partial", "unavailable"}
            or self.result_coverage not in {"complete", "partial", "empty"}
        ):
            raise ValueError("delivery obligation is invalid")
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "public_provenance", tuple(self.public_provenance))

    @property
    def remaining(self) -> tuple[DeliveryAtomicRecord, ...]:
        return self.records[self.inventory.offset :]


@dataclass(frozen=True)
class ActionDeliveryPlan:
    """Immutable per-World discoverability result; never episode authority."""

    action_space_id: str
    world_observation_id: str
    obligations: tuple[DeliveryObligation, ...]
    foreground_scope: str | None
    plan_id: str = ""
    requested_scope: str | None = field(
        default=None, repr=False, compare=False, metadata={"serialize": False}
    )

    def __post_init__(self) -> None:
        obligations = tuple(sorted(self.obligations, key=lambda item: (item.priority, item.kind.value)))
        if (
            not self.action_space_id.strip()
            or not self.world_observation_id.strip()
            or len({item.kind for item in obligations}) != len(obligations)
            or any(not isinstance(item, DeliveryObligation) for item in obligations)
        ):
            raise ValueError("action delivery plan is invalid")
        requested = next(
            (
                item.continuation_scope or item.kind.value
                for item in obligations
                if item.remaining
                and (item.continuation_scope or item.kind.value) == self.requested_scope
            ),
            None,
        )
        expected_foreground = requested or next(
            (item.continuation_scope or item.kind.value for item in obligations if item.remaining), None
        )
        if self.foreground_scope != expected_foreground:
            raise ValueError("delivery foreground must be mechanically derived")
        payload = {
            "obligations": tuple(_public_obligation_value(item) for item in obligations),
            "foreground_scope": self.foreground_scope,
        }
        expected = (
            "action-delivery-plan:"
            + hashlib.sha256(
                json.dumps(
                    to_json_compatible(payload),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
        )
        if self.plan_id and self.plan_id != expected:
            raise ValueError("action delivery plan identity does not bind its public contents")
        object.__setattr__(self, "obligations", obligations)
        object.__setattr__(self, "plan_id", expected)

    def projection(self, admitted: Mapping[str, int] | None = None) -> ActionCandidateProjection:
        counts = dict(admitted or {})
        fragments: list[ActionDeliveryFragment] = []
        seen_routes: set[tuple[str, str, str]] = set()
        for obligation in self.obligations:
            count = counts.get(obligation.kind.value, len(obligation.remaining) if admitted is None else 0)
            if not 0 <= count <= len(obligation.remaining):
                raise ValueError("admitted obligation prefix is invalid")
            for record in obligation.remaining[:count]:
                route_fragments = (
                    (record,)
                    if isinstance(record, ActionDeliveryFragment)
                    else record.route_fragments
                    if isinstance(record, WorldDeliveryRecord)
                    else ()
                )
                for fragment in route_fragments:
                    new_routes = tuple(route for route in fragment.route_deltas if route not in seen_routes)
                    if not new_routes:
                        continue
                    seen_routes.update(new_routes)
                    fragments.append(fragment)
        candidates = tuple(replace(item.candidate, rank=index) for index, item in enumerate(fragments, 1))
        return ActionCandidateProjection(
            self.action_space_id,
            self.world_observation_id,
            candidates,
            "delivery",
        )

    def obligation(self, kind: DeliveryObligationKind) -> DeliveryObligation | None:
        return next((item for item in self.obligations if item.kind is kind), None)

    def bounded_preview_counts(self) -> dict[str, int]:
        """Bounded non-authoritative preview for non-provider diagnostics."""

        return {
            item.kind.value: min(
                len(item.remaining),
                1 if item.kind in {DeliveryObligationKind.PUBLIC_EFFECT, DeliveryObligationKind.PAGE_DIRECTORY} else 5,
            )
            for item in self.obligations
        }


@dataclass(frozen=True)
class ActionDeliveryPlanningResult:
    plan: ActionDeliveryPlan
    store: ObservationDeliveryStore

    def __post_init__(self) -> None:
        if not isinstance(self.plan, ActionDeliveryPlan) or not isinstance(
            self.store, ObservationDeliveryStore
        ):
            raise TypeError("delivery planning result requires its typed owner values")


def build_action_delivery_plan(
    *,
    action_space_id: str,
    world_observation_id: str,
    base_actions: tuple[AgentActionOptionView, ...],
    complete_actions: tuple[AgentActionOptionView, ...],
    automatic: ActionCandidateProjection,
    region_index: WorldDeliveryIndex,
    region_refs: Mapping[str, str],
    target_structural_slots: Mapping[str, tuple[str, ...]],
    discovery: ActionDiscoveryResult | None = None,
    action_space_issues: tuple[ActionSpaceIssue, ...] = (),
    target_refs: Mapping[str, str] | None = None,
    observation_delivery: ObservationDelivery | None = None,
    latest_effect: PublicEffectInventory | None = None,
    cursor_store: object | None = None,
) -> ActionDeliveryPlanningResult:
    """Build one bounded-family plan over complete current owner inventories."""

    complete_by_public = {(item.target_ref, item.operation): item for item in complete_actions}
    groups: dict[DeliveryObligationKind, list[DeliveryAtomicRecord]] = defaultdict(list)
    def append(option: AgentActionOptionView, *, kind: DeliveryObligationKind, reason: str) -> None:
        candidate = _candidate_from_option(
            option, region_index, region_refs, rank=1, reasons=(reason,)
        )
        atomic_candidates = (
            tuple(replace(candidate, destinations=(destination,)) for destination in candidate.destinations)
            if candidate.destination_required
            else (candidate,)
        )
        for atomic_candidate in atomic_candidates:
            fragment = ActionDeliveryFragment(
                atomic_candidate,
                reason,
                ("current_action_space", reason),
                len(json.dumps(_public_candidate_value(atomic_candidate), ensure_ascii=False).encode()),
            )
            assigned_routes = {
                route
                for current in groups[kind]
                if isinstance(current, ActionDeliveryFragment)
                for route in current.route_deltas
            }
            if fragment.route_deltas[0] not in assigned_routes:
                groups[kind].append(fragment)

    query_options: list[tuple[AgentActionOptionView, bool]] = []
    stored_query = getattr(cursor_store, "action_query", None)
    query_matches = (
        stored_query.matches
        if discovery is not None
        and stored_query is not None
        and stored_query.query == discovery.query
        and stored_query.world_lineage == world_observation_id
        and stored_query.action_space_lineage == action_space_id
        else discovery.matches
        if discovery is not None
        else ()
    )
    if discovery is not None and discovery.query:
        for match in query_matches:
            option = complete_by_public.get((match.target_ref, match.operation))
            if option is None:
                continue
            option = replace(
                option,
                target_label=match.label,
                target_role=match.role,
            )
            if match.destination_refs:
                option = replace(
                    option,
                    destinations=replace(
                        option.destinations,
                        items=tuple(
                            item for item in option.destinations.items if item.grounding_ref in match.destination_refs
                        ),
                    ),
                )
            exact = bool(set(match.match_kinds) & {"exact_label", "role", "operation"})
            query_options.append((option, exact))

    for option, exact in query_options:
        if exact:
            append(option, kind=DeliveryObligationKind.EXPLICIT_QUERY, reason="query_exact")
    for option, exact in query_options:
        if not exact:
            append(option, kind=DeliveryObligationKind.EXPLICIT_QUERY, reason="query_semantic")

    effect_slots = set(latest_effect.changed_target_slot_keys if latest_effect is not None else ())
    for option in sorted(complete_actions, key=_public_option_view_order):
        if target_structural_slots.get(option.target_id, ()) in effect_slots:
            append(option, kind=DeliveryObligationKind.PUBLIC_EFFECT, reason="public_effect")

    options_by_target = {item.target_id: item for item in complete_actions}
    focused_containers = {
        target_context.primary_region_key
        for target_id, target_context in region_index.target_contexts.items()
        if target_context.focused
        and target_context.container_kind in {FunctionalContainerKind.FORM, FunctionalContainerKind.SEARCH}
        and target_id in options_by_target
        and options_by_target[target_id].target_role in _FOCUS_CONTAINER_SOURCE_ROLES
    }
    for option in sorted(complete_actions, key=_public_option_view_order):
        target_context = region_index.target_contexts.get(option.target_id)
        direct = bool(target_context is not None and target_context.focused)
        same_focus_container = bool(
            target_context is not None and target_context.primary_region_key in focused_containers
        )
        if direct or same_focus_container:
            append(
                option,
                kind=DeliveryObligationKind.INTERACTION,
                reason="focused" if direct else "focus_container",
            )

    option_by_id = {item.action_id: item for item in complete_actions}
    for ranked in automatic.candidates:
        option = option_by_id.get(ranked.action_id)
        if option is None:
            continue
        target_context = region_index.target_contexts.get(option.target_id)
        reason = (
            "viewport_relevance"
            if target_context is not None and target_context.viewport == "visible"
            else "automatic_relevance"
        )
        append(option, kind=DeliveryObligationKind.BASE_ACTIONS, reason=reason)
    for option in sorted(complete_actions, key=_public_option_view_order):
        append(
            option,
            kind=(
                DeliveryObligationKind.DESTINATION_ROUTES
                if option.destination_required
                else DeliveryObligationKind.BASE_ACTIONS
            ),
            reason="base_inventory",
        )

    issue_fragments: list[ActionRouteIssueFragment] = []
    public_refs = target_refs or {}
    for issue in action_space_issues:
        source_ref = public_refs.get(issue.source_target_id, "")
        destination_refs = tuple(public_refs[item] for item in issue.destination_ids if item in public_refs)
        if not source_ref or len(destination_refs) != len(issue.destination_ids):
            raise ValueError("action-space why-not route is absent from current public grounding")
        public_value = {
            "code": issue.code.value,
            "operation": issue.operation,
            "source_ref": source_ref,
            "destination_refs": destination_refs,
            "conflicting_contract_fields": issue.conflicting_contract_fields,
        }
        issue_fragments.append(
            ActionRouteIssueFragment(
                issue.code.value,
                issue.operation,
                source_ref,
                destination_refs,
                issue.conflicting_contract_fields,
                rendered_cost_bytes=len(json.dumps(public_value, sort_keys=True, ensure_ascii=False).encode()),
            )
        )
    groups[DeliveryObligationKind.ROUTE_ISSUES].extend(issue_fragments)
    if observation_delivery is not None:
        effect_routes = tuple(
            item
            for item in groups[DeliveryObligationKind.PUBLIC_EFFECT]
            if isinstance(item, ActionDeliveryFragment)
        )
        groups[DeliveryObligationKind.PUBLIC_EFFECT] = [
            WorldDeliveryRecord(
                "effect",
                index,
                len(json.dumps(to_json_compatible(item), ensure_ascii=False).encode()),
                tuple(
                    route
                    for route in effect_routes
                    if route.candidate.target_ref == item.public_ref
                ),
            )
            for index, item in enumerate(observation_delivery.latest_effect_values)
        ]
        routed_effect_refs = {
            route.candidate.target_ref
            for record in groups[DeliveryObligationKind.PUBLIC_EFFECT]
            if isinstance(record, WorldDeliveryRecord)
            for route in record.route_fragments
        }
        groups[DeliveryObligationKind.PUBLIC_EFFECT].extend(
            route for route in effect_routes if route.candidate.target_ref not in routed_effect_refs
        )
        groups[DeliveryObligationKind.PAGE_DIRECTORY].extend(
            WorldDeliveryRecord(
                "page_directory",
                index,
                len(json.dumps(to_json_compatible(item), ensure_ascii=False).encode()),
            )
            for index, item in enumerate(observation_delivery.recovery_directory)
        )

    priorities = {
        DeliveryObligationKind.EXPLICIT_QUERY: 0 if discovery is not None else 6,
        DeliveryObligationKind.PUBLIC_EFFECT: 1,
        DeliveryObligationKind.INTERACTION: 2,
        DeliveryObligationKind.BASE_ACTIONS: 3,
        DeliveryObligationKind.PAGE_DIRECTORY: 4,
        DeliveryObligationKind.DESTINATION_ROUTES: 5,
        DeliveryObligationKind.ROUTE_ISSUES: 6,
    }
    scope_by_kind = {
        DeliveryObligationKind.EXPLICIT_QUERY: "query",
        DeliveryObligationKind.PUBLIC_EFFECT: "effect",
        DeliveryObligationKind.INTERACTION: "interaction",
        DeliveryObligationKind.BASE_ACTIONS: "base",
        DeliveryObligationKind.PAGE_DIRECTORY: "page_directory",
        DeliveryObligationKind.DESTINATION_ROUTES: "destinations",
        DeliveryObligationKind.ROUTE_ISSUES: "issues",
    }
    inventory_specs = []
    for kind, records in groups.items():
        if not records:
            continue
        order_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                to_json_compatible(tuple(_public_record_value(item) for item in records)),
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        result_lineage = (
            latest_effect.raw_delta_lineage
            if kind is DeliveryObligationKind.PUBLIC_EFFECT and latest_effect is not None
            else discovery.query
            if kind is DeliveryObligationKind.EXPLICIT_QUERY and discovery is not None
            else "current"
        )
        inventory_specs.append(
            DeliveryInventorySnapshot(
                scope_by_kind[kind],
                kind.value,
                world_observation_id,
                action_space_id,
                result_lineage or "current",
                order_digest,
                tuple(records),
            )
        )
    owner_store = (
        cursor_store if isinstance(cursor_store, ObservationDeliveryStore) else ObservationDeliveryStore()
    ).install_inventories(tuple(inventory_specs))
    obligations = []
    for inventory in owner_store.inventories:
        kind = DeliveryObligationKind(inventory.kind)
        obligations.append(
            DeliveryObligation(
                kind,
                inventory.records,
                priorities[kind],
                inventory,
                scope_by_kind[kind],
                discovery.source_coverage if kind is DeliveryObligationKind.EXPLICIT_QUERY and discovery else "complete",
                "empty" if not inventory.records else "complete",
                ("current_world", kind.value),
            )
        )
    ordered = tuple(sorted(obligations, key=lambda item: (item.priority, item.kind.value)))
    requested_scope = owner_store.requested_continuation_scope
    foreground = next(
        (
            item.continuation_scope
            for item in ordered
            if item.remaining and item.continuation_scope == requested_scope
        ),
        None,
    ) or next((item.continuation_scope for item in ordered if item.remaining), None)
    return ActionDeliveryPlanningResult(
        ActionDeliveryPlan(
            action_space_id,
            world_observation_id,
            ordered,
            foreground,
            requested_scope=requested_scope,
        ),
        owner_store,
    )


def project_action_candidates(
    actions: tuple[AgentActionOptionView, ...],
    *,
    action_space_id: str,
    world_observation_id: str,
    region_index: WorldDeliveryIndex,
    region_refs: Mapping[str, str],
    query: str = "",
    instruction: str = "",
    objectives: tuple[str, ...] = (),
    done_when: tuple[str, ...] = (),
    recent_outcomes: tuple[object, ...] = (),
    allowed_action_ids: frozenset[str] | None = None,
    top_k: int = 5,
) -> ActionCandidateProjection:
    """Project the shared ranker without changing World or action authority."""

    if not 1 <= top_k <= 32:
        raise ValueError("candidate preview bound is invalid")
    by_action = {item.action_id: item for item in actions}
    ranked = ActionReranker().rank(
        actions,
        labels={item.target_id: item.target_label for item in actions},
        roles={item.target_id: item.target_role for item in actions},
        states={item.target_id: item.target_state for item in actions},
        functional_paths={item.target_id: region_index.functional_path_for_target(item.target_id) for item in actions},
        query=query,
        instruction=instruction,
        objectives=objectives,
        done_when=done_when,
        recent_outcomes=recent_outcomes,
    )
    candidates: list[ActionCandidate] = []
    emitted_refs: set[str] = set()
    for ranked_item in ranked:
        if allowed_action_ids is not None and ranked_item.action_id not in allowed_action_ids:
            continue
        option = by_action[ranked_item.action_id]
        region = region_index.region_for_action(option.action_id) or region_index.region_for_target(option.target_id)
        if region is None or option.target_ref in emitted_refs:
            continue
        destinations = tuple(
            _project_destination(item, region_index, region_refs) for item in option.destinations.items
        )
        candidates.append(
            ActionCandidate(
                option.action_id,
                option.target_ref,
                option.operation,
                option.target_label,
                option.target_role,
                region_index.functional_path_for_target(option.target_id),
                region_refs[region.key],
                option.target_state,
                len(candidates) + 1,
                ranked_item.reasons,
                option.destination_required,
                destinations,
                option,
            )
        )
        emitted_refs.add(option.target_ref)
        if len(candidates) == top_k:
            break
    return ActionCandidateProjection(
        action_space_id,
        world_observation_id,
        tuple(candidates),
        "search" if query else "automatic",
    )


def _candidate_from_option(
    option: AgentActionOptionView,
    region_index: WorldDeliveryIndex,
    region_refs: Mapping[str, str],
    *,
    rank: int,
    reasons: tuple[str, ...],
) -> ActionCandidate:
    region = region_index.region_for_action(option.action_id) or region_index.region_for_target(option.target_id)
    if region is None:
        raise ValueError("current action is absent from the World delivery index")
    return ActionCandidate(
        option.action_id,
        option.target_ref,
        option.operation,
        option.target_label,
        option.target_role,
        region_index.functional_path_for_target(option.target_id),
        region_refs[region.key],
        option.target_state,
        rank,
        reasons,
        option.destination_required,
        tuple(_project_destination(item, region_index, region_refs) for item in option.destinations.items),
        option,
    )


def _public_candidate_value(candidate: ActionCandidate) -> dict[str, object]:
    return {
        key: value
        for key, value in to_json_compatible(candidate).items()
        if key not in {"action_id", "rank", "private_option"}
    }


def _public_fragment_value(fragment: ActionDeliveryFragment) -> dict[str, object]:
    return {
        "candidate": _public_candidate_value(fragment.candidate),
        "inclusion_reason": fragment.inclusion_reason,
        "public_provenance": fragment.public_provenance,
        "rendered_cost_bytes": fragment.rendered_cost_bytes,
    }


def _public_record_value(record: DeliveryAtomicRecord) -> Mapping[str, object]:
    if isinstance(record, ActionDeliveryFragment):
        return _public_fragment_value(record)
    if isinstance(record, ActionRouteIssueFragment):
        return freeze_json(to_json_compatible(record))
    return freeze_json(
        {
            "record_kind": record.record_kind,
            "record_index": record.record_index,
            "rendered_cost_bytes": record.rendered_cost_bytes,
            "route_fragments": tuple(_public_fragment_value(item) for item in record.route_fragments),
        }
    )


def _public_obligation_value(obligation: DeliveryObligation) -> Mapping[str, object]:
    return freeze_json(
        {
            "kind": obligation.kind.value,
            "records": tuple(_public_record_value(item) for item in obligation.records),
            "priority": obligation.priority,
            "continuation_scope": obligation.continuation_scope,
            "source_coverage": obligation.source_coverage,
            "result_coverage": obligation.result_coverage,
            "public_provenance": obligation.public_provenance,
        }
    )


def _public_option_view_order(option: AgentActionOptionView) -> tuple[object, ...]:
    return (
        option.target_ref,
        option.operation,
        tuple(item.grounding_ref for item in option.destinations.items),
        json.dumps(to_json_compatible(option.parameter_schema), sort_keys=True, ensure_ascii=False),
    )


def merge_action_candidate_projections(
    base: ActionCandidateProjection,
    query: ActionCandidateProjection,
) -> ActionCandidateProjection:
    """Build one additive view without changing either source projection."""

    if (
        base.action_space_id != query.action_space_id
        or base.world_observation_id != query.world_observation_id
        or base.scope != "automatic"
        or query.scope != "search"
    ):
        raise ValueError("additive candidate projections require one current authority")
    ordered: list[ActionCandidate] = []
    positions: dict[str, int] = {}
    for item in (*query.candidates, *base.candidates):
        if item.target_ref in positions:
            position = positions[item.target_ref]
            current = ordered[position]
            destinations = tuple(dict.fromkeys((*current.destinations, *item.destinations)))
            ordered[position] = replace(current, destinations=destinations)
            continue
        positions[item.target_ref] = len(ordered)
        ordered.append(replace(item, rank=len(ordered) + 1))
    return ActionCandidateProjection(
        base.action_space_id,
        base.world_observation_id,
        tuple(ordered),
        "search",
    )


def _project_destination(
    destination: AgentDestinationView,
    region_index: WorldDeliveryIndex,
    region_refs: Mapping[str, str],
) -> ActionCandidateDestination:
    region = region_index.region_for_target(destination.destination_id)
    if region is None:
        raise ValueError("current action destination is absent from the World delivery index")
    state = destination.semantics.get("state", {})
    return ActionCandidateDestination(
        destination.grounding_ref,
        destination.label,
        str(destination.semantics.get("role", "")),
        region_index.functional_path_for_target(destination.destination_id),
        region_refs[region.key],
        state if isinstance(state, Mapping) else {},
    )


def close_action_candidates(
    actions: AgentActionPageView,
    grounding: AgentGroundingIndexView,
    *,
    context_id: str,
) -> AgentActionPageView:
    """Close each public candidate once without choosing its final selector."""

    entities_by_ref = {item.ref: item for item in grounding.entities}
    refs_by_target = dict(grounding.target_refs)
    projected = []
    for option in actions.options:
        definition = INTERACTION_CAPABILITY_REGISTRY.require(option.semantic_action)
        entity = _grounded_entity(option.target_id, refs_by_target, entities_by_ref)
        state = _candidate_state(entity.state)
        destinations = tuple(
            _destination_candidate(
                item.destination_id,
                refs_by_target,
                entities_by_ref,
                context_id,
            )
            for item in option.destinations.items
        )
        projected.append(
            replace(
                option,
                operation=definition.semantic_action,
                target_ref=entity.ref,
                target_semantics=_target_semantics(entity, entities_by_ref, state),
                target_label=entity.label,
                target_role=entity.role,
                target_state=state,
                target_marked=entity.marked,
                subject_kind=_subject_kind(option.subject_kind, entity.role),
                destination_mode=_destination_mode(option).value,
                grounding_context_id=context_id,
                destinations=BoundedSection(
                    destinations,
                    option.destinations.total_count,
                    option.destinations.truncated,
                ),
            )
        )
    return replace(actions, options=tuple(projected))


def _subject_kind(default: str, role: str) -> str:
    if role == "viewport":
        return "viewport"
    if role == "focused_context":
        return "focused_context"
    return default


def _destination_mode(option) -> DestinationMode:
    if option.destination_required:
        return DestinationMode.REQUIRED
    if option.destinations.items:
        return DestinationMode.OPTIONAL
    return DestinationMode.FORBIDDEN


def _grounded_entity(
    target_id: str,
    refs_by_target: Mapping[str, str],
    entities_by_ref: Mapping[str, AgentGroundingEntityView],
) -> AgentGroundingEntityView:
    ref = refs_by_target.get(target_id)
    entity = entities_by_ref.get(ref or "")
    if entity is None:
        raise ValueError("current action candidate is absent from grounding projection")
    return entity


def _destination_candidate(
    destination_id: str,
    refs_by_target: Mapping[str, str],
    entities_by_ref: Mapping[str, AgentGroundingEntityView],
    context_id: str,
) -> AgentDestinationView:
    entity = _grounded_entity(destination_id, refs_by_target, entities_by_ref)
    state = _candidate_state(entity.state)
    return AgentDestinationView(
        destination_id,
        entity.label,
        entity.ref,
        _target_semantics(entity, entities_by_ref, state),
        entity.marked,
        context_id,
    )


def _candidate_state(state: Mapping[str, object]) -> dict[str, object]:
    """Expose semantic coordinates, never lattice-construction coordinates."""

    result = dict(state)
    coordinate = result.get("grid_coordinate")
    if isinstance(coordinate, Mapping):
        x = coordinate.get("x")
        y = coordinate.get("y")
        if (
            isinstance(x, int | float)
            and not isinstance(x, bool)
            and isinstance(y, int | float)
            and not isinstance(y, bool)
        ):
            result["grid_coordinate"] = {"x": x, "y": y}
            result.pop("grid_membership", None)
            result.pop("grid_coordinate_confidence", None)
    return result


def _target_semantics(
    entity: AgentGroundingEntityView,
    entities_by_ref: Mapping[str, AgentGroundingEntityView],
    state: Mapping[str, object],
) -> dict[str, object]:
    semantics: dict[str, object] = {"role": entity.role}
    if entity.label.strip():
        semantics["label"] = entity.label.strip()
    choice_state = {
        key: value
        for key, value in state.items()
        if key not in {"semantic_scope_label", "semantic_scope_role"} and _is_public_facet_value(value)
    }
    if choice_state:
        semantics["state"] = choice_state
    parent_ref = next(
        (hint.removeprefix("parent:") for hint in entity.relation_hints if hint.startswith("parent:")),
        "",
    )
    parent = entities_by_ref.get(parent_ref)
    if parent is not None:
        within: dict[str, object] = {"role": parent.role}
        if parent.label.strip():
            within["label"] = parent.label.strip()
        semantics["within"] = within
    scope_label = state.get("semantic_scope_label")
    if "within" not in semantics and isinstance(scope_label, str) and scope_label.strip():
        scope_role = state.get("semantic_scope_role")
        semantics["within"] = {
            **({"role": scope_role.strip()} if isinstance(scope_role, str) and scope_role.strip() else {}),
            "label": scope_label.strip(),
        }
    relations = tuple(
        sorted(
            hint for hint in entity.relation_hints if not hint.startswith(("parent:", "children:")) and len(hint) <= 160
        )
    )
    if relations:
        semantics["relations"] = relations
    return semantics


def _is_public_facet_value(value: object) -> bool:
    return (
        value is None
        or isinstance(value, str)
        and len(value) <= 160
        or isinstance(value, int | float | bool)
        or isinstance(value, tuple | list)
        and len(value) <= 4
        and all(item is None or isinstance(item, str | int | float | bool) for item in value)
    )
