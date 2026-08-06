"""Dated one-way ingress adapter for pre-P2 StepSpec criteria.

Canonical runtime owners must not import this module.  It exists only so
external/serialized P1 plans can be admitted during the P2 cutover and is due
for deletion with the remaining legacy planning wire format at P3-4.
"""

from __future__ import annotations

from typing import Literal

from affordance_runtime.criteria import (
    AllOf,
    AnyOf,
    LiteralValue,
    PredicateExpr,
    PredicateOperator,
    SubjectExpr,
)
from affordance_runtime.simplified_runtime_contracts import (
    CompositeCriterion,
    CompositeCriterionOperator,
    EvidenceStrength,
    LegacyCriterion,
    StateCriterion,
    StateCriterionRelation,
)
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    EvidenceSourceKind,
    SatisfactionMode,
)


def canonicalize_legacy_criteria(
    criteria: tuple[object, ...], *, role: Literal["completion", "precondition"]
) -> tuple[PredicateExpr | AllOf | AnyOf, ...]:
    legacy = tuple(item for item in criteria if isinstance(item, (StateCriterion, CompositeCriterion)))
    if len(legacy) != len(criteria):
        raise TypeError("legacy and canonical criteria cannot be mixed")
    if any(item.role != role for item in legacy):
        raise ValueError(
            "precondition cannot be used as completion criterion"
            if role == "completion"
            else "step preconditions must use precondition role"
        )
    by_id = {item.criterion_id: item for item in legacy}
    referenced = {
        child
        for item in legacy
        if isinstance(item, CompositeCriterion)
        for child in item.child_criterion_ids
    }

    def convert(item: LegacyCriterion) -> PredicateExpr | AllOf | AnyOf:
        if isinstance(item, StateCriterion):
            return _predicate(item)
        children = tuple(convert(by_id[child]) for child in item.child_criterion_ids)
        if item.operator == CompositeCriterionOperator.ALL_OF:
            return AllOf(item.criterion_id, children)
        return AnyOf(item.criterion_id, children)

    return tuple(convert(item) for item in legacy if item.criterion_id not in referenced)


def _predicate(item: StateCriterion) -> PredicateExpr:
    operator, field = _RELATIONS[item.relation]
    sources = tuple(
        EvidenceSourceKind(value)
        for value in item.evidence_policy.allowed_source_kinds
        if value in EvidenceSourceKind._value2member_map_
    )
    assurance = {
        EvidenceStrength.WEAK: AssuranceLevel.WEAK,
        EvidenceStrength.INDEPENDENT: AssuranceLevel.STRUCTURAL,
        EvidenceStrength.AUTHORITATIVE: AssuranceLevel.AUTHORITATIVE,
    }[item.evidence_policy.minimum_strength]
    action_caused = item.relation in {
        StateCriterionRelation.IS_COMPLETED,
        StateCriterionRelation.HAS_CHANGED,
    }
    return PredicateExpr(
        criterion_id=item.criterion_id,
        subject=SubjectExpr("target", item.subject, field),
        operator=operator,
        policy=CriterionPolicy(
            satisfaction=(
                SatisfactionMode.ACTION_CAUSED
                if action_caused
                else SatisfactionMode.STATE_HOLDS
            ),
            minimum_assurance=assurance,
            allowed_source_kinds=sources,
            causal_lineage_required=action_caused,
        ),
        value=None if item.expected_value is None else LiteralValue(item.expected_value),
        source_refs=tuple(ref.source_unit_id for ref in item.source_refs),
    )


_RELATIONS = {
    StateCriterionRelation.EQUALS: (PredicateOperator.EQUALS, "equals"),
    StateCriterionRelation.CONTAINS: (PredicateOperator.CONTAINS, "contains"),
    StateCriterionRelation.MATCHES: (PredicateOperator.MATCHES_REGEX, "matches"),
    StateCriterionRelation.IS_VISIBLE: (PredicateOperator.EXISTS, ""),
    StateCriterionRelation.IS_ABSENT: (PredicateOperator.ABSENT, ""),
    StateCriterionRelation.IS_AVAILABLE: (PredicateOperator.EXISTS, ""),
    StateCriterionRelation.IS_SELECTED: (PredicateOperator.SELECTED, "selected"),
    StateCriterionRelation.IS_CHECKED: (PredicateOperator.CHECKED, "checked"),
    StateCriterionRelation.IS_EXPANDED: (PredicateOperator.EQUALS, "expanded"),
    StateCriterionRelation.IS_COMPLETED: (PredicateOperator.CHANGED, "completed"),
    StateCriterionRelation.IS_ORDERED_AS: (PredicateOperator.ORDERED_AS, "ordered_as"),
    StateCriterionRelation.HAS_CHANGED: (PredicateOperator.CHANGED, "changed"),
}
