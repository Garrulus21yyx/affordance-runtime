"""Typed diagnostics derived from canonical BrowserGym semantic analysis."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.surfaces.browsergym.semantics import (
    BrowserGymSemanticAnalysis,
)
from affordance_runtime.world import SemanticInventorySummary


@dataclass(frozen=True)
class BrowserGymDiagnosticSnapshot:
    semantic_inventory: SemanticInventorySummary
    diagnostic_role_distribution: tuple[tuple[str, int], ...]

    def as_metrics(self) -> dict[str, object]:
        inventory = self.semantic_inventory
        return {
            "inventory_profile_id": inventory.profile_id,
            "inventory_status": inventory.status.value,
            "recognized_target_count": inventory.recognized_target_count,
            "projected_target_count": inventory.projected_target_count,
            "actionable_target_count": inventory.actionable_target_count,
            "non_executable_target_count": inventory.non_executable_target_count,
            "omitted_target_count": inventory.omitted_target_count,
            "informational_target_count": inventory.informational_target_count,
            "diagnostic_role_distribution": dict(self.diagnostic_role_distribution),
        }


def diagnostic_snapshot(
    analysis: BrowserGymSemanticAnalysis,
    inventory: SemanticInventorySummary,
) -> BrowserGymDiagnosticSnapshot:
    if inventory.profile_id != analysis.inventory.profile_id:
        raise ValueError("BrowserGym diagnostic inventory profile mismatch")
    if inventory.recognized_target_count != analysis.inventory.recognized_target_count:
        raise ValueError("BrowserGym diagnostic recognized count mismatch")
    return BrowserGymDiagnosticSnapshot(
        inventory,
        analysis.diagnostic_role_distribution,
    )
