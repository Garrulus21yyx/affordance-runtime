"""Environment composition for the existing one-attempt model transport."""

from __future__ import annotations

import os
from collections.abc import Mapping

from affordance_runtime.model_policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model_policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model_port import FallbackModelPort, ModelConfig, model_port_from_environment


def model_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
) -> ModelBackedAgentPolicy:
    env = os.environ if environment is None else environment
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("model policy profile forbids provider fallback")
    port = model_port_from_environment(environment)
    if isinstance(port, FallbackModelPort):
        raise ValueError("model policy profile forbids provider fallback")
    transport_timeout = max(0.001, call_timeout_s - min(1.0, call_timeout_s * 0.05))
    config = ModelConfig(
        timeout_s=transport_timeout,
        rate_limit_retries=0,
        transient_retries=0,
        prompt_version="p5-m1.1",
    )
    return ModelBackedAgentPolicy(ModelPortDecisionAdapter(port, config), call_timeout_s=call_timeout_s)


def _enabled(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}
