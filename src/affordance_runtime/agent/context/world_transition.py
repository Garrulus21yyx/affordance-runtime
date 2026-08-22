"""Single typed authority for public transitions between two unified Worlds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import SemanticTarget, StateFact, WorldObservation
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest


class PublicChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass(frozen=True)
class PublicTargetChange:
    kind: PublicChangeKind
    target_id: str
    before: SemanticTarget | None
    after: SemanticTarget | None
    before_region_key: str = ""
    after_region_key: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PublicChangeKind) or not self.target_id.strip():
            raise TypeError("public target change requires typed kind and identity")
        _validate_change_sides(self.kind, self.before, self.after)
        if self.before is not None and self.before.target_id != self.target_id:
            raise ValueError("before target identity does not match public change")
        if self.after is not None and self.after.target_id != self.target_id:
            raise ValueError("after target identity does not match public change")
        _validate_region_membership(self.kind, self.before_region_key, self.after_region_key)


@dataclass(frozen=True)
class PublicFactChange:
    kind: PublicChangeKind
    subject_id: str
    predicate: str
    before: StateFact | None
    after: StateFact | None
    before_region_key: str = ""
    after_region_key: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PublicChangeKind) or not self.subject_id.strip() or not self.predicate.strip():
            raise TypeError("public fact change requires typed kind and identity")
        _validate_change_sides(self.kind, self.before, self.after)
        for fact in (self.before, self.after):
            if fact is not None and (fact.subject_id, fact.predicate) != (
                self.subject_id,
                self.predicate,
            ):
                raise ValueError("fact identity does not match public change")
        _validate_region_membership(self.kind, self.before_region_key, self.after_region_key)


@dataclass(frozen=True)
class PublicWorldDelta:
    """Complete supported-public target/fact delta with exact World lineage."""

    before_observation_id: str
    after_observation_id: str
    before_world_digest: str
    after_world_digest: str
    target_changes: tuple[PublicTargetChange, ...] = ()
    fact_changes: tuple[PublicFactChange, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.before_observation_id,
                self.after_observation_id,
                self.before_world_digest,
                self.after_world_digest,
            )
        ):
            raise ValueError("public World delta requires complete lineage and digests")
        targets = tuple(self.target_changes)
        facts = tuple(self.fact_changes)
        if any(not isinstance(item, PublicTargetChange) for item in targets):
            raise TypeError("public target delta must be typed")
        if any(not isinstance(item, PublicFactChange) for item in facts):
            raise TypeError("public fact delta must be typed")
        if len({item.target_id for item in targets}) != len(targets):
            raise ValueError("a public target may change at most once per transition")
        object.__setattr__(self, "target_changes", targets)
        object.__setattr__(self, "fact_changes", facts)

    @property
    def changed(self) -> bool:
        return bool(self.target_changes or self.fact_changes)

    @property
    def changed_region_keys(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                key
                for item in (*self.target_changes, *self.fact_changes)
                for key in (item.before_region_key, item.after_region_key)
                if key
            )
        )


@dataclass(frozen=True)
class WorldTransitionProjector:
    """Project one deterministic public delta; never infer task semantics."""

    def project(self, before: WorldObservation, after: WorldObservation) -> PublicWorldDelta:
        if not isinstance(before, WorldObservation) or not isinstance(after, WorldObservation):
            raise TypeError("World transition projection requires exact typed Worlds")
        before_regions = WorldDeliveryIndex.from_observation(before)
        after_regions = WorldDeliveryIndex.from_observation(after)
        return PublicWorldDelta(
            before.observation_id,
            after.observation_id,
            public_world_semantic_digest(before),
            public_world_semantic_digest(after),
            _target_changes(before, after, before_regions, after_regions),
            _fact_changes(before, after, before_regions, after_regions),
        )


def _target_changes(before, after, before_regions, after_regions) -> tuple[PublicTargetChange, ...]:
    prior = {item.target_id: item for item in before.targets}
    current = {item.target_id: item for item in after.targets}
    changes: list[PublicTargetChange] = []
    for target_id in sorted(prior.keys() | current.keys()):
        old = prior.get(target_id)
        new = current.get(target_id)
        if old is not None and new is not None and _token(old) == _token(new):
            continue
        kind = (
            PublicChangeKind.ADDED
            if old is None
            else PublicChangeKind.REMOVED
            if new is None
            else PublicChangeKind.MODIFIED
        )
        changes.append(
            PublicTargetChange(
                kind,
                target_id,
                old,
                new,
                _target_region_key(before_regions, target_id),
                _target_region_key(after_regions, target_id),
            )
        )
    return tuple(changes)


def _fact_changes(before, after, before_regions, after_regions) -> tuple[PublicFactChange, ...]:
    prior = _facts_by_semantic_key(before.facts)
    current = _facts_by_semantic_key(after.facts)
    changes: list[PublicFactChange] = []
    for key in sorted(prior.keys() | current.keys()):
        old_items = list(prior.get(key, ()))
        new_items = list(current.get(key, ()))
        old_items, new_items = _unmatched_facts(old_items, new_items)
        paired = min(len(old_items), len(new_items))
        for index in range(paired):
            changes.append(
                _fact_change(
                    PublicChangeKind.MODIFIED, old_items[index], new_items[index], before_regions, after_regions
                )
            )
        for item in old_items[paired:]:
            changes.append(_fact_change(PublicChangeKind.REMOVED, item, None, before_regions, after_regions))
        for item in new_items[paired:]:
            changes.append(_fact_change(PublicChangeKind.ADDED, None, item, before_regions, after_regions))
    return tuple(changes)


def _facts_by_semantic_key(facts: tuple[StateFact, ...]) -> dict[tuple[str, str], tuple[StateFact, ...]]:
    grouped: dict[tuple[str, str], list[StateFact]] = {}
    for fact in facts:
        grouped.setdefault((fact.subject_id, fact.predicate), []).append(fact)
    return {key: tuple(sorted(items, key=_fact_value_token)) for key, items in grouped.items()}


def _unmatched_facts(
    before: list[StateFact],
    after: list[StateFact],
) -> tuple[list[StateFact], list[StateFact]]:
    prior: dict[str, list[StateFact]] = {}
    current: dict[str, list[StateFact]] = {}
    for item in before:
        prior.setdefault(_fact_value_token(item), []).append(item)
    for item in after:
        current.setdefault(_fact_value_token(item), []).append(item)
    unmatched_before: list[StateFact] = []
    unmatched_after: list[StateFact] = []
    for token in sorted(prior.keys() | current.keys()):
        old_items = prior.get(token, [])
        new_items = current.get(token, [])
        retained = min(len(old_items), len(new_items))
        unmatched_before.extend(old_items[retained:])
        unmatched_after.extend(new_items[retained:])
    return unmatched_before, unmatched_after


def _fact_change(kind, before, after, before_regions, after_regions) -> PublicFactChange:
    fact = after if after is not None else before
    assert fact is not None
    return PublicFactChange(
        kind,
        fact.subject_id,
        fact.predicate,
        before,
        after,
        _fact_region_key(before_regions, before.fact_id) if before is not None else "",
        _fact_region_key(after_regions, after.fact_id) if after is not None else "",
    )


def _target_region_key(index: WorldDeliveryIndex, target_id: str) -> str:
    region = index.region_for_target(target_id)
    return region.key if region is not None else ""


def _fact_region_key(index: WorldDeliveryIndex, fact_id: str) -> str:
    region = index.region_for_fact(fact_id)
    return region.key if region is not None else ""


def _token(value: object) -> str:
    return json.dumps(
        to_json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _fact_value_token(fact: StateFact) -> str:
    return _token(fact.value)


def _validate_change_sides(kind: PublicChangeKind, before: object, after: object) -> None:
    expected = {
        PublicChangeKind.ADDED: (False, True),
        PublicChangeKind.REMOVED: (True, False),
        PublicChangeKind.MODIFIED: (True, True),
    }[kind]
    if (before is not None, after is not None) != expected:
        raise ValueError("public change kind contradicts before/after values")


def _validate_region_membership(kind: PublicChangeKind, before: str, after: str) -> None:
    if before and not before.startswith("region:"):
        raise ValueError("before region membership must use a stable region key")
    if after and not after.startswith("region:"):
        raise ValueError("after region membership must use a stable region key")
    if kind is not PublicChangeKind.ADDED and not before:
        raise ValueError("existing public value requires before-region membership")
    if kind is not PublicChangeKind.REMOVED and not after:
        raise ValueError("current public value requires after-region membership")
