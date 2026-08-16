import asyncio
from dataclasses import dataclass, replace

from affordance_runtime.actions import (
    ActionSpaceBuilder,
)
from affordance_runtime.agent import (
    Abort,
    RunStatus,
    SelectAction,
)
from affordance_runtime.agent.context import ContextBuilder, ModelFailure, ModelFailureKind
from affordance_runtime.agent.policy import AgentDecisionPorts, PolicyFailure
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.model.policy import (
    ModelBackedAgentPolicy,
    ModelMetadata,
    ResolvedModelDecision,
)
from tests.support.agent.core_loop_support import SharedActionEvaluator, SharedTaskEvaluator, _task, _world


async def _context():
    task = _task()
    observation = _world("model-context", False)
    evaluation = await SharedTaskEvaluator().evaluate(task, observation)
    space = ActionSpaceBuilder().build(task, observation)
    return ContextBuilder().build(task, observation, space, evaluation)


@dataclass
class ScriptedPort:
    outcome: object
    calls: int = 0
    request: object | None = None

    async def generate(self, request):
        self.calls += 1
        self.request = request
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _resolved(decision, metadata: ModelMetadata | None = None):
    return ResolvedModelDecision(decision, metadata or ModelMetadata())


def test_model_request_has_one_typed_context_authority() -> None:
    async def scenario() -> None:
        context = await _context()
        port = ScriptedPort(_resolved(Abort(context.context_id, "fixture stop", "policy")))
        await ModelBackedAgentPolicy(port).decide(context)

        assert port.request.agent_context is context
        assert port.request.context_id == context.context_id
        assert not hasattr(port.request, "serialized_context")
        assert not hasattr(port.request, "decision_schema")

    asyncio.run(scenario())


def test_private_binding_route_and_credentials_never_enter_model_request() -> None:
    async def scenario() -> None:
        task = _task()
        observation = _world("private-model-context", False)
        private_binding = replace(
            observation.bindings[0],
            payload={
                "selector": "#private",
                "href": "https://private.example/action",
                "credential": "top-secret",
                "backend": "private-executor",
            },
        )
        observation = replace(observation, bindings=(private_binding,))
        evaluation = await SharedTaskEvaluator().evaluate(task, observation)
        context = ContextBuilder().build(
            task,
            observation,
            ActionSpaceBuilder().build(task, observation),
            evaluation,
        )
        port = ScriptedPort(_resolved(Abort(context.context_id, "inspection complete", "policy")))

        await ModelBackedAgentPolicy(port).decide(context)

        request = repr((
            port.request.agent_context.task,
            port.request.agent_context.progress,
            port.request.agent_context.actions,
            port.request.agent_context.actor_world,
        ))
        for private in ("#private", "private.example", "top-secret", "private-executor"):
            assert private not in request

    asyncio.run(scenario())


def test_model_backed_policy_makes_one_structured_call_and_returns_typed_decision() -> None:
    async def scenario() -> None:
        context = await _context()
        option = context.actions.options[0]
        port = ScriptedPort(_resolved(
            SelectAction(context.context_id, option.action_id),
            ModelMetadata("fixture", "scripted", "response:1"),
        ))

        decision = await ModelBackedAgentPolicy(port).decide(context)

        assert isinstance(decision, SelectAction)
        assert decision.context_id == context.context_id
        assert port.calls == 1
        assert port.request.agent_context is context

    asyncio.run(scenario())


def test_canonical_context_port_receives_the_same_agent_context() -> None:
    @dataclass
    class CanonicalContextPort:
        request: object | None = None

        async def generate(self, request):
            self.request = request
            return ResolvedModelDecision(
                Abort(request.context_id, "fixture stop", "policy"),
                ModelMetadata(),
            )

    async def scenario() -> None:
        context = await _context()
        port = CanonicalContextPort()

        outcome = await ModelBackedAgentPolicy(port).decide(context)

        assert isinstance(outcome, Abort)
        assert port.request.agent_context is context

    asyncio.run(scenario())


def test_provider_outputs_and_failures_are_distinct_from_model_authored_abort() -> None:
    outcomes = (
        "not-json",
        ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False),
        ModelFailure(ModelFailureKind.REFUSED, "provider refused", False),
        TimeoutError("credential=must-not-leak"),
    )

    async def scenario() -> None:
        context = await _context()
        for outcome in outcomes:
            port = ScriptedPort(outcome)
            decision = await ModelBackedAgentPolicy(port).decide(context)

            assert isinstance(decision, PolicyFailure)
            assert port.calls == 1
            assert "credential" not in decision.reason

    asyncio.run(scenario())


def test_policy_failure_is_terminal_zero_call_and_not_recorded_as_agent_abort() -> None:
    async def scenario() -> None:
        environment = ScriptedEnvironment(initial_observation=_world("before", False))
        result = await TargetRuntime(
            AgentDecisionPorts(
                ModelBackedAgentPolicy(
                    ScriptedPort(ModelFailure(ModelFailureKind.TIMEOUT, "timed out", False))
                )
            ),
            SharedActionEvaluator(),
            SharedTaskEvaluator(),
        ).run_task(environment, _task())

        assert result.status is RunStatus.FAILED
        assert result.policy_failure is not None
        assert result.policy_failure.kind == ModelFailureKind.TIMEOUT
        assert result.recent_steps == ()
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_model_authored_abort_remains_a_typed_agent_decision() -> None:
    async def scenario() -> None:
        context = await _context()
        decision = await ModelBackedAgentPolicy(
            ScriptedPort(_resolved(Abort(context.context_id, "stop", "policy")))
        ).decide(context)

        assert isinstance(decision, Abort)

    asyncio.run(scenario())
