"""Closed epistemic observation needs, separate from acquisition lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.world.source_profile import ObservationAssurance, ObservationModality


class ObservationPurpose(StrEnum):
    WORLD_GROUNDING = "world_grounding"
    ENTITY_DISCOVERY = "entity_discovery"
    TARGET_DISAMBIGUATION = "target_disambiguation"
    EFFECT_VERIFICATION = "effect_verification"
    CRITERION_VERIFICATION = "criterion_verification"
    CURRENTNESS_REFRESH = "currentness_refresh"


class FreshnessRequirement(StrEnum):
    CURRENT = "current"
    FRESH_ACQUISITION = "fresh_acquisition"


@dataclass(frozen=True, order=True)
class ObservationNeed:
    need_id: str
    purpose: ObservationPurpose
    subject_ids: tuple[str, ...] = ()
    required_modality: ObservationModality | None = None
    required_assurance: ObservationAssurance = ObservationAssurance.WEAK
    freshness: FreshnessRequirement = FreshnessRequirement.FRESH_ACQUISITION

    def __post_init__(self) -> None:
        if not self.need_id.strip() or len(self.need_id) > 240:
            raise ValueError("observation need requires a bounded identity")
        if not isinstance(self.purpose, ObservationPurpose):
            raise TypeError("observation need purpose must be typed")
        object.__setattr__(self, "subject_ids", tuple(self.subject_ids))
        if any(not item.strip() or len(item) > 240 for item in self.subject_ids):
            raise ValueError("observation need subjects must be bounded identities")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError("observation need subjects cannot repeat")
        if self.required_modality is not None and not isinstance(
            self.required_modality, ObservationModality
        ):
            raise TypeError("required observation modality must be typed")
        if not isinstance(self.required_assurance, ObservationAssurance):
            raise TypeError("required observation assurance must be typed")
        if not isinstance(self.freshness, FreshnessRequirement):
            raise TypeError("observation freshness requirement must be typed")
