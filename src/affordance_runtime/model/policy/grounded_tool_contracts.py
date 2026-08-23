"""Provider-neutral contracts for referentially closed grounded tools v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from affordance_runtime.agent.context.compact_world_renderer import DeliveryManifest
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.model.policy.tool_contracts import ToolSpec

GROUNDED_TOOLS_PROTOCOL = "grounded_tools.v2"
GROUNDED_TOOL_CALL_ENVELOPE = "name-arguments.v1"
MAX_GROUNDED_TOOL_COUNT = 40


class GroundedToolPhase(StrEnum):
    ACTION_SELECTION = "action_selection"


class GroundedToolResolutionCode(StrEnum):
    ACCEPTED = "accepted"
    ZERO_CALLS = "zero_tool_calls"
    MULTIPLE_CALLS = "multiple_tool_calls"
    UNKNOWN_OPERATION = "unknown_operation"
    INVALID_ARGUMENTS = "invalid_tool_arguments"
    STALE_CATALOG = "stale_tool_catalog"
    GROUNDING_GAP = "tool_grounding_gap"
    DESTINATION_UNAVAILABLE = "destination_unavailable"
    UNSUPPORTED_DESTINATION_MODE = "unsupported_destination_mode"
    GROUNDING_FALLBACK_UNAVAILABLE = "grounding_fallback_unavailable"
    CATALOG_INVALID = "grounded_tool_catalog_invalid"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENT = "invalid_argument"


class GroundedToolBinding(Protocol):
    """One registered current tool's private call resolver or local handler."""

    def resolve(
        self,
        arguments: Mapping[str, object],
        context_id: str,
        tool_call_id: str,
    ) -> AgentDecision | GroundedActionResolution: ...


@dataclass(frozen=True)
class RegisteredGroundedTool:
    """One atomic public schema/private binding pair in the per-turn Registry."""

    spec: ToolSpec
    binding: GroundedToolBinding

    def __post_init__(self) -> None:
        if not callable(getattr(self.binding, "resolve", None)):
            raise TypeError("registered grounded tool requires one resolver")


@dataclass(frozen=True)
class GroundedToolCatalog:
    """Current public tools and their opaque Runtime bindings; never a context owner."""

    catalog_id: str
    context_id: str
    delivery_id: str
    manifest: DeliveryManifest
    delivery_index: WorldDeliveryIndex
    tools: tuple[RegisteredGroundedTool, ...]
    serialized_bytes: int

    def __post_init__(self) -> None:
        if (
            not self.catalog_id.startswith("grounded-catalog:")
            or not self.context_id.startswith("context:")
            or not self.delivery_id.startswith("delivery:")
        ):
            raise ValueError("grounded catalog identity is invalid")
        if not isinstance(self.manifest, DeliveryManifest):
            raise TypeError("grounded catalog requires the current DeliveryManifest")
        if not isinstance(self.delivery_index, WorldDeliveryIndex):
            raise TypeError("grounded catalog requires the sibling current delivery index")
        if (
            not 1 <= len(self.tools) <= MAX_GROUNDED_TOOL_COUNT
            or len({item.spec.name for item in self.tools}) != len(self.tools)
            or self.serialized_bytes <= 0
        ):
            raise ValueError("grounded catalog registrations are invalid")
        object.__setattr__(self, "tools", tuple(self.tools))

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(item.spec for item in self.tools)

    @property
    def bindings(self) -> tuple[GroundedToolBinding, ...]:
        return tuple(item.binding for item in self.tools)


@dataclass(frozen=True)
class GroundedActionResolution:
    """One current action/control decision resolved from a clean action tool."""

    decision: AgentDecision
    next_delivery_store: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AgentDecision):
            raise TypeError("grounded action resolution requires a typed decision")
        if self.next_delivery_store is not None and type(self.next_delivery_store).__name__ != "ObservationDeliveryStore":
            raise TypeError("grounded action resolution requires the delivery owner's next store")


class GroundedToolResolutionError(ValueError):
    def __init__(self, code: GroundedToolResolutionCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail.strip()
        message = code.value if not self.detail else f"{code.value}: {self.detail}"
        super().__init__(message)
