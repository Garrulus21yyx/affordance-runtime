"""Bounded evidence-reference index for one current WorldObservation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from affordance_runtime.world.contracts import WorldObservation

_MAX_REFS = 4096
_MAX_REF_LENGTH = 512
_FACT_REF = re.compile(r"^fact:[A-Za-z0-9][A-Za-z0-9._:-]{0,506}$")
_ARTIFACT_REF = re.compile(r"^artifact:[A-Za-z0-9][A-Za-z0-9._:-]{1,502}$")


@dataclass(frozen=True)
class WorldEvidenceIndex:
    observation_id: str
    refs: tuple[str, ...]

    @classmethod
    def from_observation(cls, observation: WorldObservation) -> WorldEvidenceIndex:
        refs = [fact.fact_id for fact in observation.facts]
        refs.extend(
            f"artifact:{source.observation_id}:{key}"
            for source in observation.sources
            for key in source.artifacts
        )
        validated = validate_evidence_refs(tuple(refs), allow_empty=True)
        if len(validated) > _MAX_REFS:
            raise ValueError("world evidence index exceeds bounded reference count")
        return cls(observation.observation_id, tuple(sorted(validated)))

    def resolve(self, evidence_ref: str) -> bool:
        return evidence_ref in self.refs


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
