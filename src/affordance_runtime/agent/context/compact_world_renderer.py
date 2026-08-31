"""Typed PageMap/ActiveView delivery over the authoritative Actor snapshot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from affordance_runtime.actions.capabilities import InteractionSubjectKind
from affordance_runtime.agent.context.action_candidate_projection import (
    ActionCandidate,
    ActionCandidateProjection,
    ActionRouteIssueFragment,
)
from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldNodeView,
    ActorWorldSnapshot,
    actor_source_refs,
    actor_world_for_delivery,
)
from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.projection import project_model_state
from affordance_runtime.agent.context.world_region_index import (
    DELIVERY_LIMITS_V2,
    DeliveryLimits,
    WorldDeliveryIndex,
    WorldRegion,
)
from affordance_runtime.agent.public_values import is_public_scalar
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.contracts import (
    SemanticShapeCompleteness,
    SemanticShapeKind,
    WorldObservation,
)
from affordance_runtime.world.page_cursor import (
    DeliveryCursorMode,
    DeliveryCursorPosition,
    decode_delivery_cursor,
    encode_delivery_cursor,
)
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind

_SEARCHABLE_DOM_STATE_FIELDS = frozenset(
    {
        "semantic.dom.attribute.title",
        "semantic.dom.attribute.alt",
        "semantic.dom.attribute.placeholder",
        "semantic.dom.attribute.aria-label",
        "semantic.dom.attribute.aria-description",
    }
)
_TOOL_RESULT_TEXT_MAX_CHARS = 2_048
_SOURCE_TEXT_TRUNCATION_FIELD = "semantic.accessible_name.truncated"
_CURRENT_ACTION_SUBJECT_ROLES = frozenset(
    kind.value for kind in InteractionSubjectKind if kind is not InteractionSubjectKind.ENTITY
)
_AX_TEXT_ECHO_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "link",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
    }
)


@dataclass(frozen=True)
class DeliveredActionRoute:
    operation: str
    source_ref: str
    destination_ref: str = ""
    private_action_id: str = field(default="", repr=False, compare=False, metadata={"serialize": False})
    private_option: object | None = field(default=None, repr=False, compare=False, metadata={"serialize": False})

    def __post_init__(self) -> None:
        if (
            not self.operation.strip()
            or not self.private_action_id.strip()
            or self.private_option is None
            or not PublicRefCodec.accepts(self.source_ref, expected=PublicRefKind.EXECUTABLE)
        ):
            raise ValueError("delivered action route requires a public source and operation")
        if self.destination_ref and not PublicRefCodec.accepts(self.destination_ref, expected=PublicRefKind.EXECUTABLE):
            raise ValueError("delivered action route destination is invalid")


@dataclass(frozen=True)
class DeliveryManifest:
    executable_refs: tuple[str, ...] = ()
    readonly_refs: tuple[str, ...] = ()
    fact_refs: tuple[str, ...] = ()
    region_refs: tuple[str, ...] = ()
    action_routes: tuple[DeliveredActionRoute, ...] = ()

    def __post_init__(self) -> None:
        expected = (
            (PublicRefKind.EXECUTABLE, self.executable_refs),
            (PublicRefKind.NODE, self.readonly_refs),
            (PublicRefKind.FACT, self.fact_refs),
            (PublicRefKind.REGION, self.region_refs),
        )
        for kind, values in expected:
            values = tuple(values)
            if len(values) != len(set(values)) or any(
                not PublicRefCodec.accepts(item, expected=kind) for item in values
            ):
                raise ValueError(f"delivery manifest {kind.value}-refs are invalid")
        if set(self.executable_refs) & set(self.readonly_refs):
            raise ValueError("delivery manifest executable/read-only refs overlap")
        routes = tuple(self.action_routes)
        if len(routes) != len(set(routes)):
            raise ValueError("delivery manifest action routes must be unique")
        route_refs = {ref for route in routes for ref in (route.source_ref, route.destination_ref) if ref}
        if not route_refs.issubset(set(self.executable_refs)):
            raise ValueError("delivery manifest action routes reference undelivered executables")
        object.__setattr__(self, "action_routes", routes)

    @property
    def exact_refs(self) -> frozenset[str]:
        return frozenset((*self.executable_refs, *self.readonly_refs, *self.fact_refs))


@dataclass(frozen=True)
class WorldDeliveryView:
    text: str
    projection: str
    coverage: Mapping[str, object] = field(default_factory=dict)
    failure: str = ""
    rendered_refs: tuple[str, ...] = field(
        default=(),
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )

    def __post_init__(self) -> None:
        if self.projection not in {"full", "page_map"}:
            raise ValueError("delivery projection is invalid")
        if self.failure not in {"", "delivery_partition_failed", "context_capacity"}:
            raise ValueError("delivery failure is invalid")
        rendered_refs = tuple(self.rendered_refs)
        if len(rendered_refs) != len(set(rendered_refs)) or any(
            not PublicRefCodec.accepts(item) for item in rendered_refs
        ):
            raise ValueError("delivery rendered refs are invalid")
        object.__setattr__(self, "coverage", freeze_json(dict(self.coverage)))
        object.__setattr__(self, "rendered_refs", rendered_refs)

    def __str__(self) -> str:
        return self.text

    def __contains__(self, value: str) -> bool:
        return value in self.text

    def splitlines(self) -> list[str]:
        return self.text.splitlines()

    def count(self, value: str) -> int:
        return self.text.count(value)

    def encode(self, *args, **kwargs) -> bytes:
        return self.text.encode(*args, **kwargs)


@dataclass(frozen=True)
class RenderedWorldDelivery:
    """Sibling model text and exact selection projected in one deterministic pass."""

    view: WorldDeliveryView
    manifest: DeliveryManifest

    def __post_init__(self) -> None:
        manifest_refs = {
            *self.manifest.executable_refs,
            *self.manifest.readonly_refs,
            *self.manifest.fact_refs,
            *self.manifest.region_refs,
        }
        if set(self.view.rendered_refs) != manifest_refs:
            raise ValueError("rendered World text and Manifest refs must share one typed projection")

    @property
    def text(self) -> str:
        return self.view.text

    @property
    def projection(self) -> str:
        return self.view.projection

    @property
    def coverage(self) -> Mapping[str, object]:
        return self.view.coverage

    @property
    def failure(self) -> str:
        return self.view.failure

    def __str__(self) -> str:
        return self.view.text

    def __contains__(self, value: str) -> bool:
        return value in self.view.text

    def splitlines(self) -> list[str]:
        return self.view.text.splitlines()

    def count(self, value: str) -> int:
        return self.view.text.count(value)

    def encode(self, *args, **kwargs) -> bytes:
        return self.view.text.encode(*args, **kwargs)


@dataclass(frozen=True)
class DeliveryContinuation:
    kind: str
    cursor: str
    item_offset: int
    total_items: int
    path: tuple[str | int, ...] = ()
    offset: int = 0
    total: int = 0

    def __post_init__(self) -> None:
        if self.kind not in {"items", "detail"} or not self.cursor.startswith("cursor:"):
            raise ValueError("delivery continuation requires a typed kind and cursor")
        if any(
            type(value) is not int or value < 0
            for value in (self.item_offset, self.total_items, self.offset, self.total)
        ):
            raise ValueError("delivery continuation positions must be non-negative")
        if self.item_offset > self.total_items:
            raise ValueError("delivery continuation item offset exceeds total")
        if self.kind == "detail" and (not self.path or self.offset > self.total):
            raise ValueError("detail continuation requires a valid path and range")
        if self.kind == "items" and (self.path or self.offset or self.total):
            raise ValueError("item continuation cannot carry detail range")
        object.__setattr__(self, "path", tuple(self.path))


@dataclass(frozen=True)
class Opened:
    items: tuple[Mapping[str, object], ...]
    source_coverage: str = "complete"
    region_membership: str = "complete"
    result_page: str = "1/1"
    scope: Mapping[str, object] = field(default_factory=dict)
    collection_coverage: str = "not_applicable"
    collection_continuations: tuple[Mapping[str, object], ...] = ()
    continuation: DeliveryContinuation | None = None

    @property
    def next_cursor(self) -> str:
        """Compatibility projection; ``continuation`` is the sole cursor authority."""

        return self.continuation.cursor if self.continuation is not None else ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", freeze_json(dict(self.scope)))
        if self.collection_coverage not in {"not_applicable", "open", "unknown"}:
            raise ValueError("collection coverage is invalid")
        object.__setattr__(
            self,
            "collection_continuations",
            tuple(freeze_json(dict(item)) for item in self.collection_continuations),
        )


@dataclass(frozen=True)
class Matches:
    items: tuple[Mapping[str, object], ...]
    coverage: str
    continuation: DeliveryContinuation | None = None

    @property
    def next_cursor(self) -> str:
        """Compatibility projection; ``continuation`` is the sole cursor authority."""

        return self.continuation.cursor if self.continuation is not None else ""


@dataclass(frozen=True)
class Page:
    items: tuple[Mapping[str, object], ...]
    continuation: DeliveryContinuation | None = None

    @property
    def next_cursor(self) -> str:
        """Compatibility projection; ``continuation`` is the sole cursor authority."""

        return self.continuation.cursor if self.continuation is not None else ""


@dataclass(frozen=True)
class Empty:
    query: str
    coverage: str
    safe_relaxations: tuple[str, ...]


@dataclass(frozen=True)
class InvalidRegion:
    region_ref: str


@dataclass(frozen=True)
class InvalidCursor:
    cursor: str


@dataclass(frozen=True)
class StaleContext:
    expected: str
    actual: str


@dataclass(frozen=True)
class CapacityExceeded:
    required: int
    hard_limit: int


InspectWorldOutcome = Opened | Matches | Page | Empty | InvalidRegion | InvalidCursor | StaleContext | CapacityExceeded


@dataclass
class _ManifestBuilder:
    executable: list[str] = field(default_factory=list)
    readonly: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    emitted_nodes: set[str] = field(default_factory=set)
    routes: list[DeliveredActionRoute] = field(default_factory=list)

    def region(self, value: str) -> None:
        if value not in self.regions:
            self.regions.append(value)

    def node(self, value: str, *, executable: bool) -> bool:
        if not value or value in self.emitted_nodes:
            return False
        self.emitted_nodes.add(value)
        target = self.executable if executable else self.readonly
        target.append(value)
        return True

    def fact(self, value: str) -> None:
        if PublicRefCodec.accepts(value, expected=PublicRefKind.FACT) and value not in self.facts:
            self.facts.append(value)

    def route(
        self,
        operation: str,
        source_ref: str,
        destination_ref: str = "",
        *,
        private_action_id: str,
        private_option: object,
    ) -> None:
        route = DeliveredActionRoute(operation, source_ref, destination_ref, private_action_id, private_option)
        if not any(
            (item.operation, item.source_ref, item.destination_ref)
            == (route.operation, route.source_ref, route.destination_ref)
            for item in self.routes
        ):
            self.routes.append(route)

    def build(self) -> DeliveryManifest:
        return DeliveryManifest(
            tuple(self.executable),
            tuple(self.readonly),
            tuple(self.facts),
            tuple(self.regions),
            tuple(self.routes),
        )

    def clone(self) -> "_ManifestBuilder":
        return _ManifestBuilder(
            list(self.executable),
            list(self.readonly),
            list(self.facts),
            list(self.regions),
            set(self.emitted_nodes),
            list(self.routes),
        )


def render_compact_actor_world(
    snapshot: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    *,
    include_images: bool,
    region_index: WorldDeliveryIndex | None = None,
    canonical_world: CanonicalPublicWorldProjection | None = None,
    observation: WorldObservation | None = None,
    expanded_refs: frozenset[str] | None = None,
    selected_region_keys: frozenset[str] | None = None,
    action_candidates: ActionCandidateProjection | None = None,
    action_route_issues: tuple[ActionRouteIssueFragment, ...] = (),
    public_fact_bindings: Mapping[str, str] | None = None,
    evidence_index: WorldEvidenceIndex | None = None,
    force_region_delivery: bool = False,
    limits: DeliveryLimits = DELIVERY_LIMITS_V2,
) -> RenderedWorldDelivery:
    """Render text and its exact ref manifest atomically.

    With a current index the ordinary result is always PageMap + a bounded
    exact working set.  The full renderer remains a truthful fallback for
    callers that do not yet possess a partition and for partition failure.
    """

    delivered = actor_world_for_delivery(snapshot, include_images=include_images)
    # A model turn renders the exact delivered capability set, not every verb
    # available somewhere in the complete ActionSpace.  The latter remains
    # private discovery authority and may contain routes excluded by packing.
    verbs = (
        _projection_verbs(action_candidates)
        if action_candidates is not None
        else {item.ref: item.verbs for item in grounding.entities}
    )
    if region_index is None or observation is None:
        return _render_full(
            delivered,
            verbs,
            action_candidates=action_candidates,
            action_route_issues=action_route_issues,
        )
    if region_index.world_observation_id != observation.observation_id:
        raise ValueError("delivery index belongs to a previous observation")
    if canonical_world is None:
        raise ValueError("indexed rendering requires the canonical public World projection")
    return _render_page_map(
        delivered,
        grounding,
        verbs,
        region_index,
        canonical_world,
        observation,
        selected_region_keys=selected_region_keys or frozenset(),
        expanded_refs=expanded_refs or frozenset(),
        action_candidates=action_candidates,
        action_route_issues=action_route_issues,
        public_fact_bindings=public_fact_bindings or {},
        evidence_index=evidence_index,
        limits=limits,
    )


def _projection_verbs(
    projection: ActionCandidateProjection,
) -> Mapping[str, tuple[str, ...]]:
    operations: dict[str, list[str]] = {}
    if projection.route_fragments:
        for fragment in projection.route_fragments:
            candidate = fragment.candidate
            target_operations = operations.setdefault(candidate.target_ref, [])
            if candidate.operation not in target_operations:
                target_operations.append(candidate.operation)
    else:
        for candidate in projection.candidates:
            target_operations = operations.setdefault(candidate.target_ref, [])
            if candidate.operation not in target_operations:
                target_operations.append(candidate.operation)
    return {target_ref: tuple(values) for target_ref, values in operations.items()}


def _render_full(
    delivered,
    verbs,
    *,
    action_candidates: ActionCandidateProjection | None = None,
    action_route_issues: tuple[ActionRouteIssueFragment, ...] = (),
) -> WorldDeliveryView:
    manifest = _ManifestBuilder()
    lines = ["compact_world format=compact_ax.v2", "projection=full"]
    for document in delivered.documents:
        coverage = "partial" if document.truncated else "complete"
        lines.append(
            f"document {document.source_ref} modality={document.modality} "
            f"nodes={document.retained_node_count}/{document.total_node_count} coverage={coverage}"
        )
        for root in document.roots:
            lines.extend(_render_node(root, verbs, manifest, depth=1, parent_label=""))
    if delivered.global_facts:
        lines.append("global_facts")
        for item in delivered.global_facts:
            manifest.fact(item.evidence_ref)
            lines.append(f"  {item.subject}.{_short_field(item.field)}[{item.evidence_ref}]={_value(item.value)}")
    if action_candidates is not None and action_candidates.candidates:
        lines.append("ActionCandidates")
        for item in action_candidates.candidates:
            manifest.node(item.target_ref, executable=True)
            manifest.region(item.region_ref)
            for destination in item.destinations:
                manifest.node(destination.target_ref, executable=True)
                manifest.region(destination.region_ref)
            _register_candidate_routes(item, action_candidates, manifest)
            lines.append(
                f"  [{item.target_ref}] {item.role} {_value(item.label)} "
                f"path={_value(item.functional_path)} verbs={_value(verbs.get(item.target_ref, ()))} "
                f"rank={item.rank}"
            )
    lines.extend(_render_action_route_issues(action_route_issues, manifest))
    rendered_manifest = manifest.build()
    return RenderedWorldDelivery(
        WorldDeliveryView(
            "\n".join(lines),
            "full",
            {"public_content": "exact", "regions": "not_available"},
            rendered_refs=tuple(
                (
                    *rendered_manifest.executable_refs,
                    *rendered_manifest.readonly_refs,
                    *rendered_manifest.fact_refs,
                    *rendered_manifest.region_refs,
                )
            ),
        ),
        rendered_manifest,
    )


def _render_page_map(
    delivered,
    grounding,
    verbs,
    index: WorldDeliveryIndex,
    canonical_world: CanonicalPublicWorldProjection,
    observation: WorldObservation,
    *,
    selected_region_keys: frozenset[str],
    expanded_refs: frozenset[str],
    action_candidates: ActionCandidateProjection | None,
    action_route_issues: tuple[ActionRouteIssueFragment, ...],
    public_fact_bindings: Mapping[str, str],
    evidence_index: WorldEvidenceIndex | None,
    limits: DeliveryLimits,
) -> WorldDeliveryView:
    manifest = _ManifestBuilder()
    page_route = _page_route(observation)
    page_identity = f"page title={_value(_page_title(observation))}"
    if page_route:
        page_identity += f" route={_value(page_route)}"
    lines = [
        "compact_world format=compact_ax.v2",
        "projection=page_map public_content=folded recovery=read_region/search_page_content/find_controls",
        f"{page_identity} coverage={_index_coverage(index)}",
    ]
    lines.extend(_render_current_action_subjects(delivered))
    exact_region_keys = set(selected_region_keys)
    exact_region_keys.update(
        region.key for region in index.regions if _region_public_refs(region, grounding).intersection(expanded_refs)
    )
    explicit_region_key = ""
    regions_by_key = {item.key: item for item in index.regions}
    # Region expansion is an explicit read/lens operation. Action recall never
    # promotes a candidate, focus container, or delta fan-out into ActiveView.
    default_region_order: tuple[str, ...] = ()
    exact_region_keys.update(default_region_order)
    if action_candidates is not None and action_candidates.candidates:
        lines.extend(
            _render_action_candidates(
                action_candidates,
                delivered,
                grounding,
                verbs,
                manifest,
                index,
                observation,
            )
        )
    lines.extend(_render_action_route_issues(action_route_issues, manifest))

    page_map_regions = _bounded_page_map_regions(
        index,
        canonical_world,
        exact_region_keys=frozenset(exact_region_keys),
        action_candidates=action_candidates,
        observation=observation,
        limits=limits,
    )
    page_map_complete = len(page_map_regions) == len(index.regions)
    if page_map_complete:
        lines.append(f"PageMap regions={len(page_map_regions)} coverage=complete")
    else:
        lines.append(
            f"PageMap regions={len(page_map_regions)}/{len(index.regions)} coverage=partial "
            "recovery=list_regions/search_page_content"
        )
    for region in page_map_regions:
        region_ref = canonical_world.region_refs[region.key]
        manifest.region(region_ref)
        lines.append("  " + _region_descriptor_text(region, region_ref, limits))

    lines.append("ActiveView exact=true")
    rendered_any = False
    rendered_region_count = 0
    ordered_region_keys = tuple(
        dict.fromkeys(
            (
                *((explicit_region_key,) if explicit_region_key else ()),
                *default_region_order,
                *(item.key for item in index.regions if item.key in exact_region_keys),
            )
        )
    )
    # Modal/current-change and top-level navigation regions remain ahead of
    # the remaining exact region order. Candidate ordering is displayed in its
    # own typed block above and does not change region or action authority.
    priority_keys = tuple(key for key in ordered_region_keys if _precedes_candidates(regions_by_key[key], observation))
    for region_key in priority_keys:
        candidate_manifest = manifest.clone()
        region_lines = _render_world_region(
            regions_by_key[region_key],
            canonical_world.region_refs[region_key],
            delivered,
            grounding,
            verbs,
            candidate_manifest,
            observation=observation,
        )
        if not region_lines:
            continue
        lines.extend(region_lines)
        candidate_manifest.region(canonical_world.region_refs[region_key])
        manifest = candidate_manifest
        rendered_any = True
        rendered_region_count += 1

    for region_key in ordered_region_keys:
        if region_key in priority_keys:
            continue
        region = regions_by_key[region_key]
        candidate_manifest = manifest.clone()
        region_lines = _render_world_region(
            region,
            canonical_world.region_refs[region_key],
            delivered,
            grounding,
            verbs,
            candidate_manifest,
            observation=observation,
        )
        if not region_lines:
            continue
        lines.extend(region_lines)
        candidate_manifest.region(canonical_world.region_refs[region_key])
        manifest = candidate_manifest
        rendered_any = True
        rendered_region_count += 1
    if not rendered_any and ordered_region_keys:
        candidate_manifest = manifest.clone()
        fallback_lines = _render_world_region(
            regions_by_key[ordered_region_keys[0]],
            canonical_world.region_refs[ordered_region_keys[0]],
            delivered,
            grounding,
            verbs,
            candidate_manifest,
            observation=observation,
        )
        if fallback_lines:
            lines.extend(fallback_lines)
            candidate_manifest.region(canonical_world.region_refs[ordered_region_keys[0]])
            manifest = candidate_manifest
            rendered_region_count = 1

    text = "\n".join(lines)
    coverage = {
        "page_map": "complete" if page_map_complete else "partial",
        "page_map_regions": f"{len(page_map_regions)}/{len(index.regions)}",
        "active_view": "selected_exact",
        "expanded_regions": rendered_region_count,
        "folded_regions": max(0, len(index.regions) - rendered_region_count),
    }
    rendered_manifest = manifest.build()
    return RenderedWorldDelivery(
        WorldDeliveryView(
            text,
            "page_map",
            coverage,
            rendered_refs=tuple(
                (
                    *rendered_manifest.executable_refs,
                    *rendered_manifest.readonly_refs,
                    *rendered_manifest.fact_refs,
                    *rendered_manifest.region_refs,
                )
            ),
        ),
        rendered_manifest,
    )


def _render_current_action_subjects(delivered: ActorWorldSnapshot) -> list[str]:
    """Render the fixed non-entity action subjects already present in Actor World."""

    subjects = tuple(
        node
        for document in delivered.documents
        for root in document.roots
        for node in _walk_actor_nodes(root)
        if node.role.casefold() in _CURRENT_ACTION_SUBJECT_ROLES
    )
    if not subjects:
        return []
    lines = ["CurrentActionSubjects"]
    for subject in subjects:
        line = f"  {subject.role.casefold()} label={_value(subject.label)}"
        state = project_model_state(subject.state, interactive=True)
        if state:
            line += f" state={_value(state)}"
        if subject.state_truncated:
            line += f" state_coverage={len(subject.state)}/{subject.state_total_count}"
        lines.append(line)
    return lines


def _walk_actor_nodes(node: ActorWorldNodeView) -> Iterator[ActorWorldNodeView]:
    yield node
    for child in node.children:
        yield from _walk_actor_nodes(child)


def inspect_actor_world(
    snapshot: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    *,
    region_index: WorldDeliveryIndex,
    canonical_world: CanonicalPublicWorldProjection,
    observation: WorldObservation,
    action: str,
    region_ref: str = "",
    query: str = "",
    cursor: str = "",
    page_size: int = 20,
    hard_limit: int = 64 * 1024,
    public_fact_bindings: Mapping[str, str] | None = None,
    evidence_index: WorldEvidenceIndex | None = None,
) -> InspectWorldOutcome:
    """Resolve the closed read-only recovery algebra with zero GUI dispatch."""

    if region_index.world_observation_id != observation.observation_id:
        return StaleContext(region_index.world_observation_id, observation.observation_id)
    verbs_by_ref = {item.ref: item.verbs for item in grounding.entities}
    try:
        if action == "read_region":
            try:
                region = region_index.get(canonical_world.resolve_region_ref(region_ref))
                if region is None:
                    raise KeyError(region_ref)
            except KeyError:
                return InvalidRegion(region_ref)
            items = _region_items(
                region,
                canonical_world,
                observation,
                grounding,
                verbs_by_ref,
            )
            collection_coverage = "unknown" if region.semantic_unit_roots else "not_applicable"
            cursor_fingerprint = _world_read_cursor_fingerprint(
                observation.observation_id,
                action,
                region_ref,
                items,
                page_size,
                hard_limit,
            )
            return _page_delivery_items(
                items,
                cursor,
                page_size,
                cursor_fingerprint,
                hard_limit,
                lambda page, continuation, start, end, total: Opened(
                    items=page,
                    source_coverage=region.source_coverage,
                    region_membership=region.region_membership,
                    result_page=_delivery_result_page(page, start, end, total),
                    scope=_region_read_scope(region),
                    collection_coverage=collection_coverage,
                    collection_continuations=(),
                    continuation=continuation,
                ),
            )
        if action == "find":
            if not query.strip():
                return Empty("", _index_coverage(region_index), ("provide non-empty public text",))
            matches = _find_matches(
                region_index,
                canonical_world,
                query,
                observation,
                grounding,
                verbs_by_ref=verbs_by_ref,
                public_fact_bindings=public_fact_bindings or {},
                evidence_index=evidence_index,
            )
            if not matches:
                return Empty(
                    query,
                    _index_coverage(region_index),
                    ("use fewer terms", "read a visible region"),
                )
            cursor_fingerprint = _world_read_cursor_fingerprint(
                observation.observation_id,
                action,
                query,
                matches,
                page_size,
                hard_limit,
            )
            return _page_delivery_items(
                matches,
                cursor,
                page_size,
                cursor_fingerprint,
                hard_limit,
                lambda page, continuation, _start, _end, _total: Matches(
                    page,
                    _index_coverage(region_index),
                    continuation,
                ),
            )
        if action == "view_all":
            items = tuple(
                _region_item(region, canonical_world.region_refs[region.key]) for region in region_index.regions
            )
            cursor_fingerprint = _world_read_cursor_fingerprint(
                observation.observation_id,
                action,
                "",
                items,
                page_size,
                hard_limit,
            )
            return _page_delivery_items(
                items,
                cursor,
                page_size,
                cursor_fingerprint,
                hard_limit,
                lambda page, continuation, _start, _end, _total: Page(
                    page,
                    continuation,
                ),
            )
        return Empty(action, _index_coverage(region_index), ("use read_region, search, or view_all",))
    except ValueError:
        return InvalidCursor(cursor)


def inspect_outcome_public(outcome: InspectWorldOutcome) -> Mapping[str, object]:
    kind = type(outcome).__name__
    if isinstance(outcome, Opened | Page):
        result = {
            "kind": kind,
            "items": outcome.items,
            "has_more": bool(outcome.next_cursor),
            "next_cursor": outcome.next_cursor or None,
        }
        if outcome.continuation is not None:
            result["continuation"] = _delivery_continuation_public(outcome.continuation)
        if isinstance(outcome, Opened):
            result.update(
                {
                    "source_coverage": outcome.source_coverage,
                    "region_membership": outcome.region_membership,
                    "result_page": outcome.result_page,
                    "scope": outcome.scope,
                }
            )
            if outcome.collection_coverage != "not_applicable":
                result.update(
                    {
                        "collection_coverage": outcome.collection_coverage,
                        "collection_continuations": outcome.collection_continuations,
                    }
                )
        return _with_world_read_metadata(result)
    if isinstance(outcome, Matches):
        result = {
            "kind": kind,
            "items": tuple(_search_match_with_follow_up(item) for item in outcome.items),
            "coverage": outcome.coverage,
            "has_more": bool(outcome.next_cursor),
            "next_cursor": outcome.next_cursor or None,
        }
        if outcome.continuation is not None:
            result["continuation"] = _delivery_continuation_public(outcome.continuation)
        return _with_world_read_metadata(result)
    if isinstance(outcome, Empty):
        return _with_world_read_metadata(
            {
                "kind": kind,
                "items": (),
                "query": outcome.query,
                "coverage": outcome.coverage,
                "safe_relaxations": outcome.safe_relaxations,
            }
        )
    if isinstance(outcome, InvalidRegion):
        return _with_world_read_metadata(
            {"kind": kind, "items": (), "region_ref": outcome.region_ref}
        )
    if isinstance(outcome, InvalidCursor):
        return _with_world_read_metadata({"kind": kind, "items": ()})
    if isinstance(outcome, StaleContext):
        return _with_world_read_metadata(
            {"kind": kind, "items": (), "expected": outcome.expected, "actual": outcome.actual}
        )
    return _with_world_read_metadata(
        {
            "kind": kind,
            "items": (),
            "required": outcome.required,
            "hard_limit": outcome.hard_limit,
        }
    )


def _delivery_continuation_public(continuation: DeliveryContinuation) -> Mapping[str, object]:
    result: dict[str, object] = {
        "kind": continuation.kind,
        "cursor": continuation.cursor,
        "item_offset": continuation.item_offset,
        "total_items": continuation.total_items,
    }
    if continuation.kind == "detail":
        result.update(
            {
                "path": continuation.path,
                "offset": continuation.offset,
                "total": continuation.total,
            }
        )
    return freeze_json(result)


_INSPECT_RECORD_REF_KINDS: tuple[tuple[str, PublicRefKind | None], ...] = (
    ("region_ref", PublicRefKind.REGION),
    ("structural_context", PublicRefKind.REGION),
    ("target_ref", PublicRefKind.EXECUTABLE),
    ("node_ref", PublicRefKind.NODE),
    ("evidence_ref", PublicRefKind.FACT),
    ("match_ref", None),
)
_INSPECT_RECORD_EPHEMERAL_FIELDS = tuple(name for name, _kind in _INSPECT_RECORD_REF_KINDS) + (
    "verbs",
    "follow_up",
)


def inspect_outcome_ephemeral_paths(
    outcome: InspectWorldOutcome,
    _value: Mapping[str, object],
) -> tuple[tuple[str, ...], ...]:
    """Describe observation-local fields in this producer's public result.

    History projection consumes these paths after the paired ToolReturn closes.
    Semantic values are never classified by their spelling; only fields owned
    by this result producer can expire.
    """

    paths: set[tuple[str, ...]] = {("executable_grounding",)}
    if isinstance(outcome, Opened | Matches | Page):
        paths.add(("next_cursor",))
        paths.add(("continuation", "cursor"))
        for prefix in (("items", "*"), ("items", "*", "content", "*")):
            paths.update((*prefix, field_name) for field_name in _INSPECT_RECORD_EPHEMERAL_FIELDS)
            paths.add((*prefix, "source_context", "region_ref"))
    if isinstance(outcome, Opened):
        paths.update(
            {
                ("collection_continuations", "*", "target_ref"),
                ("collection_continuations", "*", "verbs"),
            }
        )
    if isinstance(outcome, InvalidRegion):
        paths.add(("region_ref",))
    if isinstance(outcome, StaleContext):
        paths.update({("expected",), ("actual",)})
    return tuple(sorted(paths))


def _with_world_read_metadata(result: Mapping[str, object]) -> Mapping[str, object]:
    public = {
        **result,
        "searched_domain": "readable_content",
        "read_only": True,
        "zero_browser_dispatch": True,
    }
    if inspect_result_grounding(result)[1]:
        public["executable_grounding"] = "attached_to_returned_readable_targets"
    return public


def inspect_result_grounding(
    value: Mapping[str, object],
) -> tuple[tuple[str, ...], tuple[tuple[str, str, str], ...]]:
    """Project live refs/routes from this producer's closed record slots.

    Readable ``state`` and other semantic subtrees are intentionally opaque.
    A business predicate named ``target_ref`` or ``verbs`` cannot become
    grounding merely by matching protocol field names.
    """

    refs: set[str] = set()
    routes: set[tuple[str, str, str]] = set()
    items = value.get("items", ())
    if not isinstance(items, tuple | list):
        return (), ()

    def add_ref(item: object, kind: PublicRefKind | None = None) -> None:
        if isinstance(item, str) and PublicRefCodec.accepts(item, expected=kind):
            refs.add(item)

    def add_record(record: object) -> None:
        if not isinstance(record, Mapping):
            return
        for field_name, kind in _INSPECT_RECORD_REF_KINDS:
            add_ref(record.get(field_name), kind)
        source_context = record.get("source_context")
        if isinstance(source_context, Mapping):
            add_ref(source_context.get("region_ref"), PublicRefKind.REGION)
        follow_up = record.get("follow_up")
        if isinstance(follow_up, Mapping):
            add_ref(follow_up.get("region_ref"), PublicRefKind.REGION)
        target_ref = record.get("target_ref")
        verbs = record.get("verbs")
        if isinstance(target_ref, str) and PublicRefCodec.accepts(target_ref, expected=PublicRefKind.EXECUTABLE):
            if isinstance(verbs, tuple | list):
                routes.update(
                    (operation, target_ref, "")
                    for operation in verbs
                    if isinstance(operation, str) and operation.strip()
                )

    for item in items:
        add_record(item)
        if isinstance(item, Mapping):
            content = item.get("content", ())
            if isinstance(content, tuple | list):
                for child in content:
                    add_record(child)
    continuations = value.get("collection_continuations", ())
    if isinstance(continuations, tuple | list):
        for continuation in continuations:
            add_record(continuation)
    return tuple(sorted(refs)), tuple(sorted(routes))


def _search_match_with_follow_up(item: Mapping[str, object]) -> Mapping[str, object]:
    projected = dict(item)
    region_ref = str(item.get("region_ref", ""))
    match_ref = str(item.get("target_ref") or item.get("node_ref") or item.get("evidence_ref") or "")
    if PublicRefCodec.accepts(region_ref, expected=PublicRefKind.REGION):
        if PublicRefCodec.accepts(match_ref) and PublicRefCodec.decode(match_ref).kind is not PublicRefKind.REGION:
            projected["match_ref"] = match_ref
        projected["follow_up"] = {
            "operation": "read_region",
            "region_ref": region_ref,
        }
    return projected


def _render_node(node, verbs, manifest, *, depth: int, parent_label: str) -> list[str]:
    label = node.label.strip()
    role = node.role.strip() or "unknown"
    public_ref = node.ref if _is_model_ref(node.ref) else ""
    current_verbs = tuple(verbs.get(public_ref, ()))
    if PublicRefCodec.accepts(public_ref, expected=PublicRefKind.EXECUTABLE) and not current_verbs:
        # E is reserved for a current executable ActionOption. A malformed or
        # synthetic Actor node cannot make a read-only E ref model-visible.
        public_ref = ""
    state = project_model_state(node.state, interactive=bool(current_verbs))
    skip = role == "InlineTextBox" or (role == "StaticText" and not label)
    if role == "StaticText" and label and parent_label and label in parent_label:
        skip = True
    if role.casefold() == "generic" and not public_ref and not label and not state and not node.facts:
        skip = True
    lines: list[str] = []
    next_depth = depth
    prefix = ""
    if not skip:
        executable = bool(PublicRefCodec.accepts(public_ref, expected=PublicRefKind.EXECUTABLE) and current_verbs)
        if public_ref and not manifest.node(public_ref, executable=executable):
            # An exact node is printed once. Its children can still be emitted
            # under the already-visible structural context.
            skip = True
            public_ref = ""
        if skip:
            line = ""
        else:
            prefix = f"[{public_ref}] " if public_ref else ""
            line = f"{'  ' * depth}{prefix}{'group' if role.casefold() == 'generic' else role}"
        if line and label:
            line += f" {_value(label)}"
        if line:
            attributes: list[str] = []
            for key, value in state.items():
                field = _short_field(key)
                evidence_ref = node.state_evidence.get(key)
                if evidence_ref:
                    manifest.fact(evidence_ref)
                    field = f"{field}[{evidence_ref}]"
                attributes.append(f"{field}={_value(value)}")
            if node.state_truncated:
                attributes.append(f"state_coverage={len(node.state)}/{node.state_total_count}")
            if current_verbs and prefix:
                attributes.append(f"verbs={_value(current_verbs)}")
            elif prefix and PublicRefCodec.accepts(public_ref, expected=PublicRefKind.NODE):
                attributes.append("read_only=true")
            for item in node.facts:
                manifest.fact(item.evidence_ref)
                attributes.append(f"fact.{_short_field(item.field)}[{item.evidence_ref}]={_value(item.value)}")
            if attributes:
                line += " " + " ".join(attributes)
            lines.append(line)
            next_depth += 1
    child_parent = label or parent_label
    for child in node.children:
        lines.extend(_render_node(child, verbs, manifest, depth=next_depth, parent_label=child_parent))
    return lines


def _render_world_region(
    region, region_ref, delivered, grounding, verbs, manifest, *, observation: WorldObservation | None = None
) -> list[str]:
    if region.semantic_unit_roots and observation is not None and not _region_has_current_salience(region, observation):
        return [
            f"  region [{region_ref}] kind={_value(region.role)} exact=true",
            f"    repeated_siblings compacted=true recovery=read_region({region_ref})",
        ]
    wanted = (
        _region_actor_refs(region, delivered, observation) | _region_public_refs(region, grounding)
        if observation is not None
        else _region_public_refs(region, grounding)
    )
    lines = [f"  region [{region_ref}] kind={_value(region.role)} exact=true"]
    before = len(lines)
    for document in delivered.documents:
        for root in document.roots:
            sliced = _slice_region_node(root, wanted)
            if sliced is not None:
                lines.extend(_render_node(sliced, verbs, manifest, depth=2, parent_label=""))
    return lines if len(lines) > before else []


def _region_has_current_salience(region: WorldRegion, observation: WorldObservation) -> bool:
    states = {item.target_id: item.state for item in observation.targets}
    return any(
        bool(states.get(target_id, {}).get(key))
        for target_id in region.member_target_ids
        for key in ("focused", "changed")
    )


def _region_actor_refs(region, delivered, observation) -> frozenset[str]:
    source_refs = actor_source_refs(observation)
    try:
        source = next(item for item in observation.sources if item.observation_id == region.source_id)
    except StopIteration:
        return frozenset()
    document = next(
        (item for item in delivered.documents if item.source_ref == source_refs[source.observation_id]),
        None,
    )
    if document is None:
        return frozenset()
    source_topology = tuple(
        item
        for item in observation.semantic_topology
        if item.source_observation_id == source.observation_id
    )
    nodes = {item.structure_id: item for item in source_topology}
    roots = tuple(
        item for item in source_topology if not item.parent_structure_id or item.parent_structure_id not in nodes
    )
    actor_ref_by_structure: dict[str, str] = {}

    def pair(structure_id: str, actor_node) -> None:
        actor_ref_by_structure[structure_id] = actor_node.ref
        source_children = tuple(item for item in nodes[structure_id].child_structure_ids if item in nodes)
        for child_id, child_actor in zip(source_children, actor_node.children, strict=False):
            pair(child_id, child_actor)

    for source_root, actor_root in zip(roots, document.roots, strict=False):
        pair(source_root.structure_id, actor_root)
    return frozenset(
        actor_ref_by_structure[item] for item in region.member_structure_ids if item in actor_ref_by_structure
    )


def _slice_region_node(node: ActorWorldNodeView, wanted: frozenset[str]) -> ActorWorldNodeView | None:
    children = tuple(
        child for child in (_slice_region_node(item, wanted) for item in node.children) if child is not None
    )
    if node.ref not in wanted and not children:
        return None
    exact = node.ref in wanted
    return ActorWorldNodeView(
        node.ref if exact else "structural-context",
        node.role,
        node.label,
        node.state if exact else {},
        node.state_evidence if exact else {},
        node.facts if exact else (),
        {},
        node.source_refs,
        node.marked if exact else False,
        children,
        node.parent_outside_snapshot,
        len(node.state) if exact else 0,
        False,
    )


def _render_search_matches(matches, observation, grounding, manifest) -> list[str]:
    targets = {item.target_id: item for item in observation.targets}
    by_ref = {ref: targets[target_id] for target_id, ref in grounding.target_refs.items() if target_id in targets}
    lines: list[str] = []
    for item in matches:
        ref = str(item.get("node_ref", ""))
        if (
            PublicRefCodec.accepts(ref, expected=PublicRefKind.NODE)
            and ref in by_ref
            and manifest.node(ref, executable=False)
        ):
            target = by_ref[ref]
            line = f"  [{ref}] {target.role} {_value(target.label)}"
            state = project_model_state(target.state, interactive=False)
            if state:
                line += " " + " ".join(f"{_short_field(k)}={_value(v)}" for k, v in state.items())
            line += " read_only=true"
            context = item.get("structural_context") or item.get("region_ref")
            if context:
                line += f" context={_value(context)}"
            evidence_ref = str(item.get("evidence_ref", ""))
            if evidence_ref:
                manifest.fact(evidence_ref)
                line += (
                    f" evidence=[{evidence_ref}] value={_value(item.get('value'))}"
                    f" coverage={_value(item.get('coverage', 'unknown'))}"
                    f" method={_value(item.get('evidence_method', 'unknown'))}"
                )
            lines.append(line)
        elif item.get("role") != "fact":
            line = f"  {item.get('role', 'content')} {_value(item.get('label', ''))} read_only=true"
            context = item.get("structural_context") or item.get("region_ref")
            if context:
                line += f" context={_value(context)}"
            lines.append(line)
        elif item.get("role") == "fact":
            fact_ref = str(item.get("evidence_ref", ""))
            if fact_ref:
                manifest.fact(fact_ref)
                lines.append(f"  [{fact_ref}] fact {_value(item.get('label', ''))}={_value(item.get('value'))}")
            else:
                lines.append(f"  fact {_value(item.get('label', ''))}={_value(item.get('value'))} read_only=true")
    return lines


def _default_active_regions(
    regions,
    observation,
    limits,
    *,
    lens_scoped: bool = False,
) -> tuple[str, ...]:
    states = {item.target_id: item.state for item in observation.targets}
    selected: list[str] = []
    for region in regions:
        if region.role in {"alert", "alertdialog", "dialog"}:
            selected.append(region.key)
    for region in regions:
        if _bounded_region(region, limits) and any(
            bool(states.get(target_id, {}).get(key))
            for target_id in region.member_target_ids
            for key in ("focused", "changed")
        ):
            selected.append(region.key)
    if not lens_scoped:
        for region in regions:
            if region.role in {"navigation", "menubar", "toolbar"} and _bounded_region(region, limits):
                selected.append(region.key)
        primary = next(
            (region.key for region in regions if region.role in {"main", "form"} and _bounded_region(region, limits)),
            next(
                (
                    region.key
                    for region in regions
                    if region.role in {"table", "grid"} and _bounded_region(region, limits)
                ),
                "",
            ),
        )
        if primary:
            selected.append(primary)
    if not lens_scoped and not any(
        region.key in selected and region.counts.get("actions", 0) > 0 for region in regions
    ):
        first_actionable = next(
            (
                region.key
                for region in regions
                if region.counts.get("actions", 0) > 0 and _bounded_region(region, limits)
            ),
            "",
        )
        if first_actionable:
            selected.append(first_actionable)
    if not lens_scoped and not selected and regions:
        selected.append(next((item.key for item in regions if _bounded_region(item, limits)), regions[0].key))
    return tuple(dict.fromkeys(selected))


def _precedes_candidates(region: WorldRegion, observation: WorldObservation) -> bool:
    if region.role in {"alert", "alertdialog", "dialog", "navigation", "menubar", "toolbar"}:
        return True
    states = {item.target_id: item.state for item in observation.targets}
    return any(
        bool(states.get(target_id, {}).get(key))
        for target_id in region.member_target_ids
        for key in ("focused", "changed")
    )


def _render_action_candidates(
    projection: ActionCandidateProjection,
    delivered,
    grounding,
    verbs,
    manifest,
    index,
    observation,
) -> list[str]:
    heading = "SearchResults" if projection.scope == "search" else "ActionCandidates"
    lines = [heading]
    target_id_by_ref = {ref: target_id for target_id, ref in grounding.target_refs.items()}
    for candidate in projection.candidates:
        target_id = target_id_by_ref.get(candidate.target_ref, "")
        if not target_id or not verbs.get(candidate.target_ref, ()):
            continue
        region = index.region_for_action(candidate.action_id) or index.region_for_target(target_id)
        if region is None:
            continue
        manifest.node(candidate.target_ref, executable=True)
        manifest.region(candidate.region_ref)
        for destination in candidate.destinations:
            manifest.node(destination.target_ref, executable=True)
            manifest.region(destination.region_ref)
        _register_candidate_routes(candidate, projection, manifest)
        context, headers = _action_structural_context(target_id, region, observation)
        descriptor = (
            f"  rank={candidate.rank} [{candidate.target_ref}] "
            f"{candidate.role} {_value(candidate.label)} "
            f"path={_value(candidate.functional_path)} region=[{candidate.region_ref}] "
            f"verbs={_value(verbs[candidate.target_ref])}"
        )
        state = project_model_state(candidate.public_state, interactive=True)
        if state:
            descriptor += f" state={_value(state)}"
        actor_node = _actor_node_for_ref(delivered, candidate.target_ref)
        if actor_node is not None:
            evidence = {
                key: ref
                for key, ref in actor_node.state_evidence.items()
                if key in state and PublicRefCodec.accepts(ref, expected=PublicRefKind.FACT)
            }
            for ref in evidence.values():
                manifest.fact(ref)
            if evidence:
                descriptor += f" state_evidence={_value(evidence)}"
        if context:
            descriptor += f" context={_value(context)}"
        if headers:
            descriptor += f" headers={_value(headers)}"
        if candidate.destinations:
            descriptor += " destinations=" + _value(
                tuple(
                    {
                        "target": destination.target_ref,
                        "label": destination.label,
                        "role": destination.role,
                        "path": destination.functional_path,
                        "region": destination.region_ref,
                        "state": destination.public_state,
                    }
                    for destination in candidate.destinations
                )
            )
        descriptor += f" reasons={_value(candidate.reasons)}"
        lines.append(descriptor)
    return lines if len(lines) > 1 else []


def _register_candidate_routes(
    candidate: ActionCandidate,
    projection: ActionCandidateProjection,
    manifest: _ManifestBuilder,
) -> None:
    """Keep private selected routes complete behind one public target descriptor."""

    fragments = tuple(item for item in projection.route_fragments if item.candidate.target_ref == candidate.target_ref)
    if fragments:
        for fragment in fragments:
            route = fragment.candidate
            if route.destination_required:
                destination = route.destinations[0]
                manifest.route(
                    route.operation,
                    route.target_ref,
                    destination.target_ref,
                    private_action_id=route.action_id,
                    private_option=route.private_option,
                )
            else:
                manifest.route(
                    route.operation,
                    route.target_ref,
                    private_action_id=route.action_id,
                    private_option=route.private_option,
                )
        return
    if candidate.destination_required:
        for destination in candidate.destinations:
            manifest.route(
                candidate.operation,
                candidate.target_ref,
                destination.target_ref,
                private_action_id=candidate.action_id,
                private_option=candidate.private_option,
            )
        return
    manifest.route(
        candidate.operation,
        candidate.target_ref,
        private_action_id=candidate.action_id,
        private_option=candidate.private_option,
    )


def _render_action_route_issues(
    issues: tuple[ActionRouteIssueFragment, ...],
    manifest: _ManifestBuilder,
) -> list[str]:
    if not issues:
        return []
    lines = ["ActionRouteIssues"]
    for issue in issues:
        routed_refs = {ref for route in manifest.routes for ref in (route.source_ref, route.destination_ref) if ref}
        visible_source = issue.source_ref if issue.source_ref in routed_refs else "unavailable"
        visible_destinations = tuple(item for item in issue.destination_refs if item in routed_refs)
        lines.append(
            f"  code={issue.code} operation={issue.operation} source={_value(visible_source)} "
            f"destinations={_value(visible_destinations)} "
            f"conflicting_contract_fields={_value(issue.conflicting_contract_fields)} "
            f"provenance={issue.provenance}"
        )
    return lines


def _actor_node_for_ref(delivered, ref: str):
    def visit(node):
        if node.ref == ref:
            return node
        for child in node.children:
            if (found := visit(child)) is not None:
                return found
        return None

    for document in delivered.documents:
        for root in document.roots:
            if (found := visit(root)) is not None:
                return found
    return None


def _region_root_actor_node(region, delivered, observation):
    pairs = _region_structure_actor_pairs(region, delivered, observation)
    return pairs.get(region.root_structure_id)


def _region_structure_actor_pairs(region, delivered, observation) -> Mapping[str, ActorWorldNodeView]:
    source_refs = actor_source_refs(observation)
    try:
        source = next(item for item in observation.sources if item.observation_id == region.source_id)
    except StopIteration:
        return {}
    document = next(
        (item for item in delivered.documents if item.source_ref == source_refs[source.observation_id]),
        None,
    )
    if document is None:
        return {}
    nodes = {item.structure_id: item for item in source.structure}
    roots = tuple(
        item for item in source.structure if not item.parent_structure_id or item.parent_structure_id not in nodes
    )
    pairs: dict[str, ActorWorldNodeView] = {}

    def pair(structure_id: str, actor_node: ActorWorldNodeView) -> None:
        pairs[structure_id] = actor_node
        source_children = tuple(item for item in nodes[structure_id].child_structure_ids if item in nodes)
        for child_id, child_actor in zip(source_children, actor_node.children, strict=False):
            pair(child_id, child_actor)

    for source_root, actor_root in zip(roots, document.roots, strict=False):
        pair(source_root.structure_id, actor_root)
    return pairs


def _action_structural_context(target_id: str, region, observation) -> tuple[tuple[str, ...], tuple[str, ...]]:
    targets = {item.target_id: item for item in observation.targets}
    path: list[str] = []
    ancestor_ids: list[str] = []
    current = target_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        target = targets.get(current)
        if target is None:
            break
        parent = target.relations.get("parent_id")
        if not isinstance(parent, str) or parent not in targets:
            break
        ancestor_ids.append(parent)
        parent_target = targets[parent]
        if parent_target.label.strip():
            path.append(parent_target.label.strip())
        current = parent
    path.reverse()
    if region.heading.strip() and region.heading.strip() not in path:
        path.insert(0, region.heading.strip())

    if any(item.source_observation_id == region.source_id for item in observation.semantic_topology):
        local_nodes = tuple(
            item
            for item in observation.semantic_topology
            if item.source_observation_id == region.source_id
            and item.structure_id in region.member_structure_ids
        )
        target_offset = next(
            (
                offset
                for offset, item in enumerate(local_nodes)
                if item.semantic_target_id == target_id
            ),
            len(local_nodes),
        )
        local_heading = next(
            (
                item.label.strip()
                for item in reversed(local_nodes[:target_offset])
                if item.role.casefold() == "heading" and item.label.strip()
            ),
            "",
        )
        if local_heading and local_heading not in path:
            insert_at = 1 if path and path[0] == region.heading.strip() else 0
            path.insert(insert_at, local_heading)

    table_ids = {item_id for item_id in ancestor_ids if targets[item_id].role.casefold() in {"table", "grid"}}
    headers: list[str] = []
    if table_ids:
        for candidate in observation.targets:
            if candidate.role.casefold() not in {"columnheader", "rowheader"} or not candidate.label.strip():
                continue
            parent = candidate.relations.get("parent_id")
            visited: set[str] = set()
            while isinstance(parent, str) and parent not in visited and parent in targets:
                visited.add(parent)
                if parent in table_ids:
                    headers.append(candidate.label.strip())
                    break
                parent = targets[parent].relations.get("parent_id")
            if len(headers) == 12:
                break
    return tuple(dict.fromkeys(path[-6:])), tuple(dict.fromkeys(headers))


def _bounded_region(region: WorldRegion, limits: DeliveryLimits) -> bool:
    if region.semantic_unit_roots and len(region.semantic_unit_roots) > limits.repeated_items:
        return False
    token_limit = (
        limits.top_navigation_tokens
        if region.role in {"navigation", "menubar", "toolbar"}
        else limits.exact_region_tokens
    )
    if (
        region.role in {"navigation", "menubar", "toolbar"}
        and region.counts.get("actions", 0) > limits.top_navigation_controls
    ):
        return False
    return region.counts.get("estimated_tokens", 0) <= token_limit


def _region_descriptor_text(region: WorldRegion, region_ref: str, limits: DeliveryLimits) -> str:
    # A selected directory row is a model-recoverable capability. Keep its
    # exact ref and recovery route while bounding optional descriptive text.
    parts = [
        f"[{region_ref}]",
        f"kind={_value(region.role or 'region')}",
        f"source_coverage={region.source_coverage}",
        f"region_membership={region.region_membership}",
        "recovery=read_region",
    ]
    optional = []
    if region.heading:
        optional.append(f"heading={_value(region.heading)}")
    if region.direct_labels:
        optional.append(f"labels={_value(region.direct_labels)}")
    if region.scope_path:
        optional.append(f"context={_value(region.scope_path)}")
    optional.extend(
        (
            f"items={region.counts.get('items', 0)}",
            f"targets={region.counts.get('targets', 0)}",
            f"facts={region.counts.get('facts', 0)}",
            f"actions={region.counts.get('actions', 0)}",
        )
    )
    if region.role in {"table", "grid"}:
        optional.append(f"available_filter_controls={region.counts.get('filter_controls', 0)}")
    if region.state_badges:
        optional.append(f"state={_value(region.state_badges)}")
    for detail in optional:
        if _estimate_tokens(" ".join((*parts, detail))) <= limits.descriptor_tokens:
            parts.append(detail)
    return " ".join(parts)


def _bounded_page_map_regions(
    index: WorldDeliveryIndex,
    canonical_world: CanonicalPublicWorldProjection,
    *,
    exact_region_keys: frozenset[str],
    action_candidates: ActionCandidateProjection | None,
    observation: WorldObservation,
    limits: DeliveryLimits,
) -> tuple[WorldRegion, ...]:
    """Project a bounded current directory without shrinking the authoritative index."""

    candidate_refs = {
        item.region_ref for item in (action_candidates.candidates if action_candidates is not None else ())
    }
    candidate_keys = {key for key, ref in canonical_world.region_refs.items() if ref in candidate_refs}
    salient_keys = {region.key for region in index.regions if _region_has_current_salience(region, observation)}
    landmark_order = {
        role: rank
        for rank, role in enumerate(("dialog", "search", "form", "navigation", "main", "table", "grid", "list"))
    }
    source_order = {region.key: position for position, region in enumerate(index.regions)}
    ordered = sorted(
        index.regions,
        key=lambda region: (
            0
            if region.key in exact_region_keys
            else 1
            if region.key in candidate_keys
            else 2
            if region.key in salient_keys
            else 3,
            landmark_order.get(region.role.casefold(), len(landmark_order)),
            source_order[region.key],
        ),
    )
    selected: list[WorldRegion] = []
    used_tokens = 0
    for region in ordered:
        descriptor = _region_descriptor_text(
            region,
            canonical_world.region_refs[region.key],
            limits,
        )
        descriptor_tokens = _estimate_tokens("  " + descriptor + "\n")
        if used_tokens + descriptor_tokens > limits.page_map_tokens:
            continue
        selected.append(region)
        used_tokens += descriptor_tokens
    return tuple(selected)


def _page_title(observation: WorldObservation) -> str:
    for source in observation.sources:
        for item in source.structure:
            if item.role.casefold() in {"document", "webarea", "rootwebarea"} and item.label.strip():
                return item.label.strip()
    return next(
        (item.label for item in observation.targets if item.role.casefold() == "heading" and item.label), "Current page"
    )


def _page_route(observation: WorldObservation) -> str:
    return next(
        (
            str(item.state["page.route"])
            for item in observation.targets
            if item.role.casefold() == "viewport" and item.state.get("page.route")
        ),
        "",
    )


def _region_public_refs(region, grounding) -> frozenset[str]:
    return frozenset(
        grounding.target_refs[target_id] for target_id in region.member_target_ids if target_id in grounding.target_refs
    )


def _find_matches(
    index,
    canonical_world,
    query,
    observation,
    grounding,
    *,
    verbs_by_ref: Mapping[str, tuple[str, ...]],
    public_fact_bindings: Mapping[str, str] | None = None,
    evidence_index: WorldEvidenceIndex | None = None,
) -> tuple[Mapping[str, object], ...]:
    needle = _normalized_readable_text(query).casefold()[:120]
    public_by_canonical = {canonical: public for public, canonical in (public_fact_bindings or {}).items()}
    sources = {item.observation_id: item for item in observation.sources}
    locations = {
        target_id: (canonical_world.region_refs[region.key], grounding.target_refs.get(target_id, ""))
        for region in index.regions
        for target_id in region.member_target_ids
    }
    matches: list[Mapping[str, object]] = []
    repeated_target_ids: set[str] = set()
    for region in index.regions:
        grouped, grouped_target_ids = _semantic_unit_records(
            region,
            canonical_world,
            observation,
            grounding,
            verbs_by_ref,
        )
        repeated_target_ids.update(grouped_target_ids)
        matches.extend(item for item in grouped if needle in _tool_record_search_text(item))
    for target in observation.targets:
        if target.target_id in repeated_target_ids:
            continue
        values = _readable_target_search_values(target)
        if needle not in _normalized_readable_text(" ".join(values)).casefold():
            continue
        region_ref, node_ref = locations.get(target.target_id, ("", ""))
        match: dict[str, object] = {
            "region_ref": region_ref,
            "role": target.role,
            "label": target.label,
            "structural_context": region_ref,
        }
        _attach_current_grounding(match, node_ref, verbs_by_ref)
        state = _readable_state_projection(target.state)
        if state:
            match["state"] = state
        record = _target_match_record(
            target,
            needle,
            observation,
            evidence_index,
        )
        if record is not None and record.evidence_ref in public_by_canonical:
            source = sources.get(record.source_observation_id)
            match.update(
                {
                    "evidence_ref": public_by_canonical[record.evidence_ref],
                    "value": record.value,
                    "source_context": {
                        "modality": record.source_modality,
                        "assurance": record.source_assurance,
                        "region_ref": region_ref,
                    },
                    "observation_lineage": {
                        "scope": "current_observation",
                        "status": "current",
                    },
                    "coverage": source.coverage.value if source is not None else "unknown",
                    "evidence_method": record.source_modality or "unknown",
                }
            )
        matches.append(match)
    for fact in observation.facts:
        if fact.subject_id in repeated_target_ids:
            continue
        if not _searchable_public_fact(fact.predicate) or needle not in str(fact.value).casefold():
            continue
        region = index.region_for_fact(fact.fact_id)
        region_ref = canonical_world.region_refs.get(region.key, "") if region else ""
        public_ref = canonical_world.private_fact_id_refs.get(fact.fact_id, "")
        canonical_record = (
            evidence_index.resolve_record(canonical_world.private_fact_resolver[public_ref])
            if evidence_index is not None and public_ref
            else None
        )
        match: dict[str, object] = {
            "region_ref": region_ref,
            "role": "fact",
            "label": fact.predicate,
            "value": fact.value,
        }
        _attach_current_grounding(
            match,
            locations.get(fact.subject_id, ("", ""))[1],
            verbs_by_ref,
        )
        if public_ref:
            match["evidence_ref"] = public_ref
        if canonical_record is not None and public_ref and is_public_scalar(canonical_record.value):
            source = sources.get(canonical_record.source_observation_id)
            match.update(
                {
                    "source_context": {
                        "modality": canonical_record.source_modality,
                        "assurance": canonical_record.source_assurance,
                        "region_ref": region_ref,
                    },
                    "observation_lineage": {
                        "scope": "current_observation",
                        "status": "current",
                    },
                    "coverage": source.coverage.value if source is not None else "unknown",
                    "evidence_method": canonical_record.source_modality or "unknown",
                }
            )
        matches.append(match)
    return tuple(matches)


def _target_match_record(target, needle, observation, evidence_index):
    if evidence_index is None:
        return None
    if needle in target.label.casefold():
        return next(
            (
                item
                for item in evidence_index.records
                if item.kind == "fact"
                and item.subject_id == target.target_id
                and item.predicate == "public.label"
                and item.value == target.label
            ),
            None,
        )
    for predicate, value in target.state.items():
        if not _searchable_public_fact(predicate) or needle not in str(value).casefold():
            continue
        record = next(
            (
                item
                for item in evidence_index.records
                if item.kind == "fact"
                and item.subject_id == target.target_id
                and item.predicate == predicate
                and item.value == value
            ),
            None,
        )
        if record is not None:
            return record
    return None


def _region_items(
    region,
    canonical_world,
    observation,
    grounding,
    verbs_by_ref,
) -> tuple[Mapping[str, object], ...]:
    targets = {item.target_id: item for item in observation.targets}
    grouped, repeated_target_ids = _semantic_unit_records(
        region,
        canonical_world,
        observation,
        grounding,
        verbs_by_ref,
    )
    if grouped:
        schema = tuple(
            {
                "kind": "schema_member",
                **_target_item(
                    canonical_world.region_refs[region.key],
                    targets[target_id],
                    grounding,
                    verbs_by_ref,
                ),
            }
            for target_id in region.member_target_ids
            if target_id in targets and target_id not in repeated_target_ids
        )
        return (*schema, *grouped)
    items: list[Mapping[str, object]] = []
    for target_id in region.member_target_ids:
        target = targets.get(target_id)
        if target is None:
            continue
        items.append(
            _target_item(
                canonical_world.region_refs[region.key],
                target,
                grounding,
                verbs_by_ref,
            )
        )
    return tuple(items)


def _semantic_unit_records(
    region,
    canonical_world,
    observation,
    grounding,
    verbs_by_ref,
) -> tuple[tuple[Mapping[str, object], ...], set[str]]:
    if not region.semantic_unit_roots:
        return (), set()
    targets = {item.target_id: item for item in observation.targets}
    nodes = {
        item.structure_id: item
        for item in observation.semantic_topology
        if item.source_observation_id == region.source_id
    }
    region_ref = canonical_world.region_refs[region.key]
    grouped: list[Mapping[str, object]] = []
    repeated_target_ids: set[str] = set()
    for root_id in region.semantic_unit_roots:
        if root_id not in nodes:
            continue
        target_ids = tuple(
            dict.fromkeys(
                nodes[item_id].semantic_target_id
                for item_id in _walk_structure_ids(root_id, nodes)
                if nodes[item_id].semantic_target_id in targets
            )
        )
        repeated_target_ids.update(target_ids)
        content = tuple(
            compact
            for target_id in target_ids
            if (
                compact := _compact_repeated_target(
                    targets[target_id],
                    grounding,
                    verbs_by_ref,
                )
            )
            is not None
        )
        root = nodes[root_id]
        shape = root.semantic_shape.kind
        partial = (
            root.semantic_shape.completeness is not SemanticShapeCompleteness.COMPLETE
            or any(targets[target_id].state.get(_SOURCE_TEXT_TRUNCATION_FIELD) is True for target_id in target_ids)
        )
        record: dict[str, object] = {
            "kind": (
                "partial_item"
                if partial
                else "complete_item"
            ),
            "region_ref": region_ref,
            "shape": shape.value if shape is not None else "unknown",
            "role": root.role,
            "content": content,
        }
        if partial:
            record["source_detail_coverage"] = "incomplete"
        if root.label:
            record["label"] = root.label
        if shape is SemanticShapeKind.RECORD:
            record["field_count"] = len(content)
        elif shape is SemanticShapeKind.CONTROL_GROUP:
            selected = tuple(
                item
                for item in content
                if isinstance(item.get("state"), Mapping)
                and any(item["state"].get(key) is True for key in ("checked", "selected", "active"))
            )
            record["member_count"] = len(content)
            record["selected_members"] = tuple(
                str(item.get("text", "")) for item in selected if item.get("text")
            )
            record["value_status"] = "known" if not partial else "incomplete"
        grouped.append(record)
    return tuple(grouped), repeated_target_ids


def _compact_repeated_target(target, grounding, verbs_by_ref) -> Mapping[str, object] | None:
    state = project_model_state(target.state, interactive=False)
    if not target.label and not state:
        return None
    item: dict[str, object] = {"role": target.role}
    if target.label:
        item["text"] = target.label
    if state:
        item["state"] = state
    if target.state.get(_SOURCE_TEXT_TRUNCATION_FIELD) is True:
        item["source_detail_coverage"] = "incomplete"
    _attach_current_grounding(
        item,
        grounding.target_refs.get(target.target_id, ""),
        verbs_by_ref,
    )
    return item


def _compact_repeated_content(
    content: tuple[Mapping[str, object], ...],
) -> tuple[Mapping[str, object], ...]:
    """Fold AX text fragments without removing readable record content.

    Browser accessibility trees commonly emit one logical text run as many
    adjacent ``StaticText`` targets, especially around highlighted search
    terms.  Repeating the role/text object wrapper for every fragment makes a
    bounded record much larger and harder to read.  The record producer owns
    this representation, so coalesce only stateless adjacent text fragments
    here and remove the exact text echo that immediately follows an
    interactive element with the same accessible label.  Links, controls,
    state, record order, and completeness metadata remain unchanged.
    """

    compacted: list[Mapping[str, object]] = []
    for item in content:
        role = item.get("role")
        text = item.get("text")
        state = item.get("state")
        is_plain_text = role == "StaticText" and isinstance(text, str) and not state
        if not is_plain_text:
            compacted.append(item)
            continue

        if compacted:
            previous = compacted[-1]
            previous_text = previous.get("text")
            if (
                previous.get("role") in _AX_TEXT_ECHO_ROLES
                and isinstance(previous_text, str)
                and _normalized_readable_text(previous_text) == _normalized_readable_text(text)
            ):
                continue
            if previous.get("role") == "StaticText" and not previous.get("state"):
                merged = dict(previous)
                merged["text"] = _join_readable_fragments(str(previous_text or ""), text)
                compacted[-1] = merged
                continue
        compacted.append(item)
    return tuple(compacted)


def _normalized_readable_text(value: str) -> str:
    return " ".join(value.split())


def _join_readable_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if left[-1].isspace() or right[0].isspace():
        return left + right
    return left + "\n" + right


def _tool_record_search_text(item: Mapping[str, object]) -> str:
    values: list[str] = []
    label = item.get("label")
    if isinstance(label, str):
        values.append(label)
    content = item.get("content")
    if isinstance(content, tuple | list):
        for current in content:
            if not isinstance(current, Mapping):
                continue
            text = current.get("text")
            if isinstance(text, str):
                values.append(text)
            state = current.get("state")
            if isinstance(state, Mapping):
                values.extend(_readable_state_search_values(state))
    return _normalized_readable_text(" ".join(values)).casefold()


def _readable_target_search_values(target) -> list[str]:
    values = [target.label] if target.label else []
    values.extend(_readable_state_search_values(target.state))
    return values


def _readable_state_search_values(state: Mapping[str, object]) -> list[str]:
    return [str(value) for value in _readable_state_projection(state).values()]


def _readable_state_projection(state: Mapping[str, object]) -> Mapping[str, object]:
    return {
        key: value
        for key, value in project_model_state(state, interactive=False).items()
        if _searchable_public_fact(key)
    }


def _searchable_public_fact(predicate: str) -> bool:
    if predicate.startswith("semantic.dom."):
        return predicate in _SEARCHABLE_DOM_STATE_FIELDS
    return predicate != _SOURCE_TEXT_TRUNCATION_FIELD


def _target_item(region_ref, target, grounding, verbs_by_ref) -> Mapping[str, object]:
    item: dict[str, object] = {
        "region_ref": region_ref,
        "role": target.role,
        "label": target.label,
    }
    state = project_model_state(target.state, interactive=False)
    if state:
        item["state"] = state
    if target.state.get(_SOURCE_TEXT_TRUNCATION_FIELD) is True:
        item["source_detail_coverage"] = "incomplete"
    _attach_current_grounding(
        item,
        grounding.target_refs.get(target.target_id, ""),
        verbs_by_ref,
    )
    return item


def _attach_current_grounding(
    item: dict[str, object],
    public_ref: str,
    verbs_by_ref: Mapping[str, tuple[str, ...]],
) -> None:
    """Attach the one fresh grounding identity already owned by World.

    Read/search still select only readable records.  When one returned record
    is also a current executable, keeping its E-ref and verbs avoids splitting
    one AX element into unrelated readable and actionable projections.
    """

    if PublicRefCodec.accepts(public_ref, expected=PublicRefKind.EXECUTABLE):
        verbs = verbs_by_ref.get(public_ref, ())
        if verbs:
            item["target_ref"] = public_ref
            item["verbs"] = verbs
            return
    if PublicRefCodec.accepts(public_ref, expected=PublicRefKind.NODE):
        item["node_ref"] = public_ref


def _walk_structure_ids(root_id, nodes):
    yield root_id
    for child_id in nodes[root_id].child_structure_ids:
        if child_id in nodes:
            yield from _walk_structure_ids(child_id, nodes)


@dataclass(frozen=True)
class _OmittedText:
    path: tuple[str | int, ...]
    value: str
    prefix_chars: int


def _project_delivery_item(
    value: object,
    leaf_prefix_chars: int,
    *,
    path: tuple[str | int, ...] = (),
) -> tuple[object, tuple[_OmittedText, ...]]:
    """Project one lossless skeleton and describe every Delivery-owned text omission."""

    if isinstance(value, str):
        if len(value) <= leaf_prefix_chars:
            return value, ()
        return value[:leaf_prefix_chars], (_OmittedText(path, value, leaf_prefix_chars),)
    if value is None or isinstance(value, bool | int | float):
        return value, ()
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        omissions: list[_OmittedText] = []
        for key, item in value.items():
            public_key = str(key)
            projected, nested = _project_delivery_item(
                item,
                leaf_prefix_chars,
                path=(*path, public_key),
            )
            result[public_key] = projected
            omissions.extend(nested)
        return result, tuple(omissions)
    if isinstance(value, tuple | list):
        sequence_result: list[object] = []
        sequence_omissions: list[_OmittedText] = []
        for index, item in enumerate(value):
            projected, nested = _project_delivery_item(
                item,
                leaf_prefix_chars,
                path=(*path, index),
            )
            sequence_result.append(projected)
            sequence_omissions.extend(nested)
        return tuple(sequence_result), tuple(sequence_omissions)
    return _project_delivery_item(str(value), leaf_prefix_chars, path=path)


def _continued_item(
    item: Mapping[str, object],
    leaf_prefix_chars: int,
) -> tuple[Mapping[str, object], tuple[_OmittedText, ...]]:
    projected, omissions = _project_delivery_item(item, leaf_prefix_chars)
    if not isinstance(projected, Mapping):
        raise TypeError("delivery item must remain an object")
    if not omissions:
        return projected, ()
    result = dict(projected)
    if result.get("kind") == "complete_item":
        result["kind"] = "partial_item"
    result["delivery_coverage"] = "continued"
    result["delivery_omissions"] = tuple(
        {
            "path": omission.path,
            "delivered_chars": omission.prefix_chars,
            "total_chars": len(omission.value),
        }
        for omission in omissions
    )
    return result, omissions


def _page_delivery_items(
    items: tuple[Mapping[str, object], ...],
    cursor: str,
    page_size: int,
    cursor_fingerprint: str,
    hard_limit: int,
    outcome_factory,
) -> InspectWorldOutcome:
    """One owner for item paging, detail continuation, and final byte admission."""

    position = decode_delivery_cursor(cursor, cursor_fingerprint)
    if position.item_offset > len(items):
        raise ValueError("delivery cursor offset exceeds current stream")
    if position.mode is DeliveryCursorMode.DETAIL:
        return _page_delivery_detail(
            items,
            position,
            cursor_fingerprint,
            hard_limit,
            outcome_factory,
        )

    start = position.item_offset
    page: list[Mapping[str, object]] = []
    index = start
    while index < len(items) and len(page) < page_size:
        candidate = (*page, items[index])
        candidate_end = index + 1
        next_position = (
            DeliveryCursorPosition(DeliveryCursorMode.ITEMS, candidate_end)
            if candidate_end < len(items)
            else None
        )
        continuation = _continuation_for_position(
            next_position,
            cursor_fingerprint,
            len(items),
        )
        outcome = outcome_factory(candidate, continuation, start, candidate_end, len(items))
        if _inspect_outcome_bytes(outcome) <= hard_limit:
            page.append(items[index])
            index = candidate_end
            continue
        if page:
            return _admitted_delivery_page(
                tuple(page),
                start,
                index,
                items,
                cursor_fingerprint,
                hard_limit,
                outcome_factory,
            )
        return _continued_delivery_item_page(
            items,
            index,
            cursor_fingerprint,
            hard_limit,
            outcome_factory,
        )
    return _admitted_delivery_page(
        tuple(page),
        start,
        index,
        items,
        cursor_fingerprint,
        hard_limit,
        outcome_factory,
    )


def _admitted_delivery_page(
    page: tuple[Mapping[str, object], ...],
    start: int,
    end: int,
    items: tuple[Mapping[str, object], ...],
    cursor_fingerprint: str,
    hard_limit: int,
    outcome_factory,
) -> InspectWorldOutcome:
    next_position = DeliveryCursorPosition(DeliveryCursorMode.ITEMS, end) if end < len(items) else None
    continuation = _continuation_for_position(
        next_position,
        cursor_fingerprint,
        len(items),
    )
    outcome = outcome_factory(page, continuation, start, end, len(items))
    required = _inspect_outcome_bytes(outcome)
    return outcome if required <= hard_limit else CapacityExceeded(required, hard_limit)


def _continued_delivery_item_page(
    items: tuple[Mapping[str, object], ...],
    item_offset: int,
    cursor_fingerprint: str,
    hard_limit: int,
    outcome_factory,
) -> InspectWorldOutcome:
    smallest_required = 0
    for leaf_prefix_chars in (_TOOL_RESULT_TEXT_MAX_CHARS, 1024, 512, 256, 128, 64, 32, 16, 8, 0):
        projected, omissions = _continued_item(items[item_offset], leaf_prefix_chars)
        if not omissions:
            continue
        position = DeliveryCursorPosition(
            DeliveryCursorMode.DETAIL,
            item_offset,
            0,
            omissions[0].prefix_chars,
            leaf_prefix_chars,
        )
        continuation = _continuation_for_position(
            position,
            cursor_fingerprint,
            len(items),
            omissions=omissions,
        )
        outcome = outcome_factory(
            (projected,),
            continuation,
            item_offset,
            item_offset + 1,
            len(items),
        )
        required = _inspect_outcome_bytes(outcome)
        smallest_required = required if not smallest_required else min(smallest_required, required)
        if required <= hard_limit:
            return outcome
    return CapacityExceeded(smallest_required or _inspect_item_bytes(items[item_offset]), hard_limit)


def _page_delivery_detail(
    items: tuple[Mapping[str, object], ...],
    position: DeliveryCursorPosition,
    cursor_fingerprint: str,
    hard_limit: int,
    outcome_factory,
) -> InspectWorldOutcome:
    if position.item_offset >= len(items):
        raise ValueError("detail cursor item is absent")
    _projected, omissions = _continued_item(items[position.item_offset], position.leaf_prefix_chars)
    if position.detail_index >= len(omissions):
        raise ValueError("detail cursor path is absent")
    omission = omissions[position.detail_index]
    if not omission.prefix_chars <= position.detail_offset < len(omission.value):
        raise ValueError("detail cursor offset is invalid")

    maximum = min(_TOOL_RESULT_TEXT_MAX_CHARS, len(omission.value) - position.detail_offset)
    low, high = 1, maximum
    admitted: InspectWorldOutcome | None = None
    smallest_required = 0
    while low <= high:
        length = (low + high) // 2
        end = position.detail_offset + length
        next_position = _position_after_detail(position, omissions, end, len(items))
        continuation = _continuation_for_position(
            next_position,
            cursor_fingerprint,
            len(items),
            omissions=omissions if next_position and next_position.mode is DeliveryCursorMode.DETAIL else (),
        )
        detail = {
            "kind": "detail_page",
            "parent_item": position.item_offset,
            "path": omission.path,
            "text": omission.value[position.detail_offset:end],
            "range": {
                "start": position.detail_offset,
                "end": end,
                "total": len(omission.value),
            },
            "delivery_coverage": "continued" if next_position is not None else "complete",
        }
        outcome = outcome_factory(
            (detail,),
            continuation,
            position.item_offset,
            position.item_offset + 1,
            len(items),
        )
        required = _inspect_outcome_bytes(outcome)
        smallest_required = required if not smallest_required else min(smallest_required, required)
        if required <= hard_limit:
            admitted = outcome
            low = length + 1
        else:
            high = length - 1
    return admitted or CapacityExceeded(smallest_required, hard_limit)


def _position_after_detail(
    position: DeliveryCursorPosition,
    omissions: tuple[_OmittedText, ...],
    end: int,
    total_items: int,
) -> DeliveryCursorPosition | None:
    omission = omissions[position.detail_index]
    if end < len(omission.value):
        return DeliveryCursorPosition(
            DeliveryCursorMode.DETAIL,
            position.item_offset,
            position.detail_index,
            end,
            position.leaf_prefix_chars,
        )
    if position.detail_index + 1 < len(omissions):
        following = omissions[position.detail_index + 1]
        return DeliveryCursorPosition(
            DeliveryCursorMode.DETAIL,
            position.item_offset,
            position.detail_index + 1,
            following.prefix_chars,
            position.leaf_prefix_chars,
        )
    if position.item_offset + 1 < total_items:
        return DeliveryCursorPosition(DeliveryCursorMode.ITEMS, position.item_offset + 1)
    return None


def _continuation_for_position(
    position: DeliveryCursorPosition | None,
    fingerprint: str,
    total_items: int,
    *,
    omissions: tuple[_OmittedText, ...] = (),
) -> DeliveryContinuation | None:
    if position is None:
        return None
    cursor = encode_delivery_cursor(position, fingerprint)
    if position.mode is DeliveryCursorMode.ITEMS:
        return DeliveryContinuation("items", cursor, position.item_offset, total_items)
    if position.detail_index >= len(omissions):
        raise ValueError("detail continuation path is absent")
    omission = omissions[position.detail_index]
    return DeliveryContinuation(
        "detail",
        cursor,
        position.item_offset,
        total_items,
        omission.path,
        position.detail_offset,
        len(omission.value),
    )


def _inspect_item_bytes(item: object) -> int:
    return len(
        json.dumps(
            to_json_compatible(item),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def _region_result_page(start: int, end: int, total: int) -> str:
    return "1/1" if start == 0 and end == total else f"records:{start + 1}-{end}/{total}"


def _delivery_result_page(
    page: tuple[Mapping[str, object], ...],
    start: int,
    end: int,
    total: int,
) -> str:
    if len(page) == 1 and page[0].get("kind") == "detail_page":
        item_range = page[0].get("range", {})
        parent_item = page[0].get("parent_item", 0)
        if isinstance(item_range, Mapping) and type(parent_item) is int:
            return (
                f"detail:item={parent_item + 1} "
                f"chars={item_range.get('start', 0)}-{item_range.get('end', 0)}/{item_range.get('total', 0)}"
            )
    return _region_result_page(start, end, total)


def _inspect_outcome_bytes(outcome: InspectWorldOutcome) -> int:
    return len(
        json.dumps(
            to_json_compatible(inspect_outcome_public(outcome)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def _region_item(region, region_ref: str) -> Mapping[str, object]:
    return {
        "region_ref": region_ref,
        "kind": region.role,
        "heading": region.heading,
        "labels": region.direct_labels,
        "counts": region.counts,
        "coverage": region.coverage,
        "recovery": "read_region",
    }


def _region_read_scope(region: WorldRegion) -> Mapping[str, object]:
    """Return the small ref-free semantic identity of one read scope."""

    scope: dict[str, object] = {"role": region.role}
    if region.heading.strip():
        scope["heading"] = region.heading
    if region.scope_path:
        scope["context"] = region.scope_path
    return scope


def _world_read_cursor_fingerprint(
    observation_id: str,
    operation: str,
    scope: str,
    items: tuple[Mapping[str, object], ...],
    page_size: int,
    hard_limit: int,
) -> str:
    """Bind one stateless cursor to the exact owner-produced result inventory."""

    payload = {
        "world": observation_id,
        "operation": operation,
        "scope": scope,
        "items": to_json_compatible(items),
        "page_size": page_size,
        "hard_limit": hard_limit,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _index_coverage(index) -> str:
    return "partial" if any(item.coverage != "complete" for item in index.regions) else "complete"


def _short_field(value: str) -> str:
    for prefix in ("semantic.dom.attribute.", "semantic.", "viewport."):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _is_model_ref(value: str) -> bool:
    return PublicRefCodec.accepts(value) and value[:1] in {"E", "N"}


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text.encode("utf-8")) + 3) // 4) if text else 0


def _value(value: object) -> str:
    return json.dumps(to_json_compatible(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
