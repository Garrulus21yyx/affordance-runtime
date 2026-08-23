from dataclasses import asdict, replace

from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget
from affordance_runtime.agent.context.evaluator_views import (
    ModelCriterionEvidenceWindow,
)
from affordance_runtime.agent.context.evaluator_views import (
    build_semantic_judge_request as _build_semantic_judge_request,
)
from affordance_runtime.evaluation import CriterionEvaluation, CriterionEvaluationStatus
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.evidence_applicability import EvidenceApplicability, assess_semantic_evidence
from affordance_runtime.evaluation.semantic_readiness import SemanticReadiness, assess_semantic_readiness
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
)
from tests.support.canonical_world import canonical_world
from tests.support.world import fused_world


def build_semantic_judge_request(task, criteria, world, index, budget=ContextProjectionBudget()):
    return _build_semantic_judge_request(
        task, criteria, world, index, canonical_world(world), budget
    )


def _task(*, hybrid=False, outputs=(), required_assurance=""):
    criterion = {
        "id": "quality", "adjudicator": "hybrid" if hybrid else "semantic",
        "kind": "hybrid" if hybrid else "semantic_rubric",
        "rubric": "The report is clear.", "evidence_scope_target_ids": ["report:1"],
        "evidence_scope_output_ids": list(outputs),
    }
    if required_assurance:
        criterion["required_assurance"] = required_assurance
    if hybrid:
        criterion.update({"subject_id": "control:1", "predicate": "enabled", "expected_value": True})
    return TaskGoal("semantic", "Create and review report", success_criteria=(criterion,))


def _world(*, coverage=CoverageState.COMPLETE, artifacts=None, include_decoy=False):
    facts = (
        StateFact("fact:report:content", "report:1", "content", "clear", "source:1"),
        StateFact("fact:report:private", "report:1", "internal", "hidden second fact", "source:1"),
    )
    source = SurfaceObservation(
        "source:1", "dom", "revision:1", ObservationSourceProfile.dom(),
        targets=(
            *((SemanticTarget("decoy:1", "content", "decoy"),) if include_decoy else ()),
            SemanticTarget("report:1", "content", "report"),
        ),
        facts=facts, artifacts=artifacts or {}, coverage=coverage,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def test_semantic_request_hides_mechanical_expected_value_and_pins_scope() -> None:
    task = _task(hybrid=True)
    world = _world(include_decoy=True)
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
    visible_public = request.visible_evidence_refs
    visible = tuple(request.private_evidence_resolver[ref] for ref in visible_public)
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
    absent = fused_world("absent", surface="dom")
    absent_request = build_semantic_judge_request(
        task, (criterion,), absent, WorldEvidenceIndex.from_observation(absent)
    )
    truncated = fused_world(
        "truncated", coverage=CoverageState.TRUNCATED, surface="dom"
    )
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


def test_scoped_evidence_below_required_assurance_is_inconclusive() -> None:
    task = _task(required_assurance="structural")
    criterion = normalize_task_criteria(task)[0]
    source = replace(
        _world().sources[0],
        source_profile=ObservationSourceProfile.visual(),
        visual_only_target_ids=("report:1",),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    weak = fused.observation
    request = build_semantic_judge_request(
        task, (criterion,), weak, WorldEvidenceIndex.from_observation(weak)
    )

    assert request.evidence_windows[0].eligible_count == 2
    assert assess_semantic_readiness(criterion, request, weak) == SemanticReadiness.INCONCLUSIVE
