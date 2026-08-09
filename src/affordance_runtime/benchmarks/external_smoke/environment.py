"""Optional BrowserGym dependency and mechanical verifier boundary."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
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


def external_dependency_status(adapter_attestation: Path | None = None) -> ExternalDependencyStatus:
    try:
        installed = version("browsergym-miniwob")
    except PackageNotFoundError:
        return ExternalDependencyStatus(False, "browsergym-miniwob", "", False)
    path = adapter_attestation
    if path is None and os.environ.get("BROWSERGYM_ADAPTER_CONFORMANCE_ATTESTATION"):
        path = Path(os.environ["BROWSERGYM_ADAPTER_CONFORMANCE_ATTESTATION"])
    ready = _adapter_attestation_ready(path, installed) if path is not None else False
    return ExternalDependencyStatus(True, "browsergym-miniwob", installed, ready)


def _adapter_attestation_ready(path: Path, installed: str) -> bool:
    from affordance_runtime.benchmarks.external_smoke.browsergym_inventory import REVIEWED_TASK_IDS
    from affordance_runtime.benchmarks.external_smoke.manifest import (
        EXTERNAL_SMOKE_MANIFEST,
        SOURCE_COMMIT,
        external_manifest_digest,
    )

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(value, dict)
        and value.get("accepted") is True
        and value.get("git_dirty") is False
        and value.get("package_version") == installed == EXTERNAL_SMOKE_MANIFEST.package_version
        and value.get("source_commit") == SOURCE_COMMIT
        and value.get("manifest_digest") == external_manifest_digest(EXTERNAL_SMOKE_MANIFEST)
        and tuple(value.get("task_ids", ())) == REVIEWED_TASK_IDS
        and value.get("target_loop_adapter_ready") is True
    )
