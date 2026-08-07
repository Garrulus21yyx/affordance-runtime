"""API/WoT/Device/resource-state evidence admission."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.criteria import PredicateExpr
from affordance_runtime.verification.contracts import (
    EvidenceSourceKind,
    PredicateEvidence,
    PredicateEvidenceContext,
)

RESOURCE_SOURCES = frozenset(
    {
        EvidenceSourceKind.API_STATE,
        EvidenceSourceKind.WOT_PROPERTY_STATE,
        EvidenceSourceKind.DEVICE_STATE,
        EvidenceSourceKind.NETWORK_TRANSACTION,
        EvidenceSourceKind.WOT_ACTION_RESULT,
    }
)


@dataclass(frozen=True)
class ResourceEvidenceProvider:
    def evidence_for(
        self, predicate: PredicateExpr, context: PredicateEvidenceContext
    ) -> tuple[PredicateEvidence, ...]:
        return tuple(
            item
            for item in context.evidence
            if item.subject_ref == predicate.subject.reference
            and item.source_kind in RESOURCE_SOURCES
        )
