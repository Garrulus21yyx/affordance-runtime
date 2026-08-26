from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .contracts import (
    Capability,
    CommandAdmission,
    RuntimeSessionSnapshot,
    ShellCommand,
    ShellEvent,
)


class RuntimeSessionHandle(Protocol):
    """Opaque public handle. It must never expose internal Runtime state."""


class RuntimeSessionUnavailable(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RuntimeSessionPort(Protocol):
    """The only shell-to-Runtime boundary."""

    @property
    def capabilities(self) -> frozenset[Capability]: ...

    async def open(self, session_id: str, expires_at: datetime) -> Any: ...

    async def recover(
        self, session_id: str, checkpoint_id: str, expires_at: datetime
    ) -> Any: ...

    async def snapshot(self, handle: Any) -> RuntimeSessionSnapshot: ...

    async def events(self, handle: Any, after: int) -> tuple[ShellEvent, ...]: ...

    async def command(self, handle: Any, command: ShellCommand) -> tuple[CommandAdmission, tuple[ShellEvent, ...]]: ...

    async def close(self, handle: Any) -> None: ...
