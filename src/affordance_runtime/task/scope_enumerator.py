"""Single Runtime owner for scope-relative candidate enumeration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.task.set_objective import (
    ScopeCoverage,
    ScopeEntityDomain,
    ScopeExtent,
    ScopeSpec,
)
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.source_profile import ObservationModality


@dataclass(frozen=True)
class ScopeEnumeration:
    scope_id: str
    observation_epoch: str
    entity_ids: tuple[str, ...]
    coverage: ScopeCoverage
    evidence_refs: tuple[str, ...] = ()
    continuation_required: bool = False

    def __post_init__(self) -> None:
        values = tuple(self.entity_ids)
        if (
            self.scope_id == ""
            or not self.observation_epoch.strip()
            or len(values) != len(set(values))
            or any(not item.strip() for item in values)
        ):
            raise ValueError("scope enumeration is invalid")
        object.__setattr__(self, "entity_ids", values)
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


class ScopeEnumeratorPort(Protocol):
    def enumerate(self, scope: ScopeSpec, observation: WorldObservation) -> ScopeEnumeration:
        """Enumerate one scope; classifiers may not implement this contract."""


@dataclass(frozen=True)
class SnapshotScopeEnumerator:
    """Complete only for the current viewport; larger scopes request traversal."""

    def enumerate(self, scope: ScopeSpec, observation: WorldObservation) -> ScopeEnumeration:
        world_ids = {item.target_id for item in observation.targets}
        structural_names = {
            source.surface
            for source in observation.sources
            if source.source_profile.modality is ObservationModality.STRUCTURAL
        } or {name for name in observation.coverage if "visual" not in name.casefold()}
        visual_names = {
            source.surface
            for source in observation.sources
            if source.source_profile.modality is ObservationModality.VISUAL
        } or {name for name in observation.coverage if "visual" in name.casefold()}
        structural_ids = {
            target.target_id
            for source in observation.sources
            if source.source_profile.modality is ObservationModality.STRUCTURAL
            for target in source.targets
            if target.target_id in world_ids
        }
        visual_ids: set[str] = set()
        for source in observation.sources:
            if source.source_profile.modality is not ObservationModality.VISUAL:
                continue
            correspondence = {item.source_target_id: item.canonical_target_id for item in source.correspondences}
            visual_ids.update(
                correspondence.get(target.target_id, target.target_id)
                for target in source.targets
                if correspondence.get(target.target_id, target.target_id) in world_ids
            )
        if not observation.sources:
            structural_ids = set(world_ids)
        entity_domain_ids = (
            structural_ids if scope.entity_domain is ScopeEntityDomain.STRUCTURED else structural_ids | visual_ids
        )
        entities = tuple(item.target_id for item in observation.targets if item.target_id in entity_domain_ids)
        structural_complete = bool(structural_names) and all(
            observation.coverage.get(name) is CoverageState.COMPLETE for name in structural_names
        )
        visual_complete = bool(visual_names) and all(
            observation.coverage.get(name) is CoverageState.COMPLETE for name in visual_names
        )
        if scope.entity_domain is ScopeEntityDomain.STRUCTURED:
            required_names = structural_names
            snapshot_complete = structural_complete
        elif scope.entity_domain is ScopeEntityDomain.ALL_VISIBLE:
            required_names = visual_names
            snapshot_complete = visual_complete
        else:
            required_names = structural_names | visual_names
            snapshot_complete = structural_complete and visual_complete
        complete_sources = tuple(
            f"source:{name}:coverage"
            for name in sorted(required_names)
            if observation.coverage.get(name) is CoverageState.COMPLETE
        )
        viewport = scope.extent is ScopeExtent.CURRENT_VIEWPORT
        complete = viewport and snapshot_complete
        return ScopeEnumeration(
            scope.scope_id,
            observation.observation_id,
            entities,
            ScopeCoverage.COMPLETE if complete else ScopeCoverage.PARTIAL,
            complete_sources if complete else (),
            continuation_required=not viewport or not snapshot_complete,
        )
