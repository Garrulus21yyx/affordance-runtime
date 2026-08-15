import asyncio
import os

import pytest
from test_agent_loop import SharedActionEvaluator, SharedTaskEvaluator, _sent, _task, _world

from affordance_runtime.agent import AgentLoop, AgentLoopStatus
from affordance_runtime.model.policy import model_policy_from_environment
from affordance_runtime.testing import StaticEnvironment


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_MODEL_POLICY_SMOKE") != "1",
    reason="live_provider_attestation: unavailable",
)
def test_opt_in_live_model_policy_smoke_uses_one_safe_internal_action() -> None:
    policy = model_policy_from_environment()
    environment = StaticEnvironment([_world("before", False), _world("after", True)], [_sent()])

    result = asyncio.run(
        (AgentLoop(policy, SharedActionEvaluator(), SharedTaskEvaluator())).run(
            environment, _task()
        )
    )

    assert result.status == AgentLoopStatus.DONE
    assert result.execution_count == 1
    assert policy.last_metadata is not None
    assert policy.last_metadata.rate_limit_retry_count == 0
    assert policy.last_metadata.transient_retry_count == 0
