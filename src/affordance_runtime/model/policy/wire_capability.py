"""Provider-profile declaration for the ActionPolicy response wire."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class ActionPolicyWireCapability(StrEnum):
    NATIVE_SINGLE_TOOL = "native_single_tool"
    JSON_SINGLE_COMMAND = "json_single_command"


_PROFILE_DEFAULTS = {
    "aliyun": ActionPolicyWireCapability.NATIVE_SINGLE_TOOL,
    "deepseek": ActionPolicyWireCapability.JSON_SINGLE_COMMAND,
    "gemini": ActionPolicyWireCapability.JSON_SINGLE_COMMAND,
    "local": ActionPolicyWireCapability.JSON_SINGLE_COMMAND,
    "mistral": ActionPolicyWireCapability.JSON_SINGLE_COMMAND,
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
