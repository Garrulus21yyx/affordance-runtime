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
    context_observer: Callable[[object], None] | None = None

    def __post_init__(self) -> None:
        if self.minimum_interval_s < 0:
            raise ValueError("fixed policy pacing interval cannot be negative")

    def __getattr__(self, name: str):
        """Keep policy decorators transparent to non-decision capabilities."""

        return getattr(self.wrapped, name)

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
        if self.context_observer is not None:
            self.context_observer(context)
        await _pace(self.minimum_interval_s, self.clock, self.sleeper, self.state)
        return await self.wrapped.decide(context)


async def _pace(minimum_interval_s, clock, sleeper, state) -> None:
    now = clock()
    if state.last_call_started_s is not None:
        delay = max(0.0, minimum_interval_s - (now - state.last_call_started_s))
        if delay:
            state.total_wait_s += delay
            await sleeper(delay)
            now = clock()
    state.last_call_started_s = now
    state.calls += 1


def validate_pacing_budget(
    max_turns: int,
    minimum_interval_s: float,
    timeout_s: float,
    scheduling_margin_s: float,
) -> None:
    if min(max_turns, timeout_s) <= 0 or min(minimum_interval_s, scheduling_margin_s) < 0:
        raise ValueError("pacing budget values must be non-negative and bounded")
    minimum_schedule_s = (max_turns - 1) * minimum_interval_s
    # Reserve one unit for each policy/execution turn and one for reset/finalization.
    minimum_execution_s = (max_turns + 1) * scheduling_margin_s
    if minimum_schedule_s + minimum_execution_s >= timeout_s:
        raise ValueError("minimum pacing and per-turn execution budget exhaust the case watchdog")
