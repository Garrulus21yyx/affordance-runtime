"""Durable Runtime checkpoint values written only after a closed pause boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from affordance_runtime.agent.run_control import (
    RunControlKind,
    RunControlOutcome,
    RunControlOutcomeKind,
)
from affordance_runtime.agent.run_state import RunState, RunStatus
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.task.contracts import TaskGoal

RUNTIME_CHECKPOINT_SCHEMA_VERSION = "affordance-runtime.checkpoint.v1"
_MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024


class RuntimeCheckpointError(RuntimeError):
    """Typed private persistence/validation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RuntimeCheckpoint:
    """One canonical, bounded recovery value with no complete World payload."""

    session_id: str
    checkpoint_id: str
    digest: str
    created_at: datetime
    task: Mapping[str, object]
    run: Mapping[str, object]
    last_step: Mapping[str, object] | None
    model_history: Mapping[str, object]
    environment_reference: str
    pause_command_id: str
    resume_eligible: bool
    schema_version: str = RUNTIME_CHECKPOINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.task, Mapping)
            or not isinstance(self.run, Mapping)
            or not isinstance(self.model_history, Mapping)
            or (self.last_step is not None and not isinstance(self.last_step, Mapping))
        ):
            raise RuntimeCheckpointError("checkpoint_payload_invalid")
        object.__setattr__(self, "task", freeze_json(self.task))
        object.__setattr__(self, "run", freeze_json(self.run))
        object.__setattr__(self, "last_step", freeze_json(self.last_step))
        object.__setattr__(self, "model_history", freeze_json(self.model_history))
        if not self.session_id.strip() or len(self.session_id) > 200:
            raise RuntimeCheckpointError("checkpoint_session_invalid")
        if self.schema_version != RUNTIME_CHECKPOINT_SCHEMA_VERSION:
            raise RuntimeCheckpointError("checkpoint_schema_unsupported")
        if not self.pause_command_id.strip() or len(self.pause_command_id) > 128:
            raise RuntimeCheckpointError("checkpoint_command_invalid")
        if self.created_at.tzinfo is None:
            raise RuntimeCheckpointError("checkpoint_timestamp_invalid")
        if len(self.environment_reference) > 2_000:
            raise RuntimeCheckpointError("checkpoint_environment_reference_invalid")
        recoverable_history = self.model_history.get("format") == "pydantic-ai.messages.v1"
        if self.resume_eligible != (bool(self.environment_reference) and recoverable_history):
            raise RuntimeCheckpointError("checkpoint_resume_eligibility_invalid")
        expected = _checkpoint_digest(self._unsigned_payload())
        if self.digest != expected or self.checkpoint_id != f"runtime-checkpoint:{expected}":
            raise RuntimeCheckpointError("checkpoint_digest_invalid")
        if len(self.to_json().encode()) > _MAX_CHECKPOINT_BYTES:
            raise RuntimeCheckpointError("checkpoint_payload_too_large")

    @classmethod
    def capture(
        cls,
        *,
        session_id: str,
        task: TaskGoal,
        state: RunState,
        model_history: Mapping[str, object],
        environment_reference: str,
        created_at: datetime | None = None,
    ) -> RuntimeCheckpoint:
        boundary = state.control_boundary
        if (
            boundary is None
            or boundary.kind is not RunControlKind.PAUSE
            or boundary.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED
        ):
            raise RuntimeCheckpointError("checkpoint_requires_pause_boundary")
        if state.terminal or state.status not in {
            RunStatus.RUNNING,
            RunStatus.WAITING_USER,
            RunStatus.WAITING_CONFIRMATION,
        }:
            raise RuntimeCheckpointError("checkpoint_run_not_resumable")
        if task.task_id != session_id or task.revision != state.task_revision:
            raise RuntimeCheckpointError("checkpoint_task_scope_mismatch")
        timestamp = created_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise RuntimeCheckpointError("checkpoint_timestamp_invalid")
        recoverable_history = model_history.get("format") == "pydantic-ai.messages.v1"
        resume_eligible = bool(environment_reference) and recoverable_history
        unsigned = {
            "schema_version": RUNTIME_CHECKPOINT_SCHEMA_VERSION,
            "session_id": session_id,
            "created_at": timestamp.astimezone(UTC).isoformat(),
            "task": to_json_compatible(task),
            "run": _run_payload(state, boundary),
            "last_step": _last_step_payload(state),
            "model_history": to_json_compatible(model_history),
            "environment_reference": environment_reference,
            "pause_command_id": boundary.command_id,
            "resume_eligible": resume_eligible,
        }
        digest = _checkpoint_digest(unsigned)
        return cls(
            session_id=session_id,
            checkpoint_id=f"runtime-checkpoint:{digest}",
            digest=digest,
            created_at=timestamp.astimezone(UTC),
            task=unsigned["task"],
            run=unsigned["run"],
            last_step=unsigned["last_step"],
            model_history=unsigned["model_history"],
            environment_reference=environment_reference,
            pause_command_id=boundary.command_id,
            resume_eligible=resume_eligible,
        )

    def _unsigned_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "created_at": self.created_at.astimezone(UTC).isoformat(),
            "task": to_json_compatible(self.task),
            "run": to_json_compatible(self.run),
            "last_step": to_json_compatible(self.last_step),
            "model_history": to_json_compatible(self.model_history),
            "environment_reference": self.environment_reference,
            "pause_command_id": self.pause_command_id,
            "resume_eligible": self.resume_eligible,
        }

    def to_json(self) -> str:
        return _canonical_json(
            {
                **self._unsigned_payload(),
                "checkpoint_id": self.checkpoint_id,
                "digest": self.digest,
            }
        )

    @classmethod
    def from_json(cls, payload: str) -> RuntimeCheckpoint:
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict):
                raise TypeError
            created_at = datetime.fromisoformat(str(raw["created_at"]))
            task = raw["task"]
            run = raw["run"]
            model_history = raw["model_history"]
            last_step = raw.get("last_step")
            if not isinstance(task, dict) or not isinstance(run, dict) or not isinstance(model_history, dict):
                raise TypeError
            if last_step is not None and not isinstance(last_step, dict):
                raise TypeError
            return cls(
                session_id=str(raw["session_id"]),
                checkpoint_id=str(raw["checkpoint_id"]),
                digest=str(raw["digest"]),
                created_at=created_at,
                task=task,
                run=run,
                last_step=last_step,
                model_history=model_history,
                environment_reference=str(raw.get("environment_reference", "")),
                pause_command_id=str(raw["pause_command_id"]),
                resume_eligible=raw.get("resume_eligible") is True,
                schema_version=str(raw["schema_version"]),
            )
        except RuntimeCheckpointError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeCheckpointError("checkpoint_payload_invalid") from exc


