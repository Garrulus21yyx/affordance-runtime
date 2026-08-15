from __future__ import annotations

import asyncio
from dataclasses import replace

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.model.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.tool_port_bridge import DynamicToolDecisionAdapter
from affordance_runtime.model.providers.port import ModelConfig
from affordance_runtime.world import WorldFusion
from tests.integration.agent.test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world
from tests.support.agent.static_environment import StaticEnvironment
from tests.unit.runtime.test_dynamic_tool_bridge import _CompactPort


def _value_world(observation_id, enabled):
    world = _world(observation_id, enabled)
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    binding = replace(
        world.bindings[0],
        semantic_action="select_option",
        primitive_action="select",
        parameter_schema=schema,
        verification_contract_digest="",
    )
    source = replace(world.sources[0], bindings=(binding,))
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def test_dynamic_tool_facade_dispatches_only_through_existing_agent_loop() -> None:
    environment = StaticEnvironment(
        [_world("before", False), _world("after", True)],
        results=[_sent()],
    )
    adapter = DynamicToolDecisionAdapter(
        _CompactPort(),
        ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
    )
    policy = ModelBackedAgentPolicy(adapter, call_timeout_s=3)

    result = asyncio.run(
        (
            AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())
    )

    assert result.status is AgentLoopStatus.DONE
    assert result.execution_count == 1
    assert len(environment.executed_requests) == 1
    transition = result.control_transitions[0]
    assert transition.admission is not None
    assert transition.admission.status.value == "admitted"
    assert transition.execution is not None
    assert transition.execution.dispatch_status.value == "sent"


def test_argument_repair_is_one_policy_turn_and_one_runtime_transition() -> None:
    class RepairPort(_CompactPort):
        async def generate_structured(self, messages, output_schema, config):
            self.payload = {
                "tool": "act_01",
                "args": {} if self.calls == 0 else {"value": "confirmed"},
            }
            return await super().generate_structured(messages, output_schema, config)

    environment = StaticEnvironment(
        [_value_world("before", False), _value_world("after", True)],
        results=[_sent()],
    )
    port = RepairPort()
    adapter = DynamicToolDecisionAdapter(
        port,
        ModelConfig(timeout_s=2, rate_limit_retries=0, transient_retries=0),
    )

    result = asyncio.run(
        (
            AgentLoop(ModelBackedAgentPolicy(adapter, call_timeout_s=3), SharedActionEvaluator(), SharedTaskEvaluator())
        ).run(environment, _task())
    )

    assert result.status is AgentLoopStatus.DONE
    assert port.calls == 2
    assert adapter.last_argument_repair_count == 1
    assert len(result.turns) == 1
    assert result.execution_count == 1
    assert len(result.control_transitions) == 1
    assert len(environment.executed_requests) == 1
    assert environment.executed_requests[0].intent.parameters == {"value": "confirmed"}
