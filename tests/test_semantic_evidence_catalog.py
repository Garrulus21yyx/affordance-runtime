from dataclasses import asdict, replace

from affordance_runtime.evaluation import CriterionEvaluation, CriterionEvaluationStatus
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_applicability import EvidenceApplicability, assess_semantic_evidence
from affordance_runtime.evaluation.semantic_readiness import SemanticReadiness, assess_semantic_readiness
from affordance_runtime.model_boundary.budgets import BoundedSection, ContextProjectionBudget
from affordance_runtime.model_boundary.evaluator_views import (
    ModelCriterionEvidenceWindow,
    build_semantic_judge_request,
)
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def _task(*, hybrid=False, outputs=()):
    criterion = {
        "id": "quality", "adjudicator": "hybrid" if hybrid else "semantic",
        "kind": "hybrid" if hybrid else "semantic_rubric",
        "rubric": "The report is clear.", "evidence_scope_target_ids": ["report:1"],
        "evidence_scope_output_ids": list(outputs),
    }
    if hybrid:
        criterion.update({"subject_id": "control:1", "predicate": "enabled", "expected_value": True})
    return TaskGoal("semantic", "Create and review report", success_criteria=(criterion,))


def _world(*, coverage=CoverageState.COMPLETE, artifacts=None):
    facts = (
        StateFact("fact:report:content", "report:1", "content", "clear", "source:1"),
        StateFact("fact:report:private", "report:1", "internal", "hidden second fact", "source:1"),
    )
    source = SurfaceObservation(
        "source:1", "dom", "revision:1", ObservationSourceProfile.dom(),
        facts=facts, artifacts=artifacts or {}, coverage=coverage,
    )
    return WorldObservation(
        "world:1", (SemanticTarget("report:1", "content", "report"),), facts, (),
        {"dom": coverage}, sources=(source,),
    )


def test_semantic_request_hides_mechanical_expected_value_and_pins_scope() -> None:
    task = _task(hybrid=True)
    world = _world()
    world = WorldObservation(
        world.observation_id,
        (SemanticTarget("decoy:1", "content", "decoy"), *world.targets),
        world.facts, (), world.coverage, sources=world.sources,
    )
    request = build_semantic_judge_request(
        task, normalize_task_criteria(task), world, WorldEvidenceIndex.from_observation(world),
        ContextProjectionBudget(max_targets=1),
    )
    payload = asdict(request)

    assert request.world.targets.items[0].target_id == "report:1"
    assert "expected_value" not in str(payload)
    assert "enabled" not in str(payload["criteria"])
    assert request.task.success_criteria.items == ()


def test_only_presented_catalog_refs_can_support_semantic_proposal() -> None:
    task = _task()
    criterion = normalize_task_criteria(task)[0]
    world = _world()
    index = WorldEvidenceIndex.from_observation(world)
    budget = ContextProjectionBudget(max_facts_per_target=1)
    request = build_semantic_judge_request(task, (criterion,), world, index, budget)
    visible = request.visible_evidence_refs
    hidden = next(ref for ref in index.refs if ref not in visible)

    accepted = CriterionEvaluation("quality", CriterionEvaluationStatus.SATISFIED, (visible[0],), "visible")
    rejected = CriterionEvaluation("quality", CriterionEvaluationStatus.SATISFIED, (hidden,), "hidden")
    assert request.evidence_catalog.truncated is True
    window = request.evidence_windows[0]
    assert window.criterion_id == "quality"
    assert window.eligible_count == 2
    assert window.visible_count == 1
    assert window.truncated is True
    assert assess_semantic_readiness(criterion, request, world) == SemanticReadiness.READY
    assert assess_semantic_evidence(criterion, accepted, index, visible) == EvidenceApplicability.ACCEPTED
    assert assess_semantic_evidence(criterion, rejected, index, visible) == EvidenceApplicability.REJECTED


def test_artifact_output_scope_is_visible_without_private_value_or_path() -> None:
    task = _task(outputs=("report",))
    world = _world(artifacts={
        "report": {"path": "/private/report.txt", "value": "raw private artifact", "public_summary": "report available"}
    })
    request = build_semantic_judge_request(
        task, normalize_task_criteria(task), world, WorldEvidenceIndex.from_observation(world)
    )
    artifact = next(item for item in request.evidence_catalog.items if item.kind == "artifact")
    representation = str(asdict(request))

    assert artifact.output_id == "report"
    assert artifact.evidence_ref == "artifact:source:1:report"
    assert artifact.public_summary == "report available"
    assert "/private/report.txt" not in representation
    assert "raw private artifact" not in representation


def test_semantic_readiness_distinguishes_present_absent_and_inconclusive_scope() -> None:
    task = _task()
    criterion = normalize_task_criteria(task)[0]
    present = _world()
    present_request = build_semantic_judge_request(
        task, (criterion,), present, WorldEvidenceIndex.from_observation(present)
    )
    absent = WorldObservation("absent", (), (), (), {"dom": CoverageState.COMPLETE})
    absent_request = build_semantic_judge_request(
        task, (criterion,), absent, WorldEvidenceIndex.from_observation(absent)
    )
    truncated = WorldObservation("truncated", (), (), (), {"dom": CoverageState.TRUNCATED})
    truncated_request = build_semantic_judge_request(
        task, (criterion,), truncated, WorldEvidenceIndex.from_observation(truncated)
    )

    assert assess_semantic_readiness(criterion, present_request, present) == SemanticReadiness.READY
    assert assess_semantic_readiness(criterion, absent_request, absent) == SemanticReadiness.NOT_READY
    assert assess_semantic_readiness(criterion, truncated_request, truncated) == SemanticReadiness.INCONCLUSIVE


def test_scoped_evidence_fully_hidden_by_budget_is_inconclusive() -> None:
    task = _task()
    criterion = normalize_task_criteria(task)[0]
    world = _world()
    request = build_semantic_judge_request(
        task, (criterion,), world, WorldEvidenceIndex.from_observation(world)
    )
    request = replace(
        request,
        evidence_catalog=BoundedSection((), 2, True),
        evidence_windows=(ModelCriterionEvidenceWindow("quality", 2, 0, True),),
    )
    assert request.evidence_windows[0].eligible_count == 2
    assert request.evidence_windows[0].visible_count == 0
    assert assess_semantic_readiness(criterion, request, world) == SemanticReadiness.INCONCLUSIVE
