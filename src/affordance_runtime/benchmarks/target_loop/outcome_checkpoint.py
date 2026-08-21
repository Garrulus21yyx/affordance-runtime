"""Durable, bounded checkpoint for an official native task evaluation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from affordance_runtime.agent.run_state import RunStatus
from affordance_runtime.evaluation.contracts import (
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeKind,
)

if TYPE_CHECKING:
    from affordance_runtime.benchmarks.target_loop.result_store import RunResultStore

OFFICIAL_OUTCOME_CHECKPOINT_SCHEMA = "benchmark-official-outcome/v1"


class PersistenceStatus(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    COMMITTED = "committed"
    FAILED = "failed"


@dataclass(frozen=True)
class OfficialOutcomeCheckpoint:
    """Runner-owned durable projection of evaluator terminal truth."""

    schema_version: str
    checkpoint_id: str
    case_id: str
    task_id: str
    observation_id: str
    evaluation_status: TaskEvaluationStatus
    run_status: RunStatus
    outcome_kind: TaskOutcomeKind | None
    outcome_code: str
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_evaluation(
        cls,
        case_id: str,
        evaluation: TaskEvaluation,
    ) -> OfficialOutcomeCheckpoint:
        outcome = evaluation.outcome
        refs = _ordered_unique(
            (
                *evaluation.completion_evidence_refs,
                *(outcome.evidence_refs if outcome is not None else ()),
                *(ref for criterion in evaluation.criteria for ref in criterion.evidence_refs),
                *(ref for output in evaluation.outputs for ref in output.evidence_refs),
            )
        )
        values = {
            "schema_version": OFFICIAL_OUTCOME_CHECKPOINT_SCHEMA,
            "case_id": case_id,
            "task_id": evaluation.task_id,
            "observation_id": evaluation.observation_id,
            "evaluation_status": evaluation.status.value,
            "run_status": _run_status(evaluation.status).value,
            "outcome_kind": outcome.kind.value if outcome is not None else "",
            "outcome_code": outcome.code if outcome is not None else "",
            "evidence_refs": refs,
        }
        digest = hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            schema_version=OFFICIAL_OUTCOME_CHECKPOINT_SCHEMA,
            checkpoint_id=f"checkpoint:{digest}",
            case_id=case_id,
            task_id=evaluation.task_id,
            observation_id=evaluation.observation_id,
            evaluation_status=evaluation.status,
            run_status=_run_status(evaluation.status),
            outcome_kind=outcome.kind if outcome is not None else None,
            outcome_code=outcome.code if outcome is not None else "",
            evidence_refs=refs,
        )


@dataclass
class OfficialOutcomeCheckpointRecorder:
    """Runner durability owner invoked at the official evaluator boundary."""

    case_id: str
    store: RunResultStore | None
    trace_recorder: object
    status_changed: Callable[[str], None] | None = None
    checkpoint: OfficialOutcomeCheckpoint | None = None
    persistence_status: PersistenceStatus = PersistenceStatus.NOT_ATTEMPTED
    persistence_error: str = ""

    @property
    def durable_checkpoint(self) -> OfficialOutcomeCheckpoint | None:
        return (
            self.checkpoint
            if self.persistence_status is PersistenceStatus.COMMITTED
            else None
        )

    def native_evaluator_returned(self, evaluation: TaskEvaluation) -> None:
        if self.status_changed is not None:
            self.status_changed("finalizing")
        self.trace_recorder.benchmark_lifecycle_phase(
            "finalizing",
            primary_result_available=False,
            primary_snapshot_available=False,
        )
        self.checkpoint = OfficialOutcomeCheckpoint.from_evaluation(
            self.case_id,
            evaluation,
        )
        self.trace_recorder.native_evaluator_returned(
            evaluation,
            checkpoint_id=self.checkpoint.checkpoint_id,
        )
        if self.store is None and self.persistence_error:
            self.persistence_status = PersistenceStatus.FAILED
        elif self.store is not None:
            try:
                self.store.commit_official_outcome(self.checkpoint)
            except RuntimeError as exc:
                self.persistence_status = PersistenceStatus.FAILED
                self.persistence_error = type(exc).__name__
            else:
                self.persistence_status = PersistenceStatus.COMMITTED
                if self.status_changed is not None:
                    self.status_changed("primary_persisted")
                self.trace_recorder.benchmark_lifecycle_phase(
                    "primary_persisted",
                    primary_result_available=False,
                    primary_snapshot_available=False,
                )
        self.trace_recorder.official_outcome_persistence(
            checkpoint_id=self.checkpoint.checkpoint_id,
            persistence_status=self.persistence_status.value,
            persistence_error=self.persistence_error,
        )


class OfficialOutcomePersistenceError(RuntimeError):
    """Typed harness failure when official outcome durability is unavailable."""


def _run_status(status: TaskEvaluationStatus) -> RunStatus:
    return {
        TaskEvaluationStatus.COMPLETE: RunStatus.DONE,
        TaskEvaluationStatus.BLOCKED: RunStatus.BLOCKED,
        TaskEvaluationStatus.UNKNOWN: RunStatus.FAILED,
        TaskEvaluationStatus.INCOMPLETE: RunStatus.FAILED,
    }[status]


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
