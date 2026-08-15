"""Pinned MiniWoB benchmark policy for BrowserGym task-state facts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from affordance_runtime.benchmarks.external_smoke.case_environment import (
    ExternalVerifierReason,
    ExternalVerifierResult,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.surfaces.browsergym.task_state import (
    BROWSERGYM_TASK_STATE_EVIDENCE_KEY,
    BrowserGymTaskStateSnapshot,
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
    """Total source-aware classifier for the pinned official MiniWoB facts."""

    if not isinstance(source, VerifierFactSource):
        return _unavailable(VerifierFactSource.READ_ONLY_PROBE, ExternalVerifierReason.UNSUPPORTED_STATE)
    required = {
        VerifierFactSource.RESET: (reward, raw_reward, terminated, truncated, done, ready),
        VerifierFactSource.POST_ACTION: (
            reward, raw_reward, terminated, truncated, done, ready,
        ),
        VerifierFactSource.READ_ONLY_PROBE: (raw_reward, done, ready),
    }[source]
    if any(value is _MISSING for value in required):
        return _unavailable(source, ExternalVerifierReason.MISSING_FACTS)
    numeric = (raw_reward,) if source is VerifierFactSource.READ_ONLY_PROBE else (reward, raw_reward)
    if any(not _is_real(value) for value in numeric):
        return _unavailable(source, ExternalVerifierReason.INVALID_FACTS)
    numeric_values = tuple(cast(int | float, value) for value in numeric)
    if any(not _is_finite_real(value) for value in numeric_values):
        return _unavailable(source, ExternalVerifierReason.NON_FINITE_FACTS)
    booleans = (done, ready) if source is VerifierFactSource.READ_ONLY_PROBE else (
        terminated, truncated, done, ready,
    )
    if any(type(value) is not bool for value in booleans):
        return _unavailable(source, ExternalVerifierReason.INVALID_FACTS)

    reward_value = numeric_values[0] if source is not VerifierFactSource.READ_ONLY_PROBE else 0.0
    raw_value = numeric_values[-1]
    if source is VerifierFactSource.RESET:
        if (
            reward_value == 0
            and raw_value == 0
            and terminated is False
            and truncated is False
            and done is False
            and ready is True
        ):
            return VerifierAssessment(source, ExternalVerifierStatus.INCOMPLETE, ExternalVerifierReason.VERIFIED_RUNNING)
        return _unavailable(source, ExternalVerifierReason.UNSUPPORTED_STATE)
    if source is VerifierFactSource.READ_ONLY_PROBE:
        if ready is True and done is False and raw_value == 0:
            return VerifierAssessment(source, ExternalVerifierStatus.INCOMPLETE, ExternalVerifierReason.VERIFIED_RUNNING)
        if ready is True and done is True and raw_value > 0:
            return VerifierAssessment(source, ExternalVerifierStatus.SUCCESS, ExternalVerifierReason.VERIFIED_SUCCESS)
        if ready is True and done is True and raw_value <= 0:
            return VerifierAssessment(
                source,
                ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
                ExternalVerifierReason.VERIFIED_TERMINAL_TASK_FAILURE,
            )
        return _unavailable(source, ExternalVerifierReason.INCONSISTENT_FACTS)

    if truncated is True:
        return _unavailable(source, ExternalVerifierReason.UNSUPPORTED_STATE)
    if (
        reward_value > 0
        and raw_value > 0
        and terminated is True
        and done is True
        and ready is True
    ):
        return VerifierAssessment(source, ExternalVerifierStatus.SUCCESS, ExternalVerifierReason.VERIFIED_SUCCESS)
    if (
        reward_value == 0
        and raw_value <= 0
        and terminated is True
        and done is True
        and ready is True
    ):
        return VerifierAssessment(
            source,
            ExternalVerifierStatus.TERMINAL_TASK_FAILURE,
            ExternalVerifierReason.VERIFIED_TERMINAL_TASK_FAILURE,
        )
    if (
        reward_value == 0
        and raw_value == 0
        and terminated is False
        and done is False
        and ready is True
    ):
        return VerifierAssessment(source, ExternalVerifierStatus.INCOMPLETE, ExternalVerifierReason.VERIFIED_RUNNING)
    return _unavailable(source, ExternalVerifierReason.INCONSISTENT_FACTS)


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
    """Interpret raw surface state under the pinned MiniWoB benchmark contract."""

    source = VerifierFactSource(snapshot.source.value)
    assessment = classify_browsergym_verifier(
        source,
        reward=snapshot.value("reward", _MISSING),
        raw_reward=snapshot.value("raw_reward", _MISSING),
        terminated=snapshot.value("terminated", _MISSING),
        truncated=snapshot.value("truncated", _MISSING),
        done=snapshot.value("done", _MISSING),
        ready=snapshot.value("ready", _MISSING),
    )
    return _snapshot(
        snapshot.task_run_id,
        snapshot.observation_id,
        snapshot.source_observation_id,
        assessment,
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


def _is_real(value: object) -> bool:
    return type(value) in {int, float}


def _is_finite_real(value: int | float) -> bool:
    return isinstance(value, int) or math.isfinite(value)


def _unavailable(
    source: VerifierFactSource,
    reason: ExternalVerifierReason,
) -> VerifierAssessment:
    return VerifierAssessment(source, ExternalVerifierStatus.UNAVAILABLE, reason)
