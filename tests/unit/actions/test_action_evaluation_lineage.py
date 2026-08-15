import asyncio

import pytest

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import ActionEvaluation, ActionEvaluationStatus
from tests.integration.agent.test_agent_loop import ScriptedPolicy, SharedTaskEvaluator, _sent, _task, _world


@pytest.mark.parametrize(
    "status",
    (ActionEvaluationStatus.EFFECT_CONFIRMED, ActionEvaluationStatus.NO_EFFECT_CONFIRMED),
)
def test_confirmed_action_evaluation_requires_authoritative_evidence_ref(status) -> None:
    with pytest.raises(ValueError, match="evidence reference"):
        ActionEvaluation(
            "request:1",
            "before:1",
            "after:1",
            status,
            "model-like reason text is not evidence",
        )


@pytest.mark.parametrize("wrong_field", ("request", "before", "after"))
def test_agent_loop_rejects_action_evaluation_with_wrong_lineage(wrong_field: str) -> None:
    class WrongLineageEvaluator:
        async def evaluate(self, task, before, request, result, after):
            del task, result
            return ActionEvaluation(
                "request:wrong" if wrong_field == "request" else request.request_id,
                "before:wrong" if wrong_field == "before" else before.observation_id,
                "after:wrong" if wrong_field == "after" else after.observation_id,
                ActionEvaluationStatus.UNKNOWN,
                "lineage fixture",
            )

    class FailIfCalledTaskEvaluator(SharedTaskEvaluator):
        def __init__(self) -> None:
            self.calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            if self.calls > 1:
                raise AssertionError("TaskEvaluator must not trust wrong action-evaluation lineage")
            return await super().evaluate(task, observation)

    async def scenario() -> None:
        task_evaluator = FailIfCalledTaskEvaluator()
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False), post_observations=(_world("after", True),), results=[_sent()]
        )
        loop = AgentLoop(ScriptedPolicy(["first"]), WrongLineageEvaluator(), task_evaluator)

        result = await (loop).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert "evaluation lineage" in result.message
        assert result.execution_count == 1
        assert result.control_transitions[-1].action_evaluation is None
        assert task_evaluator.calls == 1

    asyncio.run(scenario())
