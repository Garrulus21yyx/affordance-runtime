import asyncio

from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalEnvironmentTaskEvaluator,
    ExternalVerifierResult,
    ExternalVerifierStatus,
)
from affordance_runtime.evaluation import TaskEvaluationStatus
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import CoverageState, WorldObservation


class Verifier:
    def __init__(self, status: ExternalVerifierStatus) -> None:
        self.status = status

    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult:
        assert benchmark_task_id == "browsergym/miniwob.click-button"
        ref = "fact:external-verifier-success" if self.status == ExternalVerifierStatus.SUCCESS else ""
        return ExternalVerifierResult(self.status, ref)


def test_external_task_evaluator_uses_only_environment_native_mechanical_status() -> None:
    task = TaskGoal("external", "Complete the local benchmark instruction")
    observation = WorldObservation("current", (), (), (), {"external": CoverageState.COMPLETE})
    expected = {
        ExternalVerifierStatus.SUCCESS: TaskEvaluationStatus.COMPLETE,
        ExternalVerifierStatus.INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
        ExternalVerifierStatus.UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
    }
    for verifier_status, task_status in expected.items():
        evaluator = ExternalEnvironmentTaskEvaluator(
            "browsergym/miniwob.click-button", Verifier(verifier_status),
        )
        result = asyncio.run(evaluator.evaluate(task, observation))
        assert result.status == task_status
