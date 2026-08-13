from __future__ import annotations

import asyncio
from dataclasses import dataclass

from affordance_runtime import (
    LegacyRuntimeClient,
    NaturalLanguageTaskRequest,
    RuntimeClient,
    TargetRuntimeClient,
    TargetRuntimeRunOutcome,
    TaskBoundary,
    compose_target_runtime,
)
from affordance_runtime.agent import AgentLoopStatus, AskUser, UserInputResumed
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.task import ReadyTask, RiskProfile, TaskInputRequired
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import (
    CoverageState,
    SemanticTarget,
    StateFact,
    WorldObservation,
)


def _world() -> WorldObservation:
    target = SemanticTarget("page", "document", "Current page")
    fact = StateFact(
        "fact:page:available",
        "page",
        "available",
        True,
        "observation:client",
    )
    return WorldObservation(
        "observation:client",
        (target,),
        (fact,),
        (),
        {"static": CoverageState.COMPLETE},
    )


class UnusedActionEvaluator:
    async def evaluate(self, task, before, request, result, after):
        del task, before, request, result, after
        raise AssertionError("target client fixture must not execute an action")


class InputAwareTaskEvaluator:
    async def evaluate(self, task, observation):
        return TaskEvaluation(
            task.task_id,
            observation.observation_id,
            (
                TaskEvaluationStatus.COMPLETE
                if task.inputs.get("account") == "primary"
                else TaskEvaluationStatus.INCOMPLETE
            ),
            "fixture evaluation",
            completion_evidence_refs=(
                ("fact:page:available",)
                if task.inputs.get("account") == "primary"
                else ()
            ),
        )


@dataclass
class AskForAccountPolicy:
    calls: int = 0

    async def decide(self, context):
        self.calls += 1
        return AskUser(context.context_id, "Which account should I use?", ("inputs.account",))


def _request(*, revision: int = 1, account: str = "") -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(
        "task:target-client",
        "Inspect the selected account",
        TaskBoundary(inputs={"account": account} if account else {}),
        revision=revision,
    )


def test_target_client_runs_natural_language_request_and_resumes_input() -> None:
    async def scenario() -> None:
        policy = AskForAccountPolicy()
        client = TargetRuntimeClient(compose_target_runtime(
            policy,
            UnusedActionEvaluator(),
            InputAwareTaskEvaluator(),
        ))
        outcome = await client.run(StaticEnvironment((_world(),)), _request())

        assert isinstance(outcome, TargetRuntimeRunOutcome)
        assert isinstance(outcome.intake, ReadyTask)
        assert outcome.session is not None
        assert outcome.result is not None
        assert outcome.result.status is AgentLoopStatus.WAITING_USER
        assert outcome.result.user_input_request is not None

        resumed = await client.submit_user_input(
            outcome.session,
            outcome.result.user_input_request.input_request_id,
            _request(revision=2, account="primary"),
        )

        assert isinstance(resumed, UserInputResumed)
        assert resumed.result.status is AgentLoopStatus.DONE
        assert policy.calls == 1

    asyncio.run(scenario())


def test_target_client_preserves_nonready_intake_without_environment_access() -> None:
    class Environment:
        reset_calls = 0

        async def reset(self, task):
            del task
            self.reset_calls += 1
            raise AssertionError("nonready client intake must not reset the environment")

    environment = Environment()
    client = TargetRuntimeClient(compose_target_runtime(
        AskForAccountPolicy(),
        UnusedActionEvaluator(),
        InputAwareTaskEvaluator(),
    ))
    outcome = asyncio.run(client.run(
        environment,
        NaturalLanguageTaskRequest(
            "task:target-client-nonready",
            "Modify the selected account",
            TaskBoundary(risk_profile=RiskProfile.LOW),
        ),
    ))

    assert isinstance(outcome.intake, TaskInputRequired)
    assert not outcome.started
    assert outcome.session is None
    assert outcome.result is None
    assert environment.reset_calls == 0


def test_legacy_runtime_client_has_an_explicit_compatibility_name() -> None:
    assert LegacyRuntimeClient is RuntimeClient
