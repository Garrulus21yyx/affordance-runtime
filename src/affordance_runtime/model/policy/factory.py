"""Environment composition for the bounded model transport."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.goals.compiler import GoalCompiler, UnavailableGoalCompiler
from affordance_runtime.model.goal_compiler import (
    model_goal_compiler_from_environment,
)
from affordance_runtime.model.policy.perception import (
    DecisionPerceptionProfile,
)
from affordance_runtime.model.policy.policy import ModelBackedAgentPolicy
from affordance_runtime.model.policy.wire_capability import action_policy_wire_capability
from affordance_runtime.model.providers.port import ModelPort


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
    action_policy_wire_capability(env)
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
