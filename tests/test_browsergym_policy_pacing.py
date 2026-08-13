import asyncio

import pytest

from affordance_runtime.benchmarks.external_smoke.pacing import (
    FixedPacingState,
    PacedAgentPolicy,
    PacedRequirementHypothesisProposer,
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


def test_policy_pacing_preserves_wrapped_capabilities() -> None:
    class PolicyWithPreparation:
        visual_predicate_classifier = object()

        async def decide(self, context):
            return context

    wrapped = PolicyWithPreparation()
    policy = PacedAgentPolicy(wrapped, 0)

    assert policy.visual_predicate_classifier is wrapped.visual_predicate_classifier


def test_pacing_budget_coherence_accepts_valid_and_rejects_impossible_schedule() -> None:
    validate_pacing_budget(10, 7.5, 120.0, 5.0)
    with pytest.raises(ValueError, match="minimum pacing schedule"):
        validate_pacing_budget(20, 7.5, 120.0, 5.0)


def test_policy_and_hypothesis_proposer_share_one_provider_pacing_clock() -> None:
    now = [10.0]
    waits = []
    state = FixedPacingState()

    async def sleep(delay):
        waits.append(delay)
        now[0] += delay

    class Proposer:
        async def propose(
            self, task, observation, action_space, *, mode, observation_cursor=""
        ):
            del observation_cursor
            return task, observation, action_space, mode

    proposer = PacedRequirementHypothesisProposer(
        Proposer(),
        7.5,
        clock=lambda: now[0],
        sleeper=sleep,
        state=state,
    )
    policy = PacedAgentPolicy(
        Policy(),
        7.5,
        clock=lambda: now[0],
        sleeper=sleep,
        state=state,
    )

    async def run():
        await proposer.propose("task", "world", "actions", mode="initial")
        now[0] += 2.5
        assert await policy.decide("decision") == "decision"

    asyncio.run(run())
    assert waits == [5.0]
    assert state.calls == 2
