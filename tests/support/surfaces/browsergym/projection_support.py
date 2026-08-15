"""Test-only composition of a BrowserGym source through production fusion."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.surfaces.browsergym.projection import (
    BrowserGymProjection,
)
from affordance_runtime.surfaces.browsergym.projection import (
    project_browsergym_observation as project_browsergym_source,
)
from affordance_runtime.world import WorldFusion, WorldObservation


@dataclass(frozen=True)
class BrowserGymWorldProjection:
    world: WorldObservation
    private_bindings: tuple
    target_count_total: int
    fact_count_total: int
    semantic_analysis: object


def project_browsergym_observation(*args, **kwargs) -> BrowserGymWorldProjection:
    source_projection: BrowserGymProjection = project_browsergym_source(*args, **kwargs)
    fused = WorldFusion().fuse((source_projection.source,))
    if fused.observation is None:
        raise AssertionError(f"test BrowserGym source did not fuse: {fused.reason_code}")
    return BrowserGymWorldProjection(
        fused.observation,
        source_projection.private_bindings,
        source_projection.target_count_total,
        source_projection.fact_count_total,
        source_projection.semantic_analysis,
    )
