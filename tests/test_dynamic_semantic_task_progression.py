import asyncio
from dataclasses import dataclass

from target_agent_loop_support import FirstOfferedActionPolicy

from affordance_runtime.actions import (
    ActionBinding,
    ActionRisk,
)
from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.evaluation import (
    ActionEvaluation,
    ActionEvaluationStatus,
    CriterionEvaluationStatus,
)
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.evaluation.semantic_contracts import SemanticCriterionProposal
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldObservation,
)


def _world(identity: str, *, report: bool) -> WorldObservation:
    generator = SemanticTarget("generator:1", "button", "Generate report")
    targets = [generator]
    facts = []
    if report:
        targets.append(SemanticTarget("report:1", "content", "report"))
        facts.append(StateFact(f"fact:{identity}:report", "report:1", "content", "Clear conclusion", identity))
    binding = ActionBinding(
        f"binding:{identity}", identity, identity, f"revision:{identity}", f"fingerprint:{identity}",
        "generator:1", "generator:1", "static", "static", "activate", "click",
        "local_reversible", ("report_created",),
        {"type": "object", "properties": {}, "additionalProperties": False}, {"selector": "#private"},
        risk=ActionRisk.LOW,
    )
    source = SurfaceObservation(
        identity, "static", f"revision:{identity}", ObservationSourceProfile.dom(),
        tuple(targets), tuple(facts), (binding,),
    )
    return WorldObservation(
        identity, tuple(targets), tuple(facts), (binding,), {"static": CoverageState.COMPLETE},
        sources=(source,),
    )


def _task() -> TaskGoal:
    return TaskGoal(
        "dynamic-report", "Generate a clear report", allowed_effects=("report_created",),
        success_criteria=({
            "id": "quality", "adjudicator": "semantic", "kind": "semantic_rubric",
            "rubric": "The report is clear and contains a conclusion.",
            "evidence_scope_target_ids": ["report:1"],
        },), risk_profile=RiskProfile.LOW,
    )


@dataclass
class CatalogJudge:
    calls: int = 0

    async def evaluate(self, request):
        self.calls += 1
        evidence_ref = request.evidence_catalog.items[0].evidence_ref
        return (
            SemanticCriterionProposal(
                "quality", CriterionEvaluationStatus.SATISFIED, (evidence_ref,), "report meets rubric"
            ),
        )


class InconclusiveActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, result
        return ActionEvaluation(
            request.request_id, before.observation_id, after.observation_id,
            ActionEvaluationStatus.UNKNOWN, "no exact future state was required",
        )


def test_dynamic_semantic_target_creation_advances_from_incomplete_to_complete() -> None:
    judge = CatalogJudge()
    evaluator = ProductionTaskEvaluator(judge)
    environment = StaticEnvironment(
        [_world("before", report=False), _world("after", report=True)],
        [ActionResult("*", DispatchStatus.SENT, "static", True)],
    )

    result = asyncio.run(
        (AgentLoop(FirstOfferedActionPolicy(), InconclusiveActionEvaluator(), evaluator)).run(
            environment, _task()
        )
    )

    assert result.status == AgentLoopStatus.DONE
    assert result.observation_count == 2
    assert result.execution_count == 1
    assert judge.calls == 1
