from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, TypeAlias

from .contracts import (
    CommandAdmission,
    RecoveryAttempt,
    RevisionConversationContext,
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


@dataclass(frozen=True)
class PortRecoverableCheckpoint:
    kind: Literal["recoverable_checkpoint"]
    checkpoint_id: str


@dataclass(frozen=True)
class PortRecoveryInspectionUnavailable:
    kind: Literal["recovery_inspection_unavailable"]
    reason_code: Literal["checkpoint_not_found", "checkpoint_consumed", "checkpoint_unavailable"]


@dataclass(frozen=True)
class PortRecoveryInspectionUnsupported:
    kind: Literal["recovery_inspection_unsupported"]
    reason_code: Literal["checkpoint_store_unavailable", "recovery_reconnector_unavailable"]


@dataclass(frozen=True)
class PortRecoveryInspectionFailed:
    kind: Literal["recovery_inspection_failed"]
    reason_code: Literal["checkpoint_inspection_failed"]
    retryable: bool = False


PortRecoveryInspection: TypeAlias = (
    PortRecoverableCheckpoint
    | PortRecoveryInspectionUnavailable
    | PortRecoveryInspectionUnsupported
    | PortRecoveryInspectionFailed
)


@dataclass(frozen=True)
class PortRecoveredHandle:
    handle: Any
    attempt: RecoveryAttempt


class RuntimeSessionPort(Protocol):
    """The only Shell-to-Runtime boundary."""

    async def open(self, session_id: str, expires_at: datetime) -> Any: ...

    async def inspect(self, session_id: str) -> PortRecoveryInspection: ...

    async def recover_absent(
        self, session_id: str, checkpoint_id: str, expires_at: datetime
    ) -> PortRecoveredHandle | RecoveryAttempt: ...

    async def recover_live(self, handle: Any, checkpoint_id: str) -> RecoveryAttempt: ...

    async def snapshot(self, handle: Any) -> RuntimeSessionSnapshot: ...

    async def events(self, handle: Any, after: int) -> tuple[ShellEvent, ...]: ...

    async def forward_viewer_input(
        self,
        handle: Any,
        control_lease_id: str,
        forward: Callable[[], Awaitable[None]],
    ) -> bool: ...

    async def command(
        self,
        handle: Any,
        command: ShellCommand,
        *,
        revision_conversation: RevisionConversationContext | None = None,
    ) -> CommandAdmission: ...

    async def close(self, handle: Any) -> None: ...
