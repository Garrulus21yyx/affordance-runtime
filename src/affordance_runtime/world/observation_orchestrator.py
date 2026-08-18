"""Sole pure owner of bounded observation-source selection."""

from __future__ import annotations

from dataclasses import dataclass, replace

from affordance_runtime.world.acquisition import (
    AcquisitionStatus,
    ObservationOffer,
    ObservationRequestKind,
    ObservationSelectionPlan,
    SourceRequirement,
    SourceSelection,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import SurfaceObservation
from affordance_runtime.world.observation_needs import (
    FreshnessRequirement,
    ObservationNeed,
    ObservationPurpose,
)
from affordance_runtime.world.source_profile import (
    AcquisitionCost,
    ObservationAssurance,
    ObservationModality,
    assurance_satisfies,
)
from affordance_runtime.world.vision_escalation import (
    VisionEvidenceNeed,
    derive_visual_evidence_needs,
)

_COST = {AcquisitionCost.LOW: 0, AcquisitionCost.MEDIUM: 1, AcquisitionCost.HIGH: 2}
_MODALITY = {
    ObservationModality.STRUCTURAL: 0,
    ObservationModality.ENVIRONMENT_STATE: 1,
    ObservationModality.VISUAL: 2,
    ObservationModality.USER: 3,
}


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
    acquisition_budget: int = 2

    def __post_init__(self) -> None:
        if self.acquisition_budget not in {1, 2}:
            raise ValueError("A.2 supports an acquisition budget of one or two sources")

    def select(
        self,
        offers: tuple[ObservationOffer, ...],
        request: WorldObservationRequest,
        *,
        route_source: str = "",
    ) -> ObservationSelectionResult:
        return self._select(offers, request, route_source=route_source)

    def _select(
        self,
        offers: tuple[ObservationOffer, ...],
        request: WorldObservationRequest,
        *,
        route_source: str = "",
        optional_need_ids: frozenset[str] = frozenset(),
    ) -> ObservationSelectionResult:
        ordered = tuple(sorted(offers, key=_offer_rank))
        if not ordered:
            return ObservationSelectionResult(
                None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, "no_source_offer"
            )
        lifecycle_need = _lifecycle_need(request)
        needs = request.needs or (lifecycle_need,)
        unresolved_needs = needs
        selected: dict[str, SourceSelection] = {}
        if route_source:
            route_offer = next((item for item in ordered if item.source == route_source), None)
            if route_offer is None:
                return ObservationSelectionResult(
                    None,
                    AcquisitionStatus.CAPABILITY_UNAVAILABLE,
                    "route_source_unavailable",
                )
            if request.needs:
                needs = _needs_by_id((lifecycle_need, *request.needs))
            selected[route_source] = SourceSelection(
                route_source,
                SourceRequirement.REQUIRED,
                "route_source_refresh",
                (lifecycle_need.need_id,),
            )
            unresolved_needs = request.needs
        for need in sorted(unresolved_needs, key=lambda item: item.need_id):
            requirement = (
                SourceRequirement.OPTIONAL
                if need.need_id in optional_need_ids
                else SourceRequirement.REQUIRED
            )
            if _selected_satisfies(selected, ordered, need, requirement):
                continue
            adequate = tuple(item for item in ordered if _offer_satisfies(item, need))
            if (
                adequate
                and all(item.modality is ObservationModality.VISUAL for item in adequate)
                and not any(
                    _offer(item.source, ordered).modality is ObservationModality.STRUCTURAL
                    for item in selected.values()
                )
            ):
                structural = next(
                    (
                        item
                        for item in ordered
                        if item.modality is ObservationModality.STRUCTURAL
                        and ObservationPurpose.WORLD_GROUNDING in item.supported_purposes
                    ),
                    None,
                )
                if structural is not None:
                    baseline_need = ObservationNeed(
                        f"baseline:{need.need_id}",
                        ObservationPurpose.WORLD_GROUNDING,
                        need.subject_ids,
                        ObservationModality.STRUCTURAL,
                        ObservationAssurance.STRUCTURAL,
                        need.freshness,
                    )
                    needs = (*needs, baseline_need)
                    failure = self._add(
                        selected,
                        structural,
                        SourceSelection(
                            structural.source,
                            SourceRequirement.REQUIRED,
                            "structured_baseline",
                            (baseline_need.need_id,),
                        ),
                    )
                    if failure is not None:
                        return failure
            if not adequate:
                reason = (
                    "requested_assurance_unavailable"
                    if any(
                        (need.required_modality is None or item.modality is need.required_modality)
                        and need.purpose in item.supported_purposes
                        for item in ordered
                    )
                    else "requested_modality_unavailable"
                )
                return ObservationSelectionResult(
                    None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, reason
                )
            chosen = next((item for item in adequate if item.source not in selected), adequate[0])
            if chosen.source in selected:
                existing = selected[chosen.source]
                selected[chosen.source] = replace(
                    existing,
                    requirement=(
                        SourceRequirement.REQUIRED
                        if requirement is SourceRequirement.REQUIRED
                        else existing.requirement
                    ),
                    need_ids=tuple(sorted(set(existing.need_ids) | {need.need_id})),
                )
                continue
            failure = self._add(
                selected,
                chosen,
                SourceSelection(
                    chosen.source,
                    requirement,
                    _selection_reason(need, chosen),
                    (need.need_id,),
                ),
            )
            if failure is not None:
                return failure
        selections = tuple(selected[item.source] for item in ordered if item.source in selected)
        if not selections:
            return ObservationSelectionResult(
                None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, "no_sufficient_source"
            )
        unselected = tuple(
            SourceSelection(
                item.source,
                SourceRequirement.UNSELECTED,
                "source_not_needed",
            )
            for item in ordered
            if item.source not in selected
        )
        reasons = tuple(dict.fromkeys(item.reason_code for item in selections))
        return ObservationSelectionResult(
            ObservationSelectionPlan(
                selections,
                unselected,
                self.acquisition_budget,
                tuple(sorted(needs, key=lambda item: item.need_id)),
                reasons,
            ),
            AcquisitionStatus.ACQUIRED,
            "sources_selected",
        )

    def select_after_baseline(
        self,
        offers: tuple[ObservationOffer, ...],
        request: WorldObservationRequest,
        structured: SurfaceObservation,
        *,
        terminal: bool,
        route_source: str = "",
    ) -> ObservationSelectionResult:
        """Complete stage two using typed residual need, without adapter selection."""

        residual = tuple(
            need
            for need in _residual_needs(request, structured, terminal=terminal)
            if any(_offer_satisfies(offer, need) for offer in offers)
        )
        needs = tuple(dict.fromkeys((request.needs or (_lifecycle_need(request),)) + residual))
        return self._select(
            offers,
            replace(request, needs=needs),
            route_source=route_source,
            optional_need_ids=frozenset(item.need_id for item in residual),
        )

    def _add(
        self,
        selected: dict[str, SourceSelection],
        offer: ObservationOffer,
        selection: SourceSelection,
    ) -> ObservationSelectionResult | None:
        if offer.source in selected:
            return None
        if len(selected) >= self.acquisition_budget:
            return ObservationSelectionResult(
                None, AcquisitionStatus.CAPABILITY_UNAVAILABLE, "source_budget_exhausted"
            )
        selected[offer.source] = selection
        return None


def _lifecycle_need(request: WorldObservationRequest) -> ObservationNeed:
    purpose = (
        ObservationPurpose.WORLD_GROUNDING
        if request.kind is ObservationRequestKind.POLICY_REQUEST
        else ObservationPurpose.CURRENTNESS_REFRESH
    )
    return ObservationNeed(
        f"lifecycle:{request.kind.value}",
        purpose,
        required_assurance=ObservationAssurance.WEAK,
        freshness=FreshnessRequirement.FRESH_ACQUISITION,
    )


def _residual_needs(
    request: WorldObservationRequest,
    structured: SurfaceObservation,
    *,
    terminal: bool,
) -> tuple[ObservationNeed, ...]:
    evidence_needs = derive_visual_evidence_needs(structured, terminal=terminal)
    residual: list[ObservationNeed] = []
    for evidence_need in evidence_needs:
        purpose = {
            VisionEvidenceNeed.SINGLE_TARGET_DISAMBIGUATION: ObservationPurpose.TARGET_DISAMBIGUATION,
            VisionEvidenceNeed.OPEN_WORLD_ENTITY_DISCOVERY: ObservationPurpose.ENTITY_DISCOVERY,
            VisionEvidenceNeed.POSTCONDITION_DIAGNOSIS: ObservationPurpose.EFFECT_VERIFICATION,
            VisionEvidenceNeed.RAW_SCREENSHOT: ObservationPurpose.WORLD_GROUNDING,
        }.get(evidence_need)
        if purpose is None or any(item.purpose is purpose for item in request.needs):
            continue
        residual.append(ObservationNeed(
            f"residual:{purpose.value}",
            purpose,
            required_modality=ObservationModality.VISUAL,
            required_assurance=ObservationAssurance.WEAK,
            freshness=FreshnessRequirement.FRESH_ACQUISITION,
        ))
    return tuple(residual)


def _offer_satisfies(offer: ObservationOffer, need: ObservationNeed) -> bool:
    return (
        (need.required_modality is None or offer.modality is need.required_modality)
        and need.purpose in offer.supported_purposes
        and assurance_satisfies(offer.assurance, need.required_assurance)
    )


def _needs_by_id(needs: tuple[ObservationNeed, ...]) -> tuple[ObservationNeed, ...]:
    unique: dict[str, ObservationNeed] = {}
    for need in needs:
        unique.setdefault(need.need_id, need)
    return tuple(unique.values())


def _selected_satisfies(
    selected: dict[str, SourceSelection],
    offers: tuple[ObservationOffer, ...],
    need: ObservationNeed,
    requirement: SourceRequirement,
) -> bool:
    for source, selection in tuple(selected.items()):
        if not _offer_satisfies(_offer(source, offers), need):
            continue
        selected[source] = replace(
            selection,
            requirement=(
                SourceRequirement.REQUIRED
                if requirement is SourceRequirement.REQUIRED
                else selection.requirement
            ),
            need_ids=tuple(sorted(set(selection.need_ids) | {need.need_id})),
        )
        return True
    return False


def _offer(source: str, offers: tuple[ObservationOffer, ...]) -> ObservationOffer:
    return next(item for item in offers if item.source == source)


def _selection_reason(need: ObservationNeed, offer: ObservationOffer) -> str:
    if offer.modality is ObservationModality.VISUAL:
        return {
            ObservationPurpose.ENTITY_DISCOVERY: "visual_entity_discovery",
            ObservationPurpose.TARGET_DISAMBIGUATION: "visual_target_disambiguation",
            ObservationPurpose.EFFECT_VERIFICATION: "visual_effect_verification",
            ObservationPurpose.CRITERION_VERIFICATION: "visual_criterion_verification",
            ObservationPurpose.VISUAL_PROPERTY: "visual_property_grounding",
            ObservationPurpose.SPATIAL_RELATIONSHIP: "visual_spatial_grounding",
            ObservationPurpose.TEXT_IN_IMAGE: "visual_text_grounding",
        }.get(need.purpose, "visual_grounding")
    if offer.modality is ObservationModality.ENVIRONMENT_STATE:
        return "authoritative_state_grounding"
    if need.purpose is ObservationPurpose.CURRENTNESS_REFRESH:
        return "currentness_refresh"
    return "primary_grounding"


def _offer_rank(offer: ObservationOffer) -> tuple[int, int, str]:
    return (
        _COST[AcquisitionCost(offer.acquisition_cost)],
        _MODALITY[ObservationModality(offer.modality)],
        offer.source,
    )
