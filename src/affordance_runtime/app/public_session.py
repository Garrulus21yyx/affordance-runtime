"""单一 TargetRuntime 循环之上的版本化公共 Session 边界。"""

from __future__ import annotations

import asyncio
import inspect
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import cast

from affordance_runtime.actions.reconciliation import (
    EffectReconciliation,
    EffectReconciliationStatus,
    EffectRevisionDisposition,
    assess_effect_revision,
)
from affordance_runtime.agent.interactions import (
    FreeTextResponse,
    InteractionRequest,
    InteractionResponse,
    StructuredFieldsResponse,
    TextFieldValue,
    admit_interaction_response,
    interaction_response_public_value,
)
from affordance_runtime.agent.observability import FanoutRunTraceSink
from affordance_runtime.agent.run_control import (
    RunControlAdmissionKind,
    RunControlKind,
    RunControlOutcomeKind,
)
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.evaluation.contracts import (
    TaskEvaluationStatus,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import (
    NaturalLanguageTaskRequest,
    ReadyTask,
    TaskBoundary,
    TaskInputRequired,
    TaskIntakeOutcome,
    TaskPolicyRejected,
    TaskUnsupported,
)

from .checkpoint import (
    RuntimeCheckpoint,
    RuntimeCheckpointCommandOutcome,
    RuntimeCheckpointError,
    RuntimeCheckpointResumeOutcome,
    RuntimeCheckpointRevisionOutcome,
    RuntimeCheckpointStore,
)

# 兼容门面：外部调用方继续从 ``app.public_session`` 导入公共合同；
# 合同定义本身由 public_session_contracts 拥有，不能在此复制一份。
from .public_session_contracts import (
    BASE_PUBLIC_SESSION_CAPABILITIES,
    PUBLIC_SESSION_CAPABILITIES,
    PUBLIC_SESSION_SCHEMA_VERSION,
    PUBLIC_SESSION_V3_SCHEMA_VERSION,
    LiveCheckpointAdmission,
    LiveCheckpointConflict,
    LiveCheckpointCurrent,
    LiveCheckpointUnavailable,
    PublicAgentIntent,
    PublicArtifact,
    PublicCommandAccepted,
    PublicCommandAdmission,
    PublicCommandConflict,
    PublicCommandRejected,
    PublicCommandUnsupported,
    PublicCompletion,
    PublicCompletionBlock,
    PublicConfirmationRequired,
    PublicConflictCode,
    PublicControlOutcome,
    PublicEffectReconciliation,
    PublicEvidenceSummary,
    PublicFailure,
    PublicFeedSource,
    PublicGoalAccepted,
    PublicInteractionRequest,
    PublicInteractionRequested,
    PublicPendingConfirmation,
    PublicProgressStep,
    PublicRejectedCode,
    PublicRevisionApplied,
    PublicRevisionConversationContext,
    PublicRevisionConversationTurn,
    PublicRuntimeActivity,
    PublicRuntimeRecoveryInspector,
    PublicRuntimeSessionEvent,
    PublicRuntimeSessionFactory,
    PublicRuntimeSessionHandle,
    PublicRuntimeSessionSnapshot,
    PublicSessionCapability,
    PublicSessionCommand,
    PublicSessionCommandCapability,
    PublicSessionCommandKind,
    PublicSessionConflict,
    PublicSessionControlOwner,
    PublicSessionOpenError,
    PublicSessionOpenStage,
    PublicSessionStatus,
    PublicTaskRequestFactory,
    PublicTaskRevisionCommand,
    PublicUnsupportedCode,
    PublicUserTurn,
    RecoverableCheckpoint,
    RecoveryInspectionFailed,
    RecoveryInspectionUnavailable,
    RecoveryInspectionUnsupported,
    RuntimeEnvironmentFactory,
    RuntimeEnvironmentLease,
    RuntimeEnvironmentReconnectFactory,
    RuntimeRecovered,
    RuntimeRecoveryAttempt,
    RuntimeRecoveryConflict,
    RuntimeRecoveryFailed,
    RuntimeRecoveryInspection,
    RuntimeRecoveryUnavailable,
    TargetRuntimeFactory,
    default_public_task_request,
    public_interaction_response_from_value,
)
from .public_session_projection import (
    _action_feed_sources,
    _completion,
    _control_feed_sources,
    _convert_public_session_conflict,
    _feed_source,
    _interaction_response_text,
    _public_confirmation,
    _public_effect_reconciliation,
    _public_interaction_request,
    _public_status,
    _revision_feed_diff,
    _revision_pause_command_id,
    _revision_rejection,
    _SessionProjectionSink,
    _step_feed_sources,
    _takeover_pause_command_id,
    _v3_command_capabilities,
)
from .runtime import TargetRuntime, TargetRuntimeRunOutcome

# 该门面只重导出稳定公共合同；实现细节继续留在各 owner 模块。
__all__ = [
    "_action_feed_sources",
    "BASE_PUBLIC_SESSION_CAPABILITIES",
    "LiveCheckpointAdmission",
    "LiveCheckpointConflict",
    "LiveCheckpointCurrent",
    "LiveCheckpointUnavailable",
    "PUBLIC_SESSION_CAPABILITIES",
    "PUBLIC_SESSION_SCHEMA_VERSION",
    "PUBLIC_SESSION_V3_SCHEMA_VERSION",
    "PublicAgentIntent",
    "PublicArtifact",
    "PublicCommandAccepted",
    "PublicCommandAdmission",
    "PublicCommandConflict",
    "PublicCommandRejected",
    "PublicCommandUnsupported",
    "PublicCompletion",
    "PublicCompletionBlock",
    "PublicConfirmationRequired",
    "PublicConflictCode",
    "PublicControlOutcome",
    "PublicEffectReconciliation",
    "PublicEvidenceSummary",
    "PublicFailure",
    "PublicFeedSource",
    "PublicGoalAccepted",
    "PublicInteractionRequest",
    "PublicInteractionRequested",
    "PublicPendingConfirmation",
    "PublicProgressStep",
    "PublicRejectedCode",
    "PublicRevisionApplied",
    "PublicRevisionConversationContext",
    "PublicRevisionConversationTurn",
    "PublicRuntimeActivity",
    "PublicRuntimeRecoveryInspector",
    "PublicRuntimeSessionEvent",
    "PublicRuntimeSessionFactory",
    "PublicRuntimeSessionHandle",
    "PublicRuntimeSessionSnapshot",
    "PublicSessionCapability",
    "PublicSessionCommand",
    "PublicSessionCommandCapability",
    "PublicSessionCommandKind",
    "PublicSessionConflict",
    "PublicSessionControlOwner",
    "PublicSessionOpenError",
    "PublicSessionOpenStage",
    "PublicSessionStatus",
    "PublicTaskRequestFactory",
    "PublicTaskRevisionCommand",
    "PublicUnsupportedCode",
    "PublicUserTurn",
    "RecoverableCheckpoint",
    "RecoveryInspectionFailed",
    "RecoveryInspectionUnavailable",
    "RecoveryInspectionUnsupported",
    "RuntimeEnvironmentFactory",
    "RuntimeEnvironmentLease",
    "RuntimeEnvironmentReconnectFactory",
    "RuntimeRecovered",
    "RuntimeRecoveryAttempt",
    "RuntimeRecoveryConflict",
    "RuntimeRecoveryFailed",
    "RuntimeRecoveryInspection",
    "RuntimeRecoveryUnavailable",
    "TargetRuntimeFactory",
    "TargetRuntimeSession",
    "TargetRuntimeSessionFactory",
    "default_public_task_request",
    "public_interaction_response_from_value",
]


@dataclass
class TargetRuntimeSession:
    """持有唯一可恢复 Session 状态；调用方只能取得公共投影值。"""

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
    _intake_question: PublicInteractionRequest | None = field(default=None, init=False, repr=False)
    _failure: PublicCompletion | None = field(default=None, init=False, repr=False)
    _checkpoint_id: str | None = field(default=None, init=False, repr=False)
    _resume_eligible: bool = field(default=False, init=False, repr=False)
    _last_control_outcome: PublicControlOutcome | None = field(default=None, init=False, repr=False)
    _control_owner: PublicSessionControlOwner = field(
        default=PublicSessionControlOwner.AGENT,
        init=False,
        repr=False,
    )
    _control_lease_id: str | None = field(default=None, init=False, repr=False)
    _control_return_in_progress: bool = field(default=False, init=False, repr=False)
    _progress: list[PublicProgressStep] = field(default_factory=list, init=False, repr=False)
    _events: list[PublicRuntimeSessionEvent] = field(default_factory=list, init=False, repr=False)
    _active: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _cleanup_started: bool = field(default=False, init=False, repr=False)
    _command_admissions: dict[str, tuple[str, PublicCommandAdmission]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, TargetRuntime):
            raise TypeError("public Runtime session requires a TargetRuntime")
        if not isinstance(self.lease, RuntimeEnvironmentLease):
            raise TypeError("public Runtime session requires a typed environment lease")
        required_environment_methods = ("reset", "revise_task", "capture", "is_current", "execute")
        if any(not callable(getattr(self.lease.environment, method, None)) for method in required_environment_methods):
            raise TypeError("public Runtime session environment does not implement WorldEnvironment")
        if not callable(self.request_factory):
            raise TypeError("public Runtime session requires a task request factory")

    async def snapshot(self) -> PublicRuntimeSessionSnapshot:
        return self._project()

    async def admits_surface_input(self, control_lease_id: str) -> bool:
        """校验精确的 live lease；不把控制语义下放给 Shell。"""

        return (
            not self._closed
            and self._control_owner is PublicSessionControlOwner.USER
            and self._control_lease_id is not None
            and secrets.compare_digest(self._control_lease_id, control_lease_id)
        )

    async def admit(self, command: PublicSessionCommand) -> PublicCommandAdmission:
        """统一拥有 v3 命令身份、语义准入和闭合结果转换。"""

        existing = self._command_admissions.get(command.command_id)
        if existing is not None:
            digest, admission = existing
            if secrets.compare_digest(digest, command.payload_digest):
                return admission
            return PublicCommandConflict(
                "conflict",
                command.command_id,
                "command_identity_reused",
                self._project(),
            )
        current = self._project()
        if current.task_revision != command.expected_task_revision or current.status is not command.expected_run_status:
            return PublicCommandConflict(
                "conflict",
                command.command_id,
                "stale_command",
                current,
            )
        supported = {capability.kind for capability in current.command_capabilities}
        if command.kind not in supported:
            code: PublicConflictCode = (
                "control_owner_conflict"
                if self._control_owner is PublicSessionControlOwner.USER
                else "session_state_conflict"
            )
            return PublicCommandConflict("conflict", command.command_id, code, current)
        try:
            admission = await self._execute_admitted_command(command)
        except PublicSessionConflict as exc:
            admission = _convert_public_session_conflict(command.command_id, exc)
        except Exception:
            admission = PublicCommandRejected(
                "rejected",
                command.command_id,
                "command_processing_failed",
                self._project(),
            )
        if isinstance(admission, PublicCommandAccepted):
            self._command_admissions[command.command_id] = (command.payload_digest, admission)
        return admission

    async def _execute_admitted_command(
        self,
        command: PublicSessionCommand,
    ) -> PublicCommandAdmission:
        if command.kind is PublicSessionCommandKind.START_TASK:
            snapshot = await self.start(command.task)
        elif command.kind is PublicSessionCommandKind.RESPOND_INTERACTION:
            assert command.response is not None
            snapshot = await self.respond(command.response)
        elif command.kind is PublicSessionCommandKind.APPROVE_ACTION:
            snapshot = await self.confirm(command.interaction_ref, approved=True)
        elif command.kind is PublicSessionCommandKind.REJECT_ACTION:
            snapshot = await self.confirm(command.interaction_ref, approved=False)
        elif command.kind is PublicSessionCommandKind.CANCEL_TASK:
            snapshot = await self.cancel(command.command_id)
        elif command.kind is PublicSessionCommandKind.PAUSE_TASK:
            snapshot = await self.pause(command.command_id)
        elif command.kind is PublicSessionCommandKind.RESUME_TASK:
            snapshot = await self.resume(command.command_id, command.checkpoint_id)
        elif command.kind is PublicSessionCommandKind.REVISE_TASK:
            assert command.revision is not None
            snapshot = await self.revise(command.revision)
        elif command.kind is PublicSessionCommandKind.TAKE_OVER:
            snapshot = await self.take_over(command.command_id, command.checkpoint_id)
        elif command.kind is PublicSessionCommandKind.RETURN_CONTROL:
            snapshot = await self.return_control(command.command_id, command.control_lease_id)
        elif command.kind is PublicSessionCommandKind.CLOSE_SESSION:
            snapshot = self._project()
            await self.close()
        else:  # pragma: no cover - StrEnum closes the supported algebra
            return PublicCommandUnsupported(
                "unsupported",
                command.command_id,
                "command_not_supported",
                self._project(),
            )
        return PublicCommandAccepted("accepted", command.command_id, snapshot)

    async def events(self, after: int) -> tuple[PublicRuntimeSessionEvent, ...]:
        return tuple(event for event in self._events if event.cursor > after)

    async def inspect_live_checkpoint(self, checkpoint_id: str) -> LiveCheckpointAdmission:
        """直接校验 live recovery ref，不把持久投影视为当前状态。"""

        async with self._lock:
            snapshot = self._project()
            if self._checkpoint_id != checkpoint_id:
                return LiveCheckpointConflict("live_checkpoint_conflict", "checkpoint_mismatch")
            state = self._state
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not self._resume_eligible
                or state.durable_checkpoint_id != checkpoint_id
            ):
                return LiveCheckpointUnavailable(
                    "live_checkpoint_unavailable",
                    "checkpoint_unavailable",
                )
            return LiveCheckpointCurrent("live_checkpoint_current", snapshot)

    async def start(self, instruction: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_open()
            if self._status is not PublicSessionStatus.IDLE or self._active is not None:
                raise PublicSessionConflict("session_not_idle", self._project())
            self._request = self.request_factory(self.session_id, instruction)
            if self._request.request_id != self.session_id or self._request.revision != 1:
                raise TypeError("public task request factory must preserve session identity and initial revision")
            intake = self.runtime.admit(self._request)
            if isinstance(intake, ReadyTask):
                self._admitted = intake
            self._status = PublicSessionStatus.RUNNING
            source_factories = [_feed_source(lambda source_id: PublicUserTurn(source_id, instruction))]
            if self._admitted is not None:
                accepted = self._admitted.task
                source_factories.append(
                    _feed_source(
                        lambda source_id: PublicGoalAccepted(
                            source_id,
                            accepted.revision,
                            accepted.instruction,
                            accepted.constraints,
                        )
                    )
                )
            self._emit(
                "RUN_STARTED",
                tuple(source_factories),
            )
            self._active = asyncio.create_task(
                self._run_start(intake),
                name=f"runtime-session:{self.session_id}",
            )
            return self._project()

    async def respond(self, response: InteractionResponse) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
            self._require_open()
            pending_step = self._state.last_step if self._state is not None else None
            pending = pending_step.decision if pending_step is not None else None
            if not isinstance(pending, InteractionRequest):
                raise PublicSessionConflict("interrupt_mismatch", self._project())
            if response.request_id != pending.request_id:
                raise PublicSessionConflict("interrupt_mismatch", self._project())
            admission = admit_interaction_response(pending, response)
            if not admission.admitted:
                raise PublicSessionConflict(
                    admission.rejection_code.value if admission.rejection_code is not None else "interaction_invalid",
                    self._project(),
                )
            if self._request is None or self._state is None:
                raise PublicSessionConflict("run_not_resumable", self._project())
            boundary = self._request.boundary
            inputs = dict(boundary.inputs)
            responses = list(inputs.get("user_responses", ()))
            responses.append(interaction_response_public_value(response))
            revised_boundary = replace(boundary, inputs={**inputs, "user_responses": responses})
            self._request = replace(
                self._request,
                boundary=revised_boundary,
                revision=self._request.revision + 1,
            )
            response_text = _interaction_response_text(pending, response)
            self._status = PublicSessionStatus.RUNNING
            self._intake_question = None
            self._emit(
                "RUN_STARTED",
                (lambda source_id: PublicUserTurn(source_id, response_text),),
            )
            self._active = asyncio.create_task(self._run_answer(), name=f"runtime-resume:{self.session_id}")
            return self._project()

    async def answer(self, interrupt_id: str, answer: str) -> PublicRuntimeSessionSnapshot:
        """把旧自由文本回答接入规范化 response 合同。"""
        pending_step = self._state.last_step if self._state is not None else None
        pending = pending_step.decision if pending_step is not None else None
        if (
            isinstance(pending, InteractionRequest)
            and pending.request_id == interrupt_id
            and pending.response_kind.value == "structured_fields"
            and len(pending.fields) == 1
            and pending.fields[0].kind.value == "text"
        ):
            return await self.respond(
                StructuredFieldsResponse(
                    interrupt_id,
                    (TextFieldValue(pending.fields[0].field_id, answer),),
                )
            )
        return await self.respond(FreeTextResponse(interrupt_id, answer))

    async def confirm(self, interrupt_id: str, *, approved: bool) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
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
            self._require_agent_control()
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            state = self._state
            if (state is not None and state.terminal) or (state is None and self._active is None):
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
            self._require_agent_control()
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            if self.checkpoint_store is None:
                raise PublicSessionConflict("pause_unavailable", self._project())
            state = self._state
            if state is not None and state.status is RunStatus.PAUSED:
                existing = await self.checkpoint_store.command_outcome(self.session_id, command_id)
                if existing is not None and existing.checkpoint_id == state.durable_checkpoint_id:
                    return self._project()
                raise PublicSessionConflict("run_not_active", self._project())
            if (state is not None and state.terminal) or (state is None and self._active is None):
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
                if outcome is None or outcome.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED:
                    raise PublicSessionConflict("control_boundary_failed", self._project())
                await self._settle_pause_boundary(self.runtime, self._admitted.task, state)
            return self._project()

    async def resume(
        self,
        command_id: str,
        checkpoint_id: str,
    ) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
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
                state is not None
                and state.effect_reconciliation is not None
                and state.effect_reconciliation.status is EffectReconciliationStatus.NEEDS_INPUT
            ):
                raise PublicSessionConflict(
                    state.effect_reconciliation.reason.value,
                    self._project(),
                )
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

    async def take_over(
        self,
        command_id: str,
        checkpoint_id: str = "",
    ) -> PublicRuntimeSessionSnapshot:
        """到达持久暂停边界后，签发一个进程内用户控制 lease。"""

        async with self._lock:
            self._require_agent_control()
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            store = self.checkpoint_store
            if store is None:
                raise PublicSessionConflict("takeover_unavailable", self._project())
            try:
                existing = await store.resume_outcome(self.session_id, command_id)
            except Exception as exc:
                raise PublicSessionConflict("takeover_persistence_failed", self._project()) from exc
            if existing is not None:
                if existing.checkpoint_id == checkpoint_id:
                    raise PublicSessionConflict("takeover_command_consumed", self._project())
                raise PublicSessionConflict("takeover_command_conflict", self._project())
            state = self._state
            already_paused = state is not None and state.status is RunStatus.PAUSED
            if already_paused:
                if not checkpoint_id or self._checkpoint_id != checkpoint_id:
                    raise PublicSessionConflict("checkpoint_mismatch", self._project())
            else:
                if checkpoint_id:
                    raise PublicSessionConflict("checkpoint_mismatch", self._project())
                await self._ensure_durable_pause(_takeover_pause_command_id(command_id))
                state = self._state
                checkpoint_id = self._checkpoint_id or ""
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not checkpoint_id
                or self._checkpoint_id != checkpoint_id
                or state.durable_checkpoint_id != checkpoint_id
            ):
                raise PublicSessionConflict("takeover_pause_failed", self._project())
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
            self._control_owner = PublicSessionControlOwner.USER
            self._control_lease_id = secrets.token_urlsafe(24)
            self._resume_eligible = False
            self._last_control_outcome = PublicControlOutcome(
                command_id,
                "take_over",
                "user_control_granted",
                "user_control_granted",
                checkpoint_id,
            )
            self._emit("USER_CONTROL_GRANTED")
            return self._project()

    async def return_control(
        self,
        command_id: str,
        control_lease_id: str,
    ) -> PublicRuntimeSessionSnapshot:
        """撤销用户输入权，并且只在 owner 产出 fresh World 后恢复 Agent。"""

        async with self._lock:
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            if self._control_owner is not PublicSessionControlOwner.USER:
                raise PublicSessionConflict("user_control_not_active", self._project())
            if self._control_lease_id is None or not secrets.compare_digest(self._control_lease_id, control_lease_id):
                raise PublicSessionConflict("control_lease_mismatch", self._project())
            if self._active is not None or self._admitted is None or self._state is None:
                raise PublicSessionConflict("user_control_return_unavailable", self._project())
            runtime = self._runtime_with_projection()
            state = self._state
            # 先撤销用户输入 lease，再采集供 Agent 继续执行的权威 fresh World。
            self._control_owner = PublicSessionControlOwner.AGENT
            self._control_lease_id = None
            self._control_return_in_progress = True
            self._emit("USER_CONTROL_REVOKED")
            try:
                if state.status is RunStatus.PAUSED:
                    runtime.resume_control(state, command_id)
                self._state = await runtime.refresh_after_user_control(
                    self.lease.environment,
                    self._admitted.task,
                    state,
                )
            except BaseException as exc:
                self._control_return_in_progress = False
                self._control_owner = PublicSessionControlOwner.USER
                # 采集失败时以新 epoch 恢复人工控制；旧 lease 永远不能再次生效。
                self._control_lease_id = secrets.token_urlsafe(24)
                code = str(getattr(exc, "reason_code", "")) or "user_control_currentness_unavailable"
                self._last_control_outcome = PublicControlOutcome(
                    command_id,
                    "return_control",
                    "failed",
                    code,
                    message="Agent control remains disabled until fresh currentness is available.",
                )
                self._emit("USER_CONTROL_RETURN_FAILED")
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise PublicSessionConflict(code, self._project()) from exc
            self._control_return_in_progress = False
            self._checkpoint_id = None
            self._resume_eligible = False
            self._status = _public_status(state.status)
            self._last_control_outcome = PublicControlOutcome(
                command_id,
                "return_control",
                "user_control_returned",
                "user_control_currentness_refreshed",
            )
            self._emit("USER_CONTROL_RETURNED")
            if state.status is RunStatus.RUNNING:
                self._active = asyncio.create_task(
                    self._run_continue(),
                    name=f"runtime-user-control-return:{self.session_id}",
                )
            return self._project()

    async def revise(self, command: PublicTaskRevisionCommand) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
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
            checkpoint_matches_entry = self._checkpoint_id == command.expected_checkpoint_id
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
                    checkpoint_id=(existing.result_checkpoint_id if existing.outcome == "revised" else None),
                    message=existing.message,
                    code=existing.result_code,
                )
                if existing.outcome == "revised":
                    return self._project()
                raise PublicSessionConflict(existing.result_code, self._project())
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
            if (
                state.effect_reconciliation is not None
                and state.effect_reconciliation.status is not EffectReconciliationStatus.COMPENSATED
            ):
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    "effect_reconciliation_required",
                    "The current revision still has an unresolved effect reconciliation.",
                )
            early_effect = assess_effect_revision(
                execution_count=state.execution_count,
                latest_effect=state.latest_effect,
                revised_goal_satisfied=False,
            )
            if early_effect.disposition in {
                EffectRevisionDisposition.UNKNOWN,
                EffectRevisionDisposition.UNSUPPORTED,
            } and (state.execution_count != 1 or state.latest_effect is None):
                code = (
                    "effect_reconciliation_unsupported"
                    if early_effect.disposition is EffectRevisionDisposition.UNSUPPORTED
                    else "effect_reconciliation_unknown"
                )
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    code,
                    early_effect.reason.value,
                    outcome="effect_reconciliation_required",
                )
            compiled = await self.runtime.compile_task_revision(
                admitted_at_entry,
                command.conversation,
                state,
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
                evaluation = candidate.current_task_evaluation
                effect_assessment = assess_effect_revision(
                    execution_count=state.execution_count,
                    latest_effect=state.latest_effect,
                    revised_goal_satisfied=(
                        evaluation is not None and evaluation.status is TaskEvaluationStatus.COMPLETE
                    ),
                )
                if effect_assessment.disposition is EffectRevisionDisposition.COMPENSATION_REQUIRED:
                    assert effect_assessment.effect is not None
                    candidate.install_effect_reconciliation(
                        EffectReconciliation(
                            effect_assessment.effect,
                            revised.task.revision,
                        )
                    )
                elif effect_assessment.disposition in {
                    EffectRevisionDisposition.NON_COMPENSABLE,
                    EffectRevisionDisposition.UNKNOWN,
                    EffectRevisionDisposition.UNSUPPORTED,
                }:
                    await self._restore_revision_source(runtime, source_checkpoint)
                    code = {
                        EffectRevisionDisposition.NON_COMPENSABLE: "effect_non_compensable",
                        EffectRevisionDisposition.UNKNOWN: "effect_reconciliation_unknown",
                        EffectRevisionDisposition.UNSUPPORTED: "effect_reconciliation_unsupported",
                    }[effect_assessment.disposition]
                    await self._reject_revision(
                        command,
                        source_checkpoint_id,
                        state.task_revision,
                        code,
                        effect_assessment.reason.value,
                        outcome="effect_reconciliation_required",
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
            except PublicSessionConflict:
                raise
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
            self._emit(
                "TASK_REVISED",
                (
                    lambda source_id: PublicUserTurn(source_id, command.text),
                    lambda source_id: _revision_feed_diff(
                        current.task,
                        revised.task,
                        source_id,
                    ),
                ),
            )
            return self._project()

    async def _ensure_revision_pause(self, command_id: str) -> None:
        await self._ensure_durable_pause(_revision_pause_command_id(command_id))

    async def _ensure_durable_pause(self, pause_id: str) -> None:
        state = self._state
        if state is not None and state.status is RunStatus.PAUSED:
            return
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
            if outcome is None or outcome.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED:
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
        *,
        outcome: str | None = None,
    ) -> None:
        store = self.checkpoint_store
        assert store is not None
        message = message[:2000]
        durable_outcome = outcome or code
        stored = RuntimeCheckpointRevisionOutcome(
            self.session_id,
            command.command_id,
            source_checkpoint_id,
            source_checkpoint_id,
            task_revision,
            durable_outcome,
            command.payload_digest,
            message,
            code,
        )
        try:
            await store.commit_revision(None, stored)
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
        self._set_revision_outcome(
            durable_outcome,
            command.command_id,
            message=message,
            code=code,
        )
        self._emit(
            "TASK_REVISION_REJECTED",
            (
                lambda source_id: PublicUserTurn(source_id, command.text),
                lambda source_id: PublicRuntimeActivity(
                    source_id,
                    "failed",
                    message or "The task revision could not be applied.",
                ),
            ),
        )
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
        code: str | None = None,
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
            code or outcome,
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

    async def _run_start(self, intake: TaskIntakeOutcome) -> None:
        assert self._request is not None
        session_runtime = self._runtime_with_projection()
        try:
            outcome = (
                await session_runtime.run_admitted(self.lease.environment, intake)
                if isinstance(intake, ReadyTask)
                else TargetRuntimeRunOutcome(intake)
            )
            if isinstance(outcome.intake, ReadyTask):
                self._admitted = outcome.intake
                self._state = outcome.state
                if outcome.state is not None:
                    await self._settle_pause_boundary(session_runtime, outcome.intake.task, outcome.state)
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
            await self._cleanup_if_closed_or_terminal()

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
                await self._settle_pause_boundary(self._runtime_with_projection(), outcome.intake.task, outcome.state)
        except BaseException as exc:
            self._fail("runtime_session_resume_failed", type(exc).__name__)
        finally:
            self._active = None
            await self._cleanup_if_closed_or_terminal()

    async def _run_confirmation(self, approved: bool) -> None:
        assert self._admitted is not None and self._state is not None
        try:
            self._state = await self._runtime_with_projection().resume_confirmation(
                self.lease.environment,
                self._admitted.task,
                self._state,
                approved=approved,
            )
            await self._settle_pause_boundary(self._runtime_with_projection(), self._admitted.task, self._state)
        except BaseException as exc:
            self._fail("runtime_session_confirmation_failed", type(exc).__name__)
        finally:
            self._active = None
            await self._cleanup_if_closed_or_terminal()

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
            await self._cleanup_if_closed_or_terminal()

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
        self._emit("STEP_FINISHED", _step_feed_sources(result))

    def _observe_paused(self, state: RunState) -> None:
        self._state = state
        self._status = _public_status(state.status)
        completion = _completion(state, self._status)
        sources: tuple[Callable[[str], PublicFeedSource], ...] = ()
        if completion is not None:
            if completion.outcome in {"success", "cancelled"}:
                sources = (lambda source_id: PublicCompletionBlock(source_id, completion),)
            else:
                sources = (
                    lambda source_id: PublicFailure(
                        source_id,
                        completion.code,
                        completion.message or "The Runtime could not complete the task.",
                    ),
                )
        self._emit("RUN_FINISHED", sources)

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
        self._emit(
            "RUN_ERROR",
            (lambda source_id: PublicFailure(source_id, code, message),),
        )

    def _emit(
        self,
        event_type: str,
        source_factories: tuple[Callable[[str], PublicFeedSource], ...] = (),
    ) -> None:
        cursor = len(self._events) + 1
        snapshot = self._project(event_cursor=cursor)
        factories = source_factories or _control_feed_sources(event_type, self._last_control_outcome)
        sources = tuple(
            factory(f"feed:{self._event_epoch}:{cursor}:{ordinal}") for ordinal, factory in enumerate(factories)
        )
        self._events.append(
            PublicRuntimeSessionEvent(
                self.session_id,
                self._event_epoch,
                cursor,
                event_type,
                snapshot,
                sources,
            )
        )

    def _project(self, *, event_cursor: int | None = None) -> PublicRuntimeSessionSnapshot:
        state = self._state
        status = self._status if self._active is not None or state is None else _public_status(state.status)
        if self._control_owner is PublicSessionControlOwner.USER or self._control_return_in_progress:
            status = PublicSessionStatus.PAUSED
        pending_interaction = self._intake_question
        pending_confirmation = None
        if state is not None and state.last_step is not None:
            if (
                self._control_owner is PublicSessionControlOwner.AGENT
                and status is PublicSessionStatus.WAITING_USER
                and isinstance(state.last_step.decision, InteractionRequest)
            ):
                decision = state.last_step.decision
                pending_interaction = _public_interaction_request(decision)
            if (
                self._control_owner is PublicSessionControlOwner.AGENT
                and status is PublicSessionStatus.WAITING_CONFIRMATION
                and state.last_step.confirmation is not None
            ):
                risk = state.last_step.confirmation
                pending_confirmation = _public_confirmation(risk)
        request = self._request
        task = self._admitted.task if self._admitted is not None else None
        completion = self._failure or _completion(state, status)
        reconciliation = _public_effect_reconciliation(state.effect_reconciliation) if state is not None else None
        reconciliation_blocks_control = reconciliation is not None
        public_resume_eligible = self._resume_eligible and (
            reconciliation is None or reconciliation.status != "needs_input"
        )
        capabilities = (
            frozenset({PublicSessionCapability.CLOSE_SESSION})
            if self._control_return_in_progress
            else frozenset(
                {
                    PublicSessionCapability.CLOSE_SESSION,
                    PublicSessionCapability.RETURN_CONTROL,
                }
            )
            if self._control_owner is PublicSessionControlOwner.USER
            else (
                BASE_PUBLIC_SESSION_CAPABILITIES
                | ({PublicSessionCapability.PAUSE_TASK} if self.checkpoint_store is not None else set())
                | (
                    {PublicSessionCapability.RESUME_TASK}
                    if status is PublicSessionStatus.PAUSED and public_resume_eligible
                    else set()
                )
                | (
                    {PublicSessionCapability.REVISE_TASK}
                    if self.checkpoint_store is not None
                    and not reconciliation_blocks_control
                    and status
                    in {
                        PublicSessionStatus.RUNNING,
                        PublicSessionStatus.WAITING_USER,
                        PublicSessionStatus.WAITING_CONFIRMATION,
                        PublicSessionStatus.PAUSED,
                    }
                    else set()
                )
                | (
                    {PublicSessionCapability.TAKE_OVER}
                    if (
                        self.checkpoint_store is not None
                        and status
                        in {
                            PublicSessionStatus.RUNNING,
                            PublicSessionStatus.WAITING_USER,
                            PublicSessionStatus.WAITING_CONFIRMATION,
                            PublicSessionStatus.PAUSED,
                        }
                        and (status is not PublicSessionStatus.PAUSED or self._checkpoint_id is not None)
                    )
                    else set()
                )
            )
        )
        return PublicRuntimeSessionSnapshot(
            self.session_id,
            self.expires_at,
            status,
            self._event_epoch,
            len(self._events) if event_cursor is None else event_cursor,
            capabilities=capabilities,
            command_capabilities=_v3_command_capabilities(
                status=status,
                checkpoint_store_available=self.checkpoint_store is not None,
                checkpoint_id=self._checkpoint_id,
                resume_eligible=public_resume_eligible,
                pending_interaction=pending_interaction,
                pending_confirmation=pending_confirmation,
                control_owner=self._control_owner,
                control_return_in_progress=self._control_return_in_progress,
                reconciliation_blocks_control=reconciliation_blocks_control,
                closed=self._closed,
            ),
            task_id=task.task_id if task is not None else (request.request_id if request else None),
            task_revision=task.revision if task is not None else (request.revision if request else 0),
            task_text=task.instruction if task is not None else (request.instruction if request else None),
            pending_interaction=pending_interaction,
            pending_confirmation=pending_confirmation,
            completion=completion,
            progress=tuple(self._progress),
            checkpoint_id=self._checkpoint_id,
            resume_eligible=public_resume_eligible,
            last_control_outcome=self._last_control_outcome,
            effect_reconciliation=reconciliation,
            control_owner=self._control_owner,
            control_lease_id=self._control_lease_id,
        )

    def _require_agent_control(self) -> None:
        if self._control_owner is not PublicSessionControlOwner.AGENT:
            raise PublicSessionConflict("user_control_active", self._project())

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

    async def _cleanup_if_closed_or_terminal(self) -> None:
        if self._closed or self._status in {
            PublicSessionStatus.DONE,
            PublicSessionStatus.CANCELLED,
            PublicSessionStatus.FAILED,
            PublicSessionStatus.BLOCKED,
        }:
            await self._cleanup_once()


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

        return await self.open_prepared(session_id, expires_at, runtime, lease)

    async def open_prepared(
        self,
        session_id: str,
        expires_at: datetime,
        runtime: TargetRuntime,
        lease: RuntimeEnvironmentLease,
        *,
        request_factory: PublicTaskRequestFactory | None = None,
    ) -> TargetRuntimeSession:
        """用 deployment 拥有的资源构造 Session，但不转移 Session authority。"""

        selected_request_factory = request_factory or self.request_factory
        if not isinstance(runtime, TargetRuntime):
            raise PublicSessionOpenError(PublicSessionOpenStage.RUNTIME, "runtime_factory_failed")
        if not isinstance(lease, RuntimeEnvironmentLease):
            raise PublicSessionOpenError(PublicSessionOpenStage.ENVIRONMENT, "environment_factory_failed")
        if not callable(selected_request_factory):
            await _cleanup_environment_lease(lease)
            raise PublicSessionOpenError(PublicSessionOpenStage.SESSION, "request_factory_invalid")
        try:
            return TargetRuntimeSession(
                runtime,
                lease,
                session_id,
                expires_at,
                selected_request_factory,
                self.checkpoint_store,
            )
        except Exception as exc:
            await _cleanup_environment_lease(lease)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "session_initialization_failed",
            ) from exc

    async def inspect(self, session_id: str) -> RuntimeRecoveryInspection:
        """只在这里把 checkpoint 事实和注入的重连能力转换一次。"""

        store = self.checkpoint_store
        if store is None:
            return RecoveryInspectionUnsupported(
                "recovery_inspection_unsupported",
                "checkpoint_store_unavailable",
            )
        if self.environment_reconnector is None:
            return RecoveryInspectionUnsupported(
                "recovery_inspection_unsupported",
                "recovery_reconnector_unavailable",
            )
        try:
            checkpoint = await store.load_latest(session_id)
            if checkpoint is None:
                return RecoveryInspectionUnavailable(
                    "recovery_inspection_unavailable",
                    "checkpoint_not_found",
                )
            resume_outcome = await store.checkpoint_resume_outcome(
                session_id,
                checkpoint.checkpoint_id,
            )
            revision_outcome = await store.checkpoint_revision_outcome(
                session_id,
                checkpoint.checkpoint_id,
            )
        except Exception:
            return RecoveryInspectionFailed(
                "recovery_inspection_failed",
                "checkpoint_inspection_failed",
            )
        if resume_outcome is not None or revision_outcome is not None:
            return RecoveryInspectionUnavailable(
                "recovery_inspection_unavailable",
                "checkpoint_consumed",
            )
        if not checkpoint.resume_eligible or not checkpoint.environment_reference:
            return RecoveryInspectionUnavailable(
                "recovery_inspection_unavailable",
                "checkpoint_unavailable",
            )
        return RecoverableCheckpoint("recoverable_checkpoint", checkpoint.checkpoint_id)

    async def recover_typed(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> RuntimeRecoveryAttempt:
        store = self.checkpoint_store
        if store is None:
            return RuntimeRecoveryUnavailable(
                "recovery_unavailable",
                ("environment_not_reconnectable" if self.environment_reconnector is None else "recovery_unsupported"),
            )
        try:
            checkpoint = await store.load(session_id, checkpoint_id)
            resume_outcome = await store.checkpoint_resume_outcome(session_id, checkpoint_id)
            revision_outcome = await store.checkpoint_revision_outcome(session_id, checkpoint_id)
        except Exception:
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "checkpoint_store_failed",
            )
        if checkpoint is None:
            return RuntimeRecoveryUnavailable(
                "recovery_unavailable",
                "checkpoint_not_found",
            )
        if resume_outcome is not None:
            return RuntimeRecoveryConflict(
                "recovery_conflict",
                "checkpoint_already_resumed",
            )
        if revision_outcome is not None:
            return RuntimeRecoveryConflict(
                "recovery_conflict",
                "checkpoint_already_revised",
            )
        reconnector = self.environment_reconnector
        if not checkpoint.resume_eligible or not checkpoint.environment_reference or reconnector is None:
            return RuntimeRecoveryUnavailable(
                "recovery_unavailable",
                "environment_not_reconnectable",
            )
        try:
            runtime = self.runtime_factory(session_id)
            if inspect.isawaitable(runtime):
                runtime = await runtime
            if not isinstance(runtime, TargetRuntime):
                raise TypeError("Runtime factory must return TargetRuntime")
        except Exception:
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "runtime_factory_failed",
            )
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
        except Exception:
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "environment_reconnect_failed",
            )
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
            return RuntimeRecovered("recovered", session)
        except Exception:
            await _cleanup_environment_lease(lease)
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "session_restore_failed",
            )

    async def recover(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> TargetRuntimeSession:
        attempt = await self.recover_typed(session_id, checkpoint_id, expires_at)
        if isinstance(attempt, RuntimeRecovered):
            return cast(TargetRuntimeSession, attempt.handle)
        if isinstance(attempt, RuntimeRecoveryConflict):
            raise PublicSessionOpenError(PublicSessionOpenStage.SESSION, attempt.reason_code)
        if isinstance(attempt, RuntimeRecoveryUnavailable):
            stage = (
                PublicSessionOpenStage.ENVIRONMENT
                if attempt.reason_code == "environment_not_reconnectable"
                else PublicSessionOpenStage.SESSION
            )
            legacy_code = (
                "checkpoint_store_unavailable" if attempt.reason_code == "recovery_unsupported" else attempt.reason_code
            )
            raise PublicSessionOpenError(stage, legacy_code)
        legacy_failure = {
            "checkpoint_store_failed": (PublicSessionOpenStage.SESSION, "checkpoint_invalid"),
            "runtime_factory_failed": (PublicSessionOpenStage.RUNTIME, "runtime_factory_failed"),
            "environment_reconnect_failed": (
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_not_reconnectable",
            ),
            "session_restore_failed": (PublicSessionOpenStage.SESSION, "checkpoint_restore_failed"),
        }[attempt.reason_code]
        raise PublicSessionOpenError(*legacy_failure)


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
