from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from .contracts import (
    Capability,
    RuntimeSessionSnapshot,
    ShellCommand,
    Unsupported,
)


@dataclass(frozen=True)
class UnavailableHandle:
    session_id: str
    expires_at: datetime
    event_epoch: str


class UnavailableRuntimeSessionPort:
    """Production-safe default until Runtime publishes a versioned public session port."""

    capabilities = frozenset({Capability.CLOSE_SESSION})

    async def open(self, session_id: str, expires_at: datetime) -> UnavailableHandle:
        return UnavailableHandle(session_id, expires_at, secrets.token_urlsafe(18))

    async def snapshot(self, handle: UnavailableHandle) -> RuntimeSessionSnapshot:
        return RuntimeSessionSnapshot(
            session_id=handle.session_id,
            expires_at=handle.expires_at,
            event_epoch=handle.event_epoch,
            capabilities=self.capabilities,
        )

    async def events(self, handle: UnavailableHandle, after: int):
        del handle, after
        return ()

    async def command(self, handle: UnavailableHandle, command: ShellCommand):
        snapshot = await self.snapshot(handle)
        capability = Capability(command.kind)
        return (
            Unsupported(
                command_id=command.command_id,
                capability=capability,
                reason="Runtime has not published the required versioned session capability",
                snapshot=snapshot,
            ),
            (),
        )

    async def close(self, handle: UnavailableHandle) -> None:
        return None
