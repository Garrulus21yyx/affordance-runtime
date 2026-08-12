"""Pure deterministic fusion of selected source observations into one world."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import (
    ActionBinding,
    ObservationConflict,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


class FusionStatus(StrEnum):
    FUSED = "fused"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class FusedEntityProvenance:
    canonical_target_id: str
    source_refs: tuple[tuple[str, str], ...]
    acquisition_roots: tuple[str, ...]


@dataclass(frozen=True)
class WorldFusionResult:
    status: FusionStatus
    observation: WorldObservation | None
    entity_provenance: tuple[FusedEntityProvenance, ...]
    reason_code: str

    def __post_init__(self) -> None:
        if (self.status is FusionStatus.FUSED) != isinstance(self.observation, WorldObservation):
            raise ValueError("fusion status and observation disagree")


@dataclass(frozen=True)
class WorldFusion:
    def fuse(self, sources: tuple[SurfaceObservation, ...]) -> WorldFusionResult:
        if not sources:
            return WorldFusionResult(FusionStatus.INCONCLUSIVE, None, (), "no_acquired_source")
        for source in sources:
            local_ids = {item.target_id for item in source.targets}
            if any(item.subject_id not in local_ids for item in source.facts) or any(
                item.target_id not in local_ids
                or any(destination not in local_ids for destination in item.eligible_destination_ids)
                for item in source.bindings
            ):
                return WorldFusionResult(
                    FusionStatus.INCONCLUSIVE, None, (), "unresolved_source_subject",
                )
        world_id = _world_id(sources)
        maps = _canonical_maps(sources)
        targets: dict[str, SemanticTarget] = {}
        provenance: dict[str, list[tuple[str, str, str]]] = {}
        conflicts: list[ObservationConflict] = []
        facts: list[StateFact] = []
        fact_values: dict[tuple[str, str], tuple[object, str]] = {}
        fact_ids: set[str] = set()
        bindings: list[ActionBinding] = []
        fused_sources: list[SurfaceObservation] = []

        for source in sources:
            mapping = maps[source.surface]
            for target in source.targets:
                canonical_id = mapping[target.target_id]
                rewritten = replace(
                    target,
                    target_id=canonical_id,
                    relations=_rewrite_relations(dict(target.relations), mapping),
                )
                prior = targets.get(canonical_id)
                if prior is None:
                    targets[canonical_id] = rewritten
                else:
                    conflicts.extend(_target_conflicts(canonical_id, prior, rewritten))
                provenance.setdefault(canonical_id, []).append(
                    (source.surface, target.target_id, source.acquisition_root_id or source.observation_id)
                )
            for fact in source.facts:
                canonical_id = mapping[fact.subject_id]
                key = (canonical_id, fact.predicate)
                prior = fact_values.get(key)
                encoded = json.dumps(to_json_compatible(fact.value), sort_keys=True, separators=(",", ":"))
                if prior is not None and prior[0] != encoded:
                    conflicts.append(ObservationConflict(
                        _conflict_id(canonical_id, fact.predicate), canonical_id, fact.predicate,
                        "material source claims disagree",
                    ))
                else:
                    fact_values.setdefault(key, (encoded, fact.source_id))
                fact_id = fact.fact_id
                if fact_id in fact_ids:
                    duplicate_key = "\0".join((source.surface, fact.fact_id))
                    fact_id = f"fact:{hashlib.sha256(duplicate_key.encode()).hexdigest()}"
                fact_ids.add(fact_id)
                facts.append(replace(fact, fact_id=fact_id, subject_id=canonical_id))
            for binding in source.bindings:
                bindings.append(replace(
                    binding,
                    world_observation_id=world_id,
                    target_id=mapping[binding.target_id],
                    source_target_id=binding.source_target_id or binding.target_id,
                    eligible_destination_ids=tuple(mapping[item] for item in binding.eligible_destination_ids),
                ))
            fused_sources.append(replace(
                source,
                media=tuple(
                    replace(media, grounding_regions=tuple(
                        replace(region, target_id=mapping[region.target_id])
                        for region in media.grounding_regions
                        if region.target_id in mapping
                    ))
                    for media in source.media
                ),
            ))
        unique_conflicts = {
            (item.subject_id, item.predicate): item for item in conflicts
        }
        world = WorldObservation(
            world_id,
            tuple(sorted(targets.values(), key=lambda item: item.target_id)),
            tuple(facts),
            tuple(bindings),
            {source.surface: source.coverage for source in sources},
            tuple(sorted(unique_conflicts.values(), key=lambda item: (item.subject_id, item.predicate))),
            tuple(fused_sources),
        )
        provenance_view = tuple(
            FusedEntityProvenance(
                canonical_id,
                tuple((surface, local_id) for surface, local_id, _ in values),
                tuple(dict.fromkeys(root for _, _, root in values)),
            )
            for canonical_id, values in sorted(provenance.items())
        )
        return WorldFusionResult(FusionStatus.FUSED, world, provenance_view, "world_fused")


def _world_id(sources: tuple[SurfaceObservation, ...]) -> str:
    payload = "\0".join(
        f"{item.surface}\0{item.observation_id}\0{item.revision}\0{item.acquisition_root_id}"
        for item in sorted(sources, key=lambda value: value.surface)
    )
    return sources[0].observation_id if len(sources) == 1 else f"world:{hashlib.sha256(payload.encode()).hexdigest()}"


def _canonical_maps(sources: tuple[SurfaceObservation, ...]) -> dict[str, dict[str, str]]:
    used: dict[str, tuple[str, str]] = {}
    values: dict[str, dict[str, str]] = {}
    for source in sorted(sources, key=lambda item: item.surface):
        explicit = {item.source_target_id: item.canonical_target_id for item in source.correspondences}
        mapping: dict[str, str] = {}
        for target in source.targets:
            candidate = explicit.get(target.target_id, target.target_id)
            owner = used.get(candidate)
            if owner is not None and target.target_id not in explicit:
                candidate = "entity:" + hashlib.sha256(
                    f"{source.surface}\0{target.target_id}".encode()
                ).hexdigest()
            used.setdefault(candidate, (source.surface, target.target_id))
            mapping[target.target_id] = candidate
        values[source.surface] = mapping
    return values


def _rewrite_relations(relations: dict[str, object], mapping: dict[str, str]) -> dict[str, object]:
    for key in ("parent_id", "label_for_id"):
        value = relations.get(key)
        if isinstance(value, str) and value in mapping:
            relations[key] = mapping[value]
    for key in ("child_ids",):
        value = relations.get(key)
        if isinstance(value, tuple | list):
            relations[key] = tuple(mapping.get(str(item), str(item)) for item in value)
    return relations


def _target_conflicts(subject: str, left: SemanticTarget, right: SemanticTarget) -> list[ObservationConflict]:
    conflicts = []
    if left.role != right.role:
        conflicts.append(ObservationConflict(_conflict_id(subject, "role"), subject, "role", "material source claims disagree"))
    if left.label != right.label:
        conflicts.append(ObservationConflict(_conflict_id(subject, "label"), subject, "label", "material source claims disagree"))
    for key in left.state.keys() & right.state.keys():
        if left.state[key] != right.state[key]:
            conflicts.append(ObservationConflict(_conflict_id(subject, key), subject, key, "material source claims disagree"))
    return conflicts


def _conflict_id(subject: str, predicate: str) -> str:
    return "conflict:" + hashlib.sha256(f"{subject}\0{predicate}".encode()).hexdigest()