@dataclass(frozen=True)
class RuntimeCheckpointCommandOutcome:
    session_id: str
    command_id: str
    checkpoint_id: str
    outcome: str = "paused"

    def __post_init__(self) -> None:
        if (
            not self.session_id.strip()
            or not self.command_id.strip()
            or not self.checkpoint_id.startswith("runtime-checkpoint:")
            or self.outcome != "paused"
        ):
            raise RuntimeCheckpointError("checkpoint_command_outcome_invalid")


class RuntimeCheckpointStore(Protocol):
    async def commit_pause(
        self,
        checkpoint: RuntimeCheckpoint,
        outcome: RuntimeCheckpointCommandOutcome,
    ) -> None: ...

    async def load_latest(self, session_id: str) -> RuntimeCheckpoint | None: ...

    async def command_outcome(
        self, session_id: str, command_id: str
    ) -> RuntimeCheckpointCommandOutcome | None: ...


@dataclass(frozen=True)
class SQLiteRuntimeCheckpointStore:
    """SQLite WAL store; checkpoint and command outcome commit together."""

    path: Path

    def __post_init__(self) -> None:
        path = Path(self.path)
        if not str(path).strip() or path.name in {"", ".", ".."}:
            raise ValueError("checkpoint store path is invalid")
        object.__setattr__(self, "path", path)

    async def commit_pause(
        self,
        checkpoint: RuntimeCheckpoint,
        outcome: RuntimeCheckpointCommandOutcome,
    ) -> None:
        if outcome.session_id != checkpoint.session_id or outcome.command_id != checkpoint.pause_command_id:
            raise RuntimeCheckpointError("checkpoint_command_scope_mismatch")
        if outcome.checkpoint_id != checkpoint.checkpoint_id:
            raise RuntimeCheckpointError("checkpoint_command_join_mismatch")
        try:
            await asyncio.to_thread(self._commit_pause, checkpoint, outcome)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_persistence_failed") from exc

    async def load_latest(self, session_id: str) -> RuntimeCheckpoint | None:
        try:
            return await asyncio.to_thread(self._load_latest, session_id)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_load_failed") from exc

    async def command_outcome(
        self, session_id: str, command_id: str
    ) -> RuntimeCheckpointCommandOutcome | None:
        try:
            return await asyncio.to_thread(self._command_outcome, session_id, command_id)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_load_failed") from exc

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(_SCHEMA)
        return connection

    def _commit_pause(
        self,
        checkpoint: RuntimeCheckpoint,
        outcome: RuntimeCheckpointCommandOutcome,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT checkpoint_id, outcome FROM runtime_command_outcomes "
                "WHERE session_id = ? AND command_id = ?",
                (outcome.session_id, outcome.command_id),
            ).fetchone()
            if existing is not None:
                if existing != (outcome.checkpoint_id, outcome.outcome):
                    raise RuntimeCheckpointError("checkpoint_command_conflict")
                connection.commit()
                return
            connection.execute(
                "INSERT OR IGNORE INTO runtime_checkpoints "
                "(session_id, checkpoint_id, schema_version, digest, created_at, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    checkpoint.session_id,
                    checkpoint.checkpoint_id,
                    checkpoint.schema_version,
                    checkpoint.digest,
                    checkpoint.created_at.isoformat(),
                    checkpoint.to_json(),
                ),
            )
            row = connection.execute(
                "SELECT digest, payload_json FROM runtime_checkpoints "
                "WHERE session_id = ? AND checkpoint_id = ?",
                (checkpoint.session_id, checkpoint.checkpoint_id),
            ).fetchone()
            if row != (checkpoint.digest, checkpoint.to_json()):
                raise RuntimeCheckpointError("checkpoint_identity_conflict")
            connection.execute(
                "INSERT INTO runtime_command_outcomes "
                "(session_id, command_id, kind, outcome, checkpoint_id, created_at) "
                "VALUES (?, ?, 'pause', ?, ?, ?)",
                (
                    outcome.session_id,
                    outcome.command_id,
                    outcome.outcome,
                    outcome.checkpoint_id,
                    checkpoint.created_at.isoformat(),
                ),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _load_latest(self, session_id: str) -> RuntimeCheckpoint | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload_json FROM runtime_checkpoints WHERE session_id = ? "
                "ORDER BY created_at DESC, checkpoint_id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else RuntimeCheckpoint.from_json(str(row[0]))

    def _command_outcome(
        self, session_id: str, command_id: str
    ) -> RuntimeCheckpointCommandOutcome | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT checkpoint_id, outcome FROM runtime_command_outcomes "
                "WHERE session_id = ? AND command_id = ?",
                (session_id, command_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return RuntimeCheckpointCommandOutcome(session_id, command_id, str(row[0]), str(row[1]))


def _run_payload(state: RunState, boundary: RunControlOutcome) -> dict[str, object]:
    return {
        "status": "paused",
        "status_before_pause": state.status.value,
        "remaining_steps": state.remaining_steps,
        "observation_count": state.observation_count,
        "execution_count": state.execution_count,
        "step_count": state.step_count,
        "context_generation": state.context_generation,
        "waited_ms": state.waited_ms,
        "task_revision": state.task_revision,
        "goal_resolution": _goal_resolution_payload(state.goal_resolution),
        "goal_plan_version_counter": state.goal_plan_version_counter,
        "committed_sent_unknown_count": state.committed_sent_unknown_count,
        "decision_counts": {
            kind.value: count for kind, count in sorted(state.decision_counts.items(), key=lambda item: item[0].value)
        },
        "currentness_probe_count": state.currentness_probe_count,
        "workspace": to_json_compatible(state.workspace),
        "pause_boundary": to_json_compatible(boundary),
        "current_observation_id": state.current_world.observation_id,
    }


def _goal_resolution_payload(resolution: object | None) -> object:
    if resolution is None:
        return None
    name = type(resolution).__name__
    kind = {
        "Ready": "ready",
        "NotRequired": "not_required",
        "NeedsInput": "needs_input",
        "Unsupported": "unsupported",
        "Failed": "failed",
    }.get(name)
    if kind is None:
        raise RuntimeCheckpointError("checkpoint_goal_resolution_invalid")
    return {"kind": kind, "value": to_json_compatible(resolution)}


def _last_step_payload(state: RunState) -> dict[str, object] | None:
    step = state.last_step
    if step is None:
        return None
    decision = step.decision
    decision_kind = getattr(getattr(decision, "kind", None), "value", "policy_failure")
    receipts = () if step.execution_receipts is None else step.execution_receipts.receipts
    payload: dict[str, object] = {
        "decision_kind": str(decision_kind),
        "context_id": str(getattr(decision, "context_id", "")),
        "tool_call_id": str(getattr(decision, "tool_call_id", "")),
        "feedback": step.feedback,
        "status_after": step.status_after.value,
        "before_observation_id": step.before_world.observation_id,
        "after_observation_id": step.after_world.observation_id,
        "receipts": [
            {
                "request_id": receipt.request.request_id,
                "tool_call_id": receipt.request.tool_call_id,
                "semantic_action": receipt.request.intent.semantic_action,
                "dispatch_status": receipt.result.dispatch_status.value,
                "backend": receipt.result.backend,
                "transport_success": receipt.result.transport_success,
                "error": receipt.result.error.value if receipt.result.error is not None else None,
                "before_observation_id": receipt.before_observation_id,
                "after_observation_id": receipt.after_observation_id,
            }
            for receipt in receipts
        ],
    }
    if step.execution_receipts is not None:
        payload["execution_completion"] = step.execution_receipts.completion.value
    if step.action_outcome is not None:
        payload["action_outcome"] = {
            "request_id": step.action_outcome.request_id,
            "observed_change": step.action_outcome.observed_change.value,
            "local_postcondition": step.action_outcome.local_postcondition.value,
            "reason": step.action_outcome.reason,
            "evidence_refs": list(step.action_outcome.evidence_refs),
        }
    if hasattr(decision, "question"):
        payload["pending_question"] = {
            "identity": str(getattr(decision, "tool_call_id", "") or getattr(decision, "context_id", "")),
            "question": str(getattr(decision, "question", "")),
            "requested_fields": list(getattr(decision, "requested_fields", ())),
        }
    if step.confirmation is not None:
        payload["pending_confirmation"] = {
            "identity": step.confirmation.subject_id,
            "reason": step.confirmation.reason,
            "risk": str(step.confirmation.risk),
        }
    return payload


def _checkpoint_digest(unsigned_payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(unsigned_payload).encode()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_checkpoints (
    session_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (session_id, checkpoint_id)
);
CREATE INDEX IF NOT EXISTS runtime_checkpoints_latest
    ON runtime_checkpoints (session_id, created_at DESC);
CREATE TABLE IF NOT EXISTS runtime_command_outcomes (
    session_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind = 'pause'),
    outcome TEXT NOT NULL CHECK (outcome = 'paused'),
    checkpoint_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, command_id),
    FOREIGN KEY (session_id, checkpoint_id)
        REFERENCES runtime_checkpoints (session_id, checkpoint_id)
);
"""
