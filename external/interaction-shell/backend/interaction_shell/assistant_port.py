"""Outer conversational port that delegates GUI work to the existing Runtime port."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .assistant import (
    AssistantHistoryPersistence,
    AssistantQuestion,
    AssistantTurnRunner,
    GuiTaskResult,
)
from .contracts import (
    Accepted,
    AgentIntentBlock,
    AnswerQuestion,
    AnswerQuestionOffer,
    CancelTask,
    CancelTaskOffer,
    CloseSession,
    CloseSessionOffer,
    CommandAdmission,
    Completion,
    CompletionBlock,
    Conflict,
    ControlOwner,
    FailureBlock,
    FeedBlock,
    InteractionRequest,
    InteractionRequestBlock,
    Recovered,
    RecoveryAttemptUnavailable,
    RevisionConversationContext,
    ReviseTask,
    ReviseTaskOffer,
    RunStatus,
    RuntimeSessionSnapshot,
    SCHEMA_VERSION,
    ShellCommand,
    ShellEvent,
    SnapshotUpdated,
    StartTask,
    StartTaskOffer,
    UnavailableSurface,
    UserTurnBlock,
)
from .port import (
    PortRecoverableCheckpoint,
    PortRecoveredHandle,
    PortRecoveryInspectionUnavailable,
    PortRecoveryInspectionUnsupported,
    RuntimeSessionPort,
)


_TERMINAL = {
    RunStatus.DONE,
    RunStatus.FAILED,
    RunStatus.BLOCKED,
    RunStatus.CANCELLED,
}

logger = logging.getLogger(__name__)


@dataclass
class AssistantHandle:
    session_id: str
    expires_at: datetime
    event_epoch: str
    snapshot: RuntimeSessionSnapshot
    messages: tuple[Any, ...] = ()
    events: list[ShellEvent] = field(default_factory=list)
    active_turn: asyncio.Task[None] | None = None
    inner_handle: Any | None = None
    inner_snapshot: RuntimeSessionSnapshot | None = None
    inner_cursor: int = 0
    inner_feed_ids: set[str] = field(default_factory=set)
    inner_wakeup: asyncio.Event = field(default_factory=asyncio.Event)
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    inner_refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closed: bool = False


@dataclass(frozen=True)
class AssistantSessionPort:
    """The Shell-facing general Assistant; GUI Runtime remains an isolated delegate."""

    runner: AssistantTurnRunner
    gui_port: RuntimeSessionPort

    async def open(self, session_id: str, expires_at: datetime) -> AssistantHandle:
        event_epoch = secrets.token_urlsafe(18)
        snapshot = RuntimeSessionSnapshot(
            schema_version=SCHEMA_VERSION,
            session_id=session_id,
            event_epoch=event_epoch,
            expires_at=expires_at,
            command_offers=(
                StartTaskOffer(kind="start_task"),
                CloseSessionOffer(kind="close_session"),
            ),
            surface=UnavailableSurface(
                status="unavailable",
                reason_code="no_gui_task_active",
            ),
        )
        return AssistantHandle(session_id, expires_at, event_epoch, snapshot)

    async def inspect(self, session_id: str):
        if isinstance(self.runner, AssistantHistoryPersistence):
            checkpoint_id = await self.runner.latest_checkpoint(session_id)
            if checkpoint_id is not None:
                return PortRecoverableCheckpoint("recoverable_checkpoint", checkpoint_id)
            return PortRecoveryInspectionUnavailable(
                "recovery_inspection_unavailable",
                "checkpoint_not_found",
            )
        return PortRecoveryInspectionUnsupported(
            "recovery_inspection_unsupported",
            "recovery_reconnector_unavailable",
        )

    async def recover_absent(self, session_id: str, checkpoint_id: str, expires_at: datetime):
        if not isinstance(self.runner, AssistantHistoryPersistence):
            return RecoveryAttemptUnavailable(
                kind="recovery_unavailable",
                reason_code="recovery_unsupported",
            )
        try:
            messages = await self.runner.load_checkpoint(session_id, checkpoint_id)
        except LookupError:
            return RecoveryAttemptUnavailable(
                kind="recovery_unavailable",
                reason_code="checkpoint_not_found",
            )
        handle = await self.open(session_id, expires_at)
        handle.messages = messages
        return PortRecoveredHandle(
            handle,
            Recovered(kind="recovered", snapshot=handle.snapshot),
        )

    async def recover_live(self, handle: AssistantHandle, checkpoint_id: str):
        del handle, checkpoint_id
        return RecoveryAttemptUnavailable(
            kind="recovery_unavailable",
            reason_code="checkpoint_unavailable",
        )

    async def snapshot(self, handle: AssistantHandle) -> RuntimeSessionSnapshot:
        await self._refresh_inner(handle)
        return handle.snapshot

    async def events(
        self,
        handle: AssistantHandle,
        after: int,
    ) -> tuple[ShellEvent, ...]:
        await self._refresh_inner(handle)
        return tuple(event for event in handle.events if event.cursor > after)

    async def forward_viewer_input(
        self,
        handle: AssistantHandle,
        control_lease_id: str,
        forward: Callable[[], Awaitable[None]],
    ) -> bool:
        if handle.inner_handle is None:
            return False
        return await self.gui_port.forward_viewer_input(
            handle.inner_handle,
            control_lease_id,
            forward,
        )

    async def command(
        self,
        handle: AssistantHandle,
        command: ShellCommand,
        *,
        revision_conversation: RevisionConversationContext | None = None,
    ) -> CommandAdmission:
        await self._refresh_inner(handle)
        current = handle.snapshot
        if handle.closed:
            return Conflict(
                kind="conflict",
                command_id=command.command_id,
                code="session_closed",
                snapshot=current,
            )
        if (
            command.expected_run_status is not current.run_status
            or command.expected_task_revision != current.task_revision
        ):
            return Conflict(
                kind="conflict",
                command_id=command.command_id,
                code="stale_command",
                snapshot=current,
            )

        if isinstance(command, CloseSession):
            await self.close(handle)
            return Accepted(
                kind="accepted",
                command_id=command.command_id,
                snapshot=handle.snapshot,
            )
        if isinstance(command, CancelTask):
            return await self._cancel(handle, command)
        if isinstance(command, StartTask):
            if handle.active_turn is not None and not handle.active_turn.done():
                return Conflict(
                    kind="conflict",
                    command_id=command.command_id,
                    code="session_state_conflict",
                    snapshot=current,
                )
            await self._retire_inner(handle)
            await self._start_turn(
                handle,
                prompt=command.task,
                displayed_user_text=command.task,
                task_revision=current.task_revision + 1,
            )
            return Accepted(
                kind="accepted",
                command_id=command.command_id,
                snapshot=handle.snapshot,
            )

        if handle.inner_handle is not None and handle.inner_snapshot is not None:
            if isinstance(command, ReviseTask) and revision_conversation is None:
                raise TypeError("Shell manager must attach bounded revision conversation")
            admission = await self.gui_port.command(
                handle.inner_handle,
                command,
                revision_conversation=revision_conversation,
            )
            handle.inner_wakeup.set()
            await self._refresh_inner(handle)
            return admission.model_copy(update={"snapshot": handle.snapshot})

        if isinstance(command, ReviseTask):
            if revision_conversation is None:
                raise TypeError("Shell manager must attach bounded revision conversation")
            prior = current.task_text or ""
            if handle.active_turn is not None and not handle.active_turn.done():
                handle.active_turn.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await handle.active_turn
            revision_prompt = (
                "The user revised the currently running request.\n\n"
                f"Original request:\n{prior}\n\n"
                f"Authoritative revision:\n{command.text}"
            )
            await self._start_turn(
                handle,
                prompt=revision_prompt,
                displayed_user_text=command.text,
                task_revision=current.task_revision + 1,
            )
            return Accepted(
                kind="accepted",
                command_id=command.command_id,
                snapshot=handle.snapshot,
            )

        if isinstance(command, AnswerQuestion):
            question = next(
                (
                    offer
                    for offer in current.command_offers
                    if isinstance(offer, AnswerQuestionOffer)
                ),
                None,
            )
            if (
                current.run_status is not RunStatus.WAITING_USER
                or question is None
                or question.request_id != command.request_id
            ):
                return Conflict(
                    kind="conflict",
                    command_id=command.command_id,
                    code=(
                        "interaction_ref_mismatch"
                        if current.run_status is RunStatus.WAITING_USER
                        else "session_state_conflict"
                    ),
                    snapshot=current,
                )
            await self._start_turn(
                handle,
                prompt=command.answer,
                displayed_user_text=command.answer,
                task_revision=current.task_revision,
            )
            return Accepted(
                kind="accepted",
                command_id=command.command_id,
                snapshot=handle.snapshot,
            )

        from .contracts import Unsupported

        return Unsupported(
            kind="unsupported",
            command_id=command.command_id,
            code="command_not_supported",
            snapshot=current,
        )

    async def close(self, handle: AssistantHandle) -> None:
        if handle.closed:
            return
        handle.closed = True
        if handle.active_turn is not None and not handle.active_turn.done():
            handle.active_turn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await handle.active_turn
        await self._retire_inner(handle)

    async def _start_turn(
        self,
        handle: AssistantHandle,
        *,
        prompt: str,
        displayed_user_text: str,
        task_revision: int,
    ) -> None:
        occurred_at = datetime.now(UTC)
        snapshot = handle.snapshot.model_copy(
            update={
                "task_id": f"assistant-turn:{task_revision}",
                "task_revision": task_revision,
                "task_text": displayed_user_text,
                "run_status": RunStatus.RUNNING,
                "completion": None,
                "command_offers": self._assistant_running_offers(),
                "checkpoint_id": None,
                "resume_eligible": False,
                "last_control_outcome": None,
                "effect_reconciliation": None,
            }
        )
        await self._publish(
            handle,
            snapshot,
            (
                UserTurnBlock(
                    kind="user_turn",
                    block_id=f"assistant:user:{secrets.token_urlsafe(12)}",
                    occurred_at=occurred_at,
                    content=displayed_user_text,
                ),
                AgentIntentBlock(
                    kind="agent_intent",
                    block_id=f"assistant:intent:{secrets.token_urlsafe(12)}",
                    occurred_at=occurred_at,
                    content="正在理解你的请求并选择合适的能力。",
                ),
            ),
            occurred_at=occurred_at,
        )
        handle.active_turn = asyncio.create_task(self._run_turn(handle, prompt))

    async def _run_turn(self, handle: AssistantHandle, prompt: str) -> None:
        prior_messages: Sequence[Any] = handle.messages
        try:
            result = await self.runner.run(
                prompt,
                conversation_id=handle.session_id,
                message_history=prior_messages,
                run_gui_task=lambda goal: self._run_gui_task(handle, goal),
            )
            handle.messages = result.messages
            occurred_at = datetime.now(UTC)
            delegated = result.gui_results[-1] if result.gui_results else None
            if delegated is not None and delegated.outcome != "success":
                completion = Completion(
                    outcome=delegated.outcome,
                    code=delegated.code,
                    message=delegated.message,
                )
                status = {
                    "failure": RunStatus.FAILED,
                    "blocked": RunStatus.BLOCKED,
                    "cancelled": RunStatus.CANCELLED,
                }[delegated.outcome]
                snapshot = handle.snapshot.model_copy(
                    update={
                        "run_status": status,
                        "completion": completion,
                        "command_offers": (
                            StartTaskOffer(kind="start_task"),
                            CloseSessionOffer(kind="close_session"),
                        ),
                    }
                )
                # The inner Runtime failure/cancellation block is already
                # projected into the shared feed. This event only installs
                # its authoritative terminal outcome on the outer snapshot.
                blocks = ()
            elif isinstance(result.output, AssistantQuestion):
                request_id = secrets.token_urlsafe(18)
                request = InteractionRequest(
                    request_id=request_id,
                    prompt=result.output.prompt,
                    response_kind="free_text",
                    public_intent="The assistant needs one user-owned fact to continue.",
                )
                snapshot = handle.snapshot.model_copy(
                    update={
                        "run_status": RunStatus.WAITING_USER,
                        "completion": None,
                        "command_offers": (
                            AnswerQuestionOffer(
                                kind="answer_question",
                                request_id=request_id,
                                prompt=result.output.prompt,
                            ),
                            CancelTaskOffer(kind="cancel_task"),
                            CloseSessionOffer(kind="close_session"),
                        ),
                    }
                )
                blocks: tuple[FeedBlock, ...] = (
                    InteractionRequestBlock(
                        kind="interaction_request",
                        block_id=f"assistant:question:{request_id}",
                        occurred_at=occurred_at,
                        request=request,
                    ),
                )
            else:
                message = result.output.strip()
                completion = Completion(
                    outcome="success",
                    code="assistant_response",
                    message=message,
                )
                snapshot = handle.snapshot.model_copy(
                    update={
                        "run_status": RunStatus.DONE,
                        "completion": completion,
                        "command_offers": (
                            StartTaskOffer(kind="start_task"),
                            CloseSessionOffer(kind="close_session"),
                        ),
                    }
                )
                blocks = (
                    CompletionBlock(
                        kind="completion",
                        block_id=f"assistant:completion:{secrets.token_urlsafe(12)}",
                        occurred_at=occurred_at,
                        completion=completion,
                    ),
                )
            await self._publish(handle, snapshot, blocks, occurred_at=occurred_at)
        except asyncio.CancelledError:
            raise
        except Exception:  # provider/tool failures become one typed public failure
            logger.exception("Assistant turn failed for session %s", handle.session_id)
            occurred_at = datetime.now(UTC)
            code = "assistant_invocation_failed"
            message = "这次请求没有完成。模型或能力调用失败，请稍后重试。"
            completion = Completion(outcome="failure", code=code, message=message)
            snapshot = handle.snapshot.model_copy(
                update={
                    "run_status": RunStatus.FAILED,
                    "completion": completion,
                    "command_offers": (
                        StartTaskOffer(kind="start_task"),
                        CloseSessionOffer(kind="close_session"),
                    ),
                }
            )
            await self._publish(
                handle,
                snapshot,
                (
                    FailureBlock(
                        kind="failure",
                        block_id=f"assistant:failure:{secrets.token_urlsafe(12)}",
                        occurred_at=occurred_at,
                        code=code,
                        message=message,
                    ),
                ),
                occurred_at=occurred_at,
            )

    async def _run_gui_task(self, handle: AssistantHandle, goal: str) -> GuiTaskResult:
        await self._retire_inner(handle)
        inner_handle = await self.gui_port.open(handle.session_id, handle.expires_at)
        handle.inner_handle = inner_handle
        handle.inner_snapshot = await self.gui_port.snapshot(inner_handle)
        handle.inner_cursor = 0
        handle.inner_feed_ids.clear()
        start = StartTask(
            kind="start_task",
            command_id=f"assistant-gui:{secrets.token_urlsafe(16)}",
            expected_task_revision=handle.inner_snapshot.task_revision,
            expected_run_status=handle.inner_snapshot.run_status,
            task=goal,
        )
        admission = await self.gui_port.command(inner_handle, start)
        if not isinstance(admission, Accepted):
            return GuiTaskResult(
                outcome="failure",
                code=getattr(admission, "code", "gui_task_rejected"),
                message="The GUI Runtime did not admit the delegated task.",
            )
        handle.inner_snapshot = admission.snapshot
        await self._refresh_inner(handle)

        while True:
            await self._refresh_inner(handle)
            current = handle.inner_snapshot
            if current is None:
                return GuiTaskResult(
                    outcome="failure",
                    code="gui_snapshot_unavailable",
                    message="The GUI Runtime stopped without a public result.",
                )
            if current.run_status in _TERMINAL:
                completion = current.completion
                if completion is None:
                    return GuiTaskResult(
                        outcome="failure",
                        code="gui_completion_missing",
                        message="The GUI Runtime reached a terminal state without a completion payload.",
                    )
                artifact_summary = completion.artifact.summary if completion.artifact else ""
                return GuiTaskResult(
                    outcome=completion.outcome,
                    code=completion.code,
                    message=completion.message,
                    artifact_summary=artifact_summary,
                    evidence_refs=completion.evidence_refs,
                )
            if current.run_status in {
                RunStatus.WAITING_USER,
                RunStatus.WAITING_CONFIRMATION,
                RunStatus.PAUSED,
            }:
                await handle.inner_wakeup.wait()
                handle.inner_wakeup.clear()
            else:
                await asyncio.sleep(0.1)

    async def _refresh_inner(self, handle: AssistantHandle) -> None:
        if handle.inner_handle is None:
            return
        async with handle.inner_refresh_lock:
            events = await self.gui_port.events(handle.inner_handle, handle.inner_cursor)
            for event in events:
                handle.inner_cursor = event.cursor
                handle.inner_snapshot = event.snapshot
                blocks = tuple(
                    self._project_inner_block(block)
                    for block in event.feed_delta
                    if self._include_inner_block(block, handle)
                )
                snapshot = self._project_inner_snapshot(handle, event.snapshot)
                await self._publish(
                    handle,
                    snapshot,
                    blocks,
                    occurred_at=event.emitted_at,
                )

    @staticmethod
    def _include_inner_block(block: FeedBlock, handle: AssistantHandle) -> bool:
        if isinstance(block, (UserTurnBlock, CompletionBlock)):
            return False
        projected_id = f"gui:{block.block_id}"
        if projected_id in handle.inner_feed_ids:
            return False
        handle.inner_feed_ids.add(projected_id)
        return True

    @staticmethod
    def _project_inner_block(block: FeedBlock) -> FeedBlock:
        return block.model_copy(update={"block_id": f"gui:{block.block_id}"})

    def _project_inner_snapshot(
        self,
        handle: AssistantHandle,
        inner: RuntimeSessionSnapshot,
    ) -> RuntimeSessionSnapshot:
        status = inner.run_status
        offers = inner.command_offers
        completion = None
        if status in _TERMINAL:
            status = RunStatus.RUNNING
            offers = self._assistant_running_offers()
        return inner.model_copy(
            update={
                "task_id": handle.snapshot.task_id,
                "task_text": handle.snapshot.task_text,
                "event_epoch": handle.event_epoch,
                "event_cursor": handle.snapshot.event_cursor,
                "run_status": status,
                "completion": completion,
                "command_offers": offers,
                "expires_at": handle.expires_at,
            }
        )

    async def _cancel(self, handle: AssistantHandle, command: CancelTask) -> CommandAdmission:
        if handle.inner_handle is not None and handle.inner_snapshot is not None:
            with contextlib.suppress(Exception):
                await self.gui_port.command(handle.inner_handle, command)
        if handle.active_turn is not None and not handle.active_turn.done():
            handle.active_turn.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await handle.active_turn
        occurred_at = datetime.now(UTC)
        completion = Completion(
            outcome="cancelled",
            code="user_cancelled",
            message="已按你的要求停止当前请求。",
        )
        snapshot = handle.snapshot.model_copy(
            update={
                "run_status": RunStatus.CANCELLED,
                "completion": completion,
                "command_offers": (
                    StartTaskOffer(kind="start_task"),
                    CloseSessionOffer(kind="close_session"),
                ),
            }
        )
        await self._publish(
            handle,
            snapshot,
            (
                CompletionBlock(
                    kind="completion",
                    block_id=f"assistant:cancelled:{secrets.token_urlsafe(12)}",
                    occurred_at=occurred_at,
                    completion=completion,
                ),
            ),
            occurred_at=occurred_at,
        )
        return Accepted(
            kind="accepted",
            command_id=command.command_id,
            snapshot=handle.snapshot,
        )

    async def _retire_inner(self, handle: AssistantHandle) -> None:
        inner = handle.inner_handle
        handle.inner_handle = None
        handle.inner_snapshot = None
        handle.inner_cursor = 0
        handle.inner_feed_ids.clear()
        handle.inner_wakeup.set()
        if inner is not None:
            await self.gui_port.close(inner)
        if handle.snapshot.surface.status != "unavailable":
            handle.snapshot = handle.snapshot.model_copy(
                update={
                    "surface": UnavailableSurface(
                        status="unavailable",
                        reason_code="no_gui_task_active",
                    ),
                    "control_owner": ControlOwner.AGENT,
                    "control_lease_id": None,
                }
            )

    async def _publish(
        self,
        handle: AssistantHandle,
        snapshot: RuntimeSessionSnapshot,
        feed_delta: tuple[FeedBlock, ...],
        *,
        occurred_at: datetime,
    ) -> None:
        async with handle.state_lock:
            cursor = handle.snapshot.event_cursor + 1
            current = snapshot.model_copy(
                update={
                    "event_epoch": handle.event_epoch,
                    "event_cursor": cursor,
                    "expires_at": handle.expires_at,
                }
            )
            event = SnapshotUpdated(
                schema_version=SCHEMA_VERSION,
                type="snapshot.updated",
                session_id=handle.session_id,
                event_epoch=handle.event_epoch,
                cursor=cursor,
                emitted_at=occurred_at,
                snapshot=current,
                feed_delta=feed_delta,
            )
            handle.snapshot = current
            handle.events.append(event)

    @staticmethod
    def _assistant_running_offers():
        return (
            CancelTaskOffer(kind="cancel_task"),
            ReviseTaskOffer(kind="revise_task"),
            CloseSessionOffer(kind="close_session"),
        )


__all__ = ["AssistantHandle", "AssistantSessionPort"]
