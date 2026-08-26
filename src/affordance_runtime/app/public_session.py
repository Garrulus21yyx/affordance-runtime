"""Versioned public session boundary over the single TargetRuntime loop."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol

from affordance_runtime.agent.decisions import AskUser
from affordance_runtime.agent.observability import FanoutRunTraceSink, NullRunTraceSink
from affordance_runtime.agent.run_control import (
    RunControlAdmissionKind,
    RunControlKind,
    RunControlOutcomeKind,
)
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.evaluation.contracts import TaskOutcomeKind
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import (
    NaturalLanguageTaskRequest,
    ReadyTask,
    TaskBoundary,
    TaskInputRequired,
    TaskPolicyRejected,
    TaskUnsupported,
)
from affordance_runtime.task.revision import (
    RevisionFailed,
    RevisionNeedsInput,
    RevisionNewTaskSuggested,
    RevisionNoChange,
    RevisionReady,
    RevisionUnsupported,
    revision_outcome_code,
)
from affordance_runtime.world.environment import WorldEnvironment

from .checkpoint import (
    RuntimeCheckpoint,
    RuntimeCheckpointCommandOutcome,
    RuntimeCheckpointError,
    RuntimeCheckpointResumeOutcome,
    RuntimeCheckpointRevisionOutcome,
    RuntimeCheckpointStore,
)
from .runtime import TargetRuntime

PUBLIC_SESSION_SCHEMA_VERSION = "affordance-runtime.session.v1"


class PublicSessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class PublicTaskRevisionCommand:
    """Complete Runtime-owned revision command and its canonical identity."""

    command_id: str
    expected_task_revision: int
    expected_run_status: PublicSessionStatus
    expected_checkpoint_id: str | None
    text: str

    def __post_init__(self) -> None:
        if (
            not self.command_id.strip()
            or len(self.command_id) > 128
            or type(self.expected_task_revision) is not int
            or self.expected_task_revision < 0
            or not isinstance(self.expected_run_status, PublicSessionStatus)
            or (
                self.expected_checkpoint_id is not None
                and (
                    len(self.expected_checkpoint_id) > 200
                    or not self.expected_checkpoint_id.startswith("runtime-checkpoint:")
                )
            )
            or not self.text.strip()
            or len(self.text) > 8000
        ):
            raise ValueError("public task revision command is invalid")

    @property
    def payload_digest(self) -> str:
        payload = {
            "expected_checkpoint_id": self.expected_checkpoint_id,
            "expected_run_status": self.expected_run_status.value,
            "expected_task_revision": self.expected_task_revision,
            "kind": "revise_task",
            "schema_version": PUBLIC_SESSION_SCHEMA_VERSION,
            "text": self.text,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PublicSessionCapability(StrEnum):
    START_TASK = "start_task"
    ANSWER_QUESTION = "answer_question"
    APPROVE_ACTION = "approve_action"
    REJECT_ACTION = "reject_action"
    CANCEL_TASK = "cancel_task"
    PAUSE_TASK = "pause_task"
    RESUME_TASK = "resume_task"
    REVISE_TASK = "revise_task"
    CLOSE_SESSION = "close_session"


PUBLIC_SESSION_CAPABILITIES = frozenset(PublicSessionCapability)
BASE_PUBLIC_SESSION_CAPABILITIES = PUBLIC_SESSION_CAPABILITIES - {
    PublicSessionCapability.PAUSE_TASK,
    PublicSessionCapability.RESUME_TASK,
    PublicSessionCapability.REVISE_TASK,
}


@dataclass(frozen=True)
class PublicPendingQuestion:
    interrupt_id: str
    prompt: str
    requested_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicPendingConfirmation:
    interrupt_id: str
    summary: str
    risk: str


@dataclass(frozen=True)
class PublicCompletion:
    outcome: Literal["success", "failure", "blocked", "cancelled"]
    code: str
    message: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicProgressStep:
    step: int
    status: str
    label: str


@dataclass(frozen=True)
class PublicControlOutcome:
    command_id: str
    kind: Literal["pause", "revise"]
    outcome: Literal[
        "paused",
        "failed",
        "revised",
        "needs_input",
        "no_change",
        "new_task_suggested",
        "unsupported",
        "effect_reconciliation_required",
    ]
    code: str
    checkpoint_id: str | None = None
    message: str = ""


@dataclass(frozen=True)
class PublicRuntimeSessionSnapshot:
    session_id: str
    expires_at: datetime
    status: PublicSessionStatus
    event_epoch: str
    event_cursor: int
    capabilities: frozenset[PublicSessionCapability] = BASE_PUBLIC_SESSION_CAPABILITIES
    task_id: str | None = None
    task_revision: int = 0
    task_text: str | None = None
    pending_question: PublicPendingQuestion | None = None
    pending_confirmation: PublicPendingConfirmation | None = None
    completion: PublicCompletion | None = None
    progress: tuple[PublicProgressStep, ...] = ()
    checkpoint_id: str | None = None
    resume_eligible: bool = False
    last_control_outcome: PublicControlOutcome | None = None
    schema_version: str = PUBLIC_SESSION_SCHEMA_VERSION


@dataclass(frozen=True)
class PublicRuntimeSessionEvent:
    session_id: str
    event_epoch: str
    cursor: int
    type: str
    snapshot: PublicRuntimeSessionSnapshot
    emitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = PUBLIC_SESSION_SCHEMA_VERSION


class PublicSessionConflict(RuntimeError):
    def __init__(self, code: str, snapshot: PublicRuntimeSessionSnapshot) -> None:
        self.code = code
        self.snapshot = snapshot
        super().__init__(code)


class PublicSessionOpenStage(StrEnum):
    RUNTIME = "runtime"
    ENVIRONMENT = "environment"
    SESSION = "session"


class PublicSessionOpenError(RuntimeError):
    """Typed session-construction failure without leaking private resources."""

    def __init__(self, stage: PublicSessionOpenStage, code: str) -> None:
        self.stage = stage
        self.code = code
        super().__init__(f"{stage.value}:{code}")


@dataclass(frozen=True)
class RuntimeEnvironmentLease:
    environment: WorldEnvironment
    cleanup: Callable[[], object] | None = None
    reconnect_reference: str = ""


class RuntimeEnvironmentFactory(Protocol):
    def __call__(self, session_id: str) -> RuntimeEnvironmentLease | Awaitable[RuntimeEnvironmentLease]: ...


class RuntimeEnvironmentReconnectFactory(Protocol):
    def __call__(
        self, session_id: str, reconnect_reference: str
    ) -> RuntimeEnvironmentLease | Awaitable[RuntimeEnvironmentLease]: ...


class TargetRuntimeFactory(Protocol):
    def __call__(self, session_id: str) -> TargetRuntime | Awaitable[TargetRuntime]: ...


class PublicTaskRequestFactory(Protocol):
    def __call__(self, session_id: str, instruction: str) -> NaturalLanguageTaskRequest: ...


def default_public_task_request(session_id: str, instruction: str) -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(session_id, instruction, TaskBoundary())


class PublicRuntimeSessionHandle(Protocol):
    async def snapshot(self) -> PublicRuntimeSessionSnapshot: ...
    async def events(self, after: int) -> tuple[PublicRuntimeSessionEvent, ...]: ...
    async def start(self, instruction: str) -> PublicRuntimeSessionSnapshot: ...
    async def answer(self, interrupt_id: str, answer: str) -> PublicRuntimeSessionSnapshot: ...
    async def confirm(self, interrupt_id: str, *, approved: bool) -> PublicRuntimeSessionSnapshot: ...
    async def cancel(self, command_id: str) -> PublicRuntimeSessionSnapshot: ...
    async def pause(self, command_id: str) -> PublicRuntimeSessionSnapshot: ...
    async def resume(
        self, command_id: str, checkpoint_id: str
    ) -> PublicRuntimeSessionSnapshot: ...
    async def revise(
        self, command: PublicTaskRevisionCommand
    ) -> PublicRuntimeSessionSnapshot: ...
    async def close(self) -> None: ...


class PublicRuntimeSessionFactory(Protocol):
    async def open(self, session_id: str, expires_at: datetime) -> PublicRuntimeSessionHandle: ...
    async def recover(
        self, session_id: str, checkpoint_id: str, expires_at: datetime
    ) -> PublicRuntimeSessionHandle: ...


@dataclass
class TargetRuntimeSession:
    """Own the private resumable state; callers receive public values only."""

    runtime: TargetRuntime
    lease: RuntimeEnvironmentLease
    session_id: str
    expires_at: datetime
    request_factory: PublicTaskRequestFactory = default_public_task_request
    checkpoint_store: RuntimeCheckpointStore | None = None
    _event_epoch: str = field(default_factory=lambda: secrets.token_urlsafe(18), init=False, repr=False)
    _request: NaturalLanguageTaskRequest | None = field(default=None, init=False, repr=False)
    _admitted: ReadyTask | None = field(default=None, init=False, repr=False)
    _state: RunState | None = field(default=None, init=False, repr=False)
    _status: PublicSessionStatus = field(default=PublicSessionStatus.IDLE, init=False, repr=False)
    _intake_question: PublicPendingQuestion | None = field(default=None, init=False, repr=False)
    _failure: PublicCompletion | None = field(default=None, init=False, repr=False)
    _checkpoint_id: str | None = field(default=None, init=False, repr=False)
    _resume_eligible: bool = field(default=False, init=False, repr=False)
    _last_control_outcome: PublicControlOutcome | None = field(
        default=None, init=False, repr=False
    )
    _progress: list[PublicProgressStep] = field(default_factory=list, init=False, repr=False)
    _events: list[PublicRuntimeSessionEvent] = field(default_factory=list, init=False, repr=False)
    _active: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _cleanup_started: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, TargetRuntime):
            raise TypeError("public Runtime session requires a TargetRuntime")
        if not isinstance(self.lease, RuntimeEnvironmentLease):
            raise TypeError("public Runtime session requires a typed environment lease")
        required_environment_methods = ("reset", "revise_task", "capture", "is_current", "execute")
        if any(
            not callable(getattr(self.lease.environment, method, None))
            for method in required_environment_methods
        ):
            raise TypeError("public Runtime session environment does not implement WorldEnvironment")
        if not callable(self.request_factory):
            raise TypeError("public Runtime session requires a task request factory")

    async def snapshot(self) -> PublicRuntimeSessionSnapshot:
        return self._project()

    async def events(self, after: int) -> tuple[PublicRuntimeSessionEvent, ...]:
        return tuple(event for event in self._events if event.cursor > after)

    async def start(self, instruction: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_open()
            if self._status is not PublicSessionStatus.IDLE or self._active is not None:
                raise PublicSessionConflict("session_not_idle", self._project())
            self._request = self.request_factory(self.session_id, instruction)
            if self._request.request_id != self.session_id or self._request.revision != 1:
                raise TypeError("public task request factory must preserve session identity and initial revision")
            self._status = PublicSessionStatus.RUNNING
            self._emit("RUN_STARTED")
            self._active = asyncio.create_task(self._run_start(), name=f"runtime-session:{self.session_id}")
            return self._project()

    async def answer(self, interrupt_id: str, answer: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_open()
            pending = self._project().pending_question
            if pending is None or pending.interrupt_id != interrupt_id:
                raise PublicSessionConflict("interrupt_mismatch", self._project())
            if self._request is None or self._state is None:
                raise PublicSessionConflict("run_not_resumable", self._project())
            boundary = self._request.boundary
            inputs = dict(boundary.inputs)
            responses = list(inputs.get("user_responses", ()))
            responses.append({"interrupt_id": interrupt_id, "answer": answer})
            revised_boundary = replace(boundary, inputs={**inputs, "user_responses": responses})
            self._request = replace(
                self._request,
                boundary=revised_boundary,
                revision=self._request.revision + 1,
            )
            self._status = PublicSessionStatus.RUNNING
            self._intake_question = None
            self._emit("RUN_STARTED")
            self._active = asyncio.create_task(self._run_answer(), name=f"runtime-resume:{self.session_id}")
            return self._project()

    async def confirm(self, interrupt_id: str, *, approved: bool) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_open()
            pending = self._project().pending_confirmation
            if pending is None or pending.interrupt_id != interrupt_id:
                raise PublicSessionConflict("interrupt_mismatch", self._project())
            if self._admitted is None or self._state is None:
                raise PublicSessionConflict("run_not_resumable", self._project())
            self._status = PublicSessionStatus.RUNNING
            self._emit("RUN_STARTED")
            self._active = asyncio.create_task(
                self._run_confirmation(approved), name=f"runtime-confirm:{self.session_id}"
            )
            return self._project()

    async def cancel(self, command_id: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            state = self._state
            if (
                (state is not None and state.terminal)
                or (state is None and self._active is None)
            ):
                raise PublicSessionConflict("run_not_active", self._project())
            admission = self.runtime.request_control(command_id, RunControlKind.CANCEL)
            if admission.outcome is RunControlAdmissionKind.CONFLICT:
                raise PublicSessionConflict("control_request_conflict", self._project())
            if admission.outcome is RunControlAdmissionKind.DUPLICATE:
                return self._project()
            self._emit("CONTROL_REQUESTED")
            if self._active is None:
                if state is None:
                    raise PublicSessionConflict("run_not_active", self._project())
                outcome = self.runtime.apply_waiting_control(state)
                if outcome is None or outcome.outcome is not RunControlOutcomeKind.CANCELLED:
                    raise PublicSessionConflict("control_boundary_failed", self._project())
                self._status = PublicSessionStatus.CANCELLED
                self._resume_eligible = False
                self._emit("RUN_FINISHED")
            return self._project()

    async def pause(self, command_id: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            if self.checkpoint_store is None:
                raise PublicSessionConflict("pause_unavailable", self._project())
            state = self._state
            if state is not None and state.status is RunStatus.PAUSED:
                existing = await self.checkpoint_store.command_outcome(
                    self.session_id, command_id
                )
                if existing is not None and existing.checkpoint_id == state.durable_checkpoint_id:
                    return self._project()
                raise PublicSessionConflict("run_not_active", self._project())
            if (
                (state is not None and state.terminal)
                or (state is None and self._active is None)
            ):
                raise PublicSessionConflict("run_not_active", self._project())
            admission = self.runtime.request_control(command_id, RunControlKind.PAUSE)
            if admission.outcome is RunControlAdmissionKind.CONFLICT:
                raise PublicSessionConflict("control_request_conflict", self._project())
            if admission.outcome is RunControlAdmissionKind.DUPLICATE:
                return self._project()
            self._last_control_outcome = None
            self._emit("CONTROL_REQUESTED")
            if self._active is None:
                if state is None or self._admitted is None:
                    raise PublicSessionConflict("run_not_active", self._project())
                outcome = self.runtime.apply_waiting_control(state)
                if (
                    outcome is None
                    or outcome.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED
                ):
                    raise PublicSessionConflict("control_boundary_failed", self._project())
                await self._settle_pause_boundary(self.runtime, self._admitted.task, state)
            return self._project()

    async def resume(
        self,
        command_id: str,
        checkpoint_id: str,
    ) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_open()
            store = self.checkpoint_store
            if store is None:
                raise PublicSessionConflict("resume_unavailable", self._project())
            try:
                existing = await store.resume_outcome(self.session_id, command_id)
            except Exception as exc:
                raise PublicSessionConflict("resume_persistence_failed", self._project()) from exc
            if existing is not None:
                if existing.checkpoint_id == checkpoint_id:
                    return self._project()
                raise PublicSessionConflict("resume_command_conflict", self._project())
            state = self._state
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not self._resume_eligible
                or self._checkpoint_id != checkpoint_id
                or state.durable_checkpoint_id != checkpoint_id
            ):
                raise PublicSessionConflict("checkpoint_mismatch", self._project())
            try:
                await store.commit_resume(
                    RuntimeCheckpointResumeOutcome(
                        self.session_id,
                        command_id,
                        checkpoint_id,
                    )
                )
            except RuntimeCheckpointError as exc:
                raise PublicSessionConflict(exc.code, self._project()) from exc
            self.runtime.resume_control(state, command_id)
            self._resume_eligible = False
            self._status = _public_status(state.status)
            self._emit("RUN_FINISHED" if state.terminal else "RUN_RESUMED")
            if state.status is RunStatus.RUNNING:
                if self._admitted is None:
                    raise PublicSessionConflict("run_not_resumable", self._project())
                self._active = asyncio.create_task(
                    self._run_continue(),
                    name=f"runtime-checkpoint-resume:{self.session_id}",
                )
            return self._project()

    async def revise(
        self, command: PublicTaskRevisionCommand
    ) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            store = self.checkpoint_store
            if store is None:
                raise PublicSessionConflict("revision_unavailable", self._project())
            admitted_at_entry = self._admitted
            state_at_entry = self._state
            command_matches_entry = (
                admitted_at_entry is not None
                and state_at_entry is not None
                and admitted_at_entry.task.revision == command.expected_task_revision
                and self._status is command.expected_run_status
            )
            checkpoint_matches_entry = (
                self._checkpoint_id == command.expected_checkpoint_id
            )
            try:
                existing = await store.revision_outcome(
                    self.session_id,
                    command.command_id,
                )
            except Exception as exc:
                raise PublicSessionConflict(
                    "revision_persistence_failed",
                    self._project(),
                ) from exc
            if existing is not None:
                if existing.payload_digest != command.payload_digest:
                    raise PublicSessionConflict(
                        "command_identity_reused",
                        self._project(),
                    )
                self._set_revision_outcome(
                    existing.outcome,
                    command.command_id,
                    checkpoint_id=(
                        existing.result_checkpoint_id
                        if existing.outcome == "revised"
                        else None
                    ),
                    message=existing.message,
                )
                if existing.outcome == "revised":
                    return self._project()
                raise PublicSessionConflict(existing.outcome, self._project())
            if admitted_at_entry is None or state_at_entry is None:
                raise PublicSessionConflict("run_not_revisable", self._project())
            if not command_matches_entry:
                raise PublicSessionConflict("stale_command", self._project())
            if not checkpoint_matches_entry:
                raise PublicSessionConflict("checkpoint_mismatch", self._project())
            await self._ensure_revision_pause(command.command_id)
            state = self._state
            source_checkpoint_id = self._checkpoint_id
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not source_checkpoint_id
                or state.durable_checkpoint_id != source_checkpoint_id
            ):
                raise PublicSessionConflict("revision_pause_failed", self._project())
            try:
                source_checkpoint = await store.load(
                    self.session_id,
                    source_checkpoint_id,
                )
            except Exception as exc:
                self._set_revision_outcome(
                    "revision_persistence_failed",
                    command.command_id,
                    message=type(exc).__name__,
                )
                self._emit("CONTROL_FAILED")
                raise PublicSessionConflict(
                    "revision_persistence_failed",
                    self._project(),
                ) from exc
            if source_checkpoint is None:
                self._set_revision_outcome("checkpoint_not_found", command.command_id)
                self._emit("CONTROL_FAILED")
                raise PublicSessionConflict("checkpoint_not_found", self._project())
            if state.execution_count > 0:
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    "effect_reconciliation_required",
                    "The current revision has committed GUI effects.",
                )
            compiled = await self.runtime.compile_task_revision(
                self._admitted,
                command.text,
            )
            revised = compiled.intake
            if not isinstance(revised, ReadyTask):
                code, message = _revision_rejection(compiled.compiler, revised)
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    code,
                    message,
                )
            assert isinstance(revised, ReadyTask)
            current = self._admitted
            assert current is not None
            runtime = self._runtime_with_projection()
            try:
                candidate = await runtime.prepare_paused_task_revision(
                    self.lease.environment,
                    current.task,
                    revised.task,
                    state,
                )
                runtime.rebind_checkpoint_history(
                    task_id=self.session_id,
                    current_revision=current.task.revision,
                    revised_revision=revised.task.revision,
                )
                checkpoint = RuntimeCheckpoint.capture(
                    session_id=self.session_id,
                    task=revised.task,
                    state=candidate,
                    model_history=await runtime.persist_checkpoint_history(),
                    environment_reference=self.lease.reconnect_reference,
                )
            except Exception as exc:
                await self._restore_revision_source(runtime, source_checkpoint)
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    "revision_failed",
                    type(exc).__name__,
                )
                raise AssertionError("revision rejection must raise") from exc
            revision_outcome = RuntimeCheckpointRevisionOutcome(
                self.session_id,
                command.command_id,
                source_checkpoint_id,
                checkpoint.checkpoint_id,
                revised.task.revision,
                "revised",
                command.payload_digest,
                "",
            )
            try:
                await store.commit_revision(checkpoint, revision_outcome)
            except Exception as exc:
                await self._restore_revision_source(runtime, source_checkpoint)
                self._set_revision_outcome(
                    "revision_persistence_failed",
                    command.command_id,
                    message=type(exc).__name__,
                )
                self._emit("CONTROL_FAILED")
                raise PublicSessionConflict(
                    "revision_persistence_failed",
                    self._project(),
                ) from exc
            candidate.commit_durable_pause(checkpoint.checkpoint_id)
            self._request = _request_from_task(revised.task)
            self._admitted = revised
            self._state = candidate
            self._status = PublicSessionStatus.PAUSED
            self._checkpoint_id = checkpoint.checkpoint_id
            self._resume_eligible = checkpoint.resume_eligible
            self._set_revision_outcome(
                "revised",
                command.command_id,
                checkpoint_id=checkpoint.checkpoint_id,
            )
            self._emit("TASK_REVISED")
            return self._project()

    async def _ensure_revision_pause(self, command_id: str) -> None:
        state = self._state
        if state is not None and state.status is RunStatus.PAUSED:
            return
        pause_id = _revision_pause_command_id(command_id)
        admission = self.runtime.request_control(pause_id, RunControlKind.PAUSE)
        if admission.outcome is RunControlAdmissionKind.CONFLICT:
            raise PublicSessionConflict("control_request_conflict", self._project())
        if admission.outcome is not RunControlAdmissionKind.DUPLICATE:
            self._last_control_outcome = None
            self._emit("CONTROL_REQUESTED")
        active = self._active
        if active is None:
            if state is None or self._admitted is None:
                raise PublicSessionConflict("run_not_active", self._project())
            outcome = self.runtime.apply_waiting_control(state)
            if (
                outcome is None
                or outcome.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED
            ):
                raise PublicSessionConflict("control_boundary_failed", self._project())
            await self._settle_pause_boundary(
                self._runtime_with_projection(),
                self._admitted.task,
                state,
            )
            return
        await active

    async def _reject_revision(
        self,
        command: PublicTaskRevisionCommand,
        source_checkpoint_id: str,
        task_revision: int,
        code: str,
        message: str,
    ) -> None:
        store = self.checkpoint_store
        assert store is not None
        message = message[:2000]
        outcome = RuntimeCheckpointRevisionOutcome(
            self.session_id,
            command.command_id,
            source_checkpoint_id,
            source_checkpoint_id,
            task_revision,
            code,
            command.payload_digest,
            message,
        )
        try:
            await store.commit_revision(None, outcome)
        except Exception as exc:
            self._set_revision_outcome(
                "revision_persistence_failed",
                command.command_id,
                message=type(exc).__name__,
            )
            self._emit("CONTROL_FAILED")
            raise PublicSessionConflict(
                "revision_persistence_failed",
                self._project(),
            ) from exc
        self._set_revision_outcome(code, command.command_id, message=message)
        self._emit("TASK_REVISION_REJECTED")
        raise PublicSessionConflict(code, self._project())

    async def _restore_revision_source(
        self,
        runtime: TargetRuntime,
        checkpoint: RuntimeCheckpoint,
    ) -> None:
        task = checkpoint.restore_task()
        await runtime.restore_persisted_checkpoint_history(
            checkpoint.model_history,
            task_id=task.task_id,
            task_revision=task.revision,
        )
        await self.lease.environment.revise_task(task)
        self._state = await runtime.build_loop().restore_paused(
            self.lease.environment,
            task,
            checkpoint.restore_run_facts(),
            checkpoint.checkpoint_id,
        )
        self._request = _request_from_task(task)
        self._admitted = ReadyTask(task.task_id, task)
        self._status = PublicSessionStatus.PAUSED
        self._checkpoint_id = checkpoint.checkpoint_id
        self._resume_eligible = checkpoint.resume_eligible

    def _set_revision_outcome(
        self,
        outcome: str,
        command_id: str,
        *,
        checkpoint_id: str | None = None,
        message: str = "",
    ) -> None:
        public_outcome = {
            "revised": "revised",
            "revision_needs_input": "needs_input",
            "revision_no_change": "no_change",
            "revision_new_task_suggested": "new_task_suggested",
            "revision_unsupported": "unsupported",
            "revision_failed": "failed",
            "revision_persistence_failed": "failed",
            "checkpoint_not_found": "failed",
            "effect_reconciliation_required": "effect_reconciliation_required",
        }[outcome]
        self._last_control_outcome = PublicControlOutcome(
            command_id,
            "revise",
            public_outcome,  # type: ignore[arg-type]
            outcome,
            checkpoint_id,
            message,
        )

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            active = self._active
        if active is not None and not active.done():
            active.add_done_callback(lambda _task: asyncio.create_task(self._cleanup_once()))
            return
        await self._cleanup_once()

    async def _run_start(self) -> None:
        assert self._request is not None
        session_runtime = self._runtime_with_projection()
        try:
            outcome = await session_runtime.run_request(self.lease.environment, self._request)
            if isinstance(outcome.intake, ReadyTask):
                self._admitted = outcome.intake
                self._state = outcome.state
                if outcome.state is not None:
                    await self._settle_pause_boundary(
                        session_runtime, outcome.intake.task, outcome.state
                    )
            elif isinstance(outcome.intake, TaskInputRequired):
                self._fail(outcome.intake.reason_code, outcome.intake.question)
            else:
                code = (
                    outcome.intake.reason_code
                    if isinstance(outcome.intake, TaskPolicyRejected | TaskUnsupported)
                    else "task_intake_failed"
                )
                self._fail(code)
        except BaseException as exc:
            self._fail("runtime_session_start_failed", type(exc).__name__)
        finally:
            self._active = None
            if self._closed:
                await self._cleanup_once()

    async def _run_answer(self) -> None:
        assert self._request is not None and self._state is not None
        try:
            outcome = await self._runtime_with_projection().resume_request(
                self.lease.environment, self._state, self._request
            )
            if not isinstance(outcome.intake, ReadyTask) or outcome.state is None:
                self._fail(getattr(outcome.intake, "reason_code", "task_revision_failed"))
            else:
                self._admitted = outcome.intake
                self._state = outcome.state
                await self._settle_pause_boundary(
                    self._runtime_with_projection(), outcome.intake.task, outcome.state
                )
        except BaseException as exc:
            self._fail("runtime_session_resume_failed", type(exc).__name__)
        finally:
            self._active = None
            if self._closed:
                await self._cleanup_once()

    async def _run_confirmation(self, approved: bool) -> None:
        assert self._admitted is not None and self._state is not None
        try:
            self._state = await self._runtime_with_projection().resume_confirmation(
                self.lease.environment,
                self._admitted.task,
                self._state,
                approved=approved,
            )
            await self._settle_pause_boundary(
                self._runtime_with_projection(), self._admitted.task, self._state
            )
        except BaseException as exc:
            self._fail("runtime_session_confirmation_failed", type(exc).__name__)
        finally:
            self._active = None
            if self._closed:
                await self._cleanup_once()

    async def _run_continue(self) -> None:
        assert self._admitted is not None and self._state is not None
        runtime = self._runtime_with_projection()
        try:
            self._state = await runtime.continue_task(
                self.lease.environment,
                self._admitted.task,
                self._state,
            )
            await self._settle_pause_boundary(
                runtime,
                self._admitted.task,
                self._state,
            )
        except BaseException as exc:
            self._fail("runtime_session_resume_failed", type(exc).__name__)
        finally:
            self._active = None
            if self._closed:
                await self._cleanup_once()

    def _runtime_with_projection(self) -> TargetRuntime:
        projection = _SessionProjectionSink(self)
        return replace(
            self.runtime,
            trace_sink=FanoutRunTraceSink((self.runtime.trace_sink, projection)),
        )

    async def _settle_pause_boundary(
        self,
        runtime: TargetRuntime,
        task: TaskGoal,
        state: RunState,
    ) -> None:
        boundary = state.control_boundary
        if (
            boundary is None
            or boundary.kind is not RunControlKind.PAUSE
            or boundary.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED
        ):
            return
        store = self.checkpoint_store
        if store is None:
            raise RuntimeError("Runtime reached a pause boundary without a checkpoint store")
        try:
            checkpoint = RuntimeCheckpoint.capture(
                session_id=self.session_id,
                task=task,
                state=state,
                model_history=await runtime.persist_checkpoint_history(),
                environment_reference=self.lease.reconnect_reference,
            )
            await store.commit_pause(
                checkpoint,
                RuntimeCheckpointCommandOutcome(
                    self.session_id,
                    boundary.command_id,
                    checkpoint.checkpoint_id,
                ),
            )
        except Exception:
            self._last_control_outcome = PublicControlOutcome(
                boundary.command_id,
                "pause",
                "failed",
                "pause_persistence_failed",
            )
            self._emit("CONTROL_FAILED")
            try:
                await runtime.recover_pause_persistence_failure(
                    self.lease.environment,
                    task,
                    state,
                    f"pause-persistence-failed:{boundary.command_id}",
                )
            except Exception as exc:
                self._fail(
                    "pause_persistence_failed",
                    str(getattr(exc, "reason_code", "")) or type(exc).__name__,
                )
                return
            if state.status is RunStatus.RUNNING:
                self._state = await runtime.continue_task(
                    self.lease.environment,
                    task,
                    state,
                )
            return
        state.commit_durable_pause(checkpoint.checkpoint_id)
        self._checkpoint_id = checkpoint.checkpoint_id
        self._resume_eligible = checkpoint.resume_eligible
        self._last_control_outcome = PublicControlOutcome(
            boundary.command_id,
            "pause",
            "paused",
            "pause_checkpoint_committed",
            checkpoint.checkpoint_id,
        )
        self._status = PublicSessionStatus.PAUSED
        self._emit("RUN_PAUSED")

    def _observe_started(self, task: TaskGoal, state: RunState) -> None:
        self._admitted = ReadyTask(task.task_id, task)
        self._state = state

    def _observe_step(self, step_number: int, result: StepResult) -> None:
        kind = getattr(result.decision, "kind", "progress")
        kind_value = getattr(kind, "value", str(kind))
        labels = {
            "ask_user": "Waiting for your input",
            "select_action": "Completed an interaction",
            "request_observation": "Checked the current page",
            "final_response": "Prepared the final response",
            "policy_failure": "Runtime could not continue",
        }
        self._progress.append(
            PublicProgressStep(step_number, str(result.status_after), labels.get(kind_value, "Made progress"))
        )
        self._emit("STEP_FINISHED")

    def _observe_paused(self, state: RunState) -> None:
        self._state = state
        self._status = _public_status(state.status)
        self._emit("RUN_FINISHED")

    def _observe_finished(self, state: RunState) -> None:
        self._observe_paused(state)

    def _observe_resumed(self) -> None:
        self._status = PublicSessionStatus.RUNNING

    def _observe_error(self, error: BaseException, state: RunState) -> None:
        self._state = state
        self._fail("runtime_run_failed", type(error).__name__)

    def _fail(self, code: str, message: str = "Runtime session failed.") -> None:
        if self._status is PublicSessionStatus.FAILED and self._failure is not None:
            return
        self._status = PublicSessionStatus.FAILED
        self._failure = PublicCompletion("failure", code, message)
        self._emit("RUN_ERROR")

    def _emit(self, event_type: str) -> None:
        cursor = len(self._events) + 1
        snapshot = self._project(event_cursor=cursor)
        self._events.append(
            PublicRuntimeSessionEvent(
                self.session_id,
                self._event_epoch,
                cursor,
                event_type,
                snapshot,
            )
        )

    def _project(self, *, event_cursor: int | None = None) -> PublicRuntimeSessionSnapshot:
        state = self._state
        status = self._status if self._active is not None or state is None else _public_status(state.status)
        pending_question = self._intake_question
        pending_confirmation = None
        if state is not None and state.last_step is not None:
            if status is PublicSessionStatus.WAITING_USER and isinstance(state.last_step.decision, AskUser):
                decision = state.last_step.decision
                identity = decision.tool_call_id or decision.context_id
                pending_question = PublicPendingQuestion(
                    f"ask:{identity}", decision.question, decision.requested_fields
                )
            if status is PublicSessionStatus.WAITING_CONFIRMATION and state.last_step.confirmation is not None:
                risk = state.last_step.confirmation
                pending_confirmation = PublicPendingConfirmation(
                    f"confirmation:{risk.subject_id}", risk.reason, str(risk.risk)
                )
        request = self._request
        task = self._admitted.task if self._admitted is not None else None
        completion = self._failure or _completion(state, status)
        return PublicRuntimeSessionSnapshot(
            self.session_id,
            self.expires_at,
            status,
            self._event_epoch,
            len(self._events) if event_cursor is None else event_cursor,
            capabilities=(
                BASE_PUBLIC_SESSION_CAPABILITIES
                | ({PublicSessionCapability.PAUSE_TASK} if self.checkpoint_store is not None else set())
                | (
                    {PublicSessionCapability.RESUME_TASK}
                    if status is PublicSessionStatus.PAUSED and self._resume_eligible
                    else set()
                )
                | (
                    {PublicSessionCapability.REVISE_TASK}
                    if self.checkpoint_store is not None
                    and status
                    in {
                        PublicSessionStatus.RUNNING,
                        PublicSessionStatus.WAITING_USER,
                        PublicSessionStatus.WAITING_CONFIRMATION,
                        PublicSessionStatus.PAUSED,
                    }
                    else set()
                )
            ),
            task_id=task.task_id if task is not None else (request.request_id if request else None),
            task_revision=task.revision if task is not None else (request.revision if request else 0),
            task_text=task.instruction if task is not None else (request.instruction if request else None),
            pending_question=pending_question,
            pending_confirmation=pending_confirmation,
            completion=completion,
            progress=tuple(self._progress),
            checkpoint_id=self._checkpoint_id,
            resume_eligible=self._resume_eligible,
            last_control_outcome=self._last_control_outcome,
        )

    def _require_open(self) -> None:
        if self._closed:
            raise PublicSessionConflict("session_closed", self._project())
        if self._active is not None:
            raise PublicSessionConflict("run_active", self._project())

    async def _cleanup_once(self) -> None:
        if self._cleanup_started:
            return
        self._cleanup_started = True
        if self.lease.cleanup is None:
            return
        result = self.lease.cleanup()
        if inspect.isawaitable(result):
            await result


@dataclass(frozen=True)
class TargetRuntimeSessionFactory:
    runtime_factory: TargetRuntimeFactory
    environment_factory: RuntimeEnvironmentFactory
    request_factory: PublicTaskRequestFactory = default_public_task_request
    checkpoint_store: RuntimeCheckpointStore | None = None
    environment_reconnector: RuntimeEnvironmentReconnectFactory | None = None

    async def open(self, session_id: str, expires_at: datetime) -> TargetRuntimeSession:
        if not callable(self.request_factory):
            raise PublicSessionOpenError(PublicSessionOpenStage.SESSION, "request_factory_invalid")
        try:
            runtime = self.runtime_factory(session_id)
            if inspect.isawaitable(runtime):
                runtime = await runtime
            if not isinstance(runtime, TargetRuntime):
                raise TypeError("Runtime factory must return TargetRuntime")
        except Exception as exc:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.RUNTIME,
                "runtime_factory_failed",
            ) from exc

        lease: RuntimeEnvironmentLease | None = None
        try:
            candidate = self.environment_factory(session_id)
            if inspect.isawaitable(candidate):
                candidate = await candidate
            if not isinstance(candidate, RuntimeEnvironmentLease):
                raise TypeError("Runtime environment factory must return a typed lease")
            lease = candidate
        except Exception as exc:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_factory_failed",
            ) from exc

        try:
            return TargetRuntimeSession(
                runtime,
                lease,
                session_id,
                expires_at,
                self.request_factory,
                self.checkpoint_store,
            )
        except Exception as exc:
            await _cleanup_environment_lease(lease)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "session_initialization_failed",
            ) from exc

    async def recover(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> TargetRuntimeSession:
        store = self.checkpoint_store
        if store is None:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "checkpoint_store_unavailable",
            )
        try:
            checkpoint = await store.load(session_id, checkpoint_id)
            resume_outcome = await store.checkpoint_resume_outcome(
                session_id, checkpoint_id
            )
            revision_outcome = await store.checkpoint_revision_outcome(
                session_id, checkpoint_id
            )
        except Exception as exc:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "checkpoint_invalid",
            ) from exc
        if checkpoint is None:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "checkpoint_not_found",
            )
        if resume_outcome is not None:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "checkpoint_already_resumed",
            )
        if revision_outcome is not None:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "checkpoint_already_revised",
            )
        reconnector = self.environment_reconnector
        if (
            not checkpoint.resume_eligible
            or not checkpoint.environment_reference
            or reconnector is None
        ):
            raise PublicSessionOpenError(
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_not_reconnectable",
            )
        try:
            runtime = self.runtime_factory(session_id)
            if inspect.isawaitable(runtime):
                runtime = await runtime
            if not isinstance(runtime, TargetRuntime):
                raise TypeError("Runtime factory must return TargetRuntime")
        except Exception as exc:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.RUNTIME,
                "runtime_factory_failed",
            ) from exc
        lease: RuntimeEnvironmentLease | None = None
        try:
            candidate = reconnector(session_id, checkpoint.environment_reference)
            if inspect.isawaitable(candidate):
                candidate = await candidate
            if not isinstance(candidate, RuntimeEnvironmentLease):
                raise TypeError("environment reconnector must return a typed lease")
            if candidate.reconnect_reference != checkpoint.environment_reference:
                raise ValueError("reconnected environment reference changed")
            lease = candidate
        except Exception as exc:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_not_reconnectable",
            ) from exc
        try:
            task = checkpoint.restore_task()
            facts = checkpoint.restore_run_facts()
            await runtime.restore_persisted_checkpoint_history(
                checkpoint.model_history,
                task_id=task.task_id,
                task_revision=task.revision,
            )
            state = await runtime.restore_paused_checkpoint(
                lease.environment,
                task,
                facts,
                checkpoint.checkpoint_id,
            )
            session = TargetRuntimeSession(
                runtime,
                lease,
                session_id,
                expires_at,
                self.request_factory,
                store,
            )
            session._request = _request_from_task(task)
            session._admitted = ReadyTask(session_id, task)
            session._state = state
            session._status = PublicSessionStatus.PAUSED
            session._checkpoint_id = checkpoint.checkpoint_id
            session._resume_eligible = True
            session._last_control_outcome = PublicControlOutcome(
                checkpoint.pause_command_id,
                "pause",
                "paused",
                "pause_checkpoint_committed",
                checkpoint.checkpoint_id,
            )
            session._emit("SESSION_RECOVERED")
            return session
        except Exception as exc:
            await _cleanup_environment_lease(lease)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "checkpoint_restore_failed",
            ) from exc


def _request_from_task(task: TaskGoal) -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(
        task.task_id,
        task.instruction,
        TaskBoundary(
            constraints=task.constraints,
            allowed_effects=task.allowed_effects,
            forbidden_effects=task.forbidden_effects,
            inputs=task.inputs,
            success_criteria=task.success_criteria,
            requested_outputs=task.requested_outputs,
            risk_profile=task.risk_profile,
            material_bindings=task.material_bindings,
            loop_budget=task.loop_budget,
            evaluation_spec=task.evaluation_spec,
        ),
        source_ref="checkpoint_restore",
        revision=task.revision,
    )


async def _cleanup_environment_lease(lease: RuntimeEnvironmentLease) -> None:
    if lease.cleanup is None:
        return
    result = lease.cleanup()
    if inspect.isawaitable(result):
        await result


def _revision_pause_command_id(command_id: str) -> str:
    digest = hashlib.sha256(command_id.encode()).hexdigest()[:32]
    return f"revision-pause:{digest}"


def _revision_rejection(
    compiler: object,
    intake: object,
) -> tuple[str, str]:
    if isinstance(intake, TaskInputRequired):
        return "revision_needs_input", intake.question
    if isinstance(intake, TaskPolicyRejected | TaskUnsupported):
        return "revision_unsupported", intake.reason_code
    if isinstance(
        compiler,
        RevisionNeedsInput
        | RevisionNoChange
        | RevisionNewTaskSuggested
        | RevisionUnsupported
        | RevisionFailed,
    ):
        message = (
            compiler.question
            if isinstance(compiler, RevisionNeedsInput)
            else compiler.reason
        )
        return revision_outcome_code(compiler), message
    if isinstance(compiler, RevisionReady):
        return "revision_failed", "task_intake_failed"
    return "revision_failed", "invalid_task_revision_outcome"


@dataclass(frozen=True)
class _SessionProjectionSink(NullRunTraceSink):
    session: TargetRuntimeSession

    def run_started(self, task: object, state: object) -> None:
        if isinstance(task, TaskGoal) and isinstance(state, RunState):
            self.session._observe_started(task, state)

    def step_completed(self, step_number: int, result: object) -> None:
        if isinstance(result, StepResult):
            self.session._observe_step(step_number, result)

    def run_paused(self, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_paused(state)

    def run_finished(self, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_finished(state)

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None:
        del kind, details
        self.session._observe_resumed()

    def run_error(self, error: BaseException, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_error(error, state)


def _public_status(status: RunStatus) -> PublicSessionStatus:
    return {
        RunStatus.RUNNING: PublicSessionStatus.RUNNING,
        RunStatus.PAUSED: PublicSessionStatus.PAUSED,
        RunStatus.WAITING_USER: PublicSessionStatus.WAITING_USER,
        RunStatus.WAITING_CONFIRMATION: PublicSessionStatus.WAITING_CONFIRMATION,
        RunStatus.DONE: PublicSessionStatus.DONE,
        RunStatus.BLOCKED: PublicSessionStatus.BLOCKED,
        RunStatus.CANCELLED: PublicSessionStatus.CANCELLED,
        RunStatus.FAILED: PublicSessionStatus.FAILED,
    }[status]


def _completion(state: RunState | None, status: PublicSessionStatus) -> PublicCompletion | None:
    if state is None or status not in {
        PublicSessionStatus.DONE,
        PublicSessionStatus.BLOCKED,
        PublicSessionStatus.CANCELLED,
        PublicSessionStatus.FAILED,
    }:
        return None
    if status is PublicSessionStatus.CANCELLED:
        return PublicCompletion(
            "cancelled",
            "user_cancelled",
            "Runtime cancelled the task at a safe execution boundary.",
        )
    evaluation = state.current_task_evaluation
    outcome = evaluation.outcome if evaluation is not None else None
    if evaluation is not None and outcome is not None and outcome.kind is TaskOutcomeKind.TERMINAL_SUCCESS:
        return PublicCompletion("success", outcome.code, evaluation.reason, outcome.evidence_refs)
    if evaluation is not None and outcome is not None and outcome.kind is TaskOutcomeKind.TERMINAL_FAILURE:
        return PublicCompletion("failure", outcome.code, evaluation.reason, outcome.evidence_refs)
    failure = state.runtime_failure
    if failure is not None:
        return PublicCompletion("failure", failure.code, "Runtime could not complete the task.")
    control = state.control_termination
    if control is not None:
        return PublicCompletion("blocked", str(control.kind), "Runtime stopped before completion.")
    return PublicCompletion("blocked", "runtime_blocked", evaluation.reason if evaluation else "Task blocked.")
