"""Environment composition for the existing one-attempt model transport."""

from __future__ import annotations

import os
from collections.abc import Mapping

from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOLS_PROTOCOL,
)
from affordance_runtime.model.policy.grounded_tool_port_bridge import (
    GroundedActionAdapter,
)
from affordance_runtime.model.policy.model_port_bridge import (
    DecisionPerceptionProfile,
)
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.port import StructuredDecisionModelPort
from affordance_runtime.model.policy.provider_orchestrator import (
    ProviderCallOrchestrator,
    ProviderCallPolicy,
)
from affordance_runtime.model.providers.port import FallbackModelPort, ModelConfig, model_port_from_environment


def model_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    provider_recovery: bool = True,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    env = os.environ if environment is None else environment
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("model policy profile forbids provider fallback")
    port = model_port_from_environment(environment)
    if isinstance(port, FallbackModelPort):
        raise ValueError("model policy profile forbids provider fallback")
    configured_perception = perception_profile
    if configured_perception is None:
        configured_perception = env.get(
            "LLM_DECISION_PERCEPTION",
            DecisionPerceptionProfile.TEXT_ONLY.value,
        )
    try:
        selected_perception = DecisionPerceptionProfile(configured_perception)
    except ValueError as exc:
        raise ValueError("unsupported model decision perception profile") from exc
    orchestrator_deadline = max(0.001, call_timeout_s - min(1.0, call_timeout_s * 0.05))
    transport_timeout = min(30.0, max(0.001, orchestrator_deadline / 3))
    config = ModelConfig(
        timeout_s=transport_timeout,
        rate_limit_retries=0,
        transient_retries=0,
        provider_circuit_break_s=0.0 if provider_recovery else 60.0,
        prompt_version="p5-m1.1",
    )
    configured_protocol = env.get("LLM_INTERACTION_PROTOCOL", GROUNDED_TOOLS_PROTOCOL)
    if configured_protocol != GROUNDED_TOOLS_PROTOCOL:
        raise ValueError("grounded_tools.v2 is the only product interaction protocol")
    adapter: StructuredDecisionModelPort
    adapter = GroundedActionAdapter(
        port,
        config,
        perception_profile=selected_perception,
    )
    if not provider_recovery:
        return ModelBackedAgentPolicy(
            adapter,
            call_timeout_s=call_timeout_s,
        )
    orchestrator = ProviderCallOrchestrator(
        (adapter,),
        ProviderCallPolicy(total_elapsed_deadline_s=orchestrator_deadline),
    )
    return ModelBackedAgentPolicy(
        orchestrator,
        call_timeout_s=call_timeout_s,
    )


def _enabled(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}
