from __future__ import annotations

import asyncio

import pytest
from test_agent_loop import (
    ScriptedPolicy,
    SharedActionEvaluator,
    SharedTaskEvaluator,
    _loop,
    _sent,
    _task,
    _world,
)

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import AcquisitionOrigin


class RaisingActionEvaluator:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def evaluate(self, *args):
        del args
        raise self.exc


class SecondCallTaskEvaluator:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls = 0

    async def evaluate(self, task, observation):
        self.calls += 1
        if self.calls == 2:
            raise self.exc
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "incomplete",
        )


@pytest.mark.parametrize("stage", ("action", "task"))
def test_evaluator_runtime_error_preserves_incremental_execution_truth(stage: str) -> None:
    async def scenario() -> None:
        action_evaluator = (
            RaisingActionEvaluator(RuntimeError("private evaluator detail"))
            if stage == "action" else SharedActionEvaluator()
        )
        task_evaluator = (
            SecondCallTaskEvaluator(RuntimeError("private evaluator detail"))
            if stage == "task" else SharedTaskEvaluator()
        )
        session = await AgentEpisodeRunner(
            AgentLoop(ScriptedPolicy(["first"]), action_evaluator, task_evaluator)
        ).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [_sent()]),
            _task(),
        )

        with pytest.raises(RuntimeError, match="private evaluator detail"):
            await session.run_until_pause()

        root = session.state.recent_control_transitions[0]
        assert root.resulting_status is AgentLoopStatus.FAILED
        assert root.reason_code == "runtime_exception"
        assert root.execution is not None
        assert root.execution.dispatch_status is DispatchStatus.SENT
        assert root.after_observation_id == "after"
        assert root.acquisition is not None and root.acquisition.attempts == 1
        assert session.state.current_observation.observation_id == "after"
        assert session.execution_count == 1
        assert session.observation_count == 2

    asyncio.run(scenario())


def test_evaluator_cancellation_preserves_facts_and_propagates() -> None:
    async def scenario() -> None:
        session = await AgentEpisodeRunner(
            AgentLoop(
                ScriptedPolicy(["first"]),
                RaisingActionEvaluator(asyncio.CancelledError()),
                SharedTaskEvaluator(),
            )
        ).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [_sent()]),
            _task(),
        )
        with pytest.raises(asyncio.CancelledError):
            await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert root.resulting_status is AgentLoopStatus.CANCELLED
        assert root.reason_code == "runtime_cancelled"
        assert root.after_observation_id == "after"
        assert session.execution_count == 1
        assert session.observation_count == 2

    asyncio.run(scenario())


def test_lineage_mismatch_preserves_expected_and_actual_request_identity() -> None:
    async def scenario() -> None:
        result = ActionResult("request:wrong", DispatchStatus.SENT, "dom", True)
        session = await AgentEpisodeRunner(_loop(ScriptedPolicy(["first"]))).start(
            StaticEnvironment([_world("before", False), _world("after", True)], [result]),
            _task(),
        )
        terminal = await session.run_until_pause()
        root = session.state.recent_control_transitions[0]
        assert terminal.reason_code == "action_result_lineage_mismatch"
        assert root.execution is not None
        assert root.execution.expected_request_id == root.request_id
        assert root.execution.request_id == "request:wrong"
        assert root.acquisition is not None and root.acquisition.attempts == 1
        assert session.execution_count == 1
        assert session.observation_count == 2
        assert tuple(item.origin for item in root.acquisition_attempts) == (
            AcquisitionOrigin.POST_ACTION,
        )

    asyncio.run(scenario())
