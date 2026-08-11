import asyncio

from affordance_runtime.agent import Abort, AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.evaluation import (
    ActionEvaluation,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.task import LoopBudget, TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    CoverageState,
    EntityInventoryIssueCode,
    EntityInventoryStatus,
    EntityInventorySummary,
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldObservation,
)


class _IncompleteEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "ongoing",
        )


class _UnusedActionEvaluator:
    async def evaluate(self, *args, **kwargs):
        del args, kwargs
        return ActionEvaluation("unused", "before", "after", "unknown", "unused")


class _AbortPolicy:
    def __init__(self, category: str) -> None:
        self.category = category
        self.contexts = []

    async def decide(self, context):
        self.contexts.append(context)
        return Abort(context.context_id, "cannot continue", self.category)


def _many_target_world(count: int = 65) -> WorldObservation:
    return WorldObservation(
        "world:many",
        tuple(SemanticTarget(f"target:{index}", "StaticText", f"Item {index}") for index in range(count)),
        (),
        (),
        {"dom": CoverageState.COMPLETE},
    )


def _run(world: WorldObservation, policy: _AbortPolicy):
    async def scenario():
        task = TaskGoal(
            "task:coverage",
            "Find whether the requested item exists",
            loop_budget=LoopBudget(max_turns=3, max_observations=3),
        )
        environment = StaticEnvironment([world])
        result = await AgentEpisodeRunner(AgentLoop(policy, _UnusedActionEvaluator(), _IncompleteEvaluator())).run(
            environment, task
        )
        return result, environment

    return asyncio.run(scenario())


def test_no_progress_claim_advances_frozen_pages_before_it_is_admitted() -> None:
    policy = _AbortPolicy("no_progress")

    result, environment = _run(_many_target_world(), policy)

    assert result.status is AgentLoopStatus.FAILED
    assert result.reason_code == "abort_no_progress"
    assert len(policy.contexts) == 2
    assert policy.contexts[0].world.traversal is not None
    assert policy.contexts[1].world.traversal is None
    assert tuple(item.label for item in policy.contexts[1].world.targets.items) == ("Item 64",)
    assert result.observation_count == 1
    assert environment.capture_calls == 0


def test_non_negative_policy_abort_does_not_force_inventory_traversal() -> None:
    policy = _AbortPolicy("policy")

    result, environment = _run(_many_target_world(), policy)

    assert result.status is AgentLoopStatus.FAILED
    assert len(policy.contexts) == 1
    assert result.observation_count == 1
    assert environment.capture_calls == 0


def test_partial_inventory_yields_typed_unknown_instead_of_negative_claim() -> None:
    target = SemanticTarget("target:1", "StaticText", "Only retained item")
    source = SurfaceObservation(
        "source:partial",
        "dom",
        "revision:1",
        ObservationSourceProfile.dom(),
        targets=(target,),
        coverage=CoverageState.TRUNCATED,
        entity_inventory=EntityInventorySummary(
            EntityInventoryStatus.PARTIAL,
            entity_count=1,
            entity_total_count=2,
            issue_codes=(EntityInventoryIssueCode.ENTITY_CAPACITY_EXCEEDED,),
        ),
    )
    world = WorldObservation(
        "world:partial",
        (target,),
        (),
        (),
        {"dom": CoverageState.TRUNCATED},
        sources=(source,),
    )
    policy = _AbortPolicy("unsupported")

    result, _environment = _run(world, policy)

    assert result.status is AgentLoopStatus.BLOCKED
    assert result.reason_code == "negative_claim_source_coverage_unavailable"
    assert len(policy.contexts) == 3
