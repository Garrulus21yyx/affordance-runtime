import asyncio

import pytest

from affordance_runtime.benchmarks.external_smoke.pacing import (
    PacedAgentPolicy,
    validate_pacing_budget,
)


class Policy:
    async def decide(self, context):
        return context


def test_fixed_pacing_waits_between_calls_without_changing_decisions() -> None:
    now = [10.0]
    waits = []

    async def sleep(delay):
        waits.append(delay)
        now[0] += delay

    policy = PacedAgentPolicy(Policy(), 7.5, clock=lambda: now[0], sleeper=sleep)

    async def run():
        assert await policy.decide("first") == "first"
        now[0] += 2.5
        assert await policy.decide("second") == "second"

    asyncio.run(run())
    assert waits == [5.0]
    assert policy.calls == 2 and policy.total_wait_s == 5.0


def test_pacing_budget_coherence_accepts_valid_and_rejects_impossible_schedule() -> None:
    validate_pacing_budget(10, 7.5, 120.0, 5.0)
    with pytest.raises(ValueError, match="minimum pacing schedule"):
        validate_pacing_budget(20, 7.5, 120.0, 5.0)
