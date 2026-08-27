from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .contracts import (
    Accepted,
    AnswerQuestion,
    AuthenticatedSessionLookup,
    CommandAdmission,
    CreateSessionResponse,
    LiveSession,
    Recovered,
    RecoveryAttempt,
    RecoveryFailed,
    RecoveryInspectionFailed,
    RecoveryRequired,
    RecoveryUnavailable,
    RecoveryUnsupported,
    Rejected,
    ReviseTask,
    RuntimeSessionSnapshot,
    ShellCommand,
    ShellEvent,
    StartTask,
)
from .conversation import BoundedConversation, ConversationTurn
from .port import (
    PortRecoverableCheckpoint,
    PortRecoveredHandle,
    PortRecoveryInspectionFailed,
    PortRecoveryInspectionUnavailable,
    PortRecoveryInspectionUnsupported,
    RuntimeSessionPort,
    RuntimeSessionUnavailable,
)
from .session_registry import SessionRecoveryRegistry

logger = logging.getLogger(__name__)


@dataclass
class ManagedSession:
    session_id: str
    session_key: str
    runtime_handle: object
    expires_at: datetime
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    conversation: BoundedConversation = field(default_factory=BoundedConversation)
    closed: bool = False
    cleanup_started: bool = False


class SessionNotFound(KeyError):
    pass


class SessionUnauthorized(PermissionError):
    pass


class SessionExpired(PermissionError):
    pass


class ViewerInputRejected(PermissionError):
    """The connected Viewer input lease is no longer authoritative."""


