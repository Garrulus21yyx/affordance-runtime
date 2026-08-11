"""One-way model-safe projection of observation-source metadata."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.world import CoverageState, SemanticInventorySummary, SurfaceObservation


@dataclass(frozen=True)
class ModelSemanticInventoryView:
    profile_id: str
    status: str
    recognized_target_count: int
    projected_target_count: int
    actionable_target_count: int
    non_executable_target_count: int
    omitted_target_count: int
    informational_target_count: int


@dataclass(frozen=True)
class ObservationSourceSummary:
    modality: str
    assurance: str
    verification_strength: str
    acquisition_cost: str
    projection_coverage: str
    semantic_inventory: ModelSemanticInventoryView
    freshness: str
    conflict_status: str

    @property
    def coverage(self) -> str:
        """Non-serialized Python compatibility view."""

        return self.projection_coverage


def project_observation_source(
    source: SurfaceObservation,
    projection_coverage: CoverageState,
    *,
    conflicted: bool,
) -> ObservationSourceSummary:
    profile = source.source_profile
    return ObservationSourceSummary(
        str(profile.modality),
        str(profile.assurance),
        str(profile.verification_strength),
        str(profile.acquisition_cost),
        str(projection_coverage),
        project_semantic_inventory(source.semantic_inventory),
        "stale" if projection_coverage is CoverageState.STALE else "current",
        "conflicted" if conflicted else "clear",
    )


def project_semantic_inventory(
    summary: SemanticInventorySummary,
) -> ModelSemanticInventoryView:
    return ModelSemanticInventoryView(
        summary.profile_id,
        summary.status.value,
        summary.recognized_target_count,
        summary.projected_target_count,
        summary.actionable_target_count,
        summary.non_executable_target_count,
        summary.omitted_target_count,
        summary.informational_target_count,
    )
