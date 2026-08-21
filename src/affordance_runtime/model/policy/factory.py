"""Environment composition for the bounded model transport."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.goals.compiler import GoalCompiler, UnavailableGoalCompiler
from affordance_runtime.model.goal_compiler import (
    model_goal_compiler_from_environment,
)
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
from affordance_runtime.model.policy.reasoning_policy import ActionPolicyReasoningPolicy
from affordance_runtime.model.policy.wire_capability import (
    ActionPolicyWireCapability,
    action_policy_wire_capability,
)
from affordance_runtime.model.providers.port import ModelConfig, ModelPort, model_port_from_environment


@dataclass(frozen=True)
class ConfiguredModelRoles:
    """The two cognitive roles sharing one configured provider transport."""

    action_policy: ModelBackedAgentPolicy
    goal_compiler: GoalCompiler


def model_policy_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
    model_port: ModelPort | None = None,
    provider_retry_budget: int = 1,
) -> ModelBackedAgentPolicy:
    if provider_retry_budget not in {0, 1}:
        raise ValueError("ActionPolicy provider retry budget must be zero or one")
    env = os.environ if environment is None else environment
    if _enabled(env.get("LLM_PROFILE_FALLBACK_TO_LOCAL", "false")):
        raise ValueError("model policy profile forbids provider fallback")
    wire_capability = action_policy_wire_capability(env)
    if wire_capability is ActionPolicyWireCapability.NATIVE_SINGLE_TOOL:
        if provider_retry_budget != 1:
            raise ValueError("native single-tool policy owns its one-retry transport")
        if model_port is not None:
            raise ValueError("native single-tool policy owns its provider transport")
        from affordance_runtime.model.policy.pydantic_ai_bridge import (
            openai_compatible_pydantic_ai_policy_from_environment,
        )

        return openai_compatible_pydantic_ai_policy_from_environment(
            env,
            call_timeout_s=call_timeout_s,
            perception_profile=perception_profile,
        )
    if wire_capability is not ActionPolicyWireCapability.JSON_SINGLE_COMMAND:
        raise ValueError("unsupported ActionPolicy wire capability")
    port = model_port or model_port_from_environment(environment)
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
    semantic_call_deadline = max(0.001, call_timeout_s - 1.0)
    timeout_fast_retry_timeout = (
        (
            33.0
            if semantic_call_deadline >= 34.0
            else max(0.001, semantic_call_deadline * 0.37)
        )
        if provider_retry_budget
        else None
    )
    transport_timeout = (
        min(
            55.0,
            max(
                0.001,
                semantic_call_deadline - (timeout_fast_retry_timeout or 0.0) - 1.0,
            ),
        )
        if provider_retry_budget
        else semantic_call_deadline
    )
    action_output_ceiling = _bounded_int(
        env,
        "LLM_ACTION_POLICY_MAX_TOKENS",
        default=4_096,
        minimum=512,
        maximum=16_384,
    )
    ordinary_max_tokens = min(
        action_output_ceiling,
        _bounded_int(
            env,
            "LLM_ACTION_POLICY_ORDINARY_MAX_TOKENS",
            default=1024,
            minimum=512,
            maximum=1024,
        ),
    )
    deliberate_max_tokens = min(
        action_output_ceiling,
        _bounded_int(
            env,
            "LLM_ACTION_POLICY_DELIBERATE_MAX_TOKENS",
            default=2048,
            minimum=1024,
            maximum=2048,
        ),
    )
    representation_repair_max_tokens = _bounded_int(
        env,
        "LLM_ACTION_POLICY_REPRESENTATION_REPAIR_MAX_TOKENS",
        default=512,
        minimum=256,
        maximum=512,
    )
    timeout_retry_max_tokens = _bounded_int(
        env,
        "LLM_ACTION_POLICY_TIMEOUT_RETRY_MAX_TOKENS",
        default=512,
        minimum=256,
        maximum=1024,
    )
    config = ModelConfig(
        max_tokens=ordinary_max_tokens,
        timeout_s=transport_timeout,
        provider_total_timeout_s=transport_timeout,
        rate_limit_retries=provider_retry_budget,
        transient_retries=provider_retry_budget,
        timeout_retries=0,
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
        timeout_fast_retry_timeout_s=timeout_fast_retry_timeout,
        timeout_fast_retry_max_tokens=timeout_retry_max_tokens,
        timeout_fast_retry_thinking_mode="disabled",
        semantic_call_deadline_s=semantic_call_deadline,
        reasoning_policy=ActionPolicyReasoningPolicy(
            ordinary_max_tokens,
            deliberate_max_tokens,
            representation_repair_max_tokens,
        ),
    )
    return ModelBackedAgentPolicy(
        adapter,
        call_timeout_s=call_timeout_s,
    )


def model_roles_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
    perception_profile: DecisionPerceptionProfile | str | None = None,
    provider_retry_budget: int = 1,
) -> ConfiguredModelRoles:
    """Compose ActionPolicy and GoalCompiler from one selected model profile."""

    env = os.environ if environment is None else environment
    goal_compiler_mode = env.get("LLM_GOAL_COMPILER_MODE", "model").strip().casefold()
    if goal_compiler_mode not in {"model", "disabled"}:
        raise ValueError("LLM_GOAL_COMPILER_MODE must be model or disabled")
    wire_capability = action_policy_wire_capability(env)
    if wire_capability is ActionPolicyWireCapability.JSON_SINGLE_COMMAND:
        shared_port = model_port_from_environment(env)
        policy = model_policy_from_environment(
            env,
            call_timeout_s=call_timeout_s,
            perception_profile=perception_profile,
            model_port=shared_port,
            provider_retry_budget=provider_retry_budget,
        )
        compiler_model = env.get("LLM_GOAL_COMPILER_MODEL", "").strip()
        if goal_compiler_mode == "disabled":
            compiler = UnavailableGoalCompiler()
        elif compiler_model:
            compiler = model_goal_compiler_from_environment(
                _goal_compiler_environment(env),
                call_timeout_s=call_timeout_s,
            )
        else:
            compiler = model_goal_compiler_from_environment(
                env,
                port=shared_port,
                call_timeout_s=call_timeout_s,
            )
    else:
        policy = model_policy_from_environment(
            env,
            call_timeout_s=call_timeout_s,
            perception_profile=perception_profile,
            provider_retry_budget=provider_retry_budget,
        )
        compiler = (
            UnavailableGoalCompiler()
            if goal_compiler_mode == "disabled"
            else model_goal_compiler_from_environment(
                _goal_compiler_environment(env),
                call_timeout_s=call_timeout_s,
            )
        )
    return ConfiguredModelRoles(policy, compiler)


def _goal_compiler_environment(environment: Mapping[str, str]) -> Mapping[str, str]:
    compiler_model = environment.get("LLM_GOAL_COMPILER_MODEL", "").strip()
    if not compiler_model:
        return environment
    model_key = {
        "zhipu": "LLM_ZHIPU_MODEL",
        "aliyun": "LLM_ALIYUN_MODEL",
        "deepseek": "LLM_DEEPSEEK_MODEL",
        "mistral": "LLM_MISTRAL_MODEL",
        "gemini": "LLM_GEMINI_MODEL",
        "local": "LLM_LOCAL_MODEL",
    }.get(environment.get("LLM_ACTIVE_PROFILE", "local").strip().casefold())
    if model_key is None:
        raise ValueError("goal compiler model override requires a supported profile")
    compiler_environment = dict(environment)
    compiler_environment[model_key] = compiler_model
    return compiler_environment


def _enabled(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _bounded_int(
    environment: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environment.get(name, "").strip()
    try:
        value = default if not raw else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be within [{minimum}, {maximum}]")
    return value
