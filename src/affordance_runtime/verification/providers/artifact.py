"""Artifact/file/materialization evidence admission."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.criteria import PredicateExpr
from affordance_runtime.verification.contracts import (
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
        # A materialized artifact reference establishes existence only.  It is
        # not an integrity proof: authoritative admission requires a supplied
        # hash/receipt/integrity record with its own evidence identity.
        return supplied
