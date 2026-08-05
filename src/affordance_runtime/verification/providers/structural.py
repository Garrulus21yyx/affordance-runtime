"""DOM/AX/Visual/SVG structural evidence admission."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.criteria import PredicateExpr
from affordance_runtime.verification.contracts import (
    EvidenceSourceKind,
    PredicateEvidence,
    PredicateEvidenceContext,
)

STRUCTURAL_SOURCES = frozenset(
    {
        EvidenceSourceKind.DOM_STATE,
        EvidenceSourceKind.ACCESSIBILITY_STATE,
        EvidenceSourceKind.VISUAL_STATE,
        EvidenceSourceKind.SVG_GEOMETRY,
    }
)


@dataclass(frozen=True)
class StructuralEvidenceProvider:
    def evidence_for(
        self, predicate: PredicateExpr, context: PredicateEvidenceContext
    ) -> tuple[PredicateEvidence, ...]:
        return tuple(
            item
            for item in context.evidence
            if item.subject_ref == predicate.subject.reference
            and item.source_kind in STRUCTURAL_SOURCES
        )
