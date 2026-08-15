from __future__ import annotations

import asyncio
from dataclasses import dataclass

from affordance_runtime import (
    NaturalLanguageTaskRequest,
    TargetRuntimeRunOutcome,
    TaskBoundary,
)
from affordance_runtime.agent import (
    AgentLoopStatus,
    AskUser,
    UserInputResumed,
)
from affordance_runtime.app import (
    compose_target_runtime,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.task import ReadyTask, RiskProfile, TaskInputRequired
from affordance_runtime.world import SemanticTarget, StateFact, WorldObservation
from tests.support.world import fused_world


def _world() -> WorldObservation:
    target = SemanticTarget("page", "document", "Current page")
    fact = StateFact("fact:page:available", "page", "available", True, "observation:runtime")
    return fused_world("observation:runtime", (target,), (fact,), surface="static")


class UnusedActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, before, request, result, after
        raise AssertionError("target runtime fixture must not execute an action")


class InputAwareTaskEvaluator:
    async def evaluate(self, task, observation):
        complete = task.inputs.get("account") == "primary"
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            TaskEvaluationStatus.COMPLETE if complete else TaskEvaluationStatus.INCOMPLETE,
            "fixture evaluation",
            completion_evidence_refs=(("fact:page:available",) if complete else ()),
        )


@dataclass
class AskForAccountPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        return AskUser(context.context_id, "Which account should I use?", ("inputs.account",))


def _request(*, revision: int = 1, account: str = "") -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(
        "task:target-runtime",
        "Inspect the selected account",
        TaskBoundary(inputs={"account": account} if account else {}),
        revision=revision,
    )


def _runtime(policy: AskForAccountPolicy | None = None):
    return compose_target_runtime(
        policy or AskForAccountPolicy(),
        UnusedActionEvaluator(),
        InputAwareTaskEvaluator(),
    )


def test_target_runtime_runs_natural_language_request_and_resumes_input() -> None:
    async def scenario() -> None:
        policy = AskForAccountPolicy()
        runtime = _runtime(policy)
        outcome = await runtime.run_request(ScriptedEnvironment(initial_observation=_world()), _request())

        assert isinstance(outcome, TargetRuntimeRunOutcome)
        assert isinstance(outcome.intake, ReadyTask)
        assert outcome.session is not None
        assert outcome.result is not None
        assert outcome.result.status is AgentLoopStatus.WAITING_USER
        assert outcome.result.user_input_request is not None

        resumed = await runtime.submit_user_input(
            outcome.session,
            outcome.result.user_input_request.input_request_id,
            _request(revision=2, account="primary"),
        )

        assert isinstance(resumed, UserInputResumed)
        assert resumed.result.status is AgentLoopStatus.DONE
        assert policy.calls == 1

    asyncio.run(scenario())


def test_target_runtime_preserves_nonready_intake_without_environment_access() -> None:
    class Environment:
        reset_calls = 0

        async def reset(self, task):
            del task
            self.reset_calls += 1
            raise AssertionError("nonready runtime intake must not reset the environment")

    environment = Environment()
    outcome = asyncio.run(
        _runtime().run_request(
            environment,
            NaturalLanguageTaskRequest(
                "task:target-runtime-nonready",
                "Modify the selected account",
                TaskBoundary(risk_profile=RiskProfile.LOW),
            ),
        )
    )

    assert isinstance(outcome.intake, TaskInputRequired)
    assert not outcome.started
    assert outcome.session is None
    assert outcome.result is None
    assert environment.reset_calls == 0


def test_target_runtime_runs_one_pre_admitted_request_without_recompiling() -> None:
    async def scenario() -> None:
        policy = AskForAccountPolicy()
        runtime = _runtime(policy)
        admitted = runtime.admit(_request(account="primary"))
        assert isinstance(admitted, ReadyTask)

        outcome = await runtime.run_admitted(ScriptedEnvironment(initial_observation=_world()), admitted)

        assert outcome.result is not None
        assert outcome.result.status is AgentLoopStatus.DONE
        assert policy.calls == 0

    asyncio.run(scenario())
