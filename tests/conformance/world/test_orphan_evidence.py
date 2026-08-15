import asyncio

from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus, TaskEvaluationStatus
from affordance_runtime.evaluation.action_applicability import apply_action_evidence_profile
from affordance_runtime.evaluation.action_verification import derive_action_verification_obligations
from affordance_runtime.evaluation.composition import ProductionTaskEvaluator
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionIntent
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import StateFact, WorldObservation


class _Request:
    intent = ActionIntent("activate", "target:1")


def test_orphan_fact_cannot_resolve_task_or_action_claim() -> None:
    task = TaskGoal(
        "orphan", "Enable", success_criteria=(
            {"id": "enabled", "subject_id": "target:1", "predicate": "enabled", "value": True},
        ),
    )
    before = WorldObservation(
        "before", (), (StateFact("fact:before", "target:1", "enabled", False, "orphan"),),
        (), (),
    )
    after = WorldObservation(
        "after", (), (StateFact("fact:after", "target:1", "enabled", True, "orphan"),),
        (), (),
    )
    proposal = ActionEvaluation(
        "request", "before", "after", ActionEvaluationStatus.EFFECT_CONFIRMED,
        "changed", ("fact:after",),
    )
    result = apply_action_evidence_profile(
        proposal, task, _Request(), before, after, WorldEvidenceIndex.from_observation(after),
        derive_action_verification_obligations(task, _Request(), before),
    )
    assert result.status == ActionEvaluationStatus.UNKNOWN
    assert asyncio.run(ProductionTaskEvaluator().evaluate(task, after)).status == TaskEvaluationStatus.UNKNOWN
