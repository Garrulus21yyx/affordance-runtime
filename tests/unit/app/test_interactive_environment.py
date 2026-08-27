from __future__ import annotations

import asyncio
from dataclasses import dataclass

from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.policy import AgentDecisionPorts
from affordance_runtime.agent.run_state import RunStatus
from affordance_runtime.app.interactive_environment import (
    InteractiveTaskEnvironment,
    InteractiveTaskEvaluator,
)
from affordance_runtime.app.public_session import PublicSessionStatus, _completion
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import TaskEvaluationStatus, TaskOutcomeKind
from affordance_runtime.execution import DispatchStatus
from affordance_runtime.goals import NotRequiredGoalCompiler
from affordance_runtime.task import TaskGoal
from tests.support.agent.core_loop_support import SharedActionOutcomeProjector, shared_world


@dataclass
class FinalPolicy:
    async def decide(self, context):
        return FinalResponse(context.context_id, "The answer is 42.")


def test_interactive_task_closes_only_after_one_final_response_is_delivered() -> None:
    async def scenario() -> None:
        task = TaskGoal("task:interactive", "Find and report the answer")
        wrapped = ScriptedEnvironment(
            shared_world("interactive-world", False),
            independent_observations=(shared_world("interactive-world-final", False),),
        )
        environment = InteractiveTaskEnvironment(wrapped)
        evaluator = InteractiveTaskEvaluator(environment)
        initial = await environment.reset(task)
        assert initial.observation is not None

        before = await evaluator.evaluate(task, initial.observation)
        finalization = await environment.finalize("The answer is 42.")
        assert finalization.post_acquisition is not None
        assert finalization.post_acquisition.observation is not None
        after = await evaluator.evaluate(
            task,
            finalization.post_acquisition.observation,
        )
        duplicate = await environment.finalize("A conflicting second answer")

        assert before.status is TaskEvaluationStatus.INCOMPLETE
        assert finalization.result.dispatch_status is DispatchStatus.SENT
        assert after.status is TaskEvaluationStatus.COMPLETE
        assert after.outcome is not None
        assert after.outcome.kind is TaskOutcomeKind.TERMINAL_SUCCESS
        assert duplicate.result.dispatch_status is DispatchStatus.NOT_SENT

    asyncio.run(scenario())


def test_interactive_environment_closes_the_existing_core_loop_without_a_second_executor() -> None:
    async def scenario() -> None:
        task = TaskGoal("task:interactive-runtime", "Find and report the answer")
        wrapped = ScriptedEnvironment(
            shared_world("interactive-runtime", False),
            independent_observations=(shared_world("interactive-runtime-final", False),),
        )
        environment = InteractiveTaskEnvironment(wrapped)
        runtime = TargetRuntime(
            AgentDecisionPorts(FinalPolicy()),
            SharedActionOutcomeProjector(),
            InteractiveTaskEvaluator(environment),
            goal_compiler=NotRequiredGoalCompiler("interactive_session"),
        )

        state = await runtime.run_task(environment, task)  # type: ignore[arg-type]

        assert state.status is RunStatus.DONE
        assert state.last_step is not None
        assert state.last_step.feedback == "final_response_evaluated"
        assert state.finalization is not None
        assert state.finalization.stop_send_count == 1
        completion = _completion(state, PublicSessionStatus.DONE)
        assert completion is not None
        assert completion.outcome == "success"
        assert completion.message == "The answer is 42."

    asyncio.run(scenario())
