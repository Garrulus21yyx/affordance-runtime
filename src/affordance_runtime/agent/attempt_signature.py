"""One ref-free typed identity for public GUI attempts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import SemanticTarget, WorldObservation
from affordance_runtime.world.public_semantic_digest import (
    public_page_semantics,
    target_semantics,
)


@dataclass(frozen=True)
class PublicAttemptSignature:
    operation: str
    precondition_digest: str
    target_semantic_digest: str
    destination_semantic_digest: str
    parameter_digest: str

    def __post_init__(self) -> None:
        if not self.operation.strip() or len(self.operation) > 80:
            raise ValueError("attempt signature operation is invalid")
        for value in (
            self.precondition_digest,
            self.target_semantic_digest,
            self.destination_semantic_digest,
            self.parameter_digest,
        ):
            if value and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value)):
                raise ValueError("attempt signature digest is invalid")

    @property
    def digest(self) -> str:
        return "sha256:" + _digest(to_json_compatible(self))


def public_attempt_signature(
    operation: str,
    target_id: str,
    destination_id: str,
    parameters: Mapping[str, object],
    world: WorldObservation,
) -> PublicAttemptSignature:
    targets = {item.target_id: item for item in world.targets}
    return PublicAttemptSignature(
        operation,
        _precondition_digest(world, target_id, destination_id),
        _target_digest(targets.get(target_id), targets, world),
        _target_digest(targets.get(destination_id), targets, world),
        _digest(to_json_compatible(parameters)),
    )


def _precondition_digest(
    world: WorldObservation,
    target_id: str,
    destination_id: str,
) -> str:
    """Hash only action-scope facts whose change invalidates an exact replay proof."""

    routes = public_page_semantics(world)["routes"]
    scoped_endpoints = _source_target_endpoints(
        world,
        frozenset(item for item in (target_id, destination_id) if item),
    )
    scoped_sources = tuple(
        sorted(
            (
                source.surface,
                source.source_profile.modality.value,
                source.source_profile.assurance.value,
                source.source_profile.verification_strength.value,
                source.coverage.value,
            )
            for source in world.sources
            if any((source.observation_id, item.target_id) in scoped_endpoints for item in source.targets)
        )
    )
    return _digest({"routes": routes, "scoped_sources": scoped_sources})


def _target_digest(
    target: SemanticTarget | None,
    targets: Mapping[str, SemanticTarget],
    world: WorldObservation,
) -> str:
    if target is None:
        return ""
    bases = {
        item.target_id: (
            item.role.casefold(),
            item.label.strip(),
            to_json_compatible(item.state),
        )
        for item in targets.values()
    }
    semantic_value = target_semantics(target, bases)
    peers = tuple(item for item in world.targets if target_semantics(item, bases) == semantic_value)
    occurrence = peers.index(target) if target in peers else 0
    return _digest(
        {
            "semantics": semantic_value,
            "structure_paths": _structure_paths(world, target.target_id),
            "semantic_occurrence": occurrence,
        }
    )


def _structure_paths(world: WorldObservation, target_id: str) -> tuple[tuple[object, ...], ...]:
    paths: list[tuple[object, ...]] = []
    scoped_endpoints = _source_target_endpoints(world, frozenset({target_id}))
    for source in world.sources:
        nodes = {item.structure_id: item for item in source.structure}
        order = {item.structure_id: index for index, item in enumerate(source.structure)}
        for node in source.structure:
            if (source.observation_id, node.semantic_target_id) not in scoped_endpoints:
                continue
            path: list[object] = []
            current = node
            seen: set[str] = set()
            while current.structure_id not in seen and len(path) < 8:
                seen.add(current.structure_id)
                siblings = tuple(
                    item
                    for item in source.structure
                    if item.parent_structure_id == current.parent_structure_id
                    and item.role.casefold() == current.role.casefold()
                    and item.label.strip() == current.label.strip()
                    and to_json_compatible(item.state) == to_json_compatible(current.state)
                )
                sibling_ordinal = sum(order[item.structure_id] < order[current.structure_id] for item in siblings)
                path.append(
                    (
                        current.role.casefold(),
                        current.label.strip(),
                        to_json_compatible(current.state),
                        sibling_ordinal,
                    )
                )
                parent = nodes.get(current.parent_structure_id)
                if parent is None:
                    break
                current = parent
            paths.append(tuple(reversed(path)))
    return tuple(sorted(paths, key=lambda item: json.dumps(to_json_compatible(item), sort_keys=True)))


def _source_target_endpoints(
    world: WorldObservation,
    canonical_target_ids: frozenset[str],
) -> frozenset[tuple[str, str]]:
    endpoints = {
        (link.source_observation_id, link.source_target_id)
        for link in world.entity_source_links
        if link.canonical_target_id in canonical_target_ids
    }
    endpoints.update(
        (source.observation_id, target.target_id)
        for source in world.sources
        for target in source.targets
        if target.target_id in canonical_target_ids
    )
    return frozenset(endpoints)


def _digest(value: object) -> str:
    canonical = json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
