from __future__ import annotations

import asyncio

from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world
from test_dynamic_tool_bridge import _CompactPort

from affordance_runtime.agent import AgentEpisodeRunner, AgentLoop, AgentLoopStatus
from affordance_runtime.model_policy import ModelBackedAgentPolicy
from affordance_runtime.model_policy.tool_port_bridge import DynamicToolDecisionAdapter
from affordance_runtime.model_port import ModelConfig
from affordance_runtime.testing import StaticEnvironment


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
        AgentEpisodeRunner(
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
