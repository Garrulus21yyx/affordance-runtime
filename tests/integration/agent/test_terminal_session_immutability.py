import asyncio

import pytest

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.execution import ActionResult, DispatchStatus
from tests.integration.agent.test_confirmation_continuation import _decision, _loop, _task, _world


def test_action_exception_latches_terminal_result_and_prevents_reentry() -> None:
    class RaisingEvaluator:
        calls = 0

        async def evaluate(self, *args):
            self.calls += 1
            raise RuntimeError("private evaluator detail")

    async def scenario() -> None:
        evaluator = RaisingEvaluator()
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("fresh", False, "#fresh"),),
            post_observations=(_world("after", True, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        loop = _loop()
        loop.action_evaluator = evaluator
        session = await (loop).start(environment, _task())
        paused = await session.run_until_pause()
        with pytest.raises(RuntimeError, match="private evaluator detail"):
            await session.resolve_confirmation(_decision(paused))

        terminal = await session.run_until_pause()
        repeated = await session.resolve_confirmation(
            ConfirmationDecision("confirmation:unused", "subject:unused", ConfirmationDecisionKind.DENY)
        )
        assert terminal is repeated is session.last_result
        assert terminal.status is AgentLoopStatus.FAILED
        assert terminal.reason_code == "runtime_exception"
        assert terminal.execution_count == 1
        assert len(environment.executed_requests) == 1
        assert evaluator.calls == 1
        assert session.state.control_transition_total_count == 1

    asyncio.run(scenario())


def test_confirmation_without_pending_does_not_create_a_fake_pause() -> None:
    async def scenario() -> None:
        session = await (_loop()).start(
            ScriptedEnvironment(initial_observation=_world("initial", False, "#initial")), _task()
        )
        rejected = await session.resolve_confirmation(
            ConfirmationDecision("confirmation:unused", "subject:unused", ConfirmationDecisionKind.DENY)
        )
        assert rejected.status is not AgentLoopStatus.WAITING_CONFIRMATION
        assert rejected.confirmation_request is None
        assert session.last_result is rejected

        repeated = await session.run_until_pause()
        assert repeated is rejected
        assert session.state.control_transition_total_count == 0

    asyncio.run(scenario())


def test_done_session_returns_original_result_after_repeated_confirmation() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(
            initial_observation=_world("initial", False, "#initial"),
            independent_observations=(_world("fresh", False, "#fresh"),),
            post_observations=(_world("after", True, "#after"),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await (_loop()).start(environment, _task())
        paused = await session.run_until_pause()
        decision = _decision(paused)
        terminal = await session.resolve_confirmation(decision)
        counts = (terminal.observation_count, terminal.execution_count, terminal.currentness_probe_count)

        repeated = await session.resolve_confirmation(decision)

        assert terminal.status == AgentLoopStatus.DONE
        assert repeated is terminal
        assert counts == (
            repeated.observation_count,
            repeated.execution_count,
            repeated.currentness_probe_count,
        )
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_cancelled_and_failed_sessions_cannot_be_rewritten() -> None:
    async def scenario() -> None:
        cancelled_environment = ScriptedEnvironment(initial_observation=_world("cancel", False, "#cancel"))
        cancelled_session = await (_loop()).start(cancelled_environment, _task())
        pause = await cancelled_session.run_until_pause()
        deny = _decision(pause, ConfirmationDecisionKind.DENY)
        cancelled = await cancelled_session.resolve_confirmation(deny)

        assert await cancelled_session.resolve_confirmation(deny) is cancelled
        assert await cancelled_session.run_until_pause() is cancelled
        assert cancelled.status == AgentLoopStatus.CANCELLED
        assert cancelled_environment.executed_requests == []

        repeated = _world("same", False, "#same")
        failed_environment = ScriptedEnvironment(initial_observation=repeated, independent_observations=(repeated,))
        failed_session = await (_loop()).start(failed_environment, _task())
        failed_pause = await failed_session.run_until_pause()
        confirm = _decision(failed_pause)
        failed = await failed_session.resolve_confirmation(confirm)

        assert failed.status == AgentLoopStatus.FAILED
        assert await failed_session.resolve_confirmation(confirm) is failed
        assert await failed_session.run_until_pause() is failed
        assert failed_environment.executed_requests == []

    asyncio.run(scenario())
