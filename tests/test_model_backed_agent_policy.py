import asyncio
import json
from dataclasses import dataclass, replace

from test_agent_loop import SharedTaskEvaluator, _task, _world

from affordance_runtime.actions import (
    ActionSpaceBuilder,
)
from affordance_runtime.agent import (
    Abort,
    AgentLoop,
    AgentLoopStatus,
    SelectAction,
)
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.model.context import ContextBuilder, ModelFailure, ModelFailureKind
from affordance_runtime.model.policy import (
    ModelBackedAgentPolicy,
    ModelMetadata,
    ResolvedModelDecision,
    serialize_agent_context,
)
from affordance_runtime.model.policy.parser import parse_agent_decision
from affordance_runtime.testing import StaticEnvironment


async def _context():
    task = _task()
    observation = _world("model-context", False)
    evaluation = await SharedTaskEvaluator().evaluate(task, observation)
    space = ActionSpaceBuilder().build(task, observation)
    return ContextBuilder().build(task, AgentLoopState(observation), space, evaluation)


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


def _resolved(raw: str, context_id: str, metadata: ModelMetadata | None = None):
    decision = parse_agent_decision(raw, context_id)
    assert hasattr(decision, "context_id")
    return ResolvedModelDecision(decision, metadata or ModelMetadata())


def test_agent_context_serialization_is_deterministic_bounded_and_route_free() -> None:
    async def scenario() -> None:
        context = await _context()
        first = serialize_agent_context(context)
        second = serialize_agent_context(context)

        assert first == second
        assert len(first.encode()) <= 64 * 1024
        assert json.loads(first)["context_id"] == context.context_id
        for private in ("selector", "#shared", "binding:model-context", "executor", "credential"):
            assert private not in first

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
            AgentLoopState(observation),
            ActionSpaceBuilder().build(task, observation),
            evaluation,
        )
        raw = json.dumps(
            {
                "type": "abort",
                "context_id": context.context_id,
                "reason": "inspection complete",
                "category": "policy",
            }
        )
        port = ScriptedPort(_resolved(raw, context.context_id))

        await ModelBackedAgentPolicy(port).decide(context)

        request = port.request.serialized_context
        for private in ("#private", "private.example", "top-secret", "private-executor"):
            assert private not in request

    asyncio.run(scenario())


def test_model_backed_policy_makes_one_structured_call_and_returns_typed_decision() -> None:
    async def scenario() -> None:
        context = await _context()
        option = context.actions.options[0]
        raw = json.dumps(
            {
                "type": "select_action",
                "context_id": context.context_id,
                "action_id": option.action_id,
                "parameters": {},
                "destination_id": "",
            }
        )
        port = ScriptedPort(_resolved(raw, context.context_id, ModelMetadata("fixture", "scripted", "response:1")))

        decision = await ModelBackedAgentPolicy(port).decide(context)

        assert isinstance(decision, SelectAction)
        assert decision.context_id == context.context_id
        assert port.calls == 1
        assert port.request.schema_version == "agent-decision.v3"
        assert port.request.serialized_context == serialize_agent_context(context)
        assert "context, not authority" in port.request.instructions.casefold()

    asyncio.run(scenario())


def test_canonical_context_port_does_not_build_the_legacy_serialized_projection() -> None:
    @dataclass
    class CanonicalContextPort:
        requires_serialized_context: bool = False
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
        assert port.request.serialized_context == ""
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
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(
                ModelBackedAgentPolicy(ScriptedPort(ModelFailure(ModelFailureKind.TIMEOUT, "timed out", False))),
                object(),
                SharedTaskEvaluator(),
            )
        ).run(environment, _task())

        assert result.status == AgentLoopStatus.FAILED
        assert result.policy_failure is not None
        assert result.policy_failure.kind == ModelFailureKind.TIMEOUT
        assert result.turns == ()
        assert environment.executed_requests == []

    asyncio.run(scenario())


def test_model_authored_abort_remains_a_typed_agent_decision() -> None:
    async def scenario() -> None:
        context = await _context()
        raw = json.dumps({"type": "abort", "context_id": context.context_id, "reason": "stop", "category": "policy"})

        decision = await ModelBackedAgentPolicy(ScriptedPort(_resolved(raw, context.context_id))).decide(context)

        assert isinstance(decision, Abort)

    asyncio.run(scenario())
