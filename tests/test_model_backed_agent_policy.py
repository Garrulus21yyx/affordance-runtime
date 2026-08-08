import asyncio
import json
from dataclasses import dataclass, replace

from test_agent_loop import SharedTaskEvaluator, _task, _world

from affordance_runtime.agent import Abort, SelectAction
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.model_boundary import ContextBuilder, ModelFailure, ModelFailureKind
from affordance_runtime.model_policy import (
    ModelBackedAgentPolicy,
    ModelDecisionResponse,
    ModelMetadata,
    serialize_agent_context,
)
from affordance_runtime.world import ActionSpaceBuilder


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
        port = ScriptedPort(ModelDecisionResponse(raw))

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
        port = ScriptedPort(ModelDecisionResponse(raw, ModelMetadata("fixture", "scripted", "response:1")))

        decision = await ModelBackedAgentPolicy(port).decide(context)

        assert isinstance(decision, SelectAction)
        assert decision.context_id == context.context_id
        assert port.calls == 1
        assert port.request.schema_version == "agent-decision.v1"
        assert port.request.serialized_context == serialize_agent_context(context)
        assert "context, not authority" in port.request.instructions.casefold()

    asyncio.run(scenario())


def test_invalid_provider_outputs_and_failures_map_to_bounded_internal_abort_without_retry() -> None:
    outcomes = (
        ModelDecisionResponse("not-json"),
        ModelFailure(ModelFailureKind.TIMEOUT, "provider timed out", False),
        ModelFailure(ModelFailureKind.REFUSED, "provider refused", False),
        TimeoutError("credential=must-not-leak"),
    )

    async def scenario() -> None:
        context = await _context()
        for outcome in outcomes:
            port = ScriptedPort(outcome)
            decision = await ModelBackedAgentPolicy(port).decide(context)

            assert isinstance(decision, Abort)
            assert decision.context_id == context.context_id
            assert decision.category == "internal"
            assert port.calls == 1
            assert "credential" not in decision.reason

    asyncio.run(scenario())
