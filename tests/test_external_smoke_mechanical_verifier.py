import asyncio

from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalEnvironmentTaskEvaluator,
    ExternalVerifierReason,
    ExternalVerifierResult,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.evaluation import TaskEvaluationStatus, TaskOutcomeKind
from affordance_runtime.task import TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationSourceProfile,
    SurfaceObservation,
    WorldObservation,
)


class Verifier:
    def __init__(self, status: ExternalVerifierStatus) -> None:
        self.status = status

    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult:
        assert benchmark_task_id == "browsergym/miniwob.click-button"
        terminal = self.status in {
            ExternalVerifierStatus.SUCCESS,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
        }
        ref = ("fact:external-verifier-status",) if terminal else ()
        reason = {
            ExternalVerifierStatus.SUCCESS: ExternalVerifierReason.VERIFIED_SUCCESS,
            ExternalVerifierStatus.INCOMPLETE: ExternalVerifierReason.VERIFIED_RUNNING,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: (
                ExternalVerifierReason.VERIFIED_TERMINAL_TASK_FAILURE
            ),
            ExternalVerifierStatus.UNAVAILABLE: ExternalVerifierReason.MISSING_FACTS,
        }[self.status]
        return ExternalVerifierResult(
            VerifierFactSource.POST_ACTION,
            self.status,
            reason,
            "current",
            "current",
            ref,
        )


def test_external_task_evaluator_uses_only_environment_native_mechanical_status() -> None:
    task = TaskGoal("external", "Complete the local benchmark instruction")
    observation = WorldObservation("current", (), (), (), {"external": CoverageState.COMPLETE})
    expected = {
        ExternalVerifierStatus.SUCCESS: TaskEvaluationStatus.COMPLETE,
        ExternalVerifierStatus.INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
        ExternalVerifierStatus.TERMINAL_TASK_FAILURE: TaskEvaluationStatus.BLOCKED,
        ExternalVerifierStatus.UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
    }
    for verifier_status, task_status in expected.items():
        evaluator = ExternalEnvironmentTaskEvaluator(
            "browsergym/miniwob.click-button", Verifier(verifier_status),
        )
        result = asyncio.run(evaluator.evaluate(task, observation))
        assert result.status == task_status
        assert result.outcome is not None
        assert result.outcome.kind is {
            ExternalVerifierStatus.SUCCESS: TaskOutcomeKind.TERMINAL_SUCCESS,
            ExternalVerifierStatus.INCOMPLETE: TaskOutcomeKind.RUNNING_INCOMPLETE,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: TaskOutcomeKind.TERMINAL_FAILURE,
            ExternalVerifierStatus.UNAVAILABLE: TaskOutcomeKind.VERIFIER_UNAVAILABLE,
        }[verifier_status]


def test_external_task_evaluator_fails_closed_on_latest_pointer_lineage_mismatch() -> None:
    class StaleVerifier:
        def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult:
            del benchmark_task_id
            return ExternalVerifierResult(
                VerifierFactSource.POST_ACTION,
                ExternalVerifierStatus.SUCCESS,
                ExternalVerifierReason.VERIFIED_SUCCESS,
                "old",
                "old",
                ("fact:old-status",),
            )

    task = TaskGoal("external", "Complete the local benchmark instruction")
    observation = WorldObservation(
        "current", (), (), (), {"external": CoverageState.COMPLETE},
    )
    result = asyncio.run(ExternalEnvironmentTaskEvaluator(
        "browsergym/miniwob.click-button", StaleVerifier(),
    ).evaluate(task, observation))
    assert result.status is TaskEvaluationStatus.UNKNOWN
    assert result.outcome is not None
    assert result.outcome.kind is TaskOutcomeKind.VERIFIER_UNAVAILABLE
    assert result.outcome.code == "source_insufficient"


def test_external_task_evaluator_accepts_current_structural_lineage_in_fused_world() -> None:
    structural = SurfaceObservation(
        "current-source",
        "browsergym",
        "revision",
        ObservationSourceProfile.dom(),
    )
    visual = SurfaceObservation(
        "current-visual",
        "browsergym_visual",
        "revision",
        ObservationSourceProfile.visual(),
    )

    class FusedVerifier:
        def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult:
            del benchmark_task_id
            return ExternalVerifierResult(
                VerifierFactSource.POST_ACTION,
                ExternalVerifierStatus.SUCCESS,
                ExternalVerifierReason.VERIFIED_SUCCESS,
                "current-source",
                "current-source",
                ("fact:status",),
            )

    observation = WorldObservation(
        "world:fused",
        (),
        (),
        (),
        {"browsergym": CoverageState.COMPLETE, "browsergym_visual": CoverageState.TRUNCATED},
        sources=(structural, visual),
    )
    result = asyncio.run(ExternalEnvironmentTaskEvaluator(
        "browsergym/miniwob.click-button",
        FusedVerifier(),
    ).evaluate(TaskGoal("external", "Complete task"), observation))

    assert result.status is TaskEvaluationStatus.COMPLETE
