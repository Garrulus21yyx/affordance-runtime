"""Provider-neutral contracts for referentially closed grounded tools v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.model_policy.tool_contracts import ToolSpec

GROUNDED_TOOLS_PROTOCOL = "grounded_tools.v2"
GROUNDED_TOOL_CALL_ENVELOPE = "name-arguments.v1"
MAX_GROUNDED_TOOL_COUNT = 40
MAX_GROUNDED_WORKSPACE_BYTES = 64 * 1024


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
    TOOL_ARGUMENT_OWNER_MISMATCH = "tool_argument_owner_mismatch"
    AMBIGUOUS_TOOL_INTENT = "ambiguous_tool_intent"
    NON_EQUIVALENT_TOOL_INTENT = "non_equivalent_tool_intent"


@dataclass(frozen=True)
class GroundedToolCatalog:
    """Current public tools and their opaque Runtime bindings; never a context owner."""

    catalog_id: str
    context_id: str
    specs: tuple[ToolSpec, ...]
    bindings: tuple[object, ...]
    serialized_bytes: int

    def __post_init__(self) -> None:
        if not self.catalog_id.startswith("grounded-catalog:") or not self.context_id.startswith("context:"):
            raise ValueError("grounded catalog identity is invalid")
        if (
            not 1 <= len(self.specs) <= MAX_GROUNDED_TOOL_COUNT
            or len(self.specs) != len(self.bindings)
            or len({item.name for item in self.specs}) != len(self.specs)
            or not 0 < self.serialized_bytes <= MAX_GROUNDED_WORKSPACE_BYTES
        ):
            raise ValueError("grounded catalog must align specs and bindings")
        object.__setattr__(self, "specs", tuple(self.specs))
        object.__setattr__(self, "bindings", tuple(self.bindings))


@dataclass(frozen=True)
class GroundedActionResolution:
    """One current action/control decision resolved from a clean action tool."""

    decision: AgentDecision

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AgentDecision):
            raise TypeError("grounded action resolution requires a typed decision")


class GroundedToolResolutionError(ValueError):
    def __init__(self, code: GroundedToolResolutionCode) -> None:
        self.code = code
        super().__init__(code.value)
