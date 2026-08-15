import asyncio
import hashlib
from dataclasses import dataclass, field, replace

import pytest

from affordance_runtime.agent.context import ModelFailure, ModelFailureKind
from affordance_runtime.evaluation import CriterionEvaluationStatus, TaskEvaluationStatus
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.evaluation.semantic_contracts import SemanticCriterionProposal
from affordance_runtime.evaluation.validation import validate_task_evaluation
from affordance_runtime.task import EvaluationSpec, TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)
from tests.support.world import fused_world


def _world(
    value=True,
    *,
    profile: ObservationSourceProfile | None = None,
    subject: str = "target:1",
    predicate: str = "ready",
    source_id: str = "source:1",
    artifacts: dict[str, object] | None = None,
) -> WorldObservation:
    chosen = profile or ObservationSourceProfile.dom()
    fact = StateFact("fact:current", subject, predicate, value, source_id)
    target = SemanticTarget(subject, "content", subject, {predicate: value})
    source = SurfaceObservation(
        source_id, chosen.debug_source, "revision:1", chosen,
        targets=(target,), facts=(fact,), artifacts=artifacts or {},
        visual_only_target_ids=((subject,) if chosen.modality.value == "visual" else ()),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _mechanical_task(*, expression=None, evaluation_spec=None) -> TaskGoal:
    spec = evaluation_spec or (EvaluationSpec(expression) if expression else None)
    return TaskGoal(
        "task:1", "Check readiness",
        success_criteria=({"id": "ready", "predicate": "ready", "value": True},),
        evaluation_spec=spec,
    )


@dataclass
class ScriptedJudge:
    outcome: object
    calls: int = 0
    requests: list[object] = field(default_factory=list)

    async def evaluate(self, request):
        self.calls += 1
        self.requests.append(request)
        return self.outcome


def test_production_mechanical_status_is_runtime_computed_without_semantic_call() -> None:
    async def scenario() -> None:
        judge = ScriptedJudge(())
        evaluator = ProductionTaskEvaluator(judge)
        satisfied = await evaluator.evaluate(_mechanical_task(), _world(True))
        unsatisfied = await evaluator.evaluate(_mechanical_task(), _world(False))
        ambiguous_world = _world(True)
        ambiguous_world = replace(
            ambiguous_world,
            facts=ambiguous_world.facts + (
                StateFact("fact:other", "target:2", "ready", True, "source:1"),
            ),
        )
        unknown = await evaluator.evaluate(_mechanical_task(), ambiguous_world)

        assert satisfied.status == TaskEvaluationStatus.COMPLETE
        assert unsatisfied.status == TaskEvaluationStatus.INCOMPLETE
        assert unknown.status == TaskEvaluationStatus.UNKNOWN
        assert judge.calls == 0

    asyncio.run(scenario())


def _semantic_task(adjudicator: str = "semantic") -> TaskGoal:
    kind = "semantic_rubric" if adjudicator == "semantic" else "hybrid"
    criterion = {
        "id": "quality",
        "adjudicator": adjudicator,
        "kind": kind,
        "rubric": "The report contains a clear conclusion.",
        "evidence_scope_target_ids": ["report:1"],
    }
    if adjudicator == "hybrid":
        criterion.update({"subject_id": "report:1", "predicate": "ready", "expected_value": True})
    return TaskGoal("semantic", "Review report", success_criteria=(criterion,))


def test_semantic_proposal_requires_exact_ids_current_refs_and_scope() -> None:
    world = _world("clear conclusion", subject="report:1", predicate="content")

    async def evaluate(outcome) -> object:
        return await ProductionTaskEvaluator(ScriptedJudge(outcome)).evaluate(_semantic_task(), world)

    accepted = (SemanticCriterionProposal("quality", CriterionEvaluationStatus.SATISFIED, ("fact:current",), "meets rubric"),)
    invented = (SemanticCriterionProposal("quality", CriterionEvaluationStatus.SATISFIED, ("fact:invented",), "invented"),)
    wrong_id = (SemanticCriterionProposal("other", CriterionEvaluationStatus.SATISFIED, ("fact:current",), "wrong"),)

    assert asyncio.run(evaluate(accepted)).status == TaskEvaluationStatus.COMPLETE
    assert asyncio.run(evaluate(invented)).status == TaskEvaluationStatus.UNKNOWN
    assert asyncio.run(evaluate(wrong_id)).status == TaskEvaluationStatus.UNKNOWN
    failure = ModelFailure(ModelFailureKind.TIMEOUT, "semantic judge timed out", False)
    assert asyncio.run(evaluate(failure)).status == TaskEvaluationStatus.UNKNOWN

    accepted_evaluation = asyncio.run(evaluate(accepted))
    assert validate_task_evaluation(
        accepted_evaluation, _semantic_task(), world, WorldEvidenceIndex.from_observation(world)
    ).status == TaskEvaluationStatus.COMPLETE


def test_semantic_missing_extra_or_wrong_target_proposals_are_unknown() -> None:
    absent_world = _world("clear conclusion", subject="other:1", predicate="content")
    absent_judge = ScriptedJudge(())
    absent = asyncio.run(ProductionTaskEvaluator(absent_judge).evaluate(_semantic_task(), absent_world))
    assert absent.status == TaskEvaluationStatus.INCOMPLETE
    assert absent_judge.calls == 0

    world = _world("clear conclusion", subject="report:1", predicate="content")
    unrelated_fact = StateFact("fact:other", "other:1", "content", "unrelated", "source:1")
    world = replace(world, facts=world.facts + (unrelated_fact,))
    proposal = SemanticCriterionProposal("quality", CriterionEvaluationStatus.SATISFIED, ("fact:other",), "wrong scope")
    extra = (
        proposal,
        SemanticCriterionProposal("extra", CriterionEvaluationStatus.UNKNOWN, (), "extra"),
    )
    evaluator = ProductionTaskEvaluator(ScriptedJudge((proposal,)))
    assert asyncio.run(evaluator.evaluate(_semantic_task(), world)).status == TaskEvaluationStatus.UNKNOWN
    assert asyncio.run(ProductionTaskEvaluator(ScriptedJudge(())).evaluate(_semantic_task(), world)).status == TaskEvaluationStatus.UNKNOWN
    assert asyncio.run(ProductionTaskEvaluator(ScriptedJudge(extra)).evaluate(_semantic_task(), world)).status == TaskEvaluationStatus.UNKNOWN


def _user_task() -> TaskGoal:
    return TaskGoal(
        "accept", "Require acceptance",
        success_criteria=({"id": "accepted", "adjudicator": "user_acceptance", "kind": "user_acceptance"},),
    )


def test_user_acceptance_requires_explicit_authoritative_user_source() -> None:
    missing = _world("approved", subject="accepted", predicate="accepted")
    accepted = _world(True, profile=ObservationSourceProfile.user(), subject="accepted", predicate="accepted")
    rejected = _world(False, profile=ObservationSourceProfile.user(), subject="accepted", predicate="accepted")
    evaluator = ProductionTaskEvaluator()

    assert asyncio.run(evaluator.evaluate(_user_task(), missing)).status == TaskEvaluationStatus.UNKNOWN
    assert asyncio.run(evaluator.evaluate(_user_task(), accepted)).status == TaskEvaluationStatus.COMPLETE
    assert asyncio.run(evaluator.evaluate(_user_task(), rejected)).status == TaskEvaluationStatus.INCOMPLETE


def test_hybrid_requires_both_mechanical_and_semantic_components() -> None:
    satisfied = SemanticCriterionProposal("quality", CriterionEvaluationStatus.SATISFIED, ("fact:semantic",), "quality ok")
    unknown = SemanticCriterionProposal("quality", CriterionEvaluationStatus.UNKNOWN, (), "cannot judge")
    task = _semantic_task("hybrid")

    failed_judge = ScriptedJudge((satisfied,))
    def hybrid_world(value):
        world = _world(value, subject="report:1")
        semantic = StateFact("fact:semantic", "report:1", "content", "clear conclusion", "source:1")
        return replace(world, facts=world.facts + (semantic,))

    mechanical_failed = asyncio.run(ProductionTaskEvaluator(failed_judge).evaluate(task, hybrid_world(False)))
    semantic_unknown = asyncio.run(ProductionTaskEvaluator(ScriptedJudge((unknown,))).evaluate(task, hybrid_world(True)))
    both = asyncio.run(ProductionTaskEvaluator(ScriptedJudge((satisfied,))).evaluate(task, hybrid_world(True)))

    assert mechanical_failed.status == TaskEvaluationStatus.INCOMPLETE
    assert failed_judge.calls == 0
    assert semantic_unknown.status == TaskEvaluationStatus.UNKNOWN
    assert both.status == TaskEvaluationStatus.COMPLETE


def test_hybrid_mechanical_fact_cannot_be_reused_as_semantic_evidence() -> None:
    task = _semantic_task("hybrid")
    proposal = SemanticCriterionProposal(
        "quality", CriterionEvaluationStatus.SATISFIED, ("fact:current",), "borrowed mechanical fact"
    )

    result = asyncio.run(
        ProductionTaskEvaluator(ScriptedJudge((proposal,))).evaluate(task, _world(True, subject="report:1"))
    )

    assert result.status == TaskEvaluationStatus.UNKNOWN


def test_hybrid_mechanical_unknown_skips_semantic_judge() -> None:
    task = _semantic_task("hybrid")
    world = _world(True, subject="report:1")
    duplicate = StateFact("fact:duplicate", "report:1", "ready", True, "source:1")
    world = replace(world, facts=world.facts + (duplicate,))
    judge = ScriptedJudge(())

    result = asyncio.run(ProductionTaskEvaluator(judge).evaluate(task, world))

    assert result.status == TaskEvaluationStatus.UNKNOWN
    assert judge.calls == 0


@pytest.mark.parametrize(
    ("expression", "expected"),
    (
        ({"all": [{"criterion": "a"}, {"criterion": "b"}]}, TaskEvaluationStatus.INCOMPLETE),
        ({"any": [{"criterion": "a"}, {"criterion": "b"}]}, TaskEvaluationStatus.COMPLETE),
        ({"not": {"criterion": "b"}}, TaskEvaluationStatus.COMPLETE),
    ),
)
def test_bounded_success_expression_all_any_not(expression, expected) -> None:
    task = TaskGoal(
        "expression", "Evaluate expression",
        success_criteria=(
            {"id": "a", "predicate": "a", "value": True},
            {"id": "b", "predicate": "b", "value": True},
        ),
        evaluation_spec=EvaluationSpec(expression),
    )
    facts = (
        StateFact("fact:a", "target:1", "a", True, "source:1"),
        StateFact("fact:b", "target:1", "b", False, "source:1"),
    )
    source = SurfaceObservation(
        "source:1", "dom", "revision:1", ObservationSourceProfile.dom(),
        targets=(SemanticTarget("target:1", "state", "target", {"a": True, "b": False}),),
        facts=facts,
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation

    result = asyncio.run(ProductionTaskEvaluator().evaluate(task, world))
    assert result.status == expected


def test_unsupported_expression_is_blocked() -> None:
    task = _mechanical_task(evaluation_spec=EvaluationSpec({"xor": [{"criterion": "ready"}]}))
    assert asyncio.run(ProductionTaskEvaluator().evaluate(task, _world(True))).status == TaskEvaluationStatus.BLOCKED


def test_authoritative_checks_and_strict_current_source_lineage() -> None:
    weak_task = _mechanical_task(evaluation_spec=EvaluationSpec({"criterion": "ready"}, authoritative_checks=("ready",)))
    strict_task = _mechanical_task(evaluation_spec=EvaluationSpec({"criterion": "ready"}, strict_source_lineage=True))

    structural = asyncio.run(ProductionTaskEvaluator().evaluate(weak_task, _world(True)))
    authoritative = asyncio.run(ProductionTaskEvaluator().evaluate(weak_task, _world(True, profile=ObservationSourceProfile.wot())))
    orphan_world = _world(True)
    orphan_fact = StateFact("fact:current", "target:1", "ready", True, "orphan")
    orphan_world = replace(orphan_world, facts=(orphan_fact,))
    orphan = asyncio.run(ProductionTaskEvaluator().evaluate(strict_task, orphan_world))

    assert structural.status == TaskEvaluationStatus.UNKNOWN
    assert authoritative.status == TaskEvaluationStatus.COMPLETE
    assert orphan.status == TaskEvaluationStatus.UNKNOWN


def test_authoritative_or_strict_semantic_absence_without_evidence_is_unknown() -> None:
    criterion = {
        "id": "quality", "adjudicator": "semantic", "kind": "semantic_rubric",
        "rubric": "A report exists", "evidence_scope_target_ids": ["report:1"],
    }
    absent = fused_world("absent", surface="dom")
    authoritative = TaskGoal(
        "authoritative", "Create report", success_criteria=(criterion,),
        evaluation_spec=EvaluationSpec({"criterion": "quality"}, authoritative_checks=("quality",)),
    )
    strict = TaskGoal(
        "strict", "Create report", success_criteria=(criterion,),
        evaluation_spec=EvaluationSpec({"criterion": "quality"}, strict_source_lineage=True),
    )
    assert asyncio.run(ProductionTaskEvaluator().evaluate(authoritative, absent)).status == TaskEvaluationStatus.UNKNOWN
    assert asyncio.run(ProductionTaskEvaluator().evaluate(strict, absent)).status == TaskEvaluationStatus.UNKNOWN


def test_missing_required_output_is_incomplete_when_inventory_is_complete() -> None:
    task = TaskGoal(
        "output-later", "Export report",
        success_criteria=({"id": "ready", "predicate": "ready", "value": True},),
        requested_outputs=("report",),
    )
    complete_inventory = _world(True)
    source = replace(complete_inventory.sources[0], coverage=CoverageState.TRUNCATED)
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    truncated = fused.observation
    assert asyncio.run(ProductionTaskEvaluator().evaluate(task, complete_inventory)).status == TaskEvaluationStatus.INCOMPLETE
    assert asyncio.run(ProductionTaskEvaluator().evaluate(task, truncated)).status == TaskEvaluationStatus.UNKNOWN


def test_missing_required_output_does_not_overwrite_unknown_criterion() -> None:
    task = TaskGoal(
        "output-unknown", "Export report",
        success_criteria=({"id": "ready", "predicate": "ready", "value": True},),
        requested_outputs=("report",),
    )
    world = _world(True)
    ambiguous = StateFact("fact:ambiguous", "target:2", "ready", False, "source:1")
    world = replace(world, facts=(*world.facts, ambiguous))

    assert asyncio.run(ProductionTaskEvaluator().evaluate(task, world)).status == TaskEvaluationStatus.UNKNOWN


def test_output_value_path_sha_file_and_current_artifact_are_bound(tmp_path) -> None:
    output = tmp_path / "report.txt"
    output.write_text("complete report", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    requirement = {"path": str(output), "sha256": digest}
    task = TaskGoal(
        "output", "Create report",
        success_criteria=({"id": "ready", "predicate": "ready", "value": True},),
        requested_outputs=("report",),
        evaluation_spec=EvaluationSpec({"criterion": "ready"}, required_output_integrity={"report": requirement}),
    )

    complete = asyncio.run(ProductionTaskEvaluator().evaluate(task, _world(True, artifacts={"report": requirement})))
    wrong = asyncio.run(ProductionTaskEvaluator().evaluate(task, _world(True, artifacts={"report": {"path": str(output), "sha256": "0" * 64}})))
    missing_path = asyncio.run(ProductionTaskEvaluator().evaluate(task, _world(True, artifacts={"report": {"sha256": digest}})))

    assert complete.status == TaskEvaluationStatus.COMPLETE
    assert complete.outputs[0].value == requirement
    assert wrong.status == TaskEvaluationStatus.BLOCKED
    assert missing_path.status == TaskEvaluationStatus.BLOCKED
