"""Injectable wait boundary; tests use fakes and never sleep."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


class WaitController(Protocol):
    async def wait(self, max_wait_ms: int) -> None: ...


@dataclass(frozen=True)
class SystemWaitController:
    async def wait(self, max_wait_ms: int) -> None:
        await asyncio.sleep(max_wait_ms / 1_000)
