"""Environment composition for the existing one-attempt model transport."""

from __future__ import annotations

import os
from collections.abc import Mapping

from affordance_runtime.model_policy.grounding import DecisionGroundingVariant
from affordance_runtime.model_policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model_policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model_policy.provider_orchestrator import (
    ProviderCallOrchestrator,
    ProviderCallPolicy,
)
from affordance_runtime.model_port import FallbackModelPort, ModelConfig, model_port_from_environment


def model_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    grounding_variant: DecisionGroundingVariant | str | None = None,
    provider_recovery: bool = True,
) -> ModelBackedAgentPolicy:
    env = os.environ if environment is None else environment
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("model policy profile forbids provider fallback")
    port = model_port_from_environment(environment)
    if isinstance(port, FallbackModelPort):
        raise ValueError("model policy profile forbids provider fallback")
    configured_grounding = grounding_variant
    if configured_grounding is None:
        configured_grounding = env.get(
            "LLM_DECISION_GROUNDING",
            DecisionGroundingVariant.FORMAT_ONLY.value,
        )
    try:
        selected_grounding = DecisionGroundingVariant(configured_grounding)
    except ValueError as exc:
        raise ValueError("unsupported model decision grounding profile") from exc
    if (
        selected_grounding is DecisionGroundingVariant.COMPACT_CONTRACT_V2
        and not _enabled(env.get("LLM_ENABLE_EXPERIMENTAL_GROUNDING", "false"))
    ):
        raise ValueError("experimental compact-contract-v2 grounding is not admitted")
    orchestrator_deadline = max(0.001, call_timeout_s - min(1.0, call_timeout_s * 0.05))
    transport_timeout = min(30.0, max(0.001, orchestrator_deadline / 3))
    config = ModelConfig(
        timeout_s=transport_timeout,
        rate_limit_retries=0,
        transient_retries=0,
        prompt_version="p5-m1.1",
    )
    adapter = ModelPortDecisionAdapter(port, config, grounding_variant=selected_grounding)
    if not provider_recovery:
        return ModelBackedAgentPolicy(adapter, call_timeout_s=call_timeout_s)
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
