"""Stable current-world region identity for recoverable delivery."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import CoverageState, WorldObservation


@dataclass(frozen=True)
class WorldRegion:
    key: str
    public_ref: str
    source_id: str
    root_structure_id: str
    member_target_ids: tuple[str, ...] = ()
    member_fact_ids: tuple[str, ...] = ()
    heading: str = ""
    role: str = "region"
    counts: Mapping[str, int] = field(default_factory=dict)
    coverage: str = "complete"

    def __post_init__(self) -> None:
        if (
            not self.key.startswith("region:")
            or not self.public_ref.startswith("R")
            or not self.source_id.strip()
            or not self.root_structure_id.strip()
        ):
            raise ValueError("world region requires stable private identity and public handle")
        object.__setattr__(self, "member_target_ids", tuple(self.member_target_ids))
        object.__setattr__(self, "member_fact_ids", tuple(self.member_fact_ids))
        counts = dict(self.counts)
        if any(not isinstance(value, int) or value < 0 for value in counts.values()):
            raise ValueError("world region counts must be non-negative integers")
        object.__setattr__(self, "counts", freeze_json(counts))


@dataclass(frozen=True)
class WorldRegionIndex:
    world_observation_id: str
    regions: tuple[WorldRegion, ...] = ()

    def __post_init__(self) -> None:
        if not self.world_observation_id.strip():
            raise ValueError("world region index requires observation identity")
        regions = tuple(self.regions)
        if len({item.key for item in regions}) != len(regions):
            raise ValueError("world region keys must be unique")
        if len({item.public_ref for item in regions}) != len(regions):
            raise ValueError("world region public refs must be unique")
        object.__setattr__(self, "regions", regions)

    @classmethod
    def from_observation(cls, observation: WorldObservation) -> "WorldRegionIndex":
        regions = _regions_from_sources(observation)
        if not regions:
            regions = _target_fallback_regions(observation)
        return cls(observation.observation_id, _assign_public_refs(observation.observation_id, regions))

    @property
    def public_refs(self) -> tuple[str, ...]:
        return tuple(region.public_ref for region in self.regions)

    def resolve_public_ref(self, public_ref: str) -> WorldRegion:
        for region in self.regions:
            if region.public_ref == public_ref:
                return region
        raise KeyError(public_ref)

    def get(self, key: str) -> WorldRegion | None:
        return next((region for region in self.regions if region.key == key), None)

    def member_target_ids(self, key: str) -> tuple[str, ...]:
        region = self.get(key)
        return region.member_target_ids if region is not None else ()

    def region_for_target(self, target_id: str) -> WorldRegion | None:
        return next((region for region in self.regions if target_id in region.member_target_ids), None)

    def region_for_fact(self, fact_id: str) -> WorldRegion | None:
        return next((region for region in self.regions if fact_id in region.member_fact_ids), None)


@dataclass(frozen=True)
class _RegionSeed:
    source_id: str
    root_structure_id: str
    member_target_ids: tuple[str, ...]
    member_fact_ids: tuple[str, ...]
    heading: str
    role: str
    counts: Mapping[str, int]
    coverage: str


def _regions_from_sources(observation: WorldObservation) -> tuple[_RegionSeed, ...]:
    links = {
        (item.source_observation_id, item.source_target_id): item.canonical_target_id
        for item in observation.entity_source_links
    }
    facts_by_target: dict[str, list[str]] = {}
    for fact in observation.facts:
        facts_by_target.setdefault(fact.subject_id, []).append(fact.fact_id)
    seeds: list[_RegionSeed] = []
    for source in observation.sources:
        nodes = {item.structure_id: item for item in source.structure}
        if not nodes:
            continue
        children = {child for item in nodes.values() for child in item.child_structure_ids}
        roots = [item for item in source.structure if not item.parent_structure_id and item.structure_id not in children]
        candidates = []
        for root in roots or tuple(source.structure):
            if root.role.casefold() in {"document", "webarea", "rootwebarea"} and root.child_structure_ids:
                candidates.extend(nodes[child] for child in root.child_structure_ids if child in nodes)
            else:
                candidates.append(root)
        for root in candidates:
            local_targets = tuple(
                dict.fromkeys(
                    item.semantic_target_id
                    for item in _walk_structure(root.structure_id, nodes)
                    if item.semantic_target_id
                )
            )
            target_ids = tuple(
                dict.fromkeys(
                    links.get((source.observation_id, target_id), target_id)
                    for target_id in local_targets
                )
            )
            if not target_ids and not root.label.strip():
                continue
            fact_ids = tuple(
                fact_id
                for target_id in target_ids
                for fact_id in facts_by_target.get(target_id, ())
            )
            seeds.append(_RegionSeed(
                source.observation_id,
                root.structure_id,
                target_ids,
                fact_ids,
                root.label.strip() or _first_target_label(observation, target_ids),
                root.role or "region",
                {
                    "targets": len(target_ids),
                    "facts": len(fact_ids),
                    "actions": sum(1 for item in observation.bindings if item.target_id in target_ids),
                },
                _coverage(source.coverage, len(source.structure), source.structure_total_count),
            ))
    return tuple(seeds)


def _target_fallback_regions(observation: WorldObservation) -> tuple[_RegionSeed, ...]:
    source = observation.sources[0] if observation.sources else None
    source_id = source.observation_id if source is not None else "world"
    coverage = _coverage(source.coverage, 0, 0) if source is not None else "complete"
    facts_by_target: dict[str, list[str]] = {}
    for fact in observation.facts:
        facts_by_target.setdefault(fact.subject_id, []).append(fact.fact_id)
    targets = tuple(observation.targets)
    if len(targets) > 32 and len({item.role.casefold() for item in targets}) == 1:
        seeds = []
        for index in range(0, len(targets), 32):
            group = targets[index : index + 32]
            target_ids = tuple(item.target_id for item in group)
            fact_ids = tuple(
                fact_id
                for target_id in target_ids
                for fact_id in facts_by_target.get(target_id, ())
            )
            seeds.append(_RegionSeed(
                source_id,
                f"targets:{index + 1}-{index + len(group)}",
                target_ids,
                fact_ids,
                f"{group[0].role} items {index + 1}-{index + len(group)}",
                group[0].role,
                {
                    "targets": len(target_ids),
                    "facts": len(fact_ids),
                    "actions": sum(1 for item in observation.bindings if item.target_id in target_ids),
                },
                coverage,
            ))
        return tuple(seeds)
    return tuple(_target_seed(source_id, target, facts_by_target, observation, coverage) for target in targets)


def _target_seed(
    source_id: str,
    target,
    facts_by_target: Mapping[str, list[str]],
    observation: WorldObservation,
    coverage: str,
) -> _RegionSeed:
    return _RegionSeed(
        source_id,
        target.target_id,
        (target.target_id,),
        tuple(facts_by_target.get(target.target_id, ())),
        target.label,
        target.role,
        {
            "targets": 1,
            "facts": len(facts_by_target.get(target.target_id, ())),
            "actions": sum(1 for item in observation.bindings if item.target_id == target.target_id),
        },
        coverage,
    )


def _assign_public_refs(
    observation_id: str,
    seeds: tuple[_RegionSeed, ...],
) -> tuple[WorldRegion, ...]:
    regions: list[WorldRegion] = []
    for index, seed in enumerate(seeds, 1):
        digest = hashlib.sha256(
            f"{observation_id}\0{seed.source_id}\0{seed.root_structure_id}".encode()
        ).hexdigest()[:24]
        regions.append(WorldRegion(
            f"region:{digest}",
            f"R{index}",
            seed.source_id,
            seed.root_structure_id,
            seed.member_target_ids,
            seed.member_fact_ids,
                seed.heading[:160],
                seed.role,
            seed.counts,
            seed.coverage,
        ))
    return tuple(regions)


def _walk_structure(root_id, nodes):
    root = nodes[root_id]
    yield root
    for child_id in root.child_structure_ids:
        if child_id in nodes:
            yield from _walk_structure(child_id, nodes)


def _first_target_label(observation: WorldObservation, target_ids: tuple[str, ...]) -> str:
    labels = {item.target_id: item.label for item in observation.targets}
    return next((labels[target_id] for target_id in target_ids if labels.get(target_id)), "")


def _coverage(source_coverage: CoverageState, retained: int, total: int) -> str:
    if source_coverage is not CoverageState.COMPLETE or total > retained:
        return "partial"
    return "complete"
