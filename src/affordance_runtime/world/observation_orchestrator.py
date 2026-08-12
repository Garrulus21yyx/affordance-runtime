"""Pure bounded observation-source selection; it performs no acquisition I/O."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.world.acquisition import (
    AcquisitionStatus,
    ObservationOffer,
    ObservationSelectionPlan,
    SourceRequirement,
    SourceSelection,
    WorldObservationRequest,
)
from affordance_runtime.world.source_profile import assurance_satisfies

_COST = {"low": 0, "medium": 1, "high": 2}
_MODALITY = {"structural": 0, "environment_state": 1, "visual": 2, "user": 3}


@dataclass(frozen=True)
class ObservationSelectionResult:
    plan: ObservationSelectionPlan | None
    status: AcquisitionStatus
    reason_code: str

    def __post_init__(self) -> None:
        if (self.plan is None) == (self.status is AcquisitionStatus.ACQUIRED):
            raise ValueError("selection result must contain exactly one typed outcome")


@dataclass(frozen=True)
class ObservationOrchestrator:
    max_source_calls: int = 2

    def select(
        self,
        offers: tuple[ObservationOffer, ...],
        request: WorldObservationRequest,
    ) -> ObservationSelectionResult:
        ordered = tuple(sorted(offers, key=_offer_rank))
        if not ordered:
            return ObservationSelectionResult(None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, "no_source_offer")
        desired_modality = request.modality.strip()
        desired_assurance = request.required_assurance.strip()
        adequate = tuple(
            item for item in ordered
            if (not desired_modality or item.modality == desired_modality)
            and (not desired_assurance or assurance_satisfies(item.assurance, desired_assurance))
        )
        if desired_modality == "visual":
            structural = next((item for item in ordered if item.modality == "structural"), None)
            visual = next((item for item in adequate if item.modality == "visual"), None)
            if visual is None:
                return ObservationSelectionResult(
                    None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, "requested_modality_unavailable",
                )
            selections = []
            if structural is not None:
                selections.append(SourceSelection(structural.source, SourceRequirement.REQUIRED, "structured_grounding"))
                selections.append(SourceSelection(visual.source, SourceRequirement.OPTIONAL, "visual_augmentation"))
            else:
                selections.append(SourceSelection(visual.source, SourceRequirement.REQUIRED, "visual_grounding"))
            return self._bounded(selections)
        if not adequate:
            reason = "requested_assurance_unavailable" if desired_assurance else "requested_modality_unavailable"
            return ObservationSelectionResult(None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, reason)
        preferred = next((item for item in adequate if item.modality == "structural"), adequate[0])
        return self._bounded([
            SourceSelection(preferred.source, SourceRequirement.REQUIRED, "primary_grounding"),
        ])

    def _bounded(self, selections: list[SourceSelection]) -> ObservationSelectionResult:
        selected = tuple(selections[: self.max_source_calls])
        if not selected or not any(item.requirement is SourceRequirement.REQUIRED for item in selected):
            return ObservationSelectionResult(None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, "source_budget_exhausted")
        return ObservationSelectionResult(
            ObservationSelectionPlan(selected, self.max_source_calls),
            AcquisitionStatus.ACQUIRED,
            "sources_selected",
        )


def _offer_rank(offer: ObservationOffer) -> tuple[int, int, str]:
    return (
        _COST.get(offer.acquisition_cost, 99),
        _MODALITY.get(offer.modality, 99),
        offer.source,
    )
