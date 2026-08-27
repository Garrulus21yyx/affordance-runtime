"""Pinned MiniWoB benchmark policy for BrowserGym task-state facts."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.benchmarks.external_smoke.case_environment import (
    ExternalVerifierReason,
    ExternalVerifierResult,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.surfaces.browsergym.task_evaluator import (
    BrowserGymTaskAssessment,
    BrowserGymTaskStatus,
)
from affordance_runtime.surfaces.browsergym.task_evaluator import (
    assess_browsergym_task_state as assess_native_browsergym_task_state,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
    BrowserGymTaskStateSnapshot,
    BrowserGymTaskStateSource,
)
from affordance_runtime.world.evidence_refs import canonical_artifact_ref

_MISSING = object()


@dataclass(frozen=True)
class VerifierAssessment:
    source: VerifierFactSource
    status: ExternalVerifierStatus
    reason: ExternalVerifierReason


@dataclass(frozen=True)
class BrowserGymVerifierSnapshot:
    task_run_id: str
    observation_id: str
    source_observation_id: str
    source: VerifierFactSource
    status: ExternalVerifierStatus
    reason: ExternalVerifierReason
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.task_run_id.strip(), self.observation_id.strip(), self.source_observation_id.strip())):
            raise ValueError("BrowserGym verifier snapshot requires complete lineage")
        if not isinstance(self.source, VerifierFactSource):
            raise TypeError("BrowserGym verifier snapshot source must be typed")
        if not isinstance(self.status, ExternalVerifierStatus):
            raise TypeError("BrowserGym verifier snapshot status must be typed")
        if not isinstance(self.reason, ExternalVerifierReason):
            raise TypeError("BrowserGym verifier snapshot reason must be typed")
        expected_reason = {
            ExternalVerifierStatus.SUCCESS: ExternalVerifierReason.VERIFIED_SUCCESS,
            ExternalVerifierStatus.INCOMPLETE: ExternalVerifierReason.VERIFIED_RUNNING,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE: (
                ExternalVerifierReason.VERIFIED_TERMINAL_TASK_FAILURE
            ),
        }.get(self.status)
        if expected_reason is not None and self.reason is not expected_reason:
            raise ValueError("BrowserGym verifier snapshot status and reason conflict")
        terminal = self.status in {
            ExternalVerifierStatus.SUCCESS,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
        }
        if terminal != bool(self.evidence_refs):
            raise ValueError("BrowserGym terminal verifier snapshot proof is inconsistent")


def classify_browsergym_verifier(
    source: object,
    *,
    reward: object = _MISSING,
    raw_reward: object = _MISSING,
    terminated: object = _MISSING,
    truncated: object = _MISSING,
    done: object = _MISSING,
    ready: object = _MISSING,
) -> VerifierAssessment:
    """Compatibility projection over the surface-owned native-state classifier."""

    if not isinstance(source, VerifierFactSource):
        return _unavailable(VerifierFactSource.READ_ONLY_PROBE, ExternalVerifierReason.UNSUPPORTED_STATE)
    values = {
        name: value
        for name, value in (
            ("reward", reward),
            ("raw_reward", raw_reward),
            ("terminated", terminated),
            ("truncated", truncated),
            ("done", done),
            ("ready", ready),
        )
        if value is not _MISSING
    }
    native = assess_native_browsergym_task_state(
        BrowserGymTaskStateSnapshot(
            "benchmark-verifier-classification",
            "benchmark-verifier-classification",
            "benchmark-verifier-classification",
            BrowserGymTaskStateSource(source.value),
            values,
            frozenset(values),
        )
    )
    return _external_assessment(native)


def verifier_snapshot(
    *,
    task_run_id: str,
    observation_id: str,
    source_observation_id: str,
    source: VerifierFactSource,
    reward: object,
    terminated: object,
    truncated: object,
    task_info: object,
) -> BrowserGymVerifierSnapshot:
    values = task_info if type(task_info) is dict else {}
    assessment = classify_browsergym_verifier(
        source,
        reward=reward,
        raw_reward=values.get("RAW_REWARD_GLOBAL", _MISSING),
        terminated=terminated,
        truncated=truncated,
        done=values.get("DONE_GLOBAL", _MISSING),
        ready=values.get("TASK_READY", _MISSING),
    )
    return _snapshot(task_run_id, observation_id, source_observation_id, assessment)


def verifier_snapshot_from_current_probe(
    *,
    task_run_id: str,
    observation_id: str,
    source_observation_id: str,
    probe: object,
) -> BrowserGymVerifierSnapshot:
    values = probe if type(probe) is dict else {}
    assessment = classify_browsergym_verifier(
        VerifierFactSource.READ_ONLY_PROBE,
        raw_reward=values.get("raw_reward", _MISSING),
        done=values.get("done", _MISSING),
        ready=values.get("ready", _MISSING),
    )
    return _snapshot(task_run_id, observation_id, source_observation_id, assessment)


def as_external_result(snapshot: BrowserGymVerifierSnapshot) -> ExternalVerifierResult:
    return ExternalVerifierResult(
        snapshot.source,
        snapshot.status,
        snapshot.reason,
        snapshot.observation_id,
        snapshot.source_observation_id,
        snapshot.evidence_refs,
    )


def assess_browsergym_task_state(
    snapshot: BrowserGymTaskStateSnapshot,
) -> BrowserGymVerifierSnapshot:
    """Project the surface-owned native assessment into benchmark compatibility types."""

    native = assess_native_browsergym_task_state(snapshot)
    assessment = _external_assessment(native)
    return BrowserGymVerifierSnapshot(
        native.task_run_id,
        native.observation_id,
        native.source_observation_id,
        assessment.source,
        assessment.status,
        assessment.reason,
        native.evidence_refs,
    )


def _snapshot(
    task_run_id: str,
    observation_id: str,
    source_observation_id: str,
    assessment: VerifierAssessment,
) -> BrowserGymVerifierSnapshot:
    evidence_refs: tuple[str, ...] = ()
    if assessment.status in {
        ExternalVerifierStatus.SUCCESS,
        ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
    }:
        evidence_refs = (
            canonical_artifact_ref(
                source_observation_id,
                BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
            ),
        )
    return BrowserGymVerifierSnapshot(
        task_run_id,
        observation_id,
        source_observation_id,
        assessment.source,
        assessment.status,
        assessment.reason,
        evidence_refs,
    )


def _external_assessment(native: BrowserGymTaskAssessment) -> VerifierAssessment:
    status = {
        BrowserGymTaskStatus.SUCCESS: ExternalVerifierStatus.SUCCESS,
        BrowserGymTaskStatus.INCOMPLETE: ExternalVerifierStatus.INCOMPLETE,
        BrowserGymTaskStatus.TERMINAL_FAILURE: ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
        BrowserGymTaskStatus.UNAVAILABLE: ExternalVerifierStatus.UNAVAILABLE,
    }[native.status]
    return VerifierAssessment(
        VerifierFactSource(native.source.value),
        status,
        ExternalVerifierReason(native.reason.value),
    )


def _unavailable(
    source: VerifierFactSource,
    reason: ExternalVerifierReason,
) -> VerifierAssessment:
    return VerifierAssessment(source, ExternalVerifierStatus.UNAVAILABLE, reason)
