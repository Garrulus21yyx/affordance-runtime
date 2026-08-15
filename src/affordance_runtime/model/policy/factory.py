"""Environment composition for the existing one-attempt model transport."""

from __future__ import annotations

import os
from collections.abc import Mapping

from affordance_runtime.model.policy.grounded_tool_contracts import (
    GROUNDED_TOOLS_PROTOCOL,
)
from affordance_runtime.model.policy.grounded_tool_port_bridge import (
    CompactJsonDecisionPort,
)
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
)
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.port import StructuredDecisionModelPort
from affordance_runtime.model.providers.port import ModelConfig, model_port_from_environment


def model_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
) -> ModelBackedAgentPolicy:
    env = os.environ if environment is None else environment
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("model policy profile forbids provider fallback")
    model_adapter = env.get("LLM_MODEL_ADAPTER", "compact-json").strip().casefold()
    if model_adapter == "pydantic-ai":
        from affordance_runtime.model.policy.pydantic_ai_bridge import (
            zhipu_pydantic_ai_policy_from_environment,
        )

        return zhipu_pydantic_ai_policy_from_environment(
            env,
            call_timeout_s=call_timeout_s,
            perception_profile=perception_profile,
        )
    if model_adapter != "compact-json":
        raise ValueError(f"unsupported LLM_MODEL_ADAPTER: {model_adapter}")
    port = model_port_from_environment(environment)
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
    transport_timeout = min(30.0, max(0.001, call_timeout_s - 1.0))
    config = ModelConfig(
        timeout_s=transport_timeout,
        rate_limit_retries=0,
        transient_retries=0,
        provider_circuit_break_s=0.0,
        prompt_version="p5-m1.1",
    )
    configured_protocol = env.get("LLM_INTERACTION_PROTOCOL", GROUNDED_TOOLS_PROTOCOL)
    if configured_protocol != GROUNDED_TOOLS_PROTOCOL:
        raise ValueError("grounded_tools.v2 is the only product interaction protocol")
    adapter: StructuredDecisionModelPort
    adapter = CompactJsonDecisionPort(
        port,
        config,
        perception_profile=selected_perception,
    )
    return ModelBackedAgentPolicy(
        adapter,
        call_timeout_s=call_timeout_s,
    )


def _enabled(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}
