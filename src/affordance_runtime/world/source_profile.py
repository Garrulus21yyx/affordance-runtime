"""Runtime-owned observation quality profile without action authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ObservationModality(StrEnum):
    STRUCTURAL = "structural"
    VISUAL = "visual"
    ENVIRONMENT_STATE = "environment_state"


class ObservationAssurance(StrEnum):
    WEAK = "weak"
    STRUCTURAL = "structural"
    AUTHORITATIVE = "authoritative"


class VerificationStrength(StrEnum):
    VISUAL = "visual"
    STRUCTURAL = "structural"
    AUTHORITATIVE = "authoritative"


class AcquisitionCost(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ObservationSourceProfile:
    modality: ObservationModality
    assurance: ObservationAssurance
    verification_strength: VerificationStrength
    acquisition_cost: AcquisitionCost
    debug_source: str

    def __post_init__(self) -> None:
        if not self.debug_source.strip():
            raise ValueError("observation source profile requires an internal debug source")

    @classmethod
    def dom(cls) -> ObservationSourceProfile:
        return cls(
            ObservationModality.STRUCTURAL,
            ObservationAssurance.STRUCTURAL,
            VerificationStrength.STRUCTURAL,
            AcquisitionCost.LOW,
            "dom",
        )

    @classmethod
    def visual(cls) -> ObservationSourceProfile:
        return cls(
            ObservationModality.VISUAL,
            ObservationAssurance.WEAK,
            VerificationStrength.VISUAL,
            AcquisitionCost.HIGH,
            "visual",
        )

    @classmethod
    def wot(cls) -> ObservationSourceProfile:
        return cls(
            ObservationModality.ENVIRONMENT_STATE,
            ObservationAssurance.AUTHORITATIVE,
            VerificationStrength.AUTHORITATIVE,
            AcquisitionCost.MEDIUM,
            "wot",
        )


def assurance_satisfies(
    offered: ObservationAssurance | str,
    required: ObservationAssurance | str,
) -> bool:
    rank = {
        ObservationAssurance.WEAK: 0,
        ObservationAssurance.STRUCTURAL: 1,
        ObservationAssurance.AUTHORITATIVE: 2,
    }
    try:
        return rank[ObservationAssurance(offered)] >= rank[ObservationAssurance(required)]
    except ValueError:
        return False
