"""Atomic, non-resumable progress for two-stage logical decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from ..matrix_progress import write_json_report
from .contracts import PacingConfiguration, TwoStageDecisionIdentity


class TwoStageProgressStage(StrEnum):
    ROUTING_STARTED = "routing_started"
    ROUTING_COMPLETED = "routing_completed"
    PAYLOAD_STARTED = "payload_started"
    PAYLOAD_COMPLETED = "payload_completed"
    RUNTIME_COMPLETED = "runtime_completed"


@dataclass(frozen=True)
class TwoStageProgressAttempt:
    identity: TwoStageDecisionIdentity
    stage: TwoStageProgressStage
    failure_category: str = ""
    routing_attempts: int = 0
    payload_attempts: int = 0
    provider_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    routing_schema_digest: str = ""
    payload_schema_digest: str = ""


def write_two_stage_progress(
    path: Path,
    *,
    run_id: str,
    pacing: PacingConfiguration,
    attempts: tuple[TwoStageProgressAttempt, ...],
    planned_attempt_count: int,
    complete: bool,
) -> None:
    write_json_report(path, {
        "schema_version": "two-stage-progress.v1",
        "run_id": run_id,
        "pacing": asdict(pacing),
        "planned_attempt_count": planned_attempt_count,
        "completed_attempt_count": sum(
            item.stage is TwoStageProgressStage.RUNTIME_COMPLETED for item in attempts
        ),
        "complete": complete,
        "attempts": [asdict(item) for item in attempts],
    })
