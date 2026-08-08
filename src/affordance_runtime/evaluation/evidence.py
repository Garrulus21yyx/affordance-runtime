"""Bounded evidence-reference index for one current WorldObservation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.evaluation.evidence_records import EvidenceRecord
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref, canonical_fact_ref

_MAX_REFS = 4096
_MAX_REF_LENGTH = 512
_FACT_REF = re.compile(r"^fact:[A-Za-z0-9][A-Za-z0-9._:-]{0,506}$")
_ARTIFACT_REF = re.compile(r"^artifact:[A-Za-z0-9][A-Za-z0-9._:-]{1,502}$")


@dataclass(frozen=True)
class WorldEvidenceIndex:
    observation_id: str
    refs: tuple[str, ...]
    records: tuple[EvidenceRecord, ...] = ()

    @classmethod
    def from_observation(cls, observation: WorldObservation) -> WorldEvidenceIndex:
        records = [_fact_record(observation, fact) for fact in observation.facts]
        records.extend(_artifact_record(observation, source, str(key)) for source in observation.sources for key in source.artifacts)
        refs = [record.evidence_ref for record in records]
        validated = validate_evidence_refs(tuple(refs), allow_empty=True)
        if len(validated) > _MAX_REFS:
            raise ValueError("world evidence index exceeds bounded reference count")
        ordered = tuple(sorted(records, key=lambda item: item.evidence_ref))
        return cls(observation.observation_id, tuple(sorted(validated)), ordered)

    def resolve(self, evidence_ref: str) -> bool:
        return evidence_ref in self.refs

    def resolve_record(self, evidence_ref: str) -> EvidenceRecord | None:
        return next((item for item in self.records if item.evidence_ref == evidence_ref), None)


def _fact_record(observation, fact) -> EvidenceRecord:
    source = next(
        (item for item in observation.sources if fact.source_id in {item.observation_id, item.surface}),
        None,
    )
    return EvidenceRecord(
        canonical_fact_ref(fact.fact_id), observation.observation_id, "fact", fact.source_id,
        source.observation_id if source else "", str(source.source_profile.modality) if source else "",
        str(source.source_profile.assurance) if source else "", fact.subject_id, fact.predicate, fact.value,
    )


def _artifact_record(observation, source, key: str) -> EvidenceRecord:
    artifact = source.artifacts.get(key)
    summary = artifact.get("public_summary", "") if isinstance(artifact, Mapping) else ""
    return EvidenceRecord(
        canonical_artifact_ref(source.observation_id, key), observation.observation_id, "artifact",
        source.surface, source.observation_id, str(source.source_profile.modality),
        str(source.source_profile.assurance), artifact_kind=key, output_id=key,
        public_summary=str(summary)[:500],
    )


def validate_evidence_refs(refs: tuple[str, ...], *, allow_empty: bool) -> tuple[str, ...]:
    values = tuple(refs)
    if not allow_empty and not values:
        raise ValueError("confirmed evaluation requires evidence references")
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError("evidence references cannot be blank")
    if len(set(values)) != len(values):
        raise ValueError("evidence references must be unique")
    if any(len(item) > _MAX_REF_LENGTH for item in values):
        raise ValueError("evidence reference exceeds bounded length")
    if any(not _valid_evidence_ref(item) for item in values):
        raise ValueError("evidence reference must use the canonical fact or artifact namespace")
    return values


def evidence_ref_contains_secret(value: str) -> bool:
    """Compatibility predicate: non-canonical values are unsafe as references."""

    return not _valid_evidence_ref(value)


def _valid_evidence_ref(value: str) -> bool:
    if _FACT_REF.fullmatch(value):
        return True
    if not _ARTIFACT_REF.fullmatch(value):
        return False
    _, source_id, safe_key = value.rsplit(":", 2)
    return bool(source_id and safe_key)