class RunSessionManager:
    """Own credentials, bounded conversation, locks, and single handle installation only."""

    def __init__(
        self,
        port: RuntimeSessionPort,
        recovery_registry: SessionRecoveryRegistry | None = None,
    ) -> None:
        self._port = port
        self._recovery_registry = recovery_registry
        self._sessions: dict[str, ManagedSession] = {}
        self._recovery_lock = asyncio.Lock()

    async def create(self, ttl_seconds: int = 1800) -> CreateSessionResponse:
        session_id = secrets.token_urlsafe(18)
        session_key = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        handle = await self._port.open(session_id, expires_at)
        managed = ManagedSession(session_id, session_key, handle, expires_at)
        try:
            snapshot = await self._snapshot(managed)
            if self._recovery_registry is not None:
                await self._recovery_registry.register(session_id, session_key, expires_at)
        except BaseException:
            await self._cleanup_once(managed)
            raise
        self._sessions[session_id] = managed
        return CreateSessionResponse(session_key=session_key, snapshot=snapshot)

    async def lookup(
        self,
        session_id: str,
        session_key: str,
    ) -> AuthenticatedSessionLookup:
        live = self._sessions.get(session_id)
        if live is not None:
            self._authenticate_live(live, session_key)
            if await self._expire_if_needed(live):
                raise SessionExpired(session_id)
            return LiveSession(kind="live_session", snapshot=await self._snapshot(live))
        if self._recovery_registry is None:
            return RecoveryUnsupported(
                kind="recovery_unsupported", reason_code="recovery_registry_unavailable"
            )
        await self._authenticate_recovery(session_id, session_key)
        inspection = await self._port.inspect(session_id)
        if isinstance(inspection, PortRecoverableCheckpoint):
            return RecoveryRequired(
                kind="recovery_required", checkpoint_id=inspection.checkpoint_id
            )
        if isinstance(inspection, PortRecoveryInspectionUnavailable):
            return RecoveryUnavailable(
                kind="recovery_unavailable", reason_code=inspection.reason_code
            )
        if isinstance(inspection, PortRecoveryInspectionUnsupported):
            return RecoveryUnsupported(
                kind="recovery_unsupported", reason_code=inspection.reason_code
            )
        assert isinstance(inspection, PortRecoveryInspectionFailed)
        return RecoveryInspectionFailed(
            kind="recovery_inspection_failed",
            reason_code=inspection.reason_code,
            retryable=inspection.retryable,
        )

    async def recover(
        self,
        session_id: str,
        session_key: str,
        checkpoint_id: str,
    ) -> RecoveryAttempt:
        async with self._recovery_lock:
            live = self._sessions.get(session_id)
            if live is not None:
                self._authenticate_live(live, session_key)
                if await self._expire_if_needed(live):
                    raise SessionExpired(session_id)
                return await self._port.recover_live(live.runtime_handle, checkpoint_id)

            if self._recovery_registry is None:
                from .contracts import RecoveryAttemptUnavailable

                return RecoveryAttemptUnavailable(
                    kind="recovery_unavailable", reason_code="recovery_unsupported"
                )

            credential = await self._authenticate_recovery(session_id, session_key)
            try:
                projection = await cast_registry(self._recovery_registry).load_projection(
                    session_id
                )
                conversation = BoundedConversation.from_projection(projection)
            except (TypeError, ValueError, LookupError):
                return RecoveryFailed(
                    kind="recovery_failed",
                    reason_code="shell_projection_restore_failed",
                    retryable=False,
                )
            except Exception:
                return RecoveryFailed(
                    kind="recovery_failed",
                    reason_code="shell_projection_restore_failed",
                    retryable=False,
                )
            result = await self._port.recover_absent(
                session_id,
                checkpoint_id,
                credential.expires_at,
            )
            if not isinstance(result, PortRecoveredHandle):
                return result
            managed = ManagedSession(
                session_id,
                session_key,
                result.handle,
                credential.expires_at,
                conversation=conversation,
            )
            try:
                snapshot = await self._snapshot(managed)
            except BaseException:
                await self._cleanup_once(managed, revoke=False)
                return RecoveryFailed(
                    kind="recovery_failed",
                    reason_code="shell_projection_restore_failed",
                    retryable=False,
                )
            # The recovery lock is the sole absent-handle installation boundary.
            self._sessions[session_id] = managed
            return Recovered(kind="recovered", snapshot=snapshot)

    def authenticate(self, session_id: str, session_key: str) -> ManagedSession:
        managed = self._sessions.get(session_id)
        if managed is None:
            raise SessionNotFound(session_id)
        self._authenticate_live(managed, session_key)
        return managed

    async def snapshot(self, session_id: str, session_key: str) -> RuntimeSessionSnapshot:
        managed = self.authenticate(session_id, session_key)
        if await self._expire_if_needed(managed):
            raise SessionExpired(session_id)
        return await self._snapshot(managed)

    async def events(
        self,
        session_id: str,
        session_key: str,
        after: int,
    ) -> tuple[ShellEvent, ...]:
        managed = self.authenticate(session_id, session_key)
        if await self._expire_if_needed(managed):
            raise SessionExpired(session_id)
        return await self._port.events(managed.runtime_handle, after)

    async def forward_viewer_input(
        self,
        session_id: str,
        session_key: str,
        control_lease_id: str,
        forward: Callable[[], Awaitable[None]],
    ) -> None:
        managed = self.authenticate(session_id, session_key)
        async with managed.lock:
            if await self._expire_if_needed(managed):
                raise SessionExpired(session_id)
            if managed.closed:
                raise ViewerInputRejected(session_id)
            if not await self._port.forward_viewer_input(
                managed.runtime_handle,
                control_lease_id,
                forward,
            ):
                raise ViewerInputRejected(session_id)

    async def admit(
        self,
        session_id: str,
        session_key: str,
        command: ShellCommand,
    ) -> CommandAdmission:
        managed = self.authenticate(session_id, session_key)
        async with managed.lock:
            if await self._expire_if_needed(managed):
                raise SessionExpired(session_id)
            conversation = None
            if isinstance(command, ReviseTask):
                candidate = managed.conversation.clone()
                first_seen = not candidate.has_revision_context(command.command_id)
                conversation = candidate.revision_context(command.command_id, command.text)
                if first_seen:
                    candidate.append(conversation.turns[-1])
                try:
                    await self._save_conversation_projection(managed, candidate)
                except RuntimeSessionUnavailable:
                    return Rejected(
                        kind="rejected",
                        command_id=command.command_id,
                        code="command_persistence_failed",
                        snapshot=await self._snapshot(managed),
                    )
                managed.conversation = candidate
            admission = await self._port.command(
                managed.runtime_handle,
                command,
                revision_conversation=conversation,
            )
            if isinstance(admission, Accepted) and isinstance(command, (StartTask, AnswerQuestion)):
                text = command.task if isinstance(command, StartTask) else command.answer
                candidate = managed.conversation.clone()
                candidate.append(
                    ConversationTurn(
                        turn_id=command.command_id,
                        role="user",
                        text=text,
                    )
                )
                try:
                    await self._save_conversation_projection(managed, candidate)
                except RuntimeSessionUnavailable:
                    logger.exception("accepted conversation projection could not be persisted")
                else:
                    managed.conversation = candidate
            return admission

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
                # Registry owns only auth/TTL/conversation and may survive process shutdown;
                # manager never reads checkpoint currentness to decide this lifecycle action.
                await self._cleanup_once(managed, revoke=False)
            except Exception as exc:
                errors.append(exc)
                logger.exception("session cleanup failed during shutdown: %s", managed.session_id)
        return tuple(errors)

    async def _authenticate_recovery(self, session_id: str, session_key: str):
        registry = self._recovery_registry
        if registry is None:
            raise RuntimeSessionUnavailable("recovery_registry_unavailable")
        credential = await registry.authenticate(session_id, session_key)
        if credential is None:
            raise SessionUnauthorized(session_id)
        if datetime.now(UTC) >= credential.expires_at:
            await registry.revoke(session_id)
            raise SessionExpired(session_id)
        return credential

    @staticmethod
    def _authenticate_live(managed: ManagedSession, session_key: str) -> None:
        if not secrets.compare_digest(managed.session_key, session_key):
            raise SessionUnauthorized(managed.session_id)

    async def _snapshot(self, managed: ManagedSession) -> RuntimeSessionSnapshot:
        snapshot = await self._port.snapshot(managed.runtime_handle)
        return snapshot.model_copy(update={"expires_at": managed.expires_at})

    async def _expire_if_needed(self, managed: ManagedSession) -> bool:
        if datetime.now(UTC) < managed.expires_at:
            return False
        await self._cleanup_once(managed)
        return True

    async def _save_conversation_projection(
        self,
        managed: ManagedSession,
        conversation: BoundedConversation,
    ) -> None:
        registry = self._recovery_registry
        if registry is None:
            return
        try:
            await registry.save_projection(managed.session_id, conversation.projection())
        except Exception as exc:
            raise RuntimeSessionUnavailable("shell_recovery_projection_persistence_failed") from exc

    async def _cleanup_once(self, managed: ManagedSession, *, revoke: bool = True) -> None:
        if managed.cleanup_started:
            return
        managed.cleanup_started = True
        try:
            await self._port.close(managed.runtime_handle)
        finally:
            managed.closed = True
            if revoke and self._recovery_registry is not None:
                await self._recovery_registry.revoke(managed.session_id)


def cast_registry(registry: SessionRecoveryRegistry | None) -> SessionRecoveryRegistry:
    if registry is None:  # guarded by _authenticate_recovery
        raise RuntimeError("recovery registry unavailable")
    return registry
