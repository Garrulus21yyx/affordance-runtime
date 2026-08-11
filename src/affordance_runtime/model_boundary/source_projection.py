"""One-way model-safe projection of observation-source metadata."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.world import (
    CoverageState,
    EntityInventorySummary,
    SemanticInventorySummary,
    SurfaceObservation,
)


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
    entity_inventory: ModelEntityInventoryView
    freshness: str
    conflict_status: str

    @property
    def coverage(self) -> str:
        """Non-serialized Python compatibility view."""

        return self.projection_coverage


@dataclass(frozen=True)
class ModelEntityInventoryView:
    status: str
    entity_count: int
    entity_total_count: int
    fact_count: int
    fact_total_count: int
    relation_count: int
    relation_total_count: int
    option_value_count: int
    option_value_total_count: int
    issue_codes: tuple[str, ...]


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
        project_entity_inventory(source.entity_inventory),
        "stale" if projection_coverage is CoverageState.STALE else "current",
        "conflicted" if conflicted else "clear",
    )


def project_entity_inventory(summary: EntityInventorySummary) -> ModelEntityInventoryView:
    return ModelEntityInventoryView(
        summary.status.value,
        summary.entity_count,
        summary.entity_total_count,
        summary.fact_count,
        summary.fact_total_count,
        summary.relation_count,
        summary.relation_total_count,
        summary.option_value_count,
        summary.option_value_total_count,
        tuple(code.value for code in summary.issue_codes),
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
