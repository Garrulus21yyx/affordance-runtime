from dataclasses import replace

import pytest

from affordance_runtime.evaluation import CriterionEvaluation, CriterionEvaluationStatus
from affordance_runtime.evaluation.criterion_contracts import CriterionAdjudicator
from affordance_runtime.evaluation.criterion_normalization import normalize_criterion, normalize_task_criteria
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_applicability import EvidenceApplicability, assess_criterion_evidence
from affordance_runtime.evaluation.mechanical_criteria import MechanicalCriterionEvaluator
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationConflict,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def _world(
    facts: tuple[StateFact, ...],
    *,
    profile: ObservationSourceProfile | None = None,
    artifacts: dict[str, object] | None = None,
    conflicts: tuple[ObservationConflict, ...] = (),
) -> WorldObservation:
    source = SurfaceObservation(
        "source:1",
        "dom" if profile is None else profile.debug_source,
        "revision:1",
        profile or ObservationSourceProfile.dom(),
        facts=facts,
        artifacts=artifacts or {},
    )
    targets = tuple(
        SemanticTarget(subject, "state", subject, {fact.predicate: fact.value for fact in facts if fact.subject_id == subject})
        for subject in sorted({fact.subject_id for fact in facts})
    )
    return WorldObservation(
        "world:1",
        targets,
        facts,
        (),
        {source.surface: CoverageState.COMPLETE},
        conflicts,
        (source,),
    )


def test_criterion_normalization_supports_legacy_and_explicit_minimum_profiles() -> None:
    legacy_fact = normalize_criterion({"id": "ready", "predicate": "ready", "value": True})
    legacy_target = normalize_criterion({"id": "enabled", "target_id": "target:1", "state": {"enabled": True}})
    semantic = normalize_criterion(
        {
            "id": "quality",
            "adjudicator": "semantic",
            "kind": "semantic_rubric",
            "rubric": "The report contains a clear conclusion.",
            "evidence_scope_target_ids": ["report:1"],
        }
    )

    assert legacy_fact.adjudicator == CriterionAdjudicator.MECHANICAL
    assert legacy_fact.kind == "fact_equals" and legacy_fact.expected_value is True
    assert legacy_target.kind == "target_state_equals" and legacy_target.state_key == "enabled"
    assert semantic.adjudicator == CriterionAdjudicator.SEMANTIC
    assert semantic.evidence_scope_target_ids == ("report:1",)


@pytest.mark.parametrize(
    "criterion",
    (
        {"id": "rubric", "rubric": "good"},
        {"id": "accept", "kind": "user_acceptance"},
        {"id": "fact", "kind": "fact_equals", "predicate": "ready"},
        {"id": "unknown", "kind": "sql", "query": "select 1"},
    ),
)
def test_unsupported_or_implicitly_authoritative_criterion_shapes_fail_closed(criterion) -> None:
    with pytest.raises(ValueError):
        normalize_criterion(criterion)


def test_normalized_task_criteria_preserve_nonblank_unique_identity() -> None:
    task = TaskGoal("task", "check", success_criteria=({"id": "same", "predicate": "ready", "value": True},))
    assert normalize_task_criteria(task)[0].criterion_id == "same"
    with pytest.raises(ValueError, match="unique"):
        normalize_task_criteria(
            replace(task, success_criteria=(task.success_criteria[0], task.success_criteria[0]))
        )


def test_world_evidence_index_resolves_typed_current_records_without_private_artifact_value() -> None:
    fact = StateFact("fact:ready", "target:1", "ready", True, "source:1")
    world = _world((fact,), artifacts={"report": {"path": "/private/report", "credential": "secret"}})
    index = WorldEvidenceIndex.from_observation(world)

    record = index.resolve_record("fact:ready")
    artifact = index.resolve_record("artifact:source:1:report")
    assert record is not None and record.subject_id == "target:1" and record.value is True
    assert record.source_assurance == "structural"
    assert artifact is not None and artifact.artifact_kind == "report"
    assert "/private/report" not in repr(index) and "secret" not in repr(index)


def test_mechanical_fact_equals_handles_single_ambiguous_conflicting_and_assurance() -> None:
    spec = normalize_criterion({"id": "ready", "predicate": "ready", "value": True})
    evaluator = MechanicalCriterionEvaluator()
    single = _world((StateFact("fact:one", "target:1", "ready", True, "source:1"),))
    ambiguous = _world(
        (
            StateFact("fact:one", "target:1", "ready", True, "source:1"),
            StateFact("fact:two", "target:2", "ready", True, "source:1"),
        )
    )
    conflicting = replace(
        single,
        conflicts=(ObservationConflict("conflict:1", "target:1", "ready", "sources disagree"),),
    )

    assert evaluator.evaluate(spec, single).status == CriterionEvaluationStatus.SATISFIED
    assert evaluator.evaluate(spec, ambiguous).status == CriterionEvaluationStatus.UNKNOWN
    assert evaluator.evaluate(spec, conflicting).status == CriterionEvaluationStatus.UNKNOWN

    required = replace(spec, subject_id="target:1", required_assurance="authoritative")
    assert evaluator.evaluate(required, single).status == CriterionEvaluationStatus.UNKNOWN


def test_mechanical_target_state_and_artifact_profiles() -> None:
    fact = StateFact("fact:enabled", "target:1", "enabled", False, "source:1")
    world = _world((fact,), artifacts={"receipt": {"private": "value"}})
    evaluator = MechanicalCriterionEvaluator()
    target_spec = normalize_criterion(
        {"id": "enabled", "kind": "target_state_equals", "target_id": "target:1", "state_key": "enabled", "expected_value": True}
    )
    artifact_spec = normalize_criterion(
        {"id": "receipt", "kind": "artifact_exists", "output_id": "receipt"}
    )

    assert evaluator.evaluate(target_spec, world).status == CriterionEvaluationStatus.UNSATISFIED
    artifact_result = evaluator.evaluate(artifact_spec, world)
    assert artifact_result.status == CriterionEvaluationStatus.SATISFIED
    assert artifact_result.evidence_refs == ("artifact:source:1:receipt",)


def test_evidence_applicability_rejects_scope_external_and_accepts_exact_record() -> None:
    facts = (
        StateFact("fact:one", "target:1", "ready", True, "source:1"),
        StateFact("fact:two", "target:2", "ready", True, "source:1"),
    )
    index = WorldEvidenceIndex.from_observation(_world(facts))
    spec = normalize_criterion(
        {"id": "ready", "kind": "fact_equals", "subject_id": "target:1", "predicate": "ready", "expected_value": True}
    )
    exact = CriterionEvaluation("ready", CriterionEvaluationStatus.SATISFIED, ("fact:one",), "supported")
    external = CriterionEvaluation("ready", CriterionEvaluationStatus.SATISFIED, ("fact:two",), "wrong target")
    wrong_value = replace(exact, status=CriterionEvaluationStatus.UNSATISFIED)

    assert assess_criterion_evidence(spec, exact, index) == EvidenceApplicability.ACCEPTED
    assert assess_criterion_evidence(spec, external, index) == EvidenceApplicability.REJECTED
    assert assess_criterion_evidence(spec, wrong_value, index) == EvidenceApplicability.REJECTED
