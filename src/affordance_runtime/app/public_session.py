"""Versioned public session boundary over the single TargetRuntime loop."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from affordance_runtime.agent.decisions import AskUser
from affordance_runtime.agent.observability import FanoutRunTraceSink, NullRunTraceSink
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
from affordance_runtime.world.environment import WorldEnvironment

from .runtime import TargetRuntime

PUBLIC_SESSION_SCHEMA_VERSION = "affordance-runtime.session.v1"


class PublicSessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class PublicSessionCapability(StrEnum):
    START_TASK = "start_task"
    ANSWER_QUESTION = "answer_question"
    APPROVE_ACTION = "approve_action"
    REJECT_ACTION = "reject_action"
    CLOSE_SESSION = "close_session"


PUBLIC_SESSION_CAPABILITIES = frozenset(PublicSessionCapability)


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
    outcome: Literal["success", "failure", "blocked"]
    code: str
    message: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicProgressStep:
    step: int
    status: str
    label: str


@dataclass(frozen=True)
class PublicRuntimeSessionSnapshot:
    session_id: str
    expires_at: datetime
    status: PublicSessionStatus
    event_cursor: int
    capabilities: frozenset[PublicSessionCapability] = PUBLIC_SESSION_CAPABILITIES
    task_id: str | None = None
    task_revision: int = 0
    task_text: str | None = None
    pending_question: PublicPendingQuestion | None = None
    pending_confirmation: PublicPendingConfirmation | None = None
    completion: PublicCompletion | None = None
    progress: tuple[PublicProgressStep, ...] = ()
    schema_version: str = PUBLIC_SESSION_SCHEMA_VERSION


@dataclass(frozen=True)
class PublicRuntimeSessionEvent:
    session_id: str
    cursor: int
    type: str
    snapshot: PublicRuntimeSessionSnapshot
    schema_version: str = PUBLIC_SESSION_SCHEMA_VERSION


class PublicSessionConflict(RuntimeError):
    def __init__(self, code: str, snapshot: PublicRuntimeSessionSnapshot) -> None:
        self.code = code
        self.snapshot = snapshot
        super().__init__(code)


@dataclass(frozen=True)
class RuntimeEnvironmentLease:
    environment: WorldEnvironment
    cleanup: Callable[[], object] | None = None


class RuntimeEnvironmentFactory(Protocol):
    def __call__(self, session_id: str) -> RuntimeEnvironmentLease | Awaitable[RuntimeEnvironmentLease]: ...


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
    async def close(self) -> None: ...


@dataclass
class TargetRuntimeSession:
    """Own the private resumable state; callers receive public values only."""

    runtime: TargetRuntime
    lease: RuntimeEnvironmentLease
    session_id: str
    expires_at: datetime
    request_factory: PublicTaskRequestFactory = default_public_task_request
    _request: NaturalLanguageTaskRequest | None = field(default=None, init=False, repr=False)
    _admitted: ReadyTask | None = field(default=None, init=False, repr=False)
    _state: RunState | None = field(default=None, init=False, repr=False)
    _status: PublicSessionStatus = field(default=PublicSessionStatus.IDLE, init=False, repr=False)
    _intake_question: PublicPendingQuestion | None = field(default=None, init=False, repr=False)
    _failure: PublicCompletion | None = field(default=None, init=False, repr=False)
    _progress: list[PublicProgressStep] = field(default_factory=list, init=False, repr=False)
    _events: list[PublicRuntimeSessionEvent] = field(default_factory=list, init=False, repr=False)
    _active: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _cleanup_started: bool = field(default=False, init=False, repr=False)

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
        except BaseException as exc:
            self._fail("runtime_session_confirmation_failed", type(exc).__name__)
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
        self._events.append(PublicRuntimeSessionEvent(self.session_id, cursor, event_type, snapshot))

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
            len(self._events) if event_cursor is None else event_cursor,
            task_id=task.task_id if task is not None else (request.request_id if request else None),
            task_revision=task.revision if task is not None else (request.revision if request else 0),
            task_text=task.instruction if task is not None else (request.instruction if request else None),
            pending_question=pending_question,
            pending_confirmation=pending_confirmation,
            completion=completion,
            progress=tuple(self._progress),
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
    runtime: TargetRuntime
    environment_factory: RuntimeEnvironmentFactory
    request_factory: PublicTaskRequestFactory = default_public_task_request

    async def open(self, session_id: str, expires_at: datetime) -> TargetRuntimeSession:
        lease = self.environment_factory(session_id)
        if inspect.isawaitable(lease):
            lease = await lease
        if not isinstance(lease, RuntimeEnvironmentLease):
            raise TypeError("Runtime environment factory must return a typed lease")
        return TargetRuntimeSession(
            self.runtime,
            lease,
            session_id,
            expires_at,
            self.request_factory,
        )


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
        RunStatus.WAITING_USER: PublicSessionStatus.WAITING_USER,
        RunStatus.WAITING_CONFIRMATION: PublicSessionStatus.WAITING_CONFIRMATION,
        RunStatus.DONE: PublicSessionStatus.DONE,
        RunStatus.BLOCKED: PublicSessionStatus.BLOCKED,
        RunStatus.CANCELLED: PublicSessionStatus.FAILED,
        RunStatus.FAILED: PublicSessionStatus.FAILED,
    }[status]


def _completion(state: RunState | None, status: PublicSessionStatus) -> PublicCompletion | None:
    if state is None or status not in {
        PublicSessionStatus.DONE,
        PublicSessionStatus.BLOCKED,
        PublicSessionStatus.FAILED,
    }:
        return None
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
