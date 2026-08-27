from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from .contracts import (
    CloseSessionOffer,
    SCHEMA_VERSION,
    RecoveryAttempt,
    RecoveryAttemptUnavailable,
    RevisionConversationContext,
    RuntimeSessionSnapshot,
    ShellCommand,
    Unsupported,
)
from .port import PortRecoveryInspectionUnsupported


@dataclass(frozen=True)
class UnavailableHandle:
    session_id: str
    expires_at: datetime
    event_epoch: str


class UnavailableRuntimeSessionPort:
    async def open(self, session_id: str, expires_at: datetime) -> UnavailableHandle:
        return UnavailableHandle(session_id, expires_at, secrets.token_urlsafe(18))

    async def inspect(self, session_id: str):
        del session_id
        return PortRecoveryInspectionUnsupported(
            "recovery_inspection_unsupported",
            "checkpoint_store_unavailable",
        )

    async def recover_absent(
        self, session_id: str, checkpoint_id: str, expires_at: datetime
    ) -> RecoveryAttempt:
        del session_id, checkpoint_id, expires_at
        return RecoveryAttemptUnavailable(
            kind="recovery_unavailable", reason_code="recovery_unsupported"
        )

    async def recover_live(self, handle: UnavailableHandle, checkpoint_id: str) -> RecoveryAttempt:
        del handle, checkpoint_id
        return RecoveryAttemptUnavailable(
            kind="recovery_unavailable", reason_code="checkpoint_unavailable"
        )

    async def snapshot(self, handle: UnavailableHandle) -> RuntimeSessionSnapshot:
        return RuntimeSessionSnapshot(
            schema_version=SCHEMA_VERSION,
            session_id=handle.session_id,
            expires_at=handle.expires_at,
            event_epoch=handle.event_epoch,
            command_offers=(CloseSessionOffer(kind="close_session"),),
        )

    async def events(self, handle: UnavailableHandle, after: int):
        del handle, after
        return ()

    async def forward_viewer_input(self, handle, control_lease_id, forward) -> bool:
        del handle, control_lease_id, forward
        return False

    async def command(
        self,
        handle: UnavailableHandle,
        command: ShellCommand,
        *,
        revision_conversation: RevisionConversationContext | None = None,
    ):
        del revision_conversation
        return Unsupported(
            kind="unsupported",
            command_id=command.command_id,
            code="command_not_supported",
            snapshot=await self.snapshot(handle),
        )

    async def close(self, handle: UnavailableHandle) -> None:
        del handle
