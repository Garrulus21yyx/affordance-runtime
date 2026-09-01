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

from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.actions.reconciliation import (
    EffectReconciliation,
    EffectReconciliationReason,
    EffectReconciliationStatus,
)
from affordance_runtime.actions.space_contracts import ActionRisk
from affordance_runtime.agent.attempt_signature import PublicAttemptSignature
from affordance_runtime.agent.context.contracts import (
    AgentHistoricalTargetView,
    AgentTurnView,
)
from affordance_runtime.agent.context.observation_delivery import (
    LocalDeliveryRecord,
    ObservationDeliveryStore,
)
from affordance_runtime.agent.decisions import DecisionKind, SelectAction
from affordance_runtime.agent.interactions import (
    InteractionRequest,
    interaction_request_public_value,
    legacy_interaction_request,
    restore_interaction_request_public_value,
)
from affordance_runtime.agent.recovery import (
    EpisodeMonitorSnapshot,
    RecoveryKind,
    RecoverySignal,
)
from affordance_runtime.agent.run_control import (
    RunControlBoundary,
    RunControlKind,
    RunControlOutcome,
    RunControlOutcomeKind,
)
from affordance_runtime.agent.run_state import RunCheckpointFacts, RunState, RunStatus
from affordance_runtime.agent.workspace import (
    ActivityFamily,
    ActivitySummary,
    AgentWorkspace,
    SemanticEvent,
    SemanticEventKind,
)
from affordance_runtime.execution.contracts import CommittedEffect, DispatchStatus
from affordance_runtime.goals.plan import (
    Failed,
    GoalPlan,
    GoalPlanItem,
    NeedsInput,
    NotRequired,
    Ready,
    Unsupported,
)
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.risk.contracts import (
    ConfirmationSubject,
    RiskAssessment,
    RiskDecisionKind,
)
from affordance_runtime.task.contracts import (
    EvaluationSpec,
    LoopBudget,
    MaterialBinding,
    RiskProfile,
    TaskGoal,
)

RUNTIME_CHECKPOINT_SCHEMA_VERSION = "affordance-runtime.checkpoint.v8"
_SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS = frozenset(
    {
        "affordance-runtime.checkpoint.v2",
        "affordance-runtime.checkpoint.v3",
        "affordance-runtime.checkpoint.v4",
        "affordance-runtime.checkpoint.v5",
        "affordance-runtime.checkpoint.v6",
        "affordance-runtime.checkpoint.v7",
        RUNTIME_CHECKPOINT_SCHEMA_VERSION,
    }
)
_MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024
_LEGACY_REVISION_PAYLOAD_DIGEST = "0" * 64
_RECOVERABLE_MODEL_HISTORY_FORMATS = frozenset(
    {
        "pydantic-ai.messages.v1",
        "pydantic-ai.step-persistence.v1",
    }
)


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
        if self.schema_version not in _SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS:
            raise RuntimeCheckpointError("checkpoint_schema_unsupported")
        if not self.pause_command_id.strip() or len(self.pause_command_id) > 128:
            raise RuntimeCheckpointError("checkpoint_command_invalid")
        if self.created_at.tzinfo is None:
            raise RuntimeCheckpointError("checkpoint_timestamp_invalid")
        if len(self.environment_reference) > 2_000:
            raise RuntimeCheckpointError("checkpoint_environment_reference_invalid")
        recoverable_history = self.model_history.get("format") in _RECOVERABLE_MODEL_HISTORY_FORMATS
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
        recoverable_history = model_history.get("format") in _RECOVERABLE_MODEL_HISTORY_FORMATS
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

    def restore_task(self) -> TaskGoal:
        return _restore_task(self.task)

    def restore_run_facts(self) -> RunCheckpointFacts:
        return _restore_run_facts(self.run, self.last_step)

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


@dataclass(frozen=True)
class RuntimeCheckpointResumeOutcome:
    """The single durable command allowed to consume one paused checkpoint."""

    session_id: str
    command_id: str
    checkpoint_id: str
    outcome: str = "resumed"

    def __post_init__(self) -> None:
        if (
            not self.session_id.strip()
            or not self.command_id.strip()
            or len(self.command_id) > 128
            or not self.checkpoint_id.startswith("runtime-checkpoint:")
            or self.outcome != "resumed"
        ):
            raise RuntimeCheckpointError("checkpoint_resume_outcome_invalid")


_REVISION_OUTCOMES = frozenset(
    {
        "revised",
        "revision_needs_input",
        "revision_no_change",
        "revision_new_task_suggested",
        "revision_unsupported",
        "revision_failed",
        "effect_reconciliation_required",
    }
)
_REVISION_RESULT_CODES = _REVISION_OUTCOMES | {
    "effect_non_compensable",
    "effect_reconciliation_unknown",
    "effect_reconciliation_unsupported",
}


