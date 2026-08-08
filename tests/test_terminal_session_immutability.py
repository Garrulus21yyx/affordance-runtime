import asyncio

from test_confirmation_continuation import _decision, _loop, _task, _world

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoopStatus
from affordance_runtime.confirmation import ConfirmationDecisionKind
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.testing import StaticEnvironment


def test_done_session_returns_original_result_after_repeated_confirmation() -> None:
    async def scenario() -> None:
        environment = StaticEnvironment(
            [_world("initial", False, "#initial"), _world("fresh", False, "#fresh"), _world("after", True, "#after")],
            [ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        session = await AgentEpisodeRunner(_loop()).start(environment, _task())
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
        cancelled_environment = StaticEnvironment([_world("cancel", False, "#cancel")])
        cancelled_session = await AgentEpisodeRunner(_loop()).start(cancelled_environment, _task())
        pause = await cancelled_session.run_until_pause()
        deny = _decision(pause, ConfirmationDecisionKind.DENY)
        cancelled = await cancelled_session.resolve_confirmation(deny)

        assert await cancelled_session.resolve_confirmation(deny) is cancelled
        assert await cancelled_session.run_until_pause() is cancelled
        assert cancelled.status == AgentLoopStatus.CANCELLED
        assert cancelled_environment.executed_requests == []

        repeated = _world("same", False, "#same")
        failed_environment = StaticEnvironment([repeated, repeated])
        failed_session = await AgentEpisodeRunner(_loop()).start(failed_environment, _task())
        failed_pause = await failed_session.run_until_pause()
        confirm = _decision(failed_pause)
        failed = await failed_session.resolve_confirmation(confirm)

        assert failed.status == AgentLoopStatus.FAILED
        assert await failed_session.resolve_confirmation(confirm) is failed
        assert await failed_session.run_until_pause() is failed
        assert failed_environment.executed_requests == []

    asyncio.run(scenario())
