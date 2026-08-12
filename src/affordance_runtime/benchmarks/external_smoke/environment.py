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
    TERMINAL_TASK_FAILURE = "terminal_task_failure"
    UNAVAILABLE = "unavailable"


class VerifierFactSource(StrEnum):
    RESET = "reset"
    POST_ACTION = "post_action"
    READ_ONLY_PROBE = "read_only_probe"


class ExternalVerifierReason(StrEnum):
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_RUNNING = "verified_running"
    VERIFIED_TERMINAL_TASK_FAILURE = "verified_terminal_task_failure"
    MISSING_FACTS = "missing_facts"
    INVALID_FACTS = "invalid_facts"
    NON_FINITE_FACTS = "non_finite_facts"
    INCONSISTENT_FACTS = "inconsistent_facts"
    SOURCE_INSUFFICIENT = "source_insufficient"
    UNSUPPORTED_STATE = "unsupported_state"


@dataclass(frozen=True)
class ExternalVerifierResult:
    source: VerifierFactSource
    status: ExternalVerifierStatus
    reason: ExternalVerifierReason
    observation_id: str
    source_observation_id: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        from affordance_runtime.evaluation.evidence import validate_evidence_refs

        if not isinstance(self.source, VerifierFactSource):
            raise TypeError("external verifier source must be typed")
        if not isinstance(self.status, ExternalVerifierStatus):
            raise TypeError("external verifier status must be typed")
        if not isinstance(self.reason, ExternalVerifierReason):
            raise TypeError("external verifier reason must be typed")
        if (
            not isinstance(self.observation_id, str)
            or not isinstance(self.source_observation_id, str)
            or not self.observation_id.strip()
            or not self.source_observation_id.strip()
        ):
            raise ValueError("external verifier result requires observation lineage")
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(tuple(self.evidence_refs), allow_empty=True),
        )
        expected_reason = {
            ExternalVerifierStatus.SUCCESS: ExternalVerifierReason.VERIFIED_SUCCESS,
            ExternalVerifierStatus.INCOMPLETE: ExternalVerifierReason.VERIFIED_RUNNING,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: (
                ExternalVerifierReason.VERIFIED_TERMINAL_TASK_FAILURE
            ),
        }.get(self.status)
        if expected_reason is not None and self.reason is not expected_reason:
            raise ValueError("external verifier status and reason conflict")
        terminal = self.status in {
            ExternalVerifierStatus.SUCCESS,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
        }
        if terminal != bool(self.evidence_refs):
            raise ValueError("external verifier terminal proof is inconsistent")


class ExternalVerifierPort(Protocol):
    def current_result(self, benchmark_task_id: str) -> ExternalVerifierResult: ...


@dataclass(frozen=True)
class ExternalEnvironmentTaskEvaluator:
    benchmark_task_id: str
    verifier: ExternalVerifierPort

    async def evaluate(self, task, observation) -> TaskEvaluation:
        verifier_result = self.verifier.current_result(self.benchmark_task_id)
        current_source_ids = {item.observation_id for item in observation.sources}
        verifier_lineage = {
            verifier_result.observation_id,
            verifier_result.source_observation_id,
        }
        if not (
            verifier_lineage == {observation.observation_id}
            or len(verifier_lineage) == 1
            and verifier_result.source_observation_id in current_source_ids
        ):
            verifier_result = ExternalVerifierResult(
                verifier_result.source,
                ExternalVerifierStatus.UNAVAILABLE,
                ExternalVerifierReason.SOURCE_INSUFFICIENT,
                observation.observation_id,
                observation.observation_id,
            )
        mapped = {
            ExternalVerifierStatus.SUCCESS: TaskEvaluationStatus.COMPLETE,
            ExternalVerifierStatus.INCOMPLETE: TaskEvaluationStatus.INCOMPLETE,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: TaskEvaluationStatus.BLOCKED,
            ExternalVerifierStatus.UNAVAILABLE: TaskEvaluationStatus.UNKNOWN,
        }[verifier_result.status]
        from affordance_runtime.evaluation import TaskOutcomeFact, TaskOutcomeKind

        outcome_kind = {
            ExternalVerifierStatus.SUCCESS: TaskOutcomeKind.TERMINAL_SUCCESS,
            ExternalVerifierStatus.INCOMPLETE: TaskOutcomeKind.RUNNING_INCOMPLETE,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: TaskOutcomeKind.TERMINAL_FAILURE,
            ExternalVerifierStatus.UNAVAILABLE: TaskOutcomeKind.VERIFIER_UNAVAILABLE,
        }[verifier_result.status]
        refs = verifier_result.evidence_refs
        return TaskEvaluation(
            task.task_id, observation.observation_id, mapped,
            f"environment-native verifier: {verifier_result.reason.value}",
            completion_evidence_refs=(
                refs if outcome_kind is TaskOutcomeKind.TERMINAL_SUCCESS else ()
            ),
            outcome=TaskOutcomeFact(outcome_kind, verifier_result.reason.value, refs),
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
