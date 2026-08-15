"""One-way model-safe projection of environment-owned acquisition offers."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.world.acquisition import ObservationCapabilities


@dataclass(frozen=True)
class ObservationCapabilityView:
    modality: str
    assurance: str


def project_acquisition_offers(
    capabilities: ObservationCapabilities,
) -> tuple[ObservationCapabilityView, ...]:
    if not capabilities.independent_capture:
        return ()
    pairs = {(offer.modality, offer.assurance) for offer in capabilities.offers}
    return tuple(ObservationCapabilityView(*pair) for pair in sorted(pairs))
