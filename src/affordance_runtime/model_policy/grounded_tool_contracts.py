"""Provider-neutral contracts for referentially closed grounded tools v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_policy.tool_contracts import ToolSpec

GROUNDED_TOOLS_PROTOCOL = "grounded_tools.v2"
MAX_GROUNDED_TOOL_COUNT = 40
MAX_GROUNDED_WORKSPACE_BYTES = 64 * 1024


class GroundedToolResolutionCode(StrEnum):
    ACCEPTED = "accepted"
    ZERO_CALLS = "zero_tool_calls"
    MULTIPLE_CALLS = "multiple_tool_calls"
    UNKNOWN_OPERATION = "unknown_operation"
    INVALID_ARGUMENTS = "invalid_tool_arguments"
    STALE_CATALOG = "stale_tool_catalog"
    GROUNDING_GAP = "tool_grounding_gap"
    CATALOG_INVALID = "grounded_tool_catalog_invalid"


@dataclass(frozen=True)
class ToolPolicyView:
    task_brief: Mapping[str, object]
    grounding_index: tuple[Mapping[str, object], ...]
    current_state: Mapping[str, object]
    previous_tool_result: Mapping[str, object]
    tools: tuple[ToolSpec, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_brief", freeze_json(self.task_brief))
        object.__setattr__(
            self,
            "grounding_index",
            tuple(freeze_json(item) for item in self.grounding_index),
        )
        object.__setattr__(self, "current_state", freeze_json(self.current_state))
        object.__setattr__(self, "previous_tool_result", freeze_json(self.previous_tool_result))
        object.__setattr__(self, "tools", tuple(self.tools))


@dataclass(frozen=True)
class GroundedToolCatalog:
    catalog_id: str
    context_id: str
    specs: tuple[ToolSpec, ...]
    bindings: tuple[object, ...]
    view: ToolPolicyView
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


class GroundedToolResolutionError(ValueError):
    def __init__(self, code: GroundedToolResolutionCode) -> None:
        self.code = code
        super().__init__(code.value)
