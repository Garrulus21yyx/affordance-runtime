"""DOM/AX/Visual/SVG structural evidence admission."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.criteria import PredicateExpr
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
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
        supplied = tuple(
            item
            for item in context.evidence
            if item.subject_ref == predicate.subject.reference
            and item.source_kind in STRUCTURAL_SOURCES
        )
        observation = context.current_observation
        targets = getattr(observation, "targets", ())
        target = next(
            (
                item
                for item in targets
                if getattr(item, "target_id", "") == predicate.subject.reference
            ),
            None,
        )
        if target is None:
            return supplied
        state = getattr(target, "state", {})
        field = predicate.subject.field or predicate.operator.value
        if field not in state:
            return supplied
        conflicts = tuple(getattr(target, "conflicts", ()))
        conflict = any(
            getattr(item, "property_name", "") == field and getattr(item, "material", False)
            for item in conflicts
        ) or field in tuple(getattr(target, "conflict_codes", ()))
        derived = PredicateEvidence(
            evidence_ref=f"observation:{context.current_observation_ref}:{target.target_id}:{field}",
            subject_ref=target.target_id,
            observed_value=state[field],
            source_kind=_source_kind(target),
            assurance=AssuranceLevel.STRUCTURAL,
            observation_ref=context.current_observation_ref,
            conflict=conflict,
        )
        return (*supplied, derived)


def _source_kind(target: object) -> EvidenceSourceKind:
    surfaces = tuple(getattr(target, "surfaces", ()))
    surface = str(surfaces[0].value if surfaces else getattr(target, "surface", "dom"))
    return {
        "ax": EvidenceSourceKind.ACCESSIBILITY_STATE,
        "visual": EvidenceSourceKind.VISUAL_STATE,
        "svg": EvidenceSourceKind.SVG_GEOMETRY,
    }.get(surface, EvidenceSourceKind.DOM_STATE)
