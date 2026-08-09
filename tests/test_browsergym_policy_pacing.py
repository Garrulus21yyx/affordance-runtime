import asyncio

from affordance_runtime.benchmarks.external_smoke.pacing import PacedAgentPolicy


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
