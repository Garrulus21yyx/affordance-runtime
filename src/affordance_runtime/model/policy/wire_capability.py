"""Provider-profile declaration for the ActionPolicy response wire."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class ActionPolicyWireCapability(StrEnum):
    NATIVE_SINGLE_TOOL = "native_single_tool"


_PROFILE_DEFAULTS = {
    "aliyun": ActionPolicyWireCapability.NATIVE_SINGLE_TOOL,
    "deepseek": ActionPolicyWireCapability.NATIVE_SINGLE_TOOL,
    "gemini": ActionPolicyWireCapability.NATIVE_SINGLE_TOOL,
    "local": ActionPolicyWireCapability.NATIVE_SINGLE_TOOL,
    "mistral": ActionPolicyWireCapability.NATIVE_SINGLE_TOOL,
    "zhipu": ActionPolicyWireCapability.NATIVE_SINGLE_TOOL,
}


def action_policy_wire_capability(
    environment: Mapping[str, str],
) -> ActionPolicyWireCapability:
    """Resolve one declared wire capability without inspecting a model ID."""

    explicit = environment.get("LLM_ACTION_POLICY_WIRE_CAPABILITY", "").strip().casefold()
    if explicit:
        try:
            return ActionPolicyWireCapability(explicit)
        except ValueError as exc:
            raise ValueError("unsupported LLM_ACTION_POLICY_WIRE_CAPABILITY") from exc
    profile = environment.get("LLM_ACTIVE_PROFILE", "local").strip().casefold()
    try:
        return _PROFILE_DEFAULTS[profile]
    except KeyError as exc:
        raise ValueError(f"unsupported LLM_ACTIVE_PROFILE: {profile}") from exc
