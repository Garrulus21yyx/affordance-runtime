from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .contracts import (
    Accepted,
    AnswerQuestion,
    ApproveAction,
    Capability,
    CloseSession,
    CommandAdmission,
    Conflict,
    CreateSessionResponse,
    RejectAction,
    RuntimeSessionSnapshot,
    ShellCommand,
    ShellEvent,
    StartTask,
    Unsupported,
)
from .conversation import BoundedConversation, ConversationTurn
from .port import RuntimeSessionPort


logger = logging.getLogger(__name__)


@dataclass
class ManagedSession:
    session_id: str
    session_key: str
    runtime_handle: object
    expires_at: datetime
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    commands: set[str] = field(default_factory=set)
    conversation: BoundedConversation = field(default_factory=BoundedConversation)
    closed: bool = False
    cleanup_started: bool = False


class SessionNotFound(KeyError):
    pass


class SessionUnauthorized(PermissionError):
    pass


class RunSessionManager:
    def __init__(self, port: RuntimeSessionPort) -> None:
        self._port = port
        self._sessions: dict[str, ManagedSession] = {}

    async def create(self, ttl_seconds: int = 1800) -> CreateSessionResponse:
        session_id = secrets.token_urlsafe(18)
        session_key = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        handle = await self._port.open(session_id, expires_at)
        managed = ManagedSession(session_id, session_key, handle, expires_at)
        try:
            snapshot = await self._snapshot(managed)
        except BaseException:
            await self._cleanup_once(managed)
            raise
        self._sessions[session_id] = managed
        return CreateSessionResponse(session_key=session_key, snapshot=snapshot)

    def authenticate(self, session_id: str, session_key: str) -> ManagedSession:
        managed = self._sessions.get(session_id)
        if managed is None:
            raise SessionNotFound(session_id)
        if not secrets.compare_digest(managed.session_key, session_key):
            raise SessionUnauthorized(session_id)
        return managed

    async def snapshot(self, session_id: str, session_key: str) -> RuntimeSessionSnapshot:
        managed = self.authenticate(session_id, session_key)
        await self._expire_if_needed(managed)
        snapshot = await self._snapshot(managed)
        await self._cleanup_if_terminal(managed, snapshot)
        return snapshot

    async def events(self, session_id: str, session_key: str, after: int) -> tuple[ShellEvent, ...]:
        managed = self.authenticate(session_id, session_key)
        await self._expire_if_needed(managed)
        events = await self._port.events(managed.runtime_handle, after)
        await self._cleanup_if_terminal(managed, await self._snapshot(managed))
        return events

    async def admit(self, session_id: str, session_key: str, command: ShellCommand) -> CommandAdmission:
        managed = self.authenticate(session_id, session_key)
        async with managed.lock:
            await self._expire_if_needed(managed)
            snapshot = await self._snapshot(managed)
            if command.command_id in managed.commands:
                return Conflict(
                    command_id=command.command_id,
                    code="duplicate_command",
                    snapshot=snapshot,
                )
            managed.commands.add(command.command_id)
            if managed.closed and not isinstance(command, CloseSession):
                return Conflict(command_id=command.command_id, code="session_closed", snapshot=snapshot)
            if (
                command.expected_task_revision != snapshot.task_revision
                or command.expected_run_status != snapshot.run_status
            ):
                return Conflict(command_id=command.command_id, code="stale_command", snapshot=snapshot)
            pending_conflict = self._pending_conflict(command, snapshot)
            if pending_conflict:
                return Conflict(
                    command_id=command.command_id,
                    code="pending_request_mismatch",
                    snapshot=snapshot,
                )
            capability = Capability(command.kind)
            if capability not in snapshot.capabilities:
                return Unsupported(
                    command_id=command.command_id,
                    capability=capability,
                    reason="capability_not_advertised_by_runtime_port",
                    snapshot=snapshot,
                )
            if isinstance(command, CloseSession):
                await self._cleanup_once(managed)
                closed_snapshot = await self._snapshot(managed)
                return Accepted(command_id=command.command_id, snapshot=closed_snapshot)
            admission, _events = await self._port.command(managed.runtime_handle, command)
            if isinstance(command, (StartTask, AnswerQuestion)):
                text = command.task if isinstance(command, StartTask) else command.answer
                managed.conversation.append(ConversationTurn(role="user", text=text))
            current = await self._snapshot(managed)
            if current.run_status.value in {"done", "failed", "blocked", "cancelled"}:
                await self._cleanup_if_terminal(managed, current)
                current = await self._snapshot(managed)
            return admission.model_copy(update={"snapshot": current})

    async def expire(self) -> int:
        expired = 0
        for managed in tuple(self._sessions.values()):
            if await self._expire_if_needed(managed):
                expired += 1
        return expired

    async def close_all(self) -> tuple[Exception, ...]:
        errors: list[Exception] = []
        for managed in tuple(self._sessions.values()):
            try:
                await self._cleanup_once(managed)
            except Exception as exc:
                errors.append(exc)
                logger.exception("session cleanup failed during shutdown: %s", managed.session_id)
        return tuple(errors)

    async def _snapshot(self, managed: ManagedSession) -> RuntimeSessionSnapshot:
        snapshot = await self._port.snapshot(managed.runtime_handle)
        return snapshot.model_copy(update={"expires_at": managed.expires_at})

    async def _expire_if_needed(self, managed: ManagedSession) -> bool:
        if datetime.now(UTC) < managed.expires_at:
            return False
        await self._cleanup_once(managed)
        return True

    async def _cleanup_if_terminal(self, managed: ManagedSession, snapshot: RuntimeSessionSnapshot) -> None:
        if snapshot.run_status.value in {"done", "failed", "blocked", "cancelled"}:
            await self._cleanup_once(managed)

    async def _cleanup_once(self, managed: ManagedSession) -> None:
        if managed.cleanup_started:
            return
        managed.cleanup_started = True
        try:
            await self._port.close(managed.runtime_handle)
        finally:
            managed.closed = True

    @staticmethod
    def _pending_conflict(command: ShellCommand, snapshot: RuntimeSessionSnapshot) -> bool:
        if isinstance(command, AnswerQuestion):
            return snapshot.pending_question is None or command.request_id != snapshot.pending_question.request_id
        if isinstance(command, (ApproveAction, RejectAction)):
            return (
                snapshot.pending_confirmation is None or command.request_id != snapshot.pending_confirmation.request_id
            )
        return False
