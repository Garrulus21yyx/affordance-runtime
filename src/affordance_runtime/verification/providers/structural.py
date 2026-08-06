"""DOM/AX/Visual/SVG structural evidence admission."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.criteria import PredicateExpr, PredicateOperator
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
            return (*supplied, *_metadata_evidence(predicate, context))
        state = getattr(target, "state", {})
        field = predicate.subject.field or predicate.operator.value
        if predicate.operator in {PredicateOperator.EXISTS, PredicateOperator.ABSENT} and not predicate.subject.field:
            observed_value = True
        elif field in state:
            observed_value = state[field]
        else:
            return supplied
        conflicts = tuple(getattr(target, "conflicts", ()))
        conflict = any(
            getattr(item, "property_name", "") == field and getattr(item, "material", False)
            for item in conflicts
        ) or field in tuple(getattr(target, "conflict_codes", ()))
        source_kind = _source_kind(target)
        if source_kind is None:
            return supplied
        derived = PredicateEvidence(
            evidence_ref=f"observation:{context.current_observation_ref}:{target.target_id}:{field}",
            subject_ref=target.target_id,
            observed_value=observed_value,
            source_kind=source_kind,
            assurance=AssuranceLevel.STRUCTURAL,
            observation_ref=context.current_observation_ref,
            conflict=conflict,
        )
        return (*supplied, derived)


def _source_kind(target: object) -> EvidenceSourceKind | None:
    surfaces = tuple(getattr(target, "surfaces", ()))
    surface = str(surfaces[0].value if surfaces else getattr(target, "surface", ""))
    return {
        "dom": EvidenceSourceKind.DOM_STATE,
        "accessibility": EvidenceSourceKind.ACCESSIBILITY_STATE,
        "ax": EvidenceSourceKind.ACCESSIBILITY_STATE,
        "visual": EvidenceSourceKind.VISUAL_STATE,
        "svg": EvidenceSourceKind.SVG_GEOMETRY,
    }.get(surface)


def _metadata_evidence(
    predicate: PredicateExpr, context: PredicateEvidenceContext
) -> tuple[PredicateEvidence, ...]:
    metadata = getattr(context.current_observation, "metadata", {})
    declared = metadata.get("predicate_evidence") if isinstance(metadata, Mapping) else None
    raw = declared.get(predicate.subject.reference) if isinstance(declared, Mapping) else None
    if not isinstance(raw, Mapping):
        return ()
    try:
        source = EvidenceSourceKind(str(raw["source_kind"]))
        assurance = AssuranceLevel(str(raw["assurance"]))
    except (KeyError, ValueError):
        return ()
    if source not in STRUCTURAL_SOURCES:
        return ()
    evidence_ref = str(raw.get("evidence_ref") or "")
    if not evidence_ref:
        return ()
    return (
        PredicateEvidence(
            evidence_ref=evidence_ref,
            subject_ref=predicate.subject.reference,
            observed_value=raw.get("observed_value"),
            source_kind=source,
            assurance=assurance,
            observation_ref=context.current_observation_ref,
        ),
    )
