"""Runtime-private projection of BrowserGym/MiniWoB mechanical status."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalVerifierResult,
    ExternalVerifierStatus,
)
from affordance_runtime.world.evidence_refs import canonical_artifact_ref

MECHANICAL_EVIDENCE_KEY = "mechanical-verifier"


@dataclass(frozen=True)
class BrowserGymVerifierSnapshot:
    task_run_id: str
    observation_id: str
    source_observation_id: str
    status: ExternalVerifierStatus
    evidence_ref: str


def verifier_snapshot(
    *,
    task_run_id: str,
    observation_id: str,
    source_observation_id: str,
    reward: object,
    terminated: object,
    truncated: object,
    task_info: object,
) -> BrowserGymVerifierSnapshot:
    status = _status(reward, terminated, truncated, task_info)
    evidence = (
        canonical_artifact_ref(source_observation_id, MECHANICAL_EVIDENCE_KEY)
        if status is ExternalVerifierStatus.SUCCESS
        else ""
    )
    return BrowserGymVerifierSnapshot(task_run_id, observation_id, source_observation_id, status, evidence)


def as_external_result(snapshot: BrowserGymVerifierSnapshot) -> ExternalVerifierResult:
    return ExternalVerifierResult(snapshot.status, snapshot.evidence_ref)


def _status(reward: object, terminated: object, truncated: object, task_info: object) -> ExternalVerifierStatus:
    if not isinstance(task_info, dict) or truncated is not False:
        return ExternalVerifierStatus.UNAVAILABLE
    done = task_info.get("DONE_GLOBAL")
    raw_reward = task_info.get("RAW_REWARD_GLOBAL")
    if not isinstance(reward, int | float) or isinstance(reward, bool):
        return ExternalVerifierStatus.UNAVAILABLE
    if reward > 0 and terminated is True and done is True and isinstance(raw_reward, int | float) and raw_reward > 0:
        return ExternalVerifierStatus.SUCCESS
    if reward == 0 and terminated is False and done is False and isinstance(raw_reward, int | float):
        return ExternalVerifierStatus.INCOMPLETE
    return ExternalVerifierStatus.UNAVAILABLE
