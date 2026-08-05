from __future__ import annotations

from dataclasses import dataclass

import pytest

from affordance_runtime.criteria import (
    AllOf,
    AnyOf,
    LiteralValue,
    Not,
    PredicateExpr,
    PredicateOperator,
    SubjectExpr,
)
from affordance_runtime.verification.contracts import (
    AssuranceLevel,
    CriterionPolicy,
    CriterionStatus,
    EvidenceSourceKind,
    EvidenceValidityMode,
    PredicateEvidence,
    PredicateEvidenceContext,
    SatisfactionMode,
)
from affordance_runtime.verification.predicates import PredicateEvaluator


@dataclass(frozen=True)
class FixedProvider:
    items: tuple[PredicateEvidence, ...]

    def evidence_for(self, predicate, context):  # noqa: ANN001, ANN201
        del context
        return tuple(item for item in self.items if item.subject_ref == predicate.subject.reference)


def _policy(**changes) -> CriterionPolicy:  # noqa: ANN003
    values = {
        "satisfaction": SatisfactionMode.STATE_HOLDS,
        "validity": EvidenceValidityMode.CURRENT_OBSERVATION,
        "minimum_assurance": AssuranceLevel.STRUCTURAL,
        "allowed_source_kinds": (EvidenceSourceKind.DOM_STATE,),
    }
    values.update(changes)
    return CriterionPolicy(**values)


def _predicate(operator: PredicateOperator, value="ready", *, policy=None) -> PredicateExpr:  # noqa: ANN001
    return PredicateExpr(
        f"criterion:{operator.value}",
        SubjectExpr("target", "target:status"),
        operator,
        policy or _policy(),
        None if value is None else LiteralValue(value),
    )


def _evidence(value="ready", **changes) -> PredicateEvidence:  # noqa: ANN003
    values = {
        "evidence_ref": "evidence:status",
        "subject_ref": "target:status",
        "observed_value": value,
        "source_kind": EvidenceSourceKind.DOM_STATE,
        "assurance": AssuranceLevel.STRUCTURAL,
        "observation_ref": "observation:2",
    }
    values.update(changes)
    return PredicateEvidence(**values)


@pytest.mark.parametrize(
    ("operator", "expected", "observed", "status"),
    (
        (PredicateOperator.EQUALS, "ready", "ready", CriterionStatus.SATISFIED),
        (PredicateOperator.CONTAINS, "ead", "ready", CriterionStatus.SATISFIED),
        (PredicateOperator.STARTS_WITH, "rea", "ready", CriterionStatus.SATISFIED),
        (PredicateOperator.ENDS_WITH, "ady", "ready", CriterionStatus.SATISFIED),
        (PredicateOperator.BETWEEN, (1, 3), 2, CriterionStatus.SATISFIED),
        (PredicateOperator.EQUALS, "ready", "waiting", CriterionStatus.UNSATISFIED),
        (PredicateOperator.VISIBLE, None, True, CriterionStatus.UNSUPPORTED),
    ),
)
def test_operator_policy_status_matrix(operator, expected, observed, status) -> None:  # noqa: ANN001
    evaluator = PredicateEvaluator((FixedProvider((_evidence(observed),)),))
    result = evaluator.evaluate(
        _predicate(operator, expected), PredicateEvidenceContext("observation:2")
    )
    assert result.status == status


def test_composites_preserve_typed_status_and_no_evidence_is_unknown() -> None:
    yes = _predicate(PredicateOperator.EQUALS)
    no = PredicateExpr(
        "criterion:no",
        yes.subject,
        PredicateOperator.EQUALS,
        yes.policy,
        LiteralValue("other"),
    )
    context = PredicateEvidenceContext("observation:2")
    evaluator = PredicateEvaluator((FixedProvider((_evidence(),)),))

    assert evaluator.evaluate(AllOf("all", (yes, no)), context).status == CriterionStatus.UNSATISFIED
    assert evaluator.evaluate(AnyOf("any", (yes, no)), context).status == CriterionStatus.SATISFIED
    assert evaluator.evaluate(Not("not", no), context).status == CriterionStatus.SATISFIED
    assert PredicateEvaluator().evaluate(yes, context).status == CriterionStatus.UNKNOWN
