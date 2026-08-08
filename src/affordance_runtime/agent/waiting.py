"""Injectable wait boundary; tests use fakes and never sleep."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.model_boundary.budgets import DEFAULT_MAX_TOTAL_WAIT_MS

MAX_TOTAL_WAIT_MS = DEFAULT_MAX_TOTAL_WAIT_MS


class WaitController(Protocol):
    async def wait(self, max_wait_ms: int) -> None: ...


@dataclass(frozen=True)
class SystemWaitController:
    async def wait(self, max_wait_ms: int) -> None:
        await asyncio.sleep(max_wait_ms / 1_000)
