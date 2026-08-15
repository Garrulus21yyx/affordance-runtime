import asyncio
import json
from dataclasses import dataclass

import pytest
from pydantic import ValidationError
from test_agent_loop import SharedTaskEvaluator, _task, _world

from affordance_runtime.agent import Abort, AgentLoop, AgentLoopStatus
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.state import AgentLoopState
from affordance_runtime.model_boundary import ContextBuilder, ModelFailure, ModelFailureKind
from affordance_runtime.model_policy import ModelBackedAgentPolicy, ModelMetadata, ResolvedModelDecision
from affordance_runtime.model_policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model_policy.parser import parse_agent_decision
from affordance_runtime.model_policy.spec import AgentDecisionPayload, decision_response_schema
from affordance_runtime.model_port import ModelConfig
from affordance_runtime.testing import StaticEnvironment
from affordance_runtime.world import ActionSpaceBuilder


async def _context():
    observation = _world("before", False)
    task = _task()
    return ContextBuilder().build(
        task,
        AgentLoopState(observation),
        ActionSpaceBuilder().build(task, observation),
        await SharedTaskEvaluator().evaluate(task, observation),
    )


def test_huge_json_integer_is_invalid_response_without_escaping() -> None:
    raw = (
        '{"type":"select_action","context_id":"context:1","action_id":"action:1",'
        '"parameters":{"huge":' + "9" * 5_000 + '},"destination_id":""}'
    )

    parsed = parse_agent_decision(raw, "context:1")

    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.INVALID_RESPONSE


def test_huge_json_integer_is_zero_execution_and_zero_surface_probe() -> None:
    class Port:
        async def generate(self, request):
            del request
            return ModelFailure(ModelFailureKind.INVALID_RESPONSE, "fixture invalid JSON number", False)

    async def scenario() -> None:
        environment = StaticEnvironment([_world("before", False)])
        result = await (
            AgentLoop(ModelBackedAgentPolicy(Port()), object(), SharedTaskEvaluator())
        ).run(environment, _task())
        assert result.status == AgentLoopStatus.FAILED
        assert result.execution_count == result.currentness_probe_count == 0
        assert environment.executed_requests == []

    asyncio.run(scenario())


@pytest.mark.parametrize("value", (True, False, "10", 10.0, None))
def test_wait_duration_rejects_non_json_integer_semantics(value) -> None:
    with pytest.raises(ValidationError):
        AgentDecisionPayload.model_validate(
            {"type": "wait", "context_id": "context:1", "reason": "settle", "max_wait_ms": value}
        )


def test_wait_duration_accepts_an_exact_json_integer() -> None:
    payload = AgentDecisionPayload.model_validate(
        {"type": "wait", "context_id": "context:1", "reason": "settle", "max_wait_ms": 10}
    )
    assert payload.root.max_wait_ms == 10


def test_model_facing_abort_excludes_internal_but_runtime_failure_retains_it() -> None:
    schema = json.dumps(decision_response_schema(), sort_keys=True)
    assert '"internal"' not in schema
    parsed = parse_agent_decision(
        '{"type":"abort","context_id":"context:1","reason":"failed","category":"internal"}',
        "context:1",
    )
    assert isinstance(parsed, ModelFailure)
    assert parsed.kind == ModelFailureKind.SCHEMA_ERROR

    failure = PolicyFailure(ModelFailureKind.INTERNAL_ERROR, "internal evaluation failure")
    assert failure.kind == ModelFailureKind.INTERNAL_ERROR


@dataclass
class TransportStub:
    provider: str = "fixture"
    model: str = "fixture-model"
    endpoint_class: str = "local"
    last_call: object | None = None

    async def generate_structured(self, messages, output_schema, config):
        del messages, output_schema, config
        raise AssertionError("not called")


def test_policy_rejects_transport_timeout_not_strictly_inside_deadline() -> None:
    adapter = ModelPortDecisionAdapter(
        TransportStub(),
        ModelConfig(timeout_s=10, rate_limit_retries=0, transient_retries=0),
    )
    assert adapter.transport_timeout_s == 10
    with pytest.raises(ValueError, match="transport timeout"):
        ModelBackedAgentPolicy(adapter, call_timeout_s=10)
    with pytest.raises(ValueError, match="transport timeout"):
        ModelBackedAgentPolicy(adapter, call_timeout_s=5)


def test_policy_clears_previous_metadata_before_a_failed_call() -> None:
    class Port:
        calls = 0

        async def generate(self, request):
            self.calls += 1
            if self.calls == 1:
                return ResolvedModelDecision(
                    Abort(request.context_id, "stop", "policy"),
                    ModelMetadata(provider_id="fixture", model_id="one"),
                )
            return ModelFailure(ModelFailureKind.TIMEOUT, "timed out", False)

    async def scenario() -> None:
        policy = ModelBackedAgentPolicy(Port())
        first = await policy.decide(await _context())
        assert isinstance(first, Abort)
        assert policy.last_metadata is not None
        second = await policy.decide(await _context())
        assert isinstance(second, PolicyFailure)
        assert policy.last_metadata is None

    asyncio.run(scenario())
