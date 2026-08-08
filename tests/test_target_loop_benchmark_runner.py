import asyncio
from dataclasses import dataclass

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCase, BenchmarkComposition
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus, TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.task import TaskGoal
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import CoverageState, WorldObservation


@dataclass
class NeverPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        raise AssertionError("complete task must not call policy")


class ActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        return ActionEvaluation(request.request_id, before.observation_id, after.observation_id, ActionEvaluationStatus.UNKNOWN, "unused")


class CompleteEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(task.task_id, observation.observation_id, TaskEvaluationStatus.BLOCKED, "fixture terminal")


def test_runner_is_sequential_isolated_and_always_cleans_up() -> None:
    events = []

    class Environment(StaticEnvironment):
        async def reset(self, task):
            events.append(f"start:{task.task_id}")
            await super().reset(task)

        async def close(self):
            events.append(f"close:{self.task.task_id}")

    def case(identity):
        return BenchmarkCase(
            identity, "suite", identity,
            lambda: TaskGoal(identity, "Already complete"),
            lambda _metrics: Environment([WorldObservation(identity, (), (), (), {"static": CoverageState.COMPLETE})]),
            lambda _metrics: BenchmarkComposition(NeverPolicy(), ActionEvaluator(), CompleteEvaluator()),
            (AgentLoopStatus.BLOCKED,), 2.0, 7, ("observations",), "internal",
        )

    from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest

    result = asyncio.run(run_suite(BenchmarkManifest(
        "target-loop-manifest.v1", "suite", "deterministic", 7, (case("a"), case("b")),
    )))
    assert result.acceptance.accepted
    assert events == ["start:a", "close:a", "start:b", "close:b"]
    assert [item.case_id for item in result.cases] == ["a", "b"]
