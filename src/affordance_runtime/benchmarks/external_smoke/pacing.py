"""Benchmark-only fixed policy-call pacing; never retry or failure backoff."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass
class FixedPacingState:
    calls: int = 0
    total_wait_s: float = 0.0
    last_call_started_s: float | None = None


@dataclass
class PacedAgentPolicy:
    wrapped: object
    minimum_interval_s: float = 7.5
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep
    state: FixedPacingState = field(default_factory=FixedPacingState)

    def __post_init__(self) -> None:
        if self.minimum_interval_s < 0:
            raise ValueError("fixed policy pacing interval cannot be negative")

    @property
    def last_metadata(self):
        return getattr(self.wrapped, "last_metadata", None)

    @property
    def calls(self) -> int:
        return self.state.calls

    @property
    def total_wait_s(self) -> float:
        return self.state.total_wait_s

    async def decide(self, context):
        now = self.clock()
        if self.state.last_call_started_s is not None:
            delay = max(0.0, self.minimum_interval_s - (now - self.state.last_call_started_s))
            if delay:
                self.state.total_wait_s += delay
                await self.sleeper(delay)
                now = self.clock()
        self.state.last_call_started_s = now
        self.state.calls += 1
        return await self.wrapped.decide(context)


def validate_pacing_budget(
    max_turns: int,
    minimum_interval_s: float,
    timeout_s: float,
    scheduling_margin_s: float,
) -> None:
    if min(max_turns, timeout_s) <= 0 or min(minimum_interval_s, scheduling_margin_s) < 0:
        raise ValueError("pacing budget values must be non-negative and bounded")
    minimum_schedule_s = (max_turns - 1) * minimum_interval_s
    if minimum_schedule_s >= timeout_s - scheduling_margin_s:
        raise ValueError("minimum pacing schedule exhausts the case watchdog budget")
