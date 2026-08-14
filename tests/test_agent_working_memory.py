from __future__ import annotations

import asyncio

from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import (
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    SelectAction,
    UpdateWorkingMemory,
    WorkingMemoryItem,
    WorkingMemoryItemStatus,
)
from affordance_runtime.testing import StaticEnvironment


def test_working_memory_update_is_advisory_and_zero_environment_step() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                assert context.working_memory.items == ()
                return UpdateWorkingMemory(
                    context.context_id,
                    (
                        WorkingMemoryItem(
                            "Complete the current public task",
                            WorkingMemoryItemStatus.IN_PROGRESS,
                        ),
                    ),
                )
            assert context.working_memory.revision == 1
            assert context.working_memory.items[0].description == "Complete the current public task"
            assert context.working_memory.items[0].status == "in_progress"
            return SelectAction(context.context_id, context.actions.options[0].action_id)

    async def scenario() -> None:
        environment = StaticEnvironment([_world("before", False), _world("after", True)], [_sent()])
        result = await AgentEpisodeRunner(
            AgentLoop(Policy(), SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())

        assert result.status is AgentLoopStatus.DONE
        assert result.execution_count == 1
        assert result.observation_count == 2
        assert result.control_transition_total_count == 1
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_working_memory_replacement_is_bounded_and_typed() -> None:
    decision = UpdateWorkingMemory(
        "context:1",
        (WorkingMemoryItem("Inspect current state", WorkingMemoryItemStatus.PENDING),),
    )

    assert decision.items[0].status is WorkingMemoryItemStatus.PENDING
