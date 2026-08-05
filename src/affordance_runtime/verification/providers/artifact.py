"""Artifact/file/materialization evidence admission."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.criteria import PredicateExpr
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    EvidenceSourceKind,
    PredicateEvidence,
    PredicateEvidenceContext,
)

ARTIFACT_SOURCES = frozenset(
    {
        EvidenceSourceKind.ARTIFACT_INTEGRITY,
        EvidenceSourceKind.FILE_RECEIPT,
        EvidenceSourceKind.DOWNLOAD_RECEIPT,
    }
)


@dataclass(frozen=True)
class ArtifactEvidenceProvider:
    def evidence_for(
        self, predicate: PredicateExpr, context: PredicateEvidenceContext
    ) -> tuple[PredicateEvidence, ...]:
        supplied = tuple(
            item
            for item in context.evidence
            if item.subject_ref == predicate.subject.reference
            and item.source_kind in ARTIFACT_SOURCES
        )
        observation = context.current_observation
        artifact_refs = tuple(getattr(observation, "artifact_refs", ()))
        if predicate.subject.reference not in artifact_refs:
            return supplied
        return (
            *supplied,
            PredicateEvidence(
                evidence_ref=predicate.subject.reference,
                subject_ref=predicate.subject.reference,
                observed_value=True,
                source_kind=EvidenceSourceKind.ARTIFACT_INTEGRITY,
                assurance=AssuranceLevel.AUTHORITATIVE,
                observation_ref=context.current_observation_ref,
            ),
        )
