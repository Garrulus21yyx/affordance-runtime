from __future__ import annotations

import asyncio

from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import (
    Abort,
    AgentEpisodeRunner,
    AgentLoop,
    AgentLoopStatus,
    AgentPolicyTurn,
    AgentWorkingMemory,
    SelectAction,
    WorkingMemoryItem,
    WorkingMemoryItemStatus,
)
from affordance_runtime.testing import StaticEnvironment


def test_working_memory_is_installed_atomically_with_the_current_action() -> None:
    class Policy:
        calls = 0

        async def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                assert context.working_memory.items == ()
                return AgentPolicyTurn(
                    SelectAction(context.context_id, context.actions.options[0].action_id),
                    AgentWorkingMemory(
                        items=(
                            WorkingMemoryItem(
                                "Complete the current public task",
                                WorkingMemoryItemStatus.IN_PROGRESS,
                            ),
                        ),
                        goal="Complete the current public task",
                        derived_facts=("The first action remains unverified",),
                        next_step="Inspect the fresh world",
                        blockers=("The requested end state is not yet observed",),
                    ),
                )
            assert context.working_memory.revision == 1
            assert context.working_memory.items[0].description == "Complete the current public task"
            assert context.working_memory.items[0].status == "in_progress"
            assert context.working_memory.goal == "Complete the current public task"
            assert context.working_memory.derived_facts == ("The first action remains unverified",)
            assert context.working_memory.next_step == "Inspect the fresh world"
            assert context.working_memory.blockers == ("The requested end state is not yet observed",)
            return Abort(context.context_id, "memory observed", "policy")

    async def scenario() -> None:
        policy = Policy()
        environment = StaticEnvironment([_world("before", False), _world("after", False)], [_sent()])
        result = await AgentEpisodeRunner(AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
            environment, _task()
        )

        assert result.status is AgentLoopStatus.FAILED
        assert policy.calls == 2
        assert result.execution_count == 1
        assert result.observation_count == 2
        assert len(environment.executed_requests) == 1

    asyncio.run(scenario())


def test_policy_turn_memory_is_bounded_and_typed() -> None:
    turn = AgentPolicyTurn(
        SelectAction("context:1", "action:1"),
        AgentWorkingMemory((WorkingMemoryItem("Inspect current state", WorkingMemoryItemStatus.PENDING),)),
    )

    assert turn.working_memory.items[0].status is WorkingMemoryItemStatus.PENDING
