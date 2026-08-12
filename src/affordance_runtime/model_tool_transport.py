"""Native tool-call transport contracts and exact model capability routing."""

from __future__ import annotations

from typing import Protocol, Sequence

from affordance_runtime.model_policy.tool_contracts import ToolCall, ToolSpec, ToolTransportKind
from affordance_runtime.model_port import ModelConfig, ModelMessage


def tool_transport_for_model(provider: str, model: str) -> ToolTransportKind:
    """Route exact reviewed model families; unknown profiles fail closed."""

    provider_name = provider.strip().casefold()
    model_name = model.strip().casefold()
    if provider_name == "mistral" and model_name == "mistral-medium-3-5":
        return ToolTransportKind.NATIVE_REQUIRED_ONE
    if provider_name == "zhipu" and model_name.startswith("glm-4.6v"):
        return ToolTransportKind.NATIVE_AUTO
    if provider_name == "zhipu" and model_name == "glm-4.1v-thinking-flashx":
        return ToolTransportKind.COMPACT_JSON
    raise ValueError("model profile has no admitted dynamic-tools transport")


class NativeToolModelPort(Protocol):
    async def generate_tool_calls(
        self,
        messages: Sequence[ModelMessage],
        tools: Sequence[ToolSpec],
        config: ModelConfig,
        *,
        require_one: bool,
    ) -> tuple[ToolCall, ...]: ...
