"""Disposable Top-5 projection over existing current public scalar evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.actions.paging import delivery_descriptor_matches, rank_delivery_descriptors
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.working_facts import is_public_scalar
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import CoverageState, WorldObservation


@dataclass(frozen=True)
class EvidenceCandidate:
    fact_ref: str
    value: object
    predicate: str
    source_context: str
    region_ref: str
    coverage: str
    lineage: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fact_ref.startswith("F") or not self.predicate:
            raise ValueError("evidence candidate requires a current public scalar identity")
        if self.region_ref and not self.region_ref.startswith("R"):
            raise ValueError("evidence candidate region ref is invalid")
        object.__setattr__(self, "value", freeze_json(self.value))
        object.__setattr__(self, "lineage", freeze_json(dict(self.lineage)))


@dataclass(frozen=True)
class EvidenceCandidateProjection:
    world_observation_id: str
    candidates: tuple[EvidenceCandidate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        if not self.world_observation_id or len(self.candidates) > 5:
            raise ValueError("evidence candidates require one current World and Top-5 bound")
        if len({item.fact_ref for item in self.candidates}) != len(self.candidates):
            raise ValueError("evidence candidate refs must be unique")


def project_evidence_candidates(
    observation: WorldObservation,
    evidence_index: WorldEvidenceIndex,
    canonical_to_public: Mapping[str, str],
    region_index: WorldDeliveryIndex,
    *,
    required_evidence: tuple[tuple[str, str], ...] = (),
) -> EvidenceCandidateProjection:
    sources = {item.observation_id: item for item in observation.sources}
    eligible = []
    descriptors = []
    for record in evidence_index.records:
        public_ref = canonical_to_public.get(record.evidence_ref, "")
        source = sources.get(record.source_observation_id)
        if (
            not public_ref
            or record.kind != "fact"
            or record.observation_id != observation.observation_id
            or not is_public_scalar(record.value)
            or source is None
            or source.coverage is CoverageState.STALE
        ):
            continue
        region = region_index.region_for_target(record.subject_id)
        region_ref = region.public_ref if region is not None else ""
        source_context = " ".join(
            item for item in (record.source_id, region.heading if region is not None else "") if item
        )[:240]
        candidate = EvidenceCandidate(
            public_ref,
            record.value,
            record.predicate,
            source_context,
            region_ref,
            source.coverage.value,
            {
                "scope": "current_observation",
                "status": "current",
                "source_modality": record.source_modality,
                "source_assurance": record.source_assurance,
            },
        )
        eligible.append(candidate)
        descriptors.append((public_ref, f"{record.predicate} {record.value}", (source_context, region_ref)))
    intent = " ".join(f"{key} {description}" for key, description in required_evidence)
    order = rank_delivery_descriptors(tuple(descriptors), intent=intent)
    by_ref = {item.fact_ref: item for item in eligible}
    return EvidenceCandidateProjection(
        observation.observation_id,
        tuple(by_ref[ref] for ref in order[:5]),
    )


def evidence_requirement_available(
    key: str,
    description: str,
    candidates: EvidenceCandidateProjection,
) -> bool:
    intent = f"{key} {description}"
    return any(
        delivery_descriptor_matches(
            intent,
            f"{item.predicate} {item.value}",
            (item.source_context, item.region_ref),
        )
        for item in candidates.candidates
    )


def evidence_requirement_available_in_index(
    key: str,
    description: str,
    observation: WorldObservation,
    evidence_index: WorldEvidenceIndex,
    canonical_to_public: Mapping[str, str],
    region_index: WorldDeliveryIndex,
) -> bool:
    sources = {item.observation_id: item for item in observation.sources}
    intent = f"{key} {description}"
    for record in evidence_index.records:
        source = sources.get(record.source_observation_id)
        if (
            record.evidence_ref not in canonical_to_public
            or record.kind != "fact"
            or not is_public_scalar(record.value)
            or source is None
            or source.coverage is CoverageState.STALE
        ):
            continue
        region = region_index.region_for_target(record.subject_id)
        context = (
            record.source_id,
            region.heading if region is not None else "",
            region.public_ref if region is not None else "",
        )
        if delivery_descriptor_matches(intent, f"{record.predicate} {record.value}", context):
            return True
    return False
