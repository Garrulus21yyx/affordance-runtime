"""One-way model-safe projection of environment-owned acquisition offers."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.world.acquisition import ObservationCapabilities
from affordance_runtime.world.source_profile import ObservationAssurance, ObservationModality


@dataclass(frozen=True)
class ObservationCapabilityView:
    modality: str
    assurance: str
    purposes: tuple[str, ...] = ()


def project_acquisition_offers(
    capabilities: ObservationCapabilities,
) -> tuple[ObservationCapabilityView, ...]:
    if not capabilities.independent_capture:
        return ()
    offers = {
        (ObservationModality(offer.modality).value, ObservationAssurance(offer.assurance).value): tuple(
            purpose.value for purpose in offer.supported_purposes
        )
        for offer in capabilities.offers
    }
    return tuple(
        ObservationCapabilityView(modality, assurance, offers[(modality, assurance)])
        for modality, assurance in sorted(offers)
    )