@dataclass(frozen=True)
class RuntimeCheckpointRevisionOutcome:
    """Durable closed result of one revision command against one source pause."""

    session_id: str
    command_id: str
    source_checkpoint_id: str
    result_checkpoint_id: str
    task_revision: int
    outcome: str
    payload_digest: str
    message: str
    result_code: str = ""

    def __post_init__(self) -> None:
        result_code = self.result_code.strip() or self.outcome
        object.__setattr__(self, "result_code", result_code)
        if (
            not self.session_id.strip()
            or not self.command_id.strip()
            or len(self.command_id) > 128
            or not self.source_checkpoint_id.startswith("runtime-checkpoint:")
            or not self.result_checkpoint_id.startswith("runtime-checkpoint:")
            or type(self.task_revision) is not int
            or self.task_revision < 1
            or self.outcome not in _REVISION_OUTCOMES
            or result_code not in _REVISION_RESULT_CODES
            or len(self.payload_digest) != 64
            or any(character not in "0123456789abcdef" for character in self.payload_digest)
            or len(self.message) > 2000
            or (self.outcome != "effect_reconciliation_required" and result_code != self.outcome)
            or (
                self.outcome == "effect_reconciliation_required"
                and result_code
                not in {
                    "effect_reconciliation_required",
                    "effect_non_compensable",
                    "effect_reconciliation_unknown",
                    "effect_reconciliation_unsupported",
                }
            )
            or (self.outcome == "revised" and self.result_checkpoint_id == self.source_checkpoint_id)
            or (self.outcome != "revised" and self.result_checkpoint_id != self.source_checkpoint_id)
        ):
            raise RuntimeCheckpointError("checkpoint_revision_outcome_invalid")


