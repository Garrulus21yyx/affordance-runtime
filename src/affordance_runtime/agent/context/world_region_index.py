"""Deterministic functional delivery index over one current public World."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.contracts import CoverageState, WorldObservation


@dataclass(frozen=True)
class DeliveryLimits:
    """Frozen v2 semantic-delivery limits (estimated text tokens)."""

    exact_region_tokens: int = 4_000
    repeated_items: int = 20
    top_navigation_controls: int = 24
    top_navigation_tokens: int = 1_500
    descriptor_tokens: int = 160
    page_map_tokens: int = 4_000
    version: str = "delivery-limits.v2"

    def __post_init__(self) -> None:
        numeric_limits = (
            self.exact_region_tokens,
            self.repeated_items,
            self.top_navigation_controls,
            self.top_navigation_tokens,
            self.descriptor_tokens,
            self.page_map_tokens,
        )
        if any(type(value) is not int or value < 1 for value in numeric_limits):
            raise ValueError("delivery limits must be positive integers")
        if not self.version.strip():
            raise ValueError("delivery limits require a version")


DELIVERY_LIMITS_V2 = DeliveryLimits()

_BOUNDARY_ROLES = frozenset(
    {
        "alert",
        "alertdialog",
        "application",
        "complementary",
        "dialog",
        "document",
        "feed",
        "form",
        "grid",
        "list",
        "main",
        "menu",
        "menubar",
        "navigation",
        "region",
        "search",
        "table",
        "toolbar",
        "tree",
        "webarea",
        "rootwebarea",
    }
)
_REPEATED_ITEM_ROLES = frozenset({"article", "card", "listitem", "row", "treeitem"})
_ATOMIC_CONTAINER_ROLES = frozenset({"grid", "list", "table"})
_HEADING_ROLES = frozenset({"heading"})
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)


class FunctionalContainerKind(StrEnum):
    FORM = "form"
    SEARCH = "search"
    DIALOG = "dialog"
    NAVIGATION = "navigation"
    TABLE = "table"
    LIST = "list"
    REGION = "region"
    GENERIC = "generic"


@dataclass(frozen=True)
class TargetFunctionalContext:
    """Canonical public structure facets for one current target."""

    target_id: str
    primary_region_key: str
    container_kind: FunctionalContainerKind
    public_order: int
    focused: bool = False
    viewport: str = "unknown"
    secondary_provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.primary_region_key.startswith("region:"):
            raise ValueError("functional context requires a current target and primary region")
        if type(self.public_order) is not int or self.public_order < 0:
            raise ValueError("functional context public order is invalid")
        if self.viewport not in {"visible", "offscreen", "unknown"}:
            raise ValueError("functional context viewport state is invalid")
        object.__setattr__(self, "secondary_provenance", tuple(sorted(set(self.secondary_provenance))))


@dataclass(frozen=True)
class WorldRegion:
    key: str
    source_id: str
    root_structure_id: str
    member_target_ids: tuple[str, ...] = ()
    member_fact_ids: tuple[str, ...] = ()
    heading: str = ""
    role: str = "region"
    counts: Mapping[str, int] = field(default_factory=dict)
    coverage: str = "complete"
    member_structure_ids: tuple[str, ...] = ()
    member_action_ids: tuple[str, ...] = ()
    direct_labels: tuple[str, ...] = ()
    repeated_item_roots: tuple[str, ...] = ()
    state_badges: Mapping[str, object] = field(default_factory=dict)
    source_coverage: str = ""
    region_membership: str = "complete"
    scope_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.key.startswith("region:")
            or not self.source_id.strip()
            or not self.root_structure_id.strip()
        ):
            raise ValueError("delivery region requires current private identity and public handle")
        for name in (
            "member_structure_ids",
            "member_target_ids",
            "member_fact_ids",
            "member_action_ids",
            "direct_labels",
            "repeated_item_roots",
            "scope_path",
        ):
            values = tuple(getattr(self, name))
            if len(values) != len(set(values)):
                raise ValueError(f"delivery region {name} must be unique")
            object.__setattr__(self, name, values)
        counts = dict(self.counts)
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("delivery region counts must be non-negative integers")
        object.__setattr__(self, "counts", freeze_json(counts))
        object.__setattr__(self, "state_badges", freeze_json(dict(self.state_badges)))
        if self.coverage not in {"complete", "partial"}:
            raise ValueError("delivery region coverage is invalid")
        source_coverage = self.source_coverage or self.coverage
        if source_coverage not in {"complete", "partial"}:
            raise ValueError("delivery region source coverage is invalid")
        if self.region_membership not in {"complete", "partial"}:
            raise ValueError("delivery region membership is invalid")
        object.__setattr__(self, "source_coverage", source_coverage)


@dataclass(frozen=True)
class RegionVersion:
    """Frozen per-document region cache contract; lifecycle wiring is stage 3."""

    region_key: str
    document_lineage: str
    content_digest: str
    structure_digest: str
    version: int
    cached_outline: tuple[str, ...] = ()
    member_target_ids: tuple[str, ...] = ()
    member_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.region_key.startswith("region:") or not all(
            value.strip() for value in (self.document_lineage, self.content_digest, self.structure_digest)
        ):
            raise ValueError("region version requires stable identity, lineage, and digests")
        if type(self.version) is not int or self.version < 1:
            raise ValueError("region version must be a positive exact integer")
        for name in ("cached_outline", "member_target_ids", "member_fact_ids"):
            values = tuple(getattr(self, name))
            if len(values) != len(set(values)):
                raise ValueError(f"region version {name} must be exact and unique")
            object.__setattr__(self, name, values)


@dataclass(frozen=True)
class WorldDeliveryIndex:
    """One recomputable partition plus complete public content/action indexes."""

    world_observation_id: str
    regions: tuple[WorldRegion, ...] = ()
    target_region_keys: Mapping[str, str] = field(default_factory=dict, repr=False)
    fact_region_keys: Mapping[str, str] = field(default_factory=dict, repr=False)
    action_region_keys: Mapping[str, str] = field(default_factory=dict, repr=False)
    target_functional_paths: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict,
        repr=False,
    )
    public_world_delta: object | None = field(default=None, repr=False, compare=False)
    document_lineage: str = ""
    region_versions: tuple[RegionVersion, ...] = ()
    target_contexts: Mapping[str, TargetFunctionalContext] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.world_observation_id.strip():
            raise ValueError("delivery index requires observation identity")
        regions = tuple(self.regions)
        if len({item.key for item in regions}) != len(regions):
            raise ValueError("delivery region keys must be unique")
        keys = {item.key for item in regions}
        for name in ("target_region_keys", "fact_region_keys", "action_region_keys"):
            mapping = dict(getattr(self, name))
            if not mapping:
                member_name = {
                    "target_region_keys": "member_target_ids",
                    "fact_region_keys": "member_fact_ids",
                    "action_region_keys": "member_action_ids",
                }[name]
                mapping = {member_id: region.key for region in regions for member_id in getattr(region, member_name)}
            if any(key not in keys for key in mapping.values()):
                raise ValueError(f"{name} points outside the delivery partition")
            object.__setattr__(self, name, freeze_json(mapping))
        if len(self.target_region_keys) != sum(len(item.member_target_ids) for item in regions):
            raise ValueError("delivery target partition is not complete and disjoint")
        if len(self.fact_region_keys) != sum(len(item.member_fact_ids) for item in regions):
            raise ValueError("delivery fact partition is not complete and disjoint")
        paths = {
            str(target_id): tuple(str(item) for item in path if str(item).strip())
            for target_id, path in dict(self.target_functional_paths).items()
        }
        if any(target_id not in self.target_region_keys for target_id in paths):
            raise ValueError("functional path points outside the target partition")
        object.__setattr__(self, "target_functional_paths", freeze_json(paths))
        object.__setattr__(self, "regions", regions)
        if self.public_world_delta is not None:
            from affordance_runtime.agent.context.world_transition import PublicWorldDelta

            if not isinstance(self.public_world_delta, PublicWorldDelta):
                raise TypeError("delivery index transition must be a typed public World delta")
            if self.public_world_delta.after_observation_id != self.world_observation_id:
                raise ValueError("delivery index transition must terminate at its current World")
        lineage = self.document_lineage or f"document:{self.world_observation_id}"
        if not lineage.startswith("document:"):
            raise ValueError("delivery index document lineage is invalid")
        versions = tuple(self.region_versions)
        if versions:
            if len({item.region_key for item in versions}) != len(versions):
                raise ValueError("delivery region versions must be unique")
            if {item.region_key for item in versions} != keys:
                raise ValueError("delivery region versions must cover the exact partition")
            if any(item.document_lineage != lineage for item in versions):
                raise ValueError("delivery region version belongs to another document lineage")
            for item in versions:
                region = self.get(item.region_key)
                assert region is not None
                if (
                    item.member_target_ids != region.member_target_ids
                    or item.member_fact_ids != region.member_fact_ids
                ):
                    raise ValueError("delivery region version membership must be exact")
        object.__setattr__(self, "document_lineage", lineage)
        object.__setattr__(self, "region_versions", versions)
        contexts = dict(self.target_contexts)
        if contexts and set(contexts) != set(self.target_region_keys):
            raise ValueError("functional contexts must cover the exact target partition")
        if any(
            not isinstance(item, TargetFunctionalContext)
            or item.target_id != target_id
            or item.primary_region_key != self.target_region_keys[target_id]
            for target_id, item in contexts.items()
        ):
            raise ValueError("functional context disagrees with the primary target partition")
        object.__setattr__(self, "target_contexts", MappingProxyType(contexts))

    @classmethod
    def from_observation(
        cls,
        observation: WorldObservation,
        action_options: Sequence[object] = (),
        *,
        limits: DeliveryLimits = DELIVERY_LIMITS_V2,
        public_world_delta: object | None = None,
        previous_index: "WorldDeliveryIndex | None" = None,
    ) -> "WorldDeliveryIndex":
        seeds = _functional_partition(observation, action_options, limits)
        regions = _materialize_regions(observation, seeds)
        target_keys = {target_id: region.key for region in regions for target_id in region.member_target_ids}
        fact_keys = {fact_id: region.key for region in regions for fact_id in region.member_fact_ids}
        action_keys = {action_id: region.key for region in regions for action_id in region.member_action_ids}
        paths = _target_functional_paths(observation, regions, target_keys)
        document_lineage = _document_lineage(observation)
        versions = _region_versions(
            observation,
            regions,
            document_lineage,
            previous_index,
            limits,
        )
        contexts = _target_functional_contexts(
            observation,
            regions,
            target_keys,
        )
        return cls(
            observation.observation_id,
            regions,
            target_keys,
            fact_keys,
            action_keys,
            paths,
            public_world_delta,
            document_lineage,
            versions,
            contexts,
        )

    def get(self, key: str) -> WorldRegion | None:
        return next((region for region in self.regions if region.key == key), None)

    def member_target_ids(self, key: str) -> tuple[str, ...]:
        region = self.get(key)
        return region.member_target_ids if region is not None else ()

    def region_for_target(self, target_id: str) -> WorldRegion | None:
        return self.get(str(self.target_region_keys.get(target_id, "")))

    def region_for_fact(self, fact_id: str) -> WorldRegion | None:
        return self.get(str(self.fact_region_keys.get(fact_id, "")))

    def region_for_action(self, action_id: str) -> WorldRegion | None:
        return self.get(str(self.action_region_keys.get(action_id, "")))

    def functional_path_for_target(self, target_id: str) -> tuple[str, ...]:
        path = self.target_functional_paths.get(target_id)
        if path:
            return tuple(path)
        region = self.region_for_target(target_id)
        return region.scope_path if region is not None else ()

    def functional_context_for_target(self, target_id: str) -> TargetFunctionalContext | None:
        return self.target_contexts.get(target_id)

    def version_for(self, region_key: str) -> RegionVersion | None:
        return next((item for item in self.region_versions if item.region_key == region_key), None)


@dataclass(frozen=True)
class _RegionSeed:
    source_id: str
    root_structure_id: str
    member_structure_ids: tuple[str, ...]
    member_target_ids: tuple[str, ...]
    member_fact_ids: tuple[str, ...]
    member_action_ids: tuple[str, ...]
    heading: str
    role: str
    direct_labels: tuple[str, ...]
    repeated_item_roots: tuple[str, ...]
    counts: Mapping[str, int]
    state_badges: Mapping[str, object]
    coverage: str
    scope_path: tuple[str, ...]


def _functional_partition(
    observation: WorldObservation,
    action_options: Sequence[object],
    limits: DeliveryLimits,
) -> tuple[_RegionSeed, ...]:
    canonical = {
        (item.source_observation_id, item.source_target_id): item.canonical_target_id
        for item in observation.entity_source_links
    }
    target_by_id = {item.target_id: item for item in observation.targets}
    source_for_target: dict[str, str] = {}
    structure_for_target: dict[str, tuple[str, str]] = {}
    seeds: list[dict[str, object]] = []
    structure_region: dict[tuple[str, str], int] = {}

    for source in observation.sources:
        nodes = {item.structure_id: item for item in source.structure}
        if not nodes:
            continue
        parents = _parents(nodes)
        roots = tuple(item.structure_id for item in source.structure if not parents.get(item.structure_id))
        candidates = _candidate_boundaries(nodes, roots, limits)
        # Icon-only/empty boundaries are representation fragments; omitting the
        # boundary merges their descendants into the nearest meaningful owner.
        candidates = {
            item
            for item in candidates
            if _meaningful_subtree(item, nodes, canonical, source.observation_id, target_by_id)
        }
        if not candidates:
            candidates = set(roots[:1])
        assigned: dict[str, list[str]] = {item: [] for item in candidates}
        for structure_id in nodes:
            owner = _nearest_candidate(structure_id, candidates, parents)
            if owner is None:
                owner = min(candidates, key=lambda item: _source_order(item, source.structure))
            assigned[owner].append(structure_id)
        for root_id in sorted(candidates, key=lambda item: _source_order(item, source.structure)):
            member_structures = tuple(assigned[root_id])
            member_targets = tuple(
                dict.fromkeys(
                    canonical.get((source.observation_id, nodes[item].semantic_target_id), "")
                    for item in member_structures
                    if nodes[item].semantic_target_id
                    and canonical.get((source.observation_id, nodes[item].semantic_target_id), "")
                )
            )
            root = nodes[root_id]
            heading = _exact_heading(root_id, member_structures, nodes, target_by_id, canonical, source.observation_id)
            direct_labels = _direct_labels(root_id, nodes)
            repeated_roots = _repeated_item_roots(root_id, member_structures, nodes)
            state_badges = _state_badges(member_targets, target_by_id)
            seed_index = len(seeds)
            scope_path = _scope_path(root_id, nodes, parents)
            seeds.append(
                {
                    "source_id": source.observation_id,
                    "root_structure_id": root_id,
                    "member_structure_ids": member_structures,
                    "member_target_ids": member_targets,
                    "member_fact_ids": [],
                    "member_action_ids": [],
                    "heading": heading,
                    "role": _region_kind(_functional_role(root)),
                    "direct_labels": direct_labels,
                    "repeated_item_roots": repeated_roots,
                    "state_badges": state_badges,
                    "coverage": _coverage(source.coverage, len(source.structure), source.structure_total_count),
                    "scope_path": scope_path,
                }
            )
            for structure_id in member_structures:
                structure_region[(source.observation_id, structure_id)] = seed_index
            for target_id in member_targets:
                source_for_target.setdefault(target_id, source.observation_id)
                structure_for_target.setdefault(target_id, (source.observation_id, root_id))

    if not seeds:
        world_coverage = (
            "partial"
            if any(source.coverage is not CoverageState.COMPLETE for source in observation.sources)
            else "complete"
        )
        seeds.append(
            {
                "source_id": observation.sources[0].observation_id if observation.sources else "world",
                "root_structure_id": "world",
                "member_structure_ids": (),
                "member_target_ids": (),
                "member_fact_ids": [],
                "member_action_ids": [],
                "heading": "Current page",
                "role": "document",
                "direct_labels": (),
                "repeated_item_roots": (),
                "state_badges": {},
                "coverage": world_coverage,
                "scope_path": ("Current page",),
            }
        )

    target_memberships: dict[str, list[int]] = defaultdict(list)
    for index, seed in enumerate(seeds):
        for target_id in seed["member_target_ids"]:  # type: ignore[union-attr]
            target_memberships[str(target_id)].append(index)
    target_owner = {
        target_id: min(indexes, key=lambda index: _primary_seed_key(seeds[index], observation))
        for target_id, indexes in target_memberships.items()
    }
    for index, seed in enumerate(seeds):
        seed["member_target_ids"] = tuple(
            target_id for target_id in seed["member_target_ids"]  # type: ignore[union-attr]
            if target_owner[str(target_id)] == index
        )
    # Targets without a structural source remain public and are merged into the
    # first matching source/document owner rather than dropped.
    for target in observation.targets:
        if target.target_id in target_owner:
            continue
        owner = next(
            (index for index, seed in enumerate(seeds) if seed["source_id"] == source_for_target.get(target.target_id)),
            0,
        )
        members = list(seeds[owner]["member_target_ids"])  # type: ignore[arg-type]
        members.append(target.target_id)
        seeds[owner]["member_target_ids"] = tuple(dict.fromkeys(members))
        target_owner[target.target_id] = owner

    for fact in observation.facts:
        owner = target_owner.get(fact.subject_id)
        if owner is None:
            owner = next(
                (
                    index
                    for (source_id, structure_id), index in structure_region.items()
                    if structure_id == fact.subject_id
                ),
                0,
            )
        seeds[owner]["member_fact_ids"].append(fact.fact_id)  # type: ignore[union-attr]

    for option in action_options:
        action_id = str(getattr(option, "action_id", ""))
        target_id = str(getattr(option, "target_id", ""))
        if not action_id:
            continue
        owner = target_owner.get(target_id, 0)
        seeds[owner]["member_action_ids"].append(action_id)  # type: ignore[union-attr]

    result: list[_RegionSeed] = []
    facts_by_id = {item.fact_id: item for item in observation.facts}
    options_by_id = {
        str(getattr(item, "action_id", "")): item for item in action_options if str(getattr(item, "action_id", ""))
    }
    for seed in seeds:
        targets = tuple(seed["member_target_ids"])  # type: ignore[arg-type]
        facts = tuple(dict.fromkeys(seed["member_fact_ids"]))  # type: ignore[arg-type]
        actions = tuple(dict.fromkeys(seed["member_action_ids"]))  # type: ignore[arg-type]
        filter_targets = {
            str(getattr(options_by_id[action_id], "target_id", ""))
            for action_id in actions
            if action_id in options_by_id
            and str(getattr(options_by_id[action_id], "semantic_action", "")) in {"select_option", "type_text"}
        }
        structures = tuple(seed["member_structure_ids"])  # type: ignore[arg-type]
        source = next(
            (item for item in observation.sources if item.observation_id == seed["source_id"]),
            None,
        )
        structures_by_id = {item.structure_id: item for item in source.structure} if source is not None else {}
        estimated_tokens = _estimate_tokens(
            " ".join(
                (
                    *(
                        f"{structures_by_id[item].role} {structures_by_id[item].label} "
                        f"{dict(structures_by_id[item].state)}"
                        for item in structures
                        if item in structures_by_id
                    ),
                    *(
                        f"{target_by_id[item].role} {target_by_id[item].label} {dict(target_by_id[item].state)}"
                        for item in targets
                        if item in target_by_id
                    ),
                    *(
                        f"{facts_by_id[item].predicate} {facts_by_id[item].value}"
                        for item in facts
                        if item in facts_by_id
                    ),
                )
            )
        )
        result.append(
            _RegionSeed(
                str(seed["source_id"]),
                str(seed["root_structure_id"]),
                structures,
                targets,
                facts,
                actions,
                str(seed["heading"]),
                str(seed["role"]),
                tuple(seed["direct_labels"]),  # type: ignore[arg-type]
                tuple(seed["repeated_item_roots"]),  # type: ignore[arg-type]
                {
                    "structures": len(structures),
                    "targets": len(targets),
                    "facts": len(facts),
                    "actions": len(actions),
                    "items": len(tuple(seed["repeated_item_roots"])),  # type: ignore[arg-type]
                    "estimated_tokens": estimated_tokens,
                    "filter_controls": len(filter_targets),
                },
                dict(seed["state_badges"]),  # type: ignore[arg-type]
                str(seed["coverage"]),
                tuple(seed["scope_path"]),  # type: ignore[arg-type]
            )
        )
    return tuple(sorted(result, key=_seed_public_sort_key))


def _target_functional_paths(
    observation: WorldObservation,
    regions: tuple[WorldRegion, ...],
    target_region_keys: Mapping[str, str],
) -> dict[str, tuple[str, ...]]:
    """Return bounded public label paths; never expose private structure IDs."""

    targets = {item.target_id: item for item in observation.targets}
    regions_by_key = {item.key: item for item in regions}
    result: dict[str, tuple[str, ...]] = {}
    for target_id, target in targets.items():
        region = regions_by_key.get(str(target_region_keys.get(target_id, "")))
        values = list(region.scope_path if region is not None else ())
        ancestors: list[str] = []
        current = target
        visited = {target_id}
        while len(ancestors) < 6:
            parent_id = current.relations.get("parent_id")
            if not isinstance(parent_id, str) or parent_id in visited:
                break
            parent = targets.get(parent_id)
            if parent is None:
                break
            visited.add(parent_id)
            if parent.label.strip():
                ancestors.append(parent.label.strip())
            current = parent
        values.extend(reversed(ancestors))
        if target.label.strip():
            values.append(target.label.strip())
        bounded = tuple(dict.fromkeys(item[:160] for item in values if item.strip()))[-8:]
        if bounded:
            result[target_id] = bounded
    return result


def _candidate_boundaries(nodes, roots: tuple[str, ...], limits: DeliveryLimits) -> set[str]:
    candidates = set(roots)
    for item in nodes.values():
        role = _functional_role(item)
        if role in _BOUNDARY_ROLES:
            candidates.add(item.structure_id)
        children = tuple(nodes[child] for child in item.child_structure_ids if child in nodes)
        if any(child.role.casefold() in _HEADING_ROLES for child in children):
            candidates.add(item.structure_id)
        repeated = defaultdict(int)
        for child in children:
            repeated[child.role.casefold()] += 1
        if any(role in _REPEATED_ITEM_ROLES and count >= 2 for role, count in repeated.items()):
            candidates.add(item.structure_id)
    for root_id in tuple(candidates):
        root = nodes[root_id]
        descendants = tuple(_walk_ids(root_id, nodes))
        boundary_count = sum(
            1 for item in descendants[1:] if _functional_role(nodes[item]) in _BOUNDARY_ROLES | _HEADING_ROLES
        )
        estimated_tokens = _estimate_tokens(" ".join(nodes[item].label for item in descendants if nodes[item].label))
        if _functional_role(root) == "generic" and (boundary_count >= 2 or estimated_tokens > limits.exact_region_tokens):
            for child_id in root.child_structure_ids:
                if child_id in nodes and _meaningful_text(nodes[child_id].label):
                    candidates.add(child_id)
    # A table/grid/list owns its structural schema and repeated items as one
    # semantic region. Descendant rowgroups/rows/listitems and incidental
    # heading boundaries cannot become orphan top-level sibling regions.
    parents = _parents(nodes)
    return {item for item in candidates if not _has_atomic_container_ancestor(item, nodes, parents)}


def _has_atomic_container_ancestor(structure_id: str, nodes, parents: Mapping[str, str]) -> bool:
    current = parents.get(structure_id, "")
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        node = nodes.get(current)
        if node is not None and node.role.casefold() in _ATOMIC_CONTAINER_ROLES:
            return True
        current = parents.get(current, "")
    return False


def _meaningful_subtree(root_id, nodes, canonical, source_id, targets) -> bool:
    for item_id in _walk_ids(root_id, nodes):
        item = nodes[item_id]
        if _meaningful_text(item.label) or _meaningful_state(item.state):
            return True
        target_id = canonical.get((source_id, item.semantic_target_id), "")
        target = targets.get(target_id)
        if target is not None and (_meaningful_text(target.label) or _meaningful_state(target.state)):
            return True
    return False


def _meaningful_text(value: object) -> bool:
    return bool(_ALNUM.search(str(value)))


def _meaningful_state(state: Mapping[str, object]) -> bool:
    return any(value not in (None, "", False, (), [], {}) for value in state.values())


def _parents(nodes) -> dict[str, str]:
    parents = {item.structure_id: item.parent_structure_id for item in nodes.values() if item.parent_structure_id}
    for item in nodes.values():
        for child in item.child_structure_ids:
            if child in nodes:
                parents.setdefault(child, item.structure_id)
    return parents


def _nearest_candidate(structure_id: str, candidates: set[str], parents: Mapping[str, str]) -> str | None:
    current = structure_id
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        if current in candidates:
            return current
        current = parents.get(current, "")
    return None


def _source_order(structure_id: str, structure: Iterable[object]) -> int:
    return next((index for index, item in enumerate(structure) if item.structure_id == structure_id), 10**9)


def _walk_ids(root_id: str, nodes) -> Iterable[str]:
    yield root_id
    for child in nodes[root_id].child_structure_ids:
        if child in nodes:
            yield from _walk_ids(child, nodes)


def _exact_heading(root_id, member_ids, nodes, targets, canonical, source_id) -> str:
    root = nodes[root_id]
    if _meaningful_text(root.label):
        return root.label.strip()
    for item_id in member_ids:
        item = nodes[item_id]
        if item.role.casefold() == "heading" and _meaningful_text(item.label):
            return item.label.strip()
    for item_id in member_ids:
        target_id = canonical.get((source_id, nodes[item_id].semantic_target_id), "")
        target = targets.get(target_id)
        if target is not None and _meaningful_text(target.label):
            return target.label.strip()
    return ""


def _direct_labels(root_id, nodes) -> tuple[str, ...]:
    root = nodes[root_id]
    labels = [
        nodes[item].label.strip()
        for item in root.child_structure_ids
        if item in nodes and _meaningful_text(nodes[item].label)
    ]
    return tuple(dict.fromkeys(labels[:8]))


def _scope_path(root_id: str, nodes, parents: Mapping[str, str]) -> tuple[str, ...]:
    """Return bounded public ancestor scope plus the functional root label."""

    lineage: list[str] = []
    current = root_id
    seen: set[str] = set()
    while current and current not in seen and current in nodes:
        seen.add(current)
        item = nodes[current]
        label = _scope_label(item.label)
        if label and item.role.casefold() in {
            "document",
            "webarea",
            "rootwebarea",
            "main",
            "region",
            "tabpanel",
            "form",
            "search",
            "table",
            "grid",
            "list",
        }:
            lineage.append(label)
        current = parents.get(current, "")
    lineage.reverse()
    page_scope = next(
        (
            _scope_label(item.label)
            for item in nodes.values()
            if item.role.casefold() in {"document", "webarea", "rootwebarea"} and _scope_label(item.label)
        ),
        "",
    )
    if page_scope and page_scope not in lineage:
        lineage.insert(0, page_scope)
    bounded = (page_scope, *lineage[-5:]) if page_scope and len(lineage) > 6 else tuple(lineage[-6:])
    return tuple(dict.fromkeys(bounded))


def _scope_label(value: object) -> str:
    label = " ".join(str(value).split()).strip()
    if not _meaningful_text(label):
        return ""
    # Some AX containers prefix their accessible name with transient status
    # announcements. A trailing name after an ellipsis is the stable local
    # scope; this rule is representation-level and independent of site text.
    if "..." in label:
        suffix = label.rsplit("...", 1)[-1].strip()
        if _meaningful_text(suffix):
            label = suffix
    return label[:160]


def _repeated_item_roots(root_id, member_ids, nodes) -> tuple[str, ...]:
    root = nodes[root_id]
    direct = tuple(
        item
        for item in root.child_structure_ids
        if item in nodes and item in member_ids and nodes[item].role.casefold() in _REPEATED_ITEM_ROLES
    )
    if len(direct) >= 2:
        return direct
    if root.role.casefold() in _ATOMIC_CONTAINER_ROLES:
        groups: list[tuple[str, ...]] = []
        for container_id in member_ids:
            container = nodes[container_id]
            repeated = tuple(
                child
                for child in container.child_structure_ids
                if (child in nodes and child in member_ids and nodes[child].role.casefold() in _REPEATED_ITEM_ROLES)
            )
            if len(repeated) >= 2:
                groups.append(repeated)
        if groups:
            return max(groups, key=lambda items: (len(items), -_source_order(items[0], nodes.values())))
    return ()


def _state_badges(target_ids: tuple[str, ...], targets) -> Mapping[str, object]:
    badges: dict[str, object] = {}
    for key in ("checked", "selected", "active", "expanded", "disabled", "required"):
        values = [targets[item].state.get(key) for item in target_ids if key in targets[item].state]
        if values and all(value == values[0] for value in values):
            badges[key] = values[0]
    return badges


def _region_kind(role: str) -> str:
    normalized = role.casefold() or "region"
    return "document" if normalized in {"webarea", "rootwebarea"} else normalized


def _functional_role(node: object) -> str:
    role = str(getattr(node, "role", "")).casefold() or "generic"
    state = getattr(node, "state", {})
    if isinstance(state, Mapping):
        public_tag = next(
            (
                str(value).casefold()
                for key, value in state.items()
                if str(key).casefold().replace("_", ".") in {"semantic.dom.tag", "dom.tag", "tag"}
            ),
            "",
        )
        if public_tag in _BOUNDARY_ROLES:
            return public_tag
    return role


def _source_family(source_id: str, observation: WorldObservation) -> str:
    manifest = next(
        (item for item in observation.source_manifest if item.source_observation_id == source_id),
        None,
    )
    if manifest is None:
        return "world"
    return f"{manifest.surface}:{manifest.modality}:{manifest.profile}"


def _source_priority(source_id: str, observation: WorldObservation) -> int:
    family = _source_family(source_id, observation).casefold()
    return next(
        (
            rank
            for rank, marker in enumerate(("accessibility", "dom", "http", "wot", "visual"))
            if marker in family
        ),
        99,
    )


def _primary_seed_key(seed: Mapping[str, object], observation: WorldObservation) -> tuple[object, ...]:
    role = str(seed["role"])
    functional_priority = 1 if role in {"generic", "region", "document"} else 0
    return (
        _source_priority(str(seed["source_id"]), observation),
        functional_priority,
        role,
        tuple(seed["scope_path"]),  # type: ignore[arg-type]
        str(seed["heading"]),
        tuple(seed["direct_labels"]),  # type: ignore[arg-type]
    )


def _seed_public_sort_key(seed: _RegionSeed) -> tuple[object, ...]:
    return (
        1 if seed.role in {"generic", "region", "document"} else 0,
        seed.scope_path,
        seed.role,
        seed.heading,
        seed.direct_labels,
        tuple(sorted(seed.state_badges.items())),
    )


def _target_functional_contexts(
    observation: WorldObservation,
    regions: tuple[WorldRegion, ...],
    target_keys: Mapping[str, str],
) -> dict[str, TargetFunctionalContext]:
    targets = {item.target_id: item for item in observation.targets}
    regions_by_key = {item.key: item for item in regions}
    structural_orders = _public_structural_target_orders(observation)
    # Public grounding IDs are scoped to one fresh document, so their
    # occurrence discriminator must be document-scoped too.  A region-local
    # rank loses information when two semantically identical controls live in
    # separate, identically-described regions (a common pattern in long AX
    # trees).  The SurfaceAdapter already owns the source structural order;
    # preserve that mature observation fact here instead of asking a downstream
    # projector or the model to guess which control is which.
    order_keys = {
        target_id: _public_target_order_key(target, structural_orders.get(target_id))
        for target_id, target in targets.items()
    }
    ranks = {key: rank for rank, key in enumerate(sorted(set(order_keys.values())))}
    order = {target_id: ranks[key] for target_id, key in order_keys.items()}
    source_families: dict[str, set[str]] = defaultdict(set)
    for link in observation.entity_source_links:
        source_families[link.canonical_target_id].add(
            _source_family(link.source_observation_id, observation)
        )
    result: dict[str, TargetFunctionalContext] = {}
    for target_id, region_key in target_keys.items():
        target = targets[target_id]
        region = regions_by_key[region_key]
        state = dict(target.state)
        focused = any(
            str(key).casefold().rsplit(".", 1)[-1] == "focused" and value is True
            for key, value in state.items()
        )
        visible = next(
            (
                value for key, value in state.items()
                if str(key).casefold().rsplit(".", 1)[-1] in {"visible", "in_viewport", "offscreen"}
                and isinstance(value, bool)
            ),
            None,
        )
        viewport = "unknown" if visible is None else "visible" if visible else "offscreen"
        primary_family = _source_family(region.source_id, observation)
        secondary = tuple(item for item in source_families.get(target_id, ()) if item != primary_family)
        kind = FunctionalContainerKind(
            region.role if region.role in FunctionalContainerKind._value2member_map_ else "generic"
        )
        result[target_id] = TargetFunctionalContext(
            target_id,
            region_key,
            kind,
            order.get(target_id, len(order)),
            focused,
            viewport,
            secondary,
        )
    return result


def _public_structural_target_orders(
    observation: WorldObservation,
) -> dict[str, tuple[object, ...]]:
    canonical = {
        (item.source_observation_id, item.source_target_id): item.canonical_target_id
        for item in observation.entity_source_links
    }
    manifests = {
        item.source_observation_id: (item.surface, item.modality, item.profile)
        for item in observation.source_manifest
    }
    result: dict[str, tuple[object, ...]] = {}
    for source in observation.sources:
        nodes = {item.structure_id: item for item in source.structure}
        parents = _parents(nodes)
        roots = sorted(
            (item for item in nodes if not parents.get(item)),
            key=lambda item: _structure_public_key(nodes[item]),
        )
        source_key = manifests.get(
            source.observation_id,
            (
                source.surface,
                source.source_profile.modality.value,
                source.source_profile.debug_source,
            ),
        )

        def visit(structure_id: str, path: tuple[int, ...]) -> None:
            node = nodes[structure_id]
            target_id = canonical.get(
                (source.observation_id, node.semantic_target_id),
                node.semantic_target_id,
            )
            if target_id:
                candidate = (*source_key, path)
                previous = result.get(target_id)
                if previous is None or candidate < previous:
                    result[target_id] = candidate
            for ordinal, child_id in enumerate(node.child_structure_ids):
                if child_id in nodes:
                    visit(child_id, (*path, ordinal))

        for ordinal, root_id in enumerate(roots):
            visit(root_id, (ordinal,))
    return result


def _structure_public_key(node: object) -> tuple[str, str, str]:
    return (
        str(getattr(node, "role", "")).casefold(),
        str(getattr(node, "label", "")).casefold(),
        str(getattr(node, "label", "")),
    )


def _public_target_order_key(target: object, structural_order: tuple[object, ...] | None) -> str:
    return json.dumps(
        (
            0 if structural_order is not None else 1,
            structural_order or (),
            str(getattr(target, "role", "")).casefold(),
            str(getattr(target, "label", "")).casefold(),
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _materialize_regions(observation: WorldObservation, seeds: tuple[_RegionSeed, ...]) -> tuple[WorldRegion, ...]:
    regions: list[WorldRegion] = []
    public_occurrences: dict[str, int] = defaultdict(int)
    manifests = {item.source_observation_id: item for item in observation.source_manifest}
    for seed in seeds:
        manifest = manifests.get(seed.source_id)
        source_family = (
            f"{manifest.surface}\0{manifest.modality}\0{manifest.profile}" if manifest is not None else "world"
        )
        public_seed = (
            source_family,
            seed.role,
            seed.heading,
            seed.scope_path,
            seed.direct_labels,
        )
        public_digest = hashlib.sha256(
            json.dumps(public_seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]
        occurrence = public_occurrences[public_digest]
        public_occurrences[public_digest] += 1
        digest = hashlib.sha256(f"{public_digest}:{occurrence}".encode()).hexdigest()[:24]
        regions.append(
            WorldRegion(
                key=f"region:{digest}",
                source_id=seed.source_id,
                root_structure_id=seed.root_structure_id,
                member_target_ids=seed.member_target_ids,
                member_fact_ids=seed.member_fact_ids,
                heading=seed.heading,
                role=seed.role,
                counts=seed.counts,
                coverage=seed.coverage,
                member_structure_ids=seed.member_structure_ids,
                member_action_ids=seed.member_action_ids,
                direct_labels=seed.direct_labels,
                repeated_item_roots=seed.repeated_item_roots,
                state_badges=seed.state_badges,
                source_coverage=seed.coverage,
                region_membership="complete",
                scope_path=seed.scope_path,
            )
        )
    return tuple(regions)


def _document_lineage(observation: WorldObservation) -> str:
    routes = tuple(
        sorted(
            str(target.state.get("page.route", "")).strip()
            for target in observation.targets
            if str(target.state.get("page.route", "")).strip()
        )
    )
    sources = tuple(
        sorted(
            (item.surface, item.modality, item.profile)
            for item in observation.source_manifest
        )
    )
    digest = _json_digest((routes, sources))
    return f"document:{digest[:32]}"


def _region_versions(
    observation: WorldObservation,
    regions: tuple[WorldRegion, ...],
    document_lineage: str,
    previous_index: WorldDeliveryIndex | None,
    limits: DeliveryLimits,
) -> tuple[RegionVersion, ...]:
    previous = {
        item.region_key: item
        for item in previous_index.region_versions
        if previous_index.document_lineage == document_lineage
    } if previous_index is not None else {}
    targets = {item.target_id: item for item in observation.targets}
    facts = {item.fact_id: item for item in observation.facts}
    sources = {item.observation_id: item for item in observation.sources}
    versions: list[RegionVersion] = []
    for region in regions:
        content_digest = _json_digest(
            (
                tuple(
                    (
                        target.target_id,
                        target.role,
                        target.label,
                        target.state,
                        target.relations,
                    )
                    for item in region.member_target_ids
                    if (target := targets.get(item)) is not None
                ),
                tuple(
                    (fact.subject_id, fact.predicate, fact.value)
                    for item in region.member_fact_ids
                    if (fact := facts.get(item)) is not None
                ),
            )
        )
        source = sources.get(region.source_id)
        structures = {item.structure_id: item for item in source.structure} if source is not None else {}
        structure_digest = _json_digest(
            tuple(
                structures[item]
                for item in region.member_structure_ids
                if item in structures
            )
        )
        prior = previous.get(region.key)
        unchanged = bool(
            prior is not None
            and prior.content_digest == content_digest
            and prior.structure_digest == structure_digest
        )
        versions.append(
            RegionVersion(
                region.key,
                document_lineage,
                content_digest,
                structure_digest,
                prior.version if unchanged else prior.version + 1 if prior is not None else 1,
                prior.cached_outline if unchanged else _cached_outline(region, limits),
                region.member_target_ids,
                region.member_fact_ids,
            )
        )
    return tuple(versions)


def _cached_outline(region: WorldRegion, limits: DeliveryLimits) -> tuple[str, ...]:
    values = (
        region.heading,
        region.role,
        *region.scope_path,
        *region.direct_labels,
    )
    bounded = tuple(dict.fromkeys(" ".join(str(item).split())[: limits.descriptor_tokens] for item in values if str(item).strip()))
    return bounded or (region.role,)


def _json_digest(value: object) -> str:
    encoded = json.dumps(
        to_json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _coverage(source_coverage: CoverageState, retained: int, total: int) -> str:
    return "partial" if source_coverage is not CoverageState.COMPLETE or total > retained else "complete"


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text.encode("utf-8")) + 3) // 4) if text else 0
