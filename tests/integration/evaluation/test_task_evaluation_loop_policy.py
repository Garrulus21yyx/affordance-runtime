import asyncio

import pytest

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.confirmation import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.evaluation import (
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
    TaskOutcomeFact,
    TaskOutcomeKind,
)
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.task.contracts import criterion_id
from tests.integration.agent.test_agent_loop import ScriptedPolicy, SharedActionEvaluator, _task, _world
from tests.integration.agent.test_confirmation_continuation import ActionEvaluator, FirstPolicy
from tests.integration.agent.test_confirmation_continuation import _task as confirmation_task
from tests.integration.agent.test_confirmation_continuation import _world as confirmation_world


class SequencedTaskEvaluator:
    def __init__(self, *statuses: TaskEvaluationStatus) -> None:
        self.statuses = list(statuses)

    async def evaluate(self, task, observation):
        status = self.statuses.pop(0)
        complete = status == TaskEvaluationStatus.COMPLETE
        fact_ref = observation.facts[0].fact_id
        criteria = (
            tuple(
                CriterionEvaluation(
                    criterion_id(item),
                    CriterionEvaluationStatus.SATISFIED,
                    (fact_ref,),
                    "criterion satisfied",
                )
                for item in task.success_criteria
            )
            if complete
            else ()
        )
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            status,
            f"task evaluation is {status.value}",
            criteria,
            (fact_ref,) if complete else (),
        )


class FailIfCalledPolicy:
    async def decide(self, context):
        task, world, action_space = context.task, context.world, context.actions
        recent_turns = context.history.items
        del task, world, action_space, recent_turns
        raise AssertionError("policy must not run for UNKNOWN/BLOCKED task evaluation")


@pytest.mark.parametrize(
    ("status", "loop_status"),
    (
        (TaskEvaluationStatus.UNKNOWN, AgentLoopStatus.WAITING_USER),
        (TaskEvaluationStatus.BLOCKED, AgentLoopStatus.BLOCKED),
    ),
)
def test_initial_non_incomplete_task_evaluation_controls_loop(status, loop_status) -> None:
    async def scenario() -> None:
        evaluator = SequencedTaskEvaluator(status)
        loop = AgentLoop(FailIfCalledPolicy(), SharedActionEvaluator(), evaluator)
        environment = ScriptedEnvironment(initial_observation=_world("initial", False))

        result = await (loop).run(environment, _task())

        assert result.status == loop_status
        assert result.execution_count == 0
        assert result.message == f"task evaluation is {status.value}"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "loop_status"),
    (
        (TaskEvaluationStatus.COMPLETE, AgentLoopStatus.DONE),
        (TaskEvaluationStatus.UNKNOWN, AgentLoopStatus.WAITING_USER),
        (TaskEvaluationStatus.BLOCKED, AgentLoopStatus.BLOCKED),
    ),
)
def test_confirmation_fresh_task_evaluation_prevents_execution(status, loop_status) -> None:
    async def scenario() -> None:
        evaluator = SequencedTaskEvaluator(TaskEvaluationStatus.INCOMPLETE, status)
        loop = AgentLoop(FirstPolicy(), ActionEvaluator(), evaluator)
        environment = ScriptedEnvironment(
            initial_observation=confirmation_world("initial", False, "#initial"),
            independent_observations=(confirmation_world("fresh", status == TaskEvaluationStatus.COMPLETE, "#fresh"),),
        )
        session = await (loop).start(environment, confirmation_task())
        paused = await session.run_until_pause()
        request = paused.confirmation_request
        assert request is not None
        decision = ConfirmationDecision(
            request.confirmation_id,
            request.subject_id,
            ConfirmationDecisionKind.CONFIRM,
        )

        result = await session.resolve_confirmation(decision)

        assert result.status == loop_status
        assert result.execution_count == 0
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_post_action_blocked_stops_before_another_policy_turn() -> None:
    async def scenario() -> None:
        evaluator = SequencedTaskEvaluator(
            TaskEvaluationStatus.INCOMPLETE,
            TaskEvaluationStatus.BLOCKED,
        )
        environment = ScriptedEnvironment(
            initial_observation=_world("before", False),
            post_observations=(_world("after", True),),
            results=[ActionResult("*", DispatchStatus.SENT, "dom", True)],
        )
        loop = AgentLoop(ScriptedPolicy(["first"]), SharedActionEvaluator(), evaluator)

        result = await (loop).run(environment, _task())

        assert result.status == AgentLoopStatus.BLOCKED
        assert result.execution_count == 1
        assert result.message == "task evaluation is blocked"

    asyncio.run(scenario())


def test_canonical_task_terminal_failure_is_absorbing_without_runtime_failure() -> None:
    class TerminalEvaluator:
        calls = 0

        async def evaluate(self, task, observation):
            self.calls += 1
            return TaskEvaluation(
                task.task_id,
                observation.observation_id,
                TaskEvaluationStatus.BLOCKED,
                "official negative terminal",
                outcome=TaskOutcomeFact(
                    TaskOutcomeKind.TERMINAL_FAILURE,
                    "verified_terminal_task_failure",
                    (observation.facts[0].fact_id,),
                ),
            )

    async def scenario() -> None:
        evaluator = TerminalEvaluator()
        loop = AgentLoop(FailIfCalledPolicy(), SharedActionEvaluator(), evaluator)
        session = await (loop).start(
            ScriptedEnvironment(initial_observation=_world("initial", False)),
            _task(),
        )

        first = await session.run_until_pause()
        second = await session.run_until_pause()

        assert first is second
        assert first.status is AgentLoopStatus.BLOCKED
        assert first.runtime_failure is None
        assert first.task_outcome is not None
        assert first.task_outcome.kind is TaskOutcomeKind.TERMINAL_FAILURE
        assert first.execution_count == 0
        assert evaluator.calls == 1

    asyncio.run(scenario())
