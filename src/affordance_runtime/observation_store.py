"""Immutable in-process canonical observation epoch store and indexes."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.grounding import GroundingCandidate, GroundingSource
from affordance_runtime.unified_observation import (
    CanonicalTarget,
    SourceCoverage,
    StateFact,
    UnifiedObservation,
)


@dataclass(frozen=True)
class ObservationRef:
    epoch_id: str
    digest: str

    def __post_init__(self) -> None:
        if not self.epoch_id.strip() or not self.digest.strip():
            raise ValueError("observation ref identity cannot be blank")


@dataclass(frozen=True)
class ObservationCommit:
    ref: ObservationRef
    environment_revision: str
    page_revision: str

    def __post_init__(self) -> None:
        if not self.environment_revision.strip() or not self.page_revision.strip():
            raise ValueError("observation commit revisions cannot be blank")


@dataclass(frozen=True)
class TargetIndex:
    _items: tuple[tuple[str, CanonicalTarget], ...]

    def get(self, target_id: str) -> CanonicalTarget | None:
        return next((value for key, value in self._items if key == target_id), None)

    def values(self) -> tuple[CanonicalTarget, ...]:
        return tuple(value for _key, value in self._items)


@dataclass(frozen=True)
class BindingIndex:
    _items: tuple[GroundingCandidate, ...]

    def for_target(self, target_id: str) -> tuple[GroundingCandidate, ...]:
        return tuple(item for item in self._items if item.semantic_target_id == target_id)

    def for_action(self, target_id: str, action_kind: str) -> tuple[GroundingCandidate, ...]:
        return tuple(
            item
            for item in self.for_target(target_id)
            if action_kind in item.supported_actions
        )


@dataclass(frozen=True)
class FactIndex:
    _items: tuple[tuple[str, StateFact], ...]

    def get(self, target_id: str, property_name: str) -> StateFact | None:
        key = f"{target_id}\0{property_name}"
        return next((value for item_key, value in self._items if item_key == key), None)


@dataclass(frozen=True)
class CoverageIndex:
    _items: tuple[tuple[GroundingSource, SourceCoverage], ...]

    def get(self, source: GroundingSource) -> SourceCoverage:
        match = next((value for key, value in self._items if key == source), None)
        if match is None:
            raise KeyError(source)
        return match


@dataclass(frozen=True)
class ObservationView:
    ref: ObservationRef
    epoch: UnifiedObservation
    targets: TargetIndex
    bindings: BindingIndex
    facts: FactIndex
    coverage: CoverageIndex


@dataclass
class InMemoryObservationStore:
    _epochs: dict[ObservationRef, UnifiedObservation] = field(default_factory=dict)

    def put(self, observation: UnifiedObservation) -> ObservationRef:
        ref = ObservationRef(observation.epoch_id, observation.digest)
        same_epoch = [item for item in self._epochs if item.epoch_id == ref.epoch_id]
        if same_epoch and ref not in self._epochs:
            raise ValueError("an immutable observation epoch cannot be replaced")
        self._epochs.setdefault(ref, observation)
        return ref

    def get(self, ref: ObservationRef) -> UnifiedObservation:
        try:
            return self._epochs[ref]
        except KeyError as exc:
            raise KeyError(f"unknown observation ref: {ref.epoch_id}") from exc

    def open(self, ref: ObservationRef) -> ObservationView:
        epoch = self.get(ref)
        return ObservationView(
            ref=ref,
            epoch=epoch,
            targets=TargetIndex(tuple((item.target_id, item) for item in epoch.targets)),
            bindings=BindingIndex(epoch.bindings),
            facts=FactIndex(
                tuple(
                    (f"{target.target_id}\0{fact.property_name}", fact)
                    for target in epoch.targets
                    for fact in target.state_facts
                )
            ),
            coverage=CoverageIndex(tuple((item.source, item) for item in epoch.source_coverage)),
        )