class RuntimeCheckpointStore(Protocol):
    async def commit_pause(
        self,
        checkpoint: RuntimeCheckpoint,
        outcome: RuntimeCheckpointCommandOutcome,
    ) -> None: ...

    async def load_latest(self, session_id: str) -> RuntimeCheckpoint | None: ...

    async def load(self, session_id: str, checkpoint_id: str) -> RuntimeCheckpoint | None: ...

    async def command_outcome(self, session_id: str, command_id: str) -> RuntimeCheckpointCommandOutcome | None: ...

    async def commit_resume(self, outcome: RuntimeCheckpointResumeOutcome) -> None: ...

    async def resume_outcome(self, session_id: str, command_id: str) -> RuntimeCheckpointResumeOutcome | None: ...

    async def checkpoint_resume_outcome(
        self, session_id: str, checkpoint_id: str
    ) -> RuntimeCheckpointResumeOutcome | None: ...

    async def commit_revision(
        self,
        checkpoint: RuntimeCheckpoint | None,
        outcome: RuntimeCheckpointRevisionOutcome,
    ) -> None: ...

    async def revision_outcome(self, session_id: str, command_id: str) -> RuntimeCheckpointRevisionOutcome | None: ...

    async def checkpoint_revision_outcome(
        self, session_id: str, checkpoint_id: str
    ) -> RuntimeCheckpointRevisionOutcome | None: ...


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

    async def load(self, session_id: str, checkpoint_id: str) -> RuntimeCheckpoint | None:
        try:
            return await asyncio.to_thread(self._load, session_id, checkpoint_id)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_load_failed") from exc

    async def command_outcome(self, session_id: str, command_id: str) -> RuntimeCheckpointCommandOutcome | None:
        try:
            return await asyncio.to_thread(self._command_outcome, session_id, command_id)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_load_failed") from exc

    async def commit_resume(self, outcome: RuntimeCheckpointResumeOutcome) -> None:
        try:
            await asyncio.to_thread(self._commit_resume, outcome)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_resume_persistence_failed") from exc

    async def resume_outcome(self, session_id: str, command_id: str) -> RuntimeCheckpointResumeOutcome | None:
        try:
            return await asyncio.to_thread(self._resume_outcome, session_id, command_id)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_load_failed") from exc

    async def checkpoint_resume_outcome(
        self, session_id: str, checkpoint_id: str
    ) -> RuntimeCheckpointResumeOutcome | None:
        try:
            return await asyncio.to_thread(self._checkpoint_resume_outcome, session_id, checkpoint_id)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_load_failed") from exc

    async def commit_revision(
        self,
        checkpoint: RuntimeCheckpoint | None,
        outcome: RuntimeCheckpointRevisionOutcome,
    ) -> None:
        if checkpoint is not None and (
            outcome.outcome != "revised"
            or checkpoint.session_id != outcome.session_id
            or checkpoint.checkpoint_id != outcome.result_checkpoint_id
            or checkpoint.restore_task().revision != outcome.task_revision
        ):
            raise RuntimeCheckpointError("checkpoint_revision_join_mismatch")
        if checkpoint is None and outcome.outcome == "revised":
            raise RuntimeCheckpointError("checkpoint_revision_missing")
        try:
            await asyncio.to_thread(self._commit_revision, checkpoint, outcome)
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_revision_persistence_failed") from exc

    async def revision_outcome(
        self,
        session_id: str,
        command_id: str,
    ) -> RuntimeCheckpointRevisionOutcome | None:
        try:
            return await asyncio.to_thread(
                self._revision_outcome,
                session_id,
                command_id,
            )
        except RuntimeCheckpointError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeCheckpointError("checkpoint_load_failed") from exc

    async def checkpoint_revision_outcome(
        self,
        session_id: str,
        checkpoint_id: str,
    ) -> RuntimeCheckpointRevisionOutcome | None:
        try:
            return await asyncio.to_thread(
                self._checkpoint_revision_outcome,
                session_id,
                checkpoint_id,
            )
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
        _migrate_revision_outcome_schema(connection)
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
                "SELECT checkpoint_id, outcome FROM runtime_command_outcomes WHERE session_id = ? AND command_id = ?",
                (outcome.session_id, outcome.command_id),
            ).fetchone()
            if existing is not None:
                if existing != (outcome.checkpoint_id, outcome.outcome):
                    raise RuntimeCheckpointError("checkpoint_command_conflict")
                connection.commit()
                return
            _persist_checkpoint_identity(connection, checkpoint)
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
        if row is None:
            return None
        checkpoint = RuntimeCheckpoint.from_json(str(row[0]))
        if checkpoint.session_id != session_id:
            raise RuntimeCheckpointError("checkpoint_scope_mismatch")
        return checkpoint

    def _load(self, session_id: str, checkpoint_id: str) -> RuntimeCheckpoint | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload_json FROM runtime_checkpoints WHERE session_id = ? AND checkpoint_id = ?",
                (session_id, checkpoint_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        checkpoint = RuntimeCheckpoint.from_json(str(row[0]))
        if checkpoint.session_id != session_id or checkpoint.checkpoint_id != checkpoint_id:
            raise RuntimeCheckpointError("checkpoint_scope_mismatch")
        return checkpoint

    def _command_outcome(self, session_id: str, command_id: str) -> RuntimeCheckpointCommandOutcome | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT checkpoint_id, outcome FROM runtime_command_outcomes WHERE session_id = ? AND command_id = ?",
                (session_id, command_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return RuntimeCheckpointCommandOutcome(session_id, command_id, str(row[0]), str(row[1]))

    def _commit_resume(self, outcome: RuntimeCheckpointResumeOutcome) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            checkpoint = connection.execute(
                "SELECT 1 FROM runtime_checkpoints WHERE session_id = ? AND checkpoint_id = ?",
                (outcome.session_id, outcome.checkpoint_id),
            ).fetchone()
            if checkpoint is None:
                raise RuntimeCheckpointError("checkpoint_not_found")
            by_command = connection.execute(
                "SELECT checkpoint_id, outcome FROM runtime_resume_outcomes WHERE session_id = ? AND command_id = ?",
                (outcome.session_id, outcome.command_id),
            ).fetchone()
            if by_command is not None:
                if by_command != (outcome.checkpoint_id, outcome.outcome):
                    raise RuntimeCheckpointError("checkpoint_resume_command_conflict")
                connection.commit()
                return
            by_checkpoint = connection.execute(
                "SELECT command_id FROM runtime_resume_outcomes WHERE session_id = ? AND checkpoint_id = ?",
                (outcome.session_id, outcome.checkpoint_id),
            ).fetchone()
            if by_checkpoint is not None:
                raise RuntimeCheckpointError("checkpoint_already_resumed")
            connection.execute(
                "INSERT INTO runtime_resume_outcomes "
                "(session_id, command_id, checkpoint_id, outcome, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    outcome.session_id,
                    outcome.command_id,
                    outcome.checkpoint_id,
                    outcome.outcome,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _resume_outcome(self, session_id: str, command_id: str) -> RuntimeCheckpointResumeOutcome | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT checkpoint_id, outcome FROM runtime_resume_outcomes WHERE session_id = ? AND command_id = ?",
                (session_id, command_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return RuntimeCheckpointResumeOutcome(session_id, command_id, str(row[0]), str(row[1]))

    def _checkpoint_resume_outcome(self, session_id: str, checkpoint_id: str) -> RuntimeCheckpointResumeOutcome | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT command_id, outcome FROM runtime_resume_outcomes WHERE session_id = ? AND checkpoint_id = ?",
                (session_id, checkpoint_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return RuntimeCheckpointResumeOutcome(session_id, str(row[0]), checkpoint_id, str(row[1]))

    def _commit_revision(
        self,
        checkpoint: RuntimeCheckpoint | None,
        outcome: RuntimeCheckpointRevisionOutcome,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                "SELECT 1 FROM runtime_checkpoints WHERE session_id = ? AND checkpoint_id = ?",
                (outcome.session_id, outcome.source_checkpoint_id),
            ).fetchone()
            if source is None:
                raise RuntimeCheckpointError("checkpoint_not_found")
            existing = connection.execute(
                "SELECT source_checkpoint_id, result_checkpoint_id, task_revision, outcome, "
                "payload_digest, message, result_code "
                "FROM runtime_revision_outcomes WHERE session_id = ? AND command_id = ?",
                (outcome.session_id, outcome.command_id),
            ).fetchone()
            expected = (
                outcome.source_checkpoint_id,
                outcome.result_checkpoint_id,
                outcome.task_revision,
                outcome.outcome,
                outcome.payload_digest,
                outcome.message,
                outcome.result_code,
            )
            if existing is not None:
                if existing != expected:
                    raise RuntimeCheckpointError("checkpoint_revision_command_conflict")
                connection.commit()
                return
            if outcome.outcome == "revised":
                assert checkpoint is not None
                consumed = connection.execute(
                    "SELECT command_id FROM runtime_revision_outcomes "
                    "WHERE session_id = ? AND source_checkpoint_id = ? AND outcome = 'revised'",
                    (outcome.session_id, outcome.source_checkpoint_id),
                ).fetchone()
                if consumed is not None:
                    raise RuntimeCheckpointError("checkpoint_already_revised")
                _persist_checkpoint_identity(connection, checkpoint)
            connection.execute(
                "INSERT INTO runtime_revision_outcomes "
                "(session_id, command_id, source_checkpoint_id, result_checkpoint_id, "
                "task_revision, outcome, payload_digest, message, result_code, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    outcome.session_id,
                    outcome.command_id,
                    outcome.source_checkpoint_id,
                    outcome.result_checkpoint_id,
                    outcome.task_revision,
                    outcome.outcome,
                    outcome.payload_digest,
                    outcome.message,
                    outcome.result_code,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _revision_outcome(
        self,
        session_id: str,
        command_id: str,
    ) -> RuntimeCheckpointRevisionOutcome | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT source_checkpoint_id, result_checkpoint_id, task_revision, outcome, "
                "payload_digest, message, result_code "
                "FROM runtime_revision_outcomes WHERE session_id = ? AND command_id = ?",
                (session_id, command_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return RuntimeCheckpointRevisionOutcome(
            session_id,
            command_id,
            str(row[0]),
            str(row[1]),
            int(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            str(row[6]),
        )

    def _checkpoint_revision_outcome(
        self,
        session_id: str,
        checkpoint_id: str,
    ) -> RuntimeCheckpointRevisionOutcome | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT command_id, result_checkpoint_id, task_revision, outcome, "
                "payload_digest, message, result_code "
                "FROM runtime_revision_outcomes "
                "WHERE session_id = ? AND source_checkpoint_id = ? AND outcome = 'revised'",
                (session_id, checkpoint_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return RuntimeCheckpointRevisionOutcome(
            session_id,
            str(row[0]),
            checkpoint_id,
            str(row[1]),
            int(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            str(row[6]),
        )


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
        "delivery_store": _delivery_store_payload(state.delivery_store),
        "recovery_signal": _recovery_signal_payload(state.recovery_signal),
        "monitor_snapshot": _monitor_snapshot_payload(state.monitor_snapshot),
        "pause_boundary": to_json_compatible(boundary),
        "current_observation_id": state.current_world.observation_id,
        "latest_effect": _committed_effect_payload(state.latest_effect),
        "effect_reconciliation": _effect_reconciliation_payload(state.effect_reconciliation),
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


def _delivery_store_payload(store: ObservationDeliveryStore) -> dict[str, object]:
    """Persist only the Monitor's bounded ref-free novelty receipts."""

    return {
        "local_deliveries": [
            {
                "operation": item.operation,
                "world_digest": item.world_digest,
                "arguments_digest": item.arguments_digest,
                "result_digest": item.result_digest,
                "item_digests": list(item.item_digests),
            }
            for item in store.local_deliveries
        ]
    }


def _recovery_signal_payload(signal: RecoverySignal | None) -> dict[str, object] | None:
    if signal is None:
        return None
    return {
        "kind": signal.kind.value,
        "epoch_id": signal.epoch_id,
        "stable_signature": signal.stable_signature,
        "evidence_revision": signal.evidence_revision,
        "observed_evidence": to_json_compatible(signal.observed_evidence),
        "attempted_modes": list(signal.attempted_modes),
        "prohibited_attempt_signatures": [to_json_compatible(item) for item in signal.prohibited_attempt_signatures],
        "human_instruction": signal.human_instruction,
        "recovery_attempt": signal.recovery_attempt,
        "monitor_state": to_json_compatible(signal.monitor_state),
    }


def _restore_recovery_signal(payload: object) -> RecoverySignal | None:
    if payload is None:
        return None
    value = _mapping(payload)
    prohibited = tuple(
        PublicAttemptSignature(
            str(item["operation"]),
            str(item["precondition_digest"]),
            str(item["target_semantic_digest"]),
            str(item["destination_semantic_digest"]),
            str(item["parameter_digest"]),
        )
        for item in _mapping_sequence(value.get("prohibited_attempt_signatures", []))
        if "precondition_digest" in item
    )
    return RecoverySignal(
        RecoveryKind(str(value["kind"])),
        str(value["stable_signature"]),
        dict(_mapping(value.get("observed_evidence", {}))),
        attempted_modes=tuple(_string_sequence(value.get("attempted_modes", []))),
        prohibited_attempt_signatures=prohibited,
        human_instruction=str(value.get("human_instruction", "")),
        recovery_attempt=_integer(value.get("recovery_attempt", 1)),
        epoch_id=str(value["epoch_id"]),
        evidence_revision=_integer(value.get("evidence_revision", 1)),
        monitor_state=dict(_mapping(value.get("monitor_state", {}))),
    )


def _monitor_snapshot_payload(snapshot: EpisodeMonitorSnapshot | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "world_digest": snapshot.world_digest,
        "failure_center_digest": snapshot.failure_center_digest,
        "failure_center_period": snapshot.failure_center_period,
        "failure_center_member_digests": list(snapshot.failure_center_member_digests),
        "failure_center_kind": snapshot.failure_center_kind.value if snapshot.failure_center_kind is not None else None,
        "failure_center_armed": snapshot.failure_center_armed,
        "recovery_epoch_counter": snapshot.recovery_epoch_counter,
    }


def _restore_monitor_snapshot(payload: object) -> EpisodeMonitorSnapshot | None:
    if payload is None:
        return None
    value = _mapping(payload)
    kind = value.get("failure_center_kind")
    armed = value.get("failure_center_armed", False)
    if type(armed) is not bool:
        raise TypeError("monitor snapshot armed state must be boolean")
    return EpisodeMonitorSnapshot(
        str(value["world_digest"]),
        failure_center_digest=str(value.get("failure_center_digest", "")),
        failure_center_period=_integer(value.get("failure_center_period", 0)),
        failure_center_member_digests=tuple(_string_sequence(value.get("failure_center_member_digests", []))),
        failure_center_kind=RecoveryKind(str(kind)) if kind is not None else None,
        failure_center_armed=armed,
        recovery_epoch_counter=_integer(value.get("recovery_epoch_counter", 0)),
    )


def _committed_effect_payload(effect: CommittedEffect | None) -> dict[str, object] | None:
    if effect is None:
        return None
    return {
        "effect_ref": effect.effect_ref,
        "task_revision": effect.task_revision,
        "request_id": effect.request_id,
        "semantic_action": effect.semantic_action,
        "resource_ref": effect.resource_ref,
        "semantic_effects": list(effect.semantic_effects),
        "reversibility": effect.reversibility.value,
        "dispatch_status": effect.dispatch_status.value,
        "before_observation_id": effect.before_observation_id,
        "after_observation_id": effect.after_observation_id,
    }


def _effect_reconciliation_payload(
    reconciliation: EffectReconciliation | None,
) -> dict[str, object] | None:
    if reconciliation is None:
        return None
    return {
        "original_effect": _committed_effect_payload(reconciliation.original_effect),
        "revised_task_revision": reconciliation.revised_task_revision,
        "status": reconciliation.status.value,
        "reason": reconciliation.reason.value,
        "compensation_effect": _committed_effect_payload(reconciliation.compensation_effect),
    }


def _restore_committed_effect(payload: object) -> CommittedEffect | None:
    if payload is None:
        return None
    value = _mapping(payload)
    return CommittedEffect(
        str(value["effect_ref"]),
        _integer(value["task_revision"]),
        str(value["request_id"]),
        str(value["semantic_action"]),
        str(value["resource_ref"]),
        tuple(_string_sequence(value.get("semantic_effects", []))),
        Reversibility(str(value["reversibility"])),
        DispatchStatus(str(value["dispatch_status"])),
        str(value["before_observation_id"]),
        str(value["after_observation_id"]),
    )


def _restore_effect_reconciliation(payload: object) -> EffectReconciliation | None:
    if payload is None:
        return None
    value = _mapping(payload)
    original = _restore_committed_effect(value["original_effect"])
    if original is None:
        raise RuntimeCheckpointError("checkpoint_effect_reconciliation_invalid")
    return EffectReconciliation(
        original,
        _integer(value["revised_task_revision"]),
        EffectReconciliationStatus(str(value["status"])),
        EffectReconciliationReason(str(value["reason"])),
        _restore_committed_effect(value.get("compensation_effect")),
    )


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
                "resource_ref": receipt.request.selection.resource_ref,
                "semantic_effects": list(receipt.request.selection.semantic_effects),
                "reversibility": receipt.request.selection.reversibility.value,
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
    if isinstance(decision, InteractionRequest):
        payload["pending_interaction"] = interaction_request_public_value(decision)
    if step.confirmation is not None:
        payload["pending_confirmation"] = {
            "identity": step.confirmation.subject_id,
            "reason": step.confirmation.reason,
            "risk": str(step.confirmation.risk),
            "decision": to_json_compatible(decision),
            "assessment": to_json_compatible(step.confirmation),
        }
    return payload


def _restore_task(payload: Mapping[str, object]) -> TaskGoal:
    try:
        materials = tuple(
            MaterialBinding(
                str(item["name"]),
                str(item["digest"]),
                str(item.get("media_type", "application/octet-stream")),
                str(item.get("public_reference", "")),
            )
            for item in _mapping_sequence(payload.get("material_bindings", []))
        )
        budget = _mapping(payload["loop_budget"])
        raw_evaluation = payload.get("evaluation_spec")
        evaluation = None
        if raw_evaluation is not None:
            evaluation_payload = _mapping(raw_evaluation)
            evaluation = EvaluationSpec(
                dict(_mapping(evaluation_payload["success_expression"])),
                dict(_mapping(evaluation_payload.get("required_output_integrity", {}))),
                tuple(_string_sequence(evaluation_payload.get("authoritative_checks", []))),
                evaluation_payload.get("strict_source_lineage") is True,
            )
        return TaskGoal(
            str(payload["task_id"]),
            str(payload["instruction"]),
            constraints=tuple(_string_sequence(payload.get("constraints", []))),
            allowed_effects=tuple(_string_sequence(payload.get("allowed_effects", []))),
            forbidden_effects=tuple(_string_sequence(payload.get("forbidden_effects", []))),
            inputs=dict(_mapping(payload.get("inputs", {}))),
            success_criteria=tuple(dict(item) for item in _mapping_sequence(payload.get("success_criteria", []))),
            requested_outputs=tuple(_string_sequence(payload.get("requested_outputs", []))),
            risk_profile=RiskProfile(str(payload["risk_profile"])),
            material_bindings=materials,
            loop_budget=LoopBudget(
                _integer(budget["max_turns"]),
                _integer(budget["max_observations"]),
            ),
            evaluation_spec=evaluation,
            revision=_integer(payload["revision"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeCheckpointError("checkpoint_task_invalid") from exc


def _restore_run_facts(
    run_payload: Mapping[str, object],
    last_step_payload: Mapping[str, object] | None,
) -> RunCheckpointFacts:
    try:
        resolution = _restore_goal_resolution(run_payload.get("goal_resolution"))
        workspace = _restore_workspace(_mapping(run_payload.get("workspace", {})))
        boundary_payload = _mapping(run_payload["pause_boundary"])
        dispatch = boundary_payload.get("dispatch_status")
        boundary = RunControlOutcome(
            str(boundary_payload["command_id"]),
            RunControlKind(str(boundary_payload["kind"])),
            RunControlOutcomeKind(str(boundary_payload["outcome"])),
            RunControlBoundary(str(boundary_payload["boundary"])),
            DispatchStatus(str(dispatch)) if dispatch is not None else None,
            str(boundary_payload.get("failure_code", "")),
        )
        status = RunStatus(str(run_payload["status_before_pause"]))
        last_decision, confirmation, feedback = _restore_pending_step(
            status,
            last_step_payload,
        )
        counts_payload = _mapping(run_payload.get("decision_counts", {}))
        latest_effect = _restore_committed_effect(run_payload.get("latest_effect"))
        reconciliation = _restore_effect_reconciliation(run_payload.get("effect_reconciliation"))
        recovery_signal = _restore_recovery_signal(run_payload.get("recovery_signal"))
        monitor_snapshot = _restore_monitor_snapshot(run_payload.get("monitor_snapshot"))
        delivery_store = _restore_delivery_store(run_payload.get("delivery_store"))
        return RunCheckpointFacts(
            status_before_pause=status,
            remaining_steps=_integer(run_payload["remaining_steps"]),
            observation_count=_integer(run_payload["observation_count"]),
            execution_count=_integer(run_payload["execution_count"]),
            step_count=_integer(run_payload["step_count"]),
            context_generation=_integer(run_payload["context_generation"]),
            waited_ms=_integer(run_payload["waited_ms"]),
            task_revision=_integer(run_payload["task_revision"]),
            goal_resolution=resolution,
            goal_plan_version_counter=_integer(run_payload["goal_plan_version_counter"]),
            committed_sent_unknown_count=_integer(run_payload["committed_sent_unknown_count"]),
            decision_counts={DecisionKind(str(kind)): _integer(value) for kind, value in counts_payload.items()},
            currentness_probe_count=_integer(run_payload["currentness_probe_count"]),
            workspace=workspace,
            pause_boundary=boundary,
            delivery_store=delivery_store,
            recovery_signal=recovery_signal,
            monitor_snapshot=monitor_snapshot,
            latest_effect=latest_effect,
            effect_reconciliation=reconciliation,
            last_decision=last_decision,
            last_confirmation=confirmation,
            last_feedback=feedback,
        )
    except RuntimeCheckpointError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeCheckpointError("checkpoint_run_state_invalid") from exc


def _restore_delivery_store(payload: object) -> ObservationDeliveryStore:
    if payload is None:
        # Checkpoint v2-v6 began a fresh bounded novelty window on restore.
        return ObservationDeliveryStore()
    store = _mapping(payload)
    records = tuple(
        LocalDeliveryRecord(
            str(item["operation"]),
            str(item["world_digest"]),
            str(item["arguments_digest"]),
            str(item["result_digest"]),
            _string_sequence(item.get("item_digests", [])),
        )
        for item in _mapping_sequence(store.get("local_deliveries", []))
    )
    return ObservationDeliveryStore(records)


def _restore_goal_resolution(payload: object):
    if payload is None:
        return None
    wrapper = _mapping(payload)
    kind = str(wrapper["kind"])
    value = _mapping(wrapper["value"])
    revision = _integer(value["task_revision"])
    if kind == "ready":
        plan_payload = _mapping(value["accepted_plan"])
        items = tuple(
            GoalPlanItem(
                str(item["id"]),
                str(item["objective"]),
                str(item["done_when"]),
                tuple(_string_sequence(item.get("depends_on", []))),
                item.get("final") is True,
            )
            for item in _mapping_sequence(plan_payload["items"])
        )
        return Ready(
            revision,
            GoalPlan(
                _integer(plan_payload["task_revision"]),
                _integer(plan_payload["plan_version"]),
                items,
            ),
        )
    if kind == "needs_input":
        return NeedsInput(
            revision,
            str(value["question"]),
            tuple(_string_sequence(value["fields"])),
        )
    cls = {
        "not_required": NotRequired,
        "unsupported": Unsupported,
        "failed": Failed,
    }.get(kind)
    if cls is None:
        raise RuntimeCheckpointError("checkpoint_goal_resolution_invalid")
    return cls(revision, str(value["reason"]))


def _restore_workspace(payload: Mapping[str, object]) -> AgentWorkspace:
    recent = tuple(
        AgentTurnView(
            str(item["decision_kind"]),
            str(item.get("semantic_action", "")),
            _restore_historical_target(item.get("target")),
            _restore_historical_target(item.get("destination")),
            dict(_mapping(item.get("public_parameters", {}))),
            str(item.get("expected_outcome", "")),
            str(item.get("dispatch_status", "")),
            str(item.get("local_postcondition", "")),
            dict(_mapping(item.get("transition", {}))),
            str(item.get("task_evaluation_status", "")),
            str(item.get("reason", "")),
            dict(_mapping(item.get("semantic_summary", {}))),
        )
        for item in _mapping_sequence(payload.get("recent_steps", []))
    )
    events = tuple(
        SemanticEvent(
            _integer(item["step_index"]),
            SemanticEventKind(str(item["kind"])),
            str(item["summary"]),
            str(item.get("operation", "")),
            str(item.get("result_lineage", "")),
        )
        for item in _mapping_sequence(payload.get("semantic_events", []))
    )
    activities = tuple(
        ActivitySummary(
            ActivityFamily(str(item["family"])),
            str(item["world_digest"]),
            _integer(item["attempt_count"]),
            _integer(item["new_finding_count"]),
            str(item["last_outcome"]),
        )
        for item in _mapping_sequence(payload.get("activities", []))
    )
    return AgentWorkspace(recent, events, activities)


def _restore_historical_target(payload: object) -> AgentHistoricalTargetView | None:
    if payload is None:
        return None
    value = _mapping(payload)
    return AgentHistoricalTargetView(
        str(value["role"]),
        str(value["label"]),
        tuple(_string_sequence(value.get("context", []))),
    )


def _restore_pending_step(
    status: RunStatus,
    payload: Mapping[str, object] | None,
) -> tuple[InteractionRequest | SelectAction | None, RiskAssessment | None, str]:
    if payload is None:
        if status in {RunStatus.WAITING_USER, RunStatus.WAITING_CONFIRMATION}:
            raise RuntimeCheckpointError("checkpoint_pending_step_missing")
        return None, None, "checkpoint_restored"
    feedback = str(payload.get("feedback", "checkpoint_restored"))
    if status is RunStatus.WAITING_USER:
        current = payload.get("pending_interaction")
        if current is not None:
            return restore_interaction_request_public_value(current), None, feedback
        pending = _mapping(payload["pending_question"])
        return (
            legacy_interaction_request(
                context_id=str(payload["context_id"]),
                prompt=str(pending["question"]),
                requested_fields=tuple(_string_sequence(pending.get("requested_fields", []))),
                tool_call_id=str(payload.get("tool_call_id", "")),
            ),
            None,
            feedback,
        )
    if status is RunStatus.WAITING_CONFIRMATION:
        pending = _mapping(payload["pending_confirmation"])
        decision_payload = _mapping(pending["decision"])
        assessment_payload = _mapping(pending["assessment"])
        subject_payload = _mapping(assessment_payload["subject"])
        subject = ConfirmationSubject(
            str(subject_payload["semantic_action"]),
            str(subject_payload["target_id"]),
            str(subject_payload.get("destination_id", "")),
            dict(_mapping(subject_payload.get("parameters", {}))),
            tuple(_string_sequence(subject_payload.get("selection_effects", []))),
            tuple(_string_sequence(subject_payload.get("assessed_effects", []))),
            ActionRisk(str(subject_payload["risk"])),
            tuple(_string_sequence(subject_payload.get("consequences", []))),
            str(subject_payload["effect_category"]),
        )
        assessment = RiskAssessment(
            RiskDecisionKind(str(assessment_payload["decision"])),
            ActionRisk(str(assessment_payload["risk"])),
            tuple(_string_sequence(assessment_payload.get("semantic_effects", []))),
            tuple(_string_sequence(assessment_payload.get("consequences", []))),
            str(assessment_payload["subject_id"]),
            str(assessment_payload["reason"]),
            subject,
        )
        return (
            SelectAction(
                str(decision_payload["context_id"]),
                str(decision_payload["action_id"]),
                dict(_mapping(decision_payload.get("parameters", {}))),
                str(decision_payload.get("destination_id", "")),
                str(decision_payload.get("tool_call_id", "")),
                str(decision_payload.get("expected_outcome", "")),
            ),
            assessment,
            feedback,
        )
    return None, None, feedback


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("checkpoint value must be an object")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise TypeError("checkpoint value must be an integer")
    return value


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list | tuple):
        raise TypeError("checkpoint value must be an object sequence")
    return tuple(_mapping(item) for item in value)


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError("checkpoint value must be a string sequence")
    return tuple(value)


def _checkpoint_digest(unsigned_payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(unsigned_payload).encode()).hexdigest()


def _persist_checkpoint_identity(
    connection: sqlite3.Connection,
    checkpoint: RuntimeCheckpoint,
) -> None:
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
        "SELECT digest, payload_json FROM runtime_checkpoints WHERE session_id = ? AND checkpoint_id = ?",
        (checkpoint.session_id, checkpoint.checkpoint_id),
    ).fetchone()
    if row != (checkpoint.digest, checkpoint.to_json()):
        raise RuntimeCheckpointError("checkpoint_identity_conflict")


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
CREATE TABLE IF NOT EXISTS runtime_resume_outcomes (
    session_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome = 'resumed'),
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, command_id),
    UNIQUE (session_id, checkpoint_id),
    FOREIGN KEY (session_id, checkpoint_id)
        REFERENCES runtime_checkpoints (session_id, checkpoint_id)
);
CREATE TABLE IF NOT EXISTS runtime_revision_outcomes (
    session_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    source_checkpoint_id TEXT NOT NULL,
    result_checkpoint_id TEXT NOT NULL,
    task_revision INTEGER NOT NULL CHECK (task_revision >= 1),
    outcome TEXT NOT NULL CHECK (outcome IN (
        'revised',
        'revision_needs_input',
        'revision_no_change',
        'revision_new_task_suggested',
        'revision_unsupported',
        'revision_failed',
        'effect_reconciliation_required'
    )),
    payload_digest TEXT NOT NULL,
    message TEXT NOT NULL,
    result_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, command_id),
    FOREIGN KEY (session_id, source_checkpoint_id)
        REFERENCES runtime_checkpoints (session_id, checkpoint_id),
    FOREIGN KEY (session_id, result_checkpoint_id)
        REFERENCES runtime_checkpoints (session_id, checkpoint_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS runtime_revision_source_consumed
    ON runtime_revision_outcomes (session_id, source_checkpoint_id)
    WHERE outcome = 'revised';
"""


def _migrate_revision_outcome_schema(connection: sqlite3.Connection) -> None:
    """Add bounded idempotency result fields without discarding legacy outcomes."""

    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(runtime_revision_outcomes)")}
    additions = {
        "payload_digest": (
            "ALTER TABLE runtime_revision_outcomes ADD COLUMN payload_digest "
            f"TEXT NOT NULL DEFAULT '{_LEGACY_REVISION_PAYLOAD_DIGEST}'"
        ),
        "message": ("ALTER TABLE runtime_revision_outcomes ADD COLUMN message TEXT NOT NULL DEFAULT ''"),
        "result_code": ("ALTER TABLE runtime_revision_outcomes ADD COLUMN result_code TEXT NOT NULL DEFAULT ''"),
    }
    for name, statement in additions.items():
        if name in columns:
            continue
        try:
            connection.execute(statement)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    connection.commit()
