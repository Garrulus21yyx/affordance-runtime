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
    VISUAL_PROPERTY = "visual_property"
    SPATIAL_RELATIONSHIP = "spatial_relationship"
    TEXT_IN_IMAGE = "text_in_image"
    POINT_GROUNDING = "point_grounding"
    VISUAL_CHANGE = "visual_change"


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
    evidence_property: str = ""
    candidate_ids: tuple[str, ...] = ()
    query_text: str = ""
    max_results: int = 1

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
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        if any(not item.strip() or len(item) > 240 for item in self.candidate_ids):
            raise ValueError("observation need candidates must be bounded identities")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("observation need candidates cannot repeat")
        if self.required_modality is not None and not isinstance(
            self.required_modality, ObservationModality
        ):
            raise TypeError("required observation modality must be typed")
        if not isinstance(self.required_assurance, ObservationAssurance):
            raise TypeError("required observation assurance must be typed")
        if not isinstance(self.freshness, FreshnessRequirement):
            raise TypeError("observation freshness requirement must be typed")
        if len(self.evidence_property) > 120:
            raise ValueError("observation evidence property exceeds its bound")
        if len(self.query_text) > 500:
            raise ValueError("observation query text exceeds its bound")
        if not 1 <= self.max_results <= 32:
            raise ValueError("observation max results must be in [1, 32]")
        if (
            self.purpose is ObservationPurpose.VISUAL_PROPERTY
        ) != bool(self.evidence_property):
            raise ValueError("visual property needs require exactly one evidence property")
