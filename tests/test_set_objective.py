from __future__ import annotations

import pytest

from affordance_runtime.task.set_objective import (
    ActionObligationStatus,
    ActionTemplate,
    And,
    CandidateUniverse,
    FactEquals,
    Not,
    Or,
    PredicateAssessment,
    PredicateAssurance,
    PredicateTruth,
    ScopeCoverage,
    ScopeExtent,
    ScopeSpec,
    SetDisposition,
    SetMemberObligation,
    SetObjective,
    SetQuantifier,
    StabilityStatus,
    VisualConcept,
    evaluate_predicate,
    predicate_digest,
    reduce_set_objective,
    transition_obligation,
)


def _objective() -> SetObjective:
    return SetObjective(
        "set-objective:test",
        ScopeSpec("scope:test", "document", ScopeExtent.CURRENT_VIEWPORT),
        FactEquals("color_family", "blue"),
        SetQuantifier.ALL_IN_CLOSED_SCOPE,
        ActionTemplate("activate", FactEquals("selected", True)),
    )


def _universe(coverage: ScopeCoverage = ScopeCoverage.COMPLETE) -> CandidateUniverse:
    return CandidateUniverse(
        "scope:test", "epoch:1", ("a", "b"), coverage,
        (("source:dom:inventory",) if coverage is ScopeCoverage.COMPLETE else ()),
    )


def _assessment(entity_id: str, truth: PredicateTruth) -> PredicateAssessment:
    objective = _objective()
    return PredicateAssessment(
        entity_id, objective.predicate_digest, truth, PredicateAssurance.STRUCTURAL,
        "style-provider", "epoch:1", (f"fact:{entity_id}",),
    )


def test_scope_owner_and_classifier_coverage_are_independent_gates() -> None:
    objective = _objective()
    partial = reduce_set_objective(objective, _universe(ScopeCoverage.PARTIAL), (), ())
    assert partial.disposition is SetDisposition.NEED_SCOPE_CLOSURE

    incomplete = reduce_set_objective(objective, _universe(), (_assessment("a", PredicateTruth.TRUE),), ())
    assert incomplete.disposition is SetDisposition.NEED_CLASSIFICATION

    unknown = reduce_set_objective(
        objective,
        _universe(),
        (_assessment("a", PredicateTruth.TRUE), _assessment("b", PredicateTruth.UNKNOWN)),
        (),
    )
    assert unknown.disposition is SetDisposition.NEED_UNKNOWN_RESOLUTION


def test_membership_and_effect_obligation_are_separate_and_certified_only_after_stability() -> None:
    objective = _objective()
    assessments = (_assessment("a", PredicateTruth.TRUE), _assessment("b", PredicateTruth.FALSE))
    obligation = SetMemberObligation(
        "a", "epoch:1", PredicateTruth.TRUE, ActionObligationStatus.UNACTED,
    )
    ready = reduce_set_objective(objective, _universe(), assessments, (obligation,))
    assert ready.disposition is SetDisposition.READY_FOR_NEXT_MEMBER
    assert ready.next_entity_id == "a"

    in_flight = transition_obligation(
        obligation, ActionObligationStatus.ACTION_IN_FLIGHT, observation_epoch="epoch:1",
    )
    confirmed = transition_obligation(
        in_flight,
        ActionObligationStatus.EFFECT_CONFIRMED,
        observation_epoch="epoch:2",
        evidence_refs=("evaluation:effect:a",),
    )
    pending = reduce_set_objective(objective, _universe(), assessments, (confirmed,))
    assert pending.disposition is SetDisposition.NEED_STABILITY_CHECK
    complete = reduce_set_objective(
        objective, _universe(), assessments, (confirmed,), stability_status=StabilityStatus.PASSED,
    )
    assert complete.disposition is SetDisposition.CERTIFIED
    assert complete.certificate is not None
    assert complete.certificate.predicate_unknown_count == 0
    assert complete.certificate.true_unacted_count == 0


def test_obligation_state_machine_rejects_impossible_shortcuts() -> None:
    obligation = SetMemberObligation(
        "a", "epoch:1", PredicateTruth.TRUE, ActionObligationStatus.UNACTED,
    )
    with pytest.raises(ValueError, match="illegal obligation transition"):
        transition_obligation(
            obligation,
            ActionObligationStatus.EFFECT_CONFIRMED,
            observation_epoch="epoch:2",
            evidence_refs=("evaluation:effect:a",),
        )


def test_predicate_algebra_uses_three_valued_logic() -> None:
    predicate = And((FactEquals("kind", "apple"), Not(VisualConcept("rotten"))))
    assert evaluate_predicate(predicate, {"kind": "apple"}) is PredicateTruth.UNKNOWN
    rotten = {predicate_digest(VisualConcept("rotten")): PredicateTruth.FALSE}
    assert evaluate_predicate(predicate, {"kind": "apple"}, rotten) is PredicateTruth.TRUE
    assert evaluate_predicate(predicate, {"kind": "pear"}) is PredicateTruth.FALSE


def test_predicate_digest_is_type_discriminated_for_composites() -> None:
    operands = (FactEquals("kind", "apple"), FactEquals("color", "red"))

    assert predicate_digest(And(operands)) != predicate_digest(Or(operands))


def test_assessment_order_is_irrelevant_and_stale_epoch_fails_closed() -> None:
    objective = _objective()
    assessments = (_assessment("a", PredicateTruth.TRUE), _assessment("b", PredicateTruth.FALSE))
    obligation = SetMemberObligation("a", "epoch:1", PredicateTruth.TRUE, ActionObligationStatus.UNACTED)
    forward = reduce_set_objective(objective, _universe(), assessments, (obligation,))
    reverse = reduce_set_objective(objective, _universe(), tuple(reversed(assessments)), (obligation,))
    assert forward == reverse
    stale = PredicateAssessment(
        "a", objective.predicate_digest, PredicateTruth.TRUE, PredicateAssurance.STRUCTURAL,
        "style-provider", "epoch:stale", ("fact:a",),
    )
    rejected = reduce_set_objective(
        objective, _universe(), (stale, _assessment("b", PredicateTruth.FALSE)), (obligation,),
    )
    assert rejected.disposition is SetDisposition.BLOCKED
    assert rejected.reason_code == "assessment_snapshot_invalid"


def test_historical_membership_survives_predicate_becoming_false() -> None:
    objective = _objective()
    assessments = (_assessment("a", PredicateTruth.FALSE), _assessment("b", PredicateTruth.FALSE))
    historical = SetMemberObligation(
        "a", "epoch:0", PredicateTruth.FALSE, ActionObligationStatus.EFFECT_CONFIRMED,
        ("evaluation:effect:a",), "epoch:1",
    )
    complete = reduce_set_objective(
        objective, _universe(), assessments, (historical,), stability_status=StabilityStatus.PASSED,
    )
    assert complete.disposition is SetDisposition.CERTIFIED
    assert complete.true_entity_ids == ("a",)
