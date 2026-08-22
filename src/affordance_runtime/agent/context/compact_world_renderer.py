"""Typed PageMap/ActiveView delivery over the authoritative Actor snapshot."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.agent.context.action_candidate_projection import ActionCandidateProjection
from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldNodeView,
    ActorWorldSnapshot,
    actor_world_for_delivery,
)
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.evidence_candidate_projection import EvidenceCandidateProjection
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.context.world_region_index import (
    DELIVERY_LIMITS_V1,
    DeliveryLimits,
    WorldDeliveryIndex,
    WorldRegion,
)
from affordance_runtime.agent.working_facts import is_public_scalar
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_fact_ref, canonical_public_text_ref

_REF = re.compile(r"^[ENF][1-9][0-9]{0,3}$")
_DROPPED_STATE_PREFIXES = ("appearance.",)
_DROPPED_STATE_FIELDS = {
    "grid_coordinate_confidence",
    "grid_membership",
    "semantic.name_status",
}
_PUBLIC_DOM_STATE_FIELDS = frozenset(
    {
        "semantic.dom.attribute.type",
        "semantic.dom.attribute.role",
        "semantic.dom.attribute.title",
        "semantic.dom.attribute.alt",
        "semantic.dom.attribute.placeholder",
        "semantic.dom.attribute.aria-label",
        "semantic.dom.attribute.aria-description",
    }
)


@dataclass(frozen=True)
class DeliveryManifest:
    world_observation_id: str
    executable_refs: tuple[str, ...] = ()
    readonly_refs: tuple[str, ...] = ()
    fact_refs: tuple[str, ...] = ()
    region_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.world_observation_id.strip():
            raise ValueError("delivery manifest requires current World identity")
        expected = (
            ("E", self.executable_refs),
            ("N", self.readonly_refs),
            ("F", self.fact_refs),
            ("R", self.region_refs),
        )
        for prefix, values in expected:
            values = tuple(values)
            if len(values) != len(set(values)) or any(
                re.fullmatch(rf"{prefix}[1-9][0-9]{{0,3}}", item) is None for item in values
            ):
                raise ValueError(f"delivery manifest {prefix}-refs are invalid")
        if set(self.executable_refs) & set(self.readonly_refs):
            raise ValueError("delivery manifest executable/read-only refs overlap")

    @property
    def exact_refs(self) -> frozenset[str]:
        return frozenset((*self.executable_refs, *self.readonly_refs, *self.fact_refs))

    def admits_executable(self, ref: str) -> bool:
        return ref in self.executable_refs


@dataclass(frozen=True)
class WorldDeliveryView:
    text: str
    projection: str
    coverage: Mapping[str, object] = field(default_factory=dict)
    failure: str = ""

    def __post_init__(self) -> None:
        if self.projection not in {"full", "page_map"}:
            raise ValueError("delivery projection is invalid")
        if self.failure not in {"", "delivery_partition_failed", "context_capacity"}:
            raise ValueError("delivery failure is invalid")
        object.__setattr__(self, "coverage", freeze_json(dict(self.coverage)))

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
class Opened:
    items: tuple[Mapping[str, object], ...]
    next_cursor: str = ""
    source_coverage: str = "complete"
    region_membership: str = "complete"
    result_page: str = "1/1"


@dataclass(frozen=True)
class Matches:
    items: tuple[Mapping[str, object], ...]
    coverage: str
    next_cursor: str = ""


@dataclass(frozen=True)
class Page:
    items: tuple[Mapping[str, object], ...]
    next_cursor: str = ""


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
    observation_id: str
    executable: list[str] = field(default_factory=list)
    readonly: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    emitted_nodes: set[str] = field(default_factory=set)

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
        if value.startswith("F") and value not in self.facts:
            self.facts.append(value)

    def build(self) -> DeliveryManifest:
        return DeliveryManifest(
            self.observation_id,
            tuple(self.executable),
            tuple(self.readonly),
            tuple(self.facts),
            tuple(self.regions),
        )


def render_compact_actor_world(
    snapshot: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    *,
    include_images: bool,
    region_index: WorldDeliveryIndex | None = None,
    observation: WorldObservation | None = None,
    delivery_lens: WorldDeliveryLens | None = None,
    expanded_refs: frozenset[str] | None = None,
    selected_region_keys: frozenset[str] | None = None,
    selected_cursor: str = "",
    action_candidates: ActionCandidateProjection | None = None,
    evidence_candidates: EvidenceCandidateProjection | None = None,
    public_fact_bindings: Mapping[str, str] | None = None,
    evidence_index: WorldEvidenceIndex | None = None,
    max_rendered_bytes: int | None = None,
    force_region_delivery: bool = False,
    limits: DeliveryLimits = DELIVERY_LIMITS_V1,
) -> RenderedWorldDelivery:
    """Render text and its exact ref manifest atomically.

    With a current index the ordinary result is always PageMap + a bounded
    exact working set.  The full renderer remains a truthful fallback for
    callers that do not yet possess a partition and for partition failure.
    """

    delivered = actor_world_for_delivery(snapshot, include_images=include_images)
    observation_id = (
        observation.observation_id
        if observation is not None
        else region_index.world_observation_id
        if region_index is not None
        else "actor-world"
    )
    verbs = {item.ref: item.verbs for item in grounding.entities}
    if region_index is None or observation is None:
        return _render_full(
            delivered,
            verbs,
            observation_id,
            action_candidates=action_candidates,
            evidence_candidates=evidence_candidates,
        )
    if region_index.world_observation_id != observation.observation_id:
        raise ValueError("delivery index belongs to a previous observation")
    return _render_page_map(
        delivered,
        grounding,
        verbs,
        region_index,
        observation,
        delivery_lens=delivery_lens,
        selected_region_keys=selected_region_keys or frozenset(),
        expanded_refs=expanded_refs or frozenset(),
        action_candidates=action_candidates,
        evidence_candidates=evidence_candidates,
        public_fact_bindings=public_fact_bindings or {},
        evidence_index=evidence_index,
        selected_cursor=selected_cursor,
        max_rendered_bytes=max_rendered_bytes,
        limits=limits,
    )


def _render_full(
    delivered,
    verbs,
    observation_id: str,
    *,
    action_candidates: ActionCandidateProjection | None = None,
    evidence_candidates: EvidenceCandidateProjection | None = None,
) -> WorldDeliveryView:
    manifest = _ManifestBuilder(observation_id)
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
    if evidence_candidates is not None and evidence_candidates.candidates:
        lines.append(f"EvidenceCandidates exact=true count={len(evidence_candidates.candidates)}")
        for item in evidence_candidates.candidates:
            manifest.fact(item.fact_ref)
            lines.append(f"  [{item.fact_ref}] predicate={_value(item.predicate)} value={_value(item.value)}")
    if action_candidates is not None and action_candidates.candidates:
        lines.append(f"ActionCandidates exact=true count={len(action_candidates.candidates)}")
        for item in action_candidates.candidates:
            lines.append(
                f"  [{item.target_ref}] {item.operation} {item.role} {_value(item.label)} "
                f"path={_value(item.functional_path)} verbs={_value(verbs.get(item.target_ref, ()))} "
                f"rank={item.rank}"
            )
    return RenderedWorldDelivery(
        WorldDeliveryView(
            "\n".join(lines),
            "full",
            {"public_content": "exact", "regions": "not_available"},
        ),
        manifest.build(),
    )


def _render_page_map(
    delivered,
    grounding,
    verbs,
    index: WorldDeliveryIndex,
    observation: WorldObservation,
    *,
    delivery_lens: WorldDeliveryLens | None,
    selected_region_keys: frozenset[str],
    expanded_refs: frozenset[str],
    action_candidates: ActionCandidateProjection | None,
    evidence_candidates: EvidenceCandidateProjection | None,
    public_fact_bindings: Mapping[str, str],
    evidence_index: WorldEvidenceIndex | None,
    selected_cursor: str,
    max_rendered_bytes: int | None,
    limits: DeliveryLimits,
) -> WorldDeliveryView:
    manifest = _ManifestBuilder(observation.observation_id)
    page_route = _page_route(observation)
    page_identity = f"page title={_value(_page_title(observation))}"
    if page_route:
        page_identity += f" route={_value(page_route)}"
    lines = [
        "compact_world format=compact_ax.v2",
        "projection=page_map public_content=folded recovery=read_region/search_page_content/find_controls",
        f"{page_identity} coverage={_index_coverage(index)}",
        f"PageMap regions={len(index.regions)}",
    ]
    invalid_descriptor = False
    for region in index.regions:
        descriptor = _region_descriptor_text(region, limits)
        if not descriptor:
            invalid_descriptor = True
            break
        manifest.region(region.public_ref)
        lines.append("  " + descriptor)
    if invalid_descriptor:
        fallback = _render_full(delivered, verbs, observation.observation_id)
        return RenderedWorldDelivery(
            WorldDeliveryView(
                fallback.text,
                "full",
                {"public_content": "exact", "partition": "failed"},
                "delivery_partition_failed",
            ),
            fallback.manifest,
        )

    search_lines: list[str] = []
    exact_region_keys = set(selected_region_keys)
    lens = delivery_lens
    if lens is not None and lens.world_observation_id == observation.observation_id:
        if lens.kind == "region" and lens.selected_region_key:
            exact_region_keys.add(lens.selected_region_key)
        elif lens.kind == "find":
            matches = _find_matches(
                index,
                lens.query,
                observation,
                grounding,
                public_fact_bindings=public_fact_bindings,
                evidence_index=evidence_index,
            )
            search_lines = _render_search_matches(matches, observation, grounding, manifest)
        elif lens.kind == "view_all":
            offset = _decode_simple_cursor(lens.page_cursor, len(index.regions))
            exact_region_keys.update(item.key for item in index.regions[offset : offset + 2])
    exact_region_keys.update(
        region.key for region in index.regions if _region_public_refs(region, grounding).intersection(expanded_refs)
    )
    explicit_region_key = (
        lens.selected_region_key if lens is not None and lens.kind == "region" and lens.selected_region_key else ""
    )
    default_region_order = _default_active_regions(
        index.regions,
        observation,
        limits,
        lens_scoped=bool(explicit_region_key),
    )
    exact_region_keys.update(default_region_order)
    if search_lines:
        lines.append(f"ContentSearchResults exact=true count={len(search_lines)}")
        lines.extend(search_lines)

    if evidence_candidates is not None and evidence_candidates.candidates:
        lines.append(f"EvidenceCandidates exact=true count={len(evidence_candidates.candidates)}")
        for rank, item in enumerate(evidence_candidates.candidates, 1):
            manifest.fact(item.fact_ref)
            lines.append(
                f"  rank={rank} [{item.fact_ref}] predicate={_value(item.predicate)} "
                f"value={_value(item.value)} region={_value(item.region_ref)} "
                f"source={_value(item.source_context)} coverage={_value(item.coverage)} "
                f"lineage={_value(item.lineage)}"
            )

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
    regions_by_key = {item.key: item for item in index.regions}

    # Modal/current-change and top-level navigation regions remain ahead of
    # the remaining exact region order. Candidate ordering is displayed in its
    # own typed block above and does not change region or action authority.
    priority_keys = tuple(key for key in ordered_region_keys if _precedes_candidates(regions_by_key[key], observation))
    for region_key in priority_keys:
        region_lines = _render_world_region(
            regions_by_key[region_key],
            delivered,
            grounding,
            verbs,
            manifest,
            observation=observation,
        )
        if not region_lines:
            continue
        candidate = "\n".join((*lines, *region_lines))
        if max_rendered_bytes and len(candidate.encode()) > max_rendered_bytes and rendered_any:
            continue
        lines.extend(region_lines)
        rendered_any = True
        rendered_region_count += 1

    for region_key in ordered_region_keys:
        if region_key in priority_keys:
            continue
        region = regions_by_key[region_key]
        region_lines = _render_world_region(region, delivered, grounding, verbs, manifest, observation=observation)
        if not region_lines:
            continue
        candidate = "\n".join((*lines, *region_lines))
        if max_rendered_bytes and len(candidate.encode()) > max_rendered_bytes and rendered_any:
            continue
        lines.extend(region_lines)
        rendered_any = True
        rendered_region_count += 1
    if not rendered_any and index.regions:
        lines.extend(
            _render_world_region(index.regions[0], delivered, grounding, verbs, manifest, observation=observation)
        )
        rendered_region_count = 1

    text = "\n".join(lines)
    if max_rendered_bytes and len(text.encode()) > max_rendered_bytes:
        # Truthful exact first atomic region is retained. Admission owns the
        # final hard-cap result and reports context_capacity with full request
        # composition; renderer never slices a row or silently drops PageMap.
        coverage = {
            "page_map": "complete",
            "active_view": "atomic_over_target",
            "expanded_regions": rendered_region_count,
            "folded_regions": max(0, len(index.regions) - rendered_region_count),
        }
    else:
        coverage = {
            "page_map": "complete",
            "active_view": "selected_exact",
            "expanded_regions": rendered_region_count,
            "folded_regions": max(0, len(index.regions) - rendered_region_count),
        }
    return RenderedWorldDelivery(
        WorldDeliveryView(text, "page_map", coverage),
        manifest.build(),
    )


def inspect_actor_world(
    snapshot: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    *,
    region_index: WorldDeliveryIndex,
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
    try:
        if action == "read_region":
            try:
                region = region_index.resolve_public_ref(region_ref)
            except KeyError:
                return InvalidRegion(region_ref)
            items = _region_items(
                region,
                observation,
                grounding,
                public_fact_bindings=public_fact_bindings or {},
                evidence_index=evidence_index,
            )
            page, next_cursor, result_page = _page_region_items(items, cursor, page_size)
            required = len(json.dumps(to_json_compatible(page), ensure_ascii=False).encode())
            if required > hard_limit:
                return CapacityExceeded(required, hard_limit)
            return Opened(
                page,
                next_cursor,
                region.source_coverage,
                region.region_membership,
                result_page,
            )
        if action == "find":
            if not query.strip():
                return Empty("", _index_coverage(region_index), ("provide non-empty public text",))
            matches = _find_matches(
                region_index,
                query,
                observation,
                grounding,
                public_fact_bindings=public_fact_bindings or {},
                evidence_index=evidence_index,
            )
            if not matches:
                return Empty(
                    query[:120],
                    _index_coverage(region_index),
                    ("use fewer terms", "read a visible region"),
                )
            offset = _decode_simple_cursor(cursor, len(matches))
            page, next_cursor = _page_items(matches, offset, page_size)
            required = len(json.dumps(to_json_compatible(page), ensure_ascii=False).encode())
            if required > hard_limit:
                return CapacityExceeded(required, hard_limit)
            return Matches(page, _index_coverage(region_index), next_cursor)
        if action == "view_all":
            items = tuple(_region_item(region) for region in region_index.regions)
            offset = _decode_simple_cursor(cursor, len(items))
            page, next_cursor = _page_items(items, offset, page_size)
            required = len(json.dumps(to_json_compatible(page), ensure_ascii=False).encode())
            if required > hard_limit:
                return CapacityExceeded(required, hard_limit)
            return Page(page, next_cursor)
        return Empty(action, _index_coverage(region_index), ("use read_region, search, or view_all",))
    except ValueError:
        return InvalidCursor(cursor)


def inspect_outcome_public(outcome: InspectWorldOutcome) -> Mapping[str, object]:
    kind = type(outcome).__name__
    if isinstance(outcome, Opened | Page):
        result = {"kind": kind, "items": outcome.items, "has_more": bool(outcome.next_cursor)}
        if isinstance(outcome, Opened):
            result.update(
                {
                    "source_coverage": outcome.source_coverage,
                    "region_membership": outcome.region_membership,
                    "result_page": outcome.result_page,
                }
            )
        return result
    if isinstance(outcome, Matches):
        return {
            "kind": kind,
            "items": outcome.items,
            "coverage": outcome.coverage,
            "has_more": bool(outcome.next_cursor),
        }
    if isinstance(outcome, Empty):
        return {
            "kind": kind,
            "query": outcome.query,
            "coverage": outcome.coverage,
            "safe_relaxations": outcome.safe_relaxations,
        }
    if isinstance(outcome, InvalidRegion):
        return {"kind": kind, "region_ref": outcome.region_ref}
    if isinstance(outcome, InvalidCursor):
        return {"kind": kind}
    if isinstance(outcome, StaleContext):
        return {"kind": kind, "expected": outcome.expected, "actual": outcome.actual}
    return {"kind": kind, "required": outcome.required, "hard_limit": outcome.hard_limit}


def _render_node(node, verbs, manifest, *, depth: int, parent_label: str) -> list[str]:
    label = node.label.strip()
    role = node.role.strip() or "unknown"
    public_ref = node.ref if _is_model_ref(node.ref) else ""
    current_verbs = tuple(verbs.get(public_ref, ()))
    if public_ref.startswith("E") and not current_verbs:
        # E is reserved for a current executable ActionOption. A malformed or
        # synthetic Actor node cannot make a read-only E ref model-visible.
        public_ref = ""
    state = _model_state(node.state, interactive=bool(current_verbs))
    skip = role == "InlineTextBox" or (role == "StaticText" and not label)
    if role == "StaticText" and label and parent_label and label in parent_label:
        skip = True
    if role.casefold() == "generic" and not public_ref and not label and not state and not node.facts:
        skip = True
    lines: list[str] = []
    next_depth = depth
    prefix = ""
    if not skip:
        executable = bool(public_ref.startswith("E") and current_verbs)
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
        elif prefix and public_ref.startswith("N"):
            attributes.append("read_only=true")
        for item in node.facts:
            manifest.fact(item.evidence_ref)
            attributes.append(f"fact.{_short_field(item.field)}[{item.evidence_ref}]={_value(item.value)}")
        if line and attributes:
            line += " " + " ".join(attributes)
        if line:
            lines.append(line)
            next_depth += 1
    child_parent = label or parent_label
    for child in node.children:
        lines.extend(_render_node(child, verbs, manifest, depth=next_depth, parent_label=child_parent))
    return lines


def _render_world_region(
    region, delivered, grounding, verbs, manifest, *, observation: WorldObservation | None = None
) -> list[str]:
    wanted = (
        _region_actor_refs(region, delivered, observation) | _region_public_refs(region, grounding)
        if observation is not None
        else _region_public_refs(region, grounding)
    )
    lines = [f"  region [{region.public_ref}] kind={_value(region.role)} exact=true"]
    before = len(lines)
    for document in delivered.documents:
        for root in document.roots:
            sliced = _slice_region_node(root, wanted)
            if sliced is not None:
                lines.extend(_render_node(sliced, verbs, manifest, depth=2, parent_label=""))
    return lines if len(lines) > before else []


def _region_actor_refs(region, delivered, observation) -> frozenset[str]:
    try:
        source_index, source = next(
            (index, item)
            for index, item in enumerate(observation.sources, 1)
            if item.observation_id == region.source_id
        )
    except StopIteration:
        return frozenset()
    document = next(
        (item for item in delivered.documents if item.source_ref == f"S{source_index}"),
        None,
    )
    if document is None:
        return frozenset()
    nodes = {item.structure_id: item for item in source.structure}
    roots = tuple(
        item for item in source.structure if not item.parent_structure_id or item.parent_structure_id not in nodes
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
        if ref.startswith("N") and ref in by_ref and manifest.node(ref, executable=False):
            target = by_ref[ref]
            line = f"  [{ref}] {target.role} {_value(target.label)}"
            state = _model_state(target.state, interactive=False)
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
    lines = [f"{heading} exact=true count={len(projection.candidates)}"]
    target_id_by_ref = {ref: target_id for target_id, ref in grounding.target_refs.items()}
    for candidate in projection.candidates:
        target_id = target_id_by_ref.get(candidate.target_ref, "")
        if not target_id or candidate.operation not in verbs.get(candidate.target_ref, ()):
            continue
        region = index.region_for_action(candidate.action_id) or index.region_for_target(target_id)
        if region is None:
            continue
        manifest.node(candidate.target_ref, executable=True)
        for destination in candidate.destinations:
            manifest.node(destination.target_ref, executable=True)
        context, headers = _action_structural_context(target_id, region, observation)
        descriptor = (
            f"  rank={candidate.rank} [{candidate.target_ref}] {candidate.operation} "
            f"{candidate.role} {_value(candidate.label)} "
            f"path={_value(candidate.functional_path)} region=[{candidate.region_ref}] "
            f"verbs={_value(verbs[candidate.target_ref])}"
        )
        state = _model_state(candidate.public_state, interactive=True)
        if state:
            descriptor += f" state={_value(state)}"
        actor_node = _actor_node_for_ref(delivered, candidate.target_ref)
        if actor_node is not None:
            evidence = {
                key: ref for key, ref in actor_node.state_evidence.items() if key in state and ref.startswith("F")
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
    try:
        source_index, source = next(
            (source_index, item)
            for source_index, item in enumerate(observation.sources, 1)
            if item.observation_id == region.source_id
        )
    except StopIteration:
        return {}
    document = next(
        (item for item in delivered.documents if item.source_ref == f"S{source_index}"),
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

    source = next(
        (item for item in observation.sources if item.observation_id == region.source_id),
        None,
    )
    if source is not None:
        canonical = {
            (item.source_observation_id, item.source_target_id): item.canonical_target_id
            for item in observation.entity_source_links
        }
        local_nodes = tuple(item for item in source.structure if item.structure_id in region.member_structure_ids)
        target_offset = next(
            (
                offset
                for offset, item in enumerate(local_nodes)
                if item.semantic_target_id
                and canonical.get((source.observation_id, item.semantic_target_id), item.semantic_target_id)
                == target_id
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
    if region.repeated_item_roots and len(region.repeated_item_roots) > limits.repeated_items:
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


def _region_descriptor_text(region: WorldRegion, limits: DeliveryLimits) -> str:
    labels = tuple(item for item in (region.heading, *region.direct_labels) if item)
    if region.role == "generic" and not labels:
        return ""
    parts = [f"[{region.public_ref}]", f"kind={_value(region.role or 'region')}"]
    if region.heading:
        parts.append(f"heading={_value(region.heading)}")
    if region.direct_labels:
        parts.append(f"labels={_value(region.direct_labels)}")
    if region.scope_path:
        parts.append(f"context={_value(region.scope_path)}")
    parts.extend(
        (
            f"items={region.counts.get('items', 0)}",
            f"targets={region.counts.get('targets', 0)}",
            f"facts={region.counts.get('facts', 0)}",
            f"actions={region.counts.get('actions', 0)}",
            f"source_coverage={region.source_coverage}",
            f"region_membership={region.region_membership}",
        )
    )
    if region.role in {"table", "grid"}:
        parts.append(f"available_filter_controls={region.counts.get('filter_controls', 0)}")
    if region.state_badges:
        parts.append(f"state={_value(region.state_badges)}")
    parts.append("recovery=read_region")
    while _estimate_tokens(" ".join(parts)) > limits.descriptor_tokens and "labels=" in " ".join(parts):
        parts = [item for item in parts if not item.startswith("labels=")]
    text = " ".join(parts)
    return text if _estimate_tokens(text) <= limits.descriptor_tokens else ""


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


def _region_search_text(region: WorldRegion) -> str:
    return " ".join((region.role, region.heading, *region.direct_labels))


def _region_public_refs(region, grounding) -> frozenset[str]:
    return frozenset(
        grounding.target_refs[target_id] for target_id in region.member_target_ids if target_id in grounding.target_refs
    )


def _find_matches(
    index,
    query,
    observation,
    grounding,
    *,
    public_fact_bindings: Mapping[str, str] | None = None,
    evidence_index: WorldEvidenceIndex | None = None,
) -> tuple[Mapping[str, object], ...]:
    needle = query.casefold()[:120]
    public_by_canonical = {canonical: public for public, canonical in (public_fact_bindings or {}).items()}
    sources = {item.observation_id: item for item in observation.sources}
    locations = {
        target_id: (region.public_ref, grounding.target_refs.get(target_id, ""))
        for region in index.regions
        for target_id in region.member_target_ids
    }
    matches: list[Mapping[str, object]] = []
    for target in observation.targets:
        values = [target.role, target.label, *(str(value) for value in target.state.values())]
        if needle not in " ".join(values).casefold():
            continue
        region_ref, node_ref = locations.get(target.target_id, ("", ""))
        match = {
            "region_ref": region_ref,
            "node_ref": node_ref if node_ref.startswith("N") else "",
            "role": target.role,
            "label": target.label,
            "structural_context": region_ref,
            "state": target.state,
        }
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
        values = [fact.predicate, str(fact.value)]
        if needle not in " ".join(values).casefold():
            continue
        region = index.region_for_fact(fact.fact_id)
        region_ref = region.public_ref if region else ""
        canonical_record = (
            evidence_index.resolve_record(canonical_fact_ref(fact.fact_id)) if evidence_index is not None else None
        )
        public_ref = public_by_canonical.get(canonical_fact_ref(fact.fact_id), "")
        match = {
            "region_ref": region.public_ref if region else "",
            "node_ref": (ref if (ref := locations.get(fact.subject_id, ("", ""))[1]).startswith("N") else ""),
            "role": "fact",
            "label": fact.predicate,
            "value": fact.value,
        }
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
        return evidence_index.resolve_record(canonical_public_text_ref(observation.observation_id, target.target_id))
    for predicate, value in target.state.items():
        if needle not in str(value).casefold():
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
    observation,
    grounding,
    *,
    public_fact_bindings: Mapping[str, str],
    evidence_index: WorldEvidenceIndex | None,
) -> tuple[Mapping[str, object], ...]:
    targets = {item.target_id: item for item in observation.targets}
    if region.repeated_item_roots:
        source = next(
            (item for item in observation.sources if item.observation_id == region.source_id),
            None,
        )
        if source is not None:
            nodes = {item.structure_id: item for item in source.structure}
            canonical = {
                item.source_target_id: item.canonical_target_id
                for item in observation.entity_source_links
                if item.source_observation_id == source.observation_id
            }
            grouped: list[Mapping[str, object]] = []
            repeated_target_ids: set[str] = set()
            for root_id in region.repeated_item_roots:
                if root_id not in nodes:
                    continue
                target_ids = tuple(
                    dict.fromkeys(
                        canonical.get(nodes[item_id].semantic_target_id, "")
                        for item_id in _walk_structure_ids(root_id, nodes)
                        if nodes[item_id].semantic_target_id
                        and canonical.get(nodes[item_id].semantic_target_id, "") in targets
                    )
                )
                repeated_target_ids.update(target_ids)
                grouped.append(
                    {
                        "kind": "complete_item",
                        "role": nodes[root_id].role,
                        "label": nodes[root_id].label,
                        "targets": tuple(
                            _target_item(
                                region,
                                targets[target_id],
                                grounding,
                                public_fact_bindings,
                                evidence_index,
                            )
                            for target_id in target_ids
                        ),
                    }
                )
            if grouped:
                schema = tuple(
                    {
                        "kind": "schema_member",
                        **_target_item(
                            region,
                            targets[target_id],
                            grounding,
                            public_fact_bindings,
                            evidence_index,
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
                region,
                target,
                grounding,
                public_fact_bindings,
                evidence_index,
            )
        )
    return tuple(items)


def _target_item(region, target, grounding, public_fact_bindings, evidence_index) -> Mapping[str, object]:
    item: dict[str, object] = {
        "region_ref": region.public_ref,
        "role": target.role,
        "label": target.label,
        "state": target.state,
    }
    if evidence_index is None:
        return item
    public_by_canonical = {canonical: public for public, canonical in public_fact_bindings.items()}
    records = tuple(
        record
        for record in evidence_index.records
        if record.subject_id == target.target_id
        and record.evidence_ref in public_by_canonical
        and is_public_scalar(record.value)
    )
    if records:
        item["evidence"] = tuple(
            {
                "evidence_ref": public_by_canonical[record.evidence_ref],
                "predicate": record.predicate,
                "value": record.value,
            }
            for record in records[:8]
        )
    return item


def _walk_structure_ids(root_id, nodes):
    yield root_id
    for child_id in nodes[root_id].child_structure_ids:
        if child_id in nodes:
            yield from _walk_structure_ids(child_id, nodes)


def _page_region_items(items, cursor: str, page_size: int):
    repeated = tuple(item for item in items if item.get("kind") == "complete_item")
    if not repeated:
        offset = _decode_simple_cursor(cursor, len(items))
        page, next_cursor = _page_items(items, offset, page_size)
        total_pages = max(1, (len(items) + page_size - 1) // page_size)
        return page, next_cursor, f"{offset // page_size + 1}/{total_pages}"
    schema = tuple(item for item in items if item.get("kind") != "complete_item")
    offset = _decode_simple_cursor(cursor, len(repeated))
    page, next_cursor = _page_items(repeated, offset, page_size)
    total_pages = max(1, (len(repeated) + page_size - 1) // page_size)
    return (*schema, *page), next_cursor, f"{offset // page_size + 1}/{total_pages}"


def _region_item(region) -> Mapping[str, object]:
    return {
        "region_ref": region.public_ref,
        "kind": region.role,
        "heading": region.heading,
        "labels": region.direct_labels,
        "counts": region.counts,
        "coverage": region.coverage,
        "recovery": "read_region",
    }


def _page_items(items, offset: int, page_size: int):
    page = tuple(items[offset : offset + page_size])
    next_offset = offset + len(page)
    return page, str(next_offset) if next_offset < len(items) else ""


def _decode_simple_cursor(cursor: str, total: int) -> int:
    if not cursor:
        return 0
    if not cursor.isdigit():
        raise ValueError("invalid cursor")
    offset = int(cursor)
    if offset < 0 or offset > total:
        raise ValueError("cursor outside result")
    return offset


def _index_coverage(index) -> str:
    return "partial" if any(item.coverage != "complete" for item in index.regions) else "complete"


def _model_state(state: Mapping[str, object], *, interactive: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in state.items():
        if key.startswith("semantic.dom.") and key not in _PUBLIC_DOM_STATE_FIELDS:
            continue
        if key in _DROPPED_STATE_FIELDS:
            continue
        if any(key.startswith(prefix) for prefix in _DROPPED_STATE_PREFIXES):
            continue
        if key == "viewport.visible" and value is True:
            continue
        if key in {"active", "checked", "selected", "pressed", "expanded", "disabled"}:
            if value is False and not interactive:
                continue
        result[key] = value
    return result


def _short_field(value: str) -> str:
    for prefix in ("semantic.dom.attribute.", "semantic.", "viewport."):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _is_model_ref(value: str) -> bool:
    return bool(_REF.fullmatch(value)) and value[:1] in {"E", "N"}


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text.encode("utf-8")) + 3) // 4) if text else 0


def _value(value: object) -> str:
    return json.dumps(to_json_compatible(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
