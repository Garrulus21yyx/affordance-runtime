"""Optional BrowserGym dependency and mechanical verifier boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from typing import Protocol

from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus


@dataclass(frozen=True)
class ExternalDependencyStatus:
    available: bool
    package_name: str
    package_version: str
    target_loop_adapter_ready: bool


class ExternalVerifierStatus(StrEnum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ExternalVerifierResult:
    status: ExternalVerifierStatus
    evidence_ref: str = ""


class ExternalVerifierPort(Protocol):
    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult: ...


@dataclass(frozen=True)
class ExternalEnvironmentTaskEvaluator:
    benchmark_task_id: str
    verifier: ExternalVerifierPort

    async def evaluate(self, task, observation) -> TaskEvaluation:
        verifier_result = self.verifier.current_result(self.benchmark_task_id)
        mapped = {
            ExternalVerifierStatus.SUCCESS: TaskEvaluationStatus.COMPLETE,
            ExternalVerifierStatus.INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
            ExternalVerifierStatus.UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
        }[verifier_result.status]
        refs = (verifier_result.evidence_ref,) if verifier_result.evidence_ref else ()
        return TaskEvaluation(
            task.task_id, observation.observation_id, mapped,
            "environment-native verifier", completion_evidence_refs=refs,
        )


def external_dependency_status() -> ExternalDependencyStatus:
    try:
        installed = version("browsergym-miniwob")
    except PackageNotFoundError:
        return ExternalDependencyStatus(False, "browsergym-miniwob", "", False)
    # The package and registry are pinned, but a target AgentLoop WorldEnvironment wrapper is deferred.
    return ExternalDependencyStatus(True, "browsergym-miniwob", installed, False)
