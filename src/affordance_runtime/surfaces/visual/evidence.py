"""Closed internal visual evidence algebra with Runtime-owned capture provenance."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias

from affordance_runtime.world.observation_needs import ObservationPurpose
from affordance_runtime.world.observation_outcomes import (
    ObservationUnknownItem,
    VisualQueryFailureReason,
)


@dataclass(frozen=True)
class VisualEvidenceProvenance:
    query_id: str
    provider: str
    model: str
    prompt_version: str
    screenshot_digest: str
    image_size: tuple[int, int]
    page_generation: str
    episode_identity: str
    viewport: tuple[float, float, float, float, float, float]
    acquisition_latency_ms: float

    def __post_init__(self) -> None:
        if (
            not all(
                item.strip()
                for item in (
                    self.query_id,
                    self.provider,
                    self.model,
                    self.prompt_version,
                    self.screenshot_digest,
                    self.page_generation,
                    self.episode_identity,
                )
            )
            or len(self.image_size) != 2
            or any(type(item) is not int or item <= 0 for item in self.image_size)
            or len(self.viewport) != 6
            or any(not math.isfinite(item) for item in self.viewport)
            or not math.isfinite(self.acquisition_latency_ms)
            or self.acquisition_latency_ms < 0
        ):
            raise ValueError("visual evidence provenance is invalid")


@dataclass(frozen=True)
class _EvidenceBase:
    evidence_id: str
    confidence: float
    provenance: VisualEvidenceProvenance = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not self.evidence_id.strip()
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
            or not isinstance(self.provenance, VisualEvidenceProvenance)
        ):
            raise ValueError("visual evidence identity or confidence is invalid")


@dataclass(frozen=True)
class RegionEvidence(_EvidenceBase):
    region_local_ref: str
    bbox: tuple[float, float, float, float]
    label: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        x, y, width, height = self.bbox
        if (
            not self.region_local_ref.strip()
            or len(self.bbox) != 4
            or any(not math.isfinite(item) for item in self.bbox)
            or x < 0
            or y < 0
            or width <= 0
            or height <= 0
        ):
            raise ValueError("region evidence is invalid")


@dataclass(frozen=True)
class PredicateEvidence(_EvidenceBase):
    subject_id: str
    predicate: str
    truth: bool

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.subject_id.strip() or not self.predicate.strip() or type(self.truth) is not bool:
            raise ValueError("predicate evidence is invalid")


@dataclass(frozen=True)
class DisambiguationEvidence(_EvidenceBase):
    candidate_ids: tuple[str, ...]
    chosen_candidate_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        if (
            not 2 <= len(self.candidate_ids) <= 32
            or len(set(self.candidate_ids)) != len(self.candidate_ids)
            or self.chosen_candidate_id not in self.candidate_ids
        ):
            raise ValueError("disambiguation evidence is invalid")


@dataclass(frozen=True)
class TextEvidence(_EvidenceBase):
    subject_id: str
    text: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.subject_id.strip() or len(self.text) > 4_000:
            raise ValueError("text evidence is invalid")


@dataclass(frozen=True)
class SpatialEvidence(_EvidenceBase):
    subject_ids: tuple[str, ...]
    predicate: str
    truth: bool

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "subject_ids", tuple(self.subject_ids))
        if (
            not 2 <= len(self.subject_ids) <= 32
            or len(set(self.subject_ids)) != len(self.subject_ids)
            or not self.predicate.strip()
            or type(self.truth) is not bool
        ):
            raise ValueError("spatial evidence is invalid")


@dataclass(frozen=True)
class PointEvidence(_EvidenceBase):
    target_local_ref: str
    point: tuple[float, float]

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            not self.target_local_ref.strip()
            or len(self.point) != 2
            or any(not math.isfinite(item) or item < 0 for item in self.point)
        ):
            raise ValueError("point evidence is invalid")


@dataclass(frozen=True)
class ChangeEvidence(_EvidenceBase):
    subject_ids: tuple[str, ...]
    predicate: str
    truth: bool

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "subject_ids", tuple(self.subject_ids))
        if (
            not 1 <= len(self.subject_ids) <= 32
            or len(set(self.subject_ids)) != len(self.subject_ids)
            or not self.predicate.strip()
            or type(self.truth) is not bool
        ):
            raise ValueError("change evidence is invalid")


VisualEvidence: TypeAlias = (
    RegionEvidence
    | PredicateEvidence
    | DisambiguationEvidence
    | TextEvidence
    | SpatialEvidence
    | PointEvidence
    | ChangeEvidence
)


class VisualQueryCoverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VisualQueryCompleted:
    query_id: str
    purpose: ObservationPurpose
    evidence: tuple[VisualEvidence, ...] = ()
    unknown_items: tuple[ObservationUnknownItem, ...] = ()
    coverage: VisualQueryCoverage = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "unknown_items", tuple(self.unknown_items))
        if not self.query_id.strip() or (not self.evidence and not self.unknown_items):
            raise ValueError("completed visual query requires evidence or a typed unknown")
        coverage = (
            VisualQueryCoverage.PARTIAL
            if self.evidence and self.unknown_items
            else VisualQueryCoverage.COMPLETE
            if self.evidence
            else VisualQueryCoverage.UNKNOWN
        )
        object.__setattr__(self, "coverage", coverage)


@dataclass(frozen=True)
class VisualQueryFailed:
    query_id: str
    purpose: ObservationPurpose
    stage: str
    reason: VisualQueryFailureReason

    def __post_init__(self) -> None:
        if not self.query_id.strip() or not self.stage.strip() or not isinstance(
            self.reason, VisualQueryFailureReason
        ):
            raise ValueError("failed visual query is invalid")


VisualQueryResult: TypeAlias = VisualQueryCompleted | VisualQueryFailed
