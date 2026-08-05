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
from affordance_runtime.verification.providers import MECHANICAL_EVIDENCE_PROVIDERS


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


@pytest.mark.parametrize(
    ("source_kind", "assurance"),
    (
        (EvidenceSourceKind.DOM_STATE, AssuranceLevel.STRUCTURAL),
        (EvidenceSourceKind.API_STATE, AssuranceLevel.AUTHORITATIVE),
        (EvidenceSourceKind.ARTIFACT_INTEGRITY, AssuranceLevel.AUTHORITATIVE),
    ),
)
def test_shared_provider_contract(source_kind, assurance) -> None:  # noqa: ANN001
    policy = _policy(
        minimum_assurance=assurance,
        allowed_source_kinds=(source_kind,),
    )
    predicate = _predicate(PredicateOperator.EQUALS, policy=policy)
    context = PredicateEvidenceContext(
        "observation:2",
        (_evidence(source_kind=source_kind, assurance=assurance),),
    )
    assert (
        PredicateEvaluator(MECHANICAL_EVIDENCE_PROVIDERS)
        .evaluate(predicate, context)
        .status
        == CriterionStatus.SATISFIED
    )


def test_provider_conflict_and_high_risk_weak_evidence_are_not_satisfied() -> None:
    predicate = _predicate(PredicateOperator.EQUALS)
    conflict = PredicateEvidenceContext(
        "observation:2",
        (
            _evidence("ready", evidence_ref="evidence:a"),
            _evidence("waiting", evidence_ref="evidence:b"),
        ),
    )
    assert PredicateEvaluator().evaluate(predicate, conflict).status == CriterionStatus.CONFLICT

    high_risk = _predicate(
        PredicateOperator.EQUALS,
        policy=_policy(
            validity=EvidenceValidityMode.FINAL_RECHECK,
            minimum_assurance=AssuranceLevel.AUTHORITATIVE,
            allowed_source_kinds=(EvidenceSourceKind.API_STATE,),
        ),
    )
    weak = PredicateEvidenceContext(
        "observation:2",
        (
            _evidence(
                source_kind=EvidenceSourceKind.MODEL_SEMANTIC,
                assurance=AssuranceLevel.WEAK,
            ),
        ),
    )
    assert PredicateEvaluator().evaluate(high_risk, weak).status == CriterionStatus.UNKNOWN
