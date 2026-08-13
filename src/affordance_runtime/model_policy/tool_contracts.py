"""Provider-neutral contracts for one ephemeral dynamic-tool proposal."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_policy.strict_json import validate_json_tree

DYNAMIC_TOOLS_PROTOCOL = "dynamic_tools.v1"
MAX_TOOL_CATALOG_SIZE = 40
MAX_TOOL_CATALOG_BYTES = 24 * 1024
_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_OPAQUE_ID = re.compile(r"[a-z][a-z0-9._:-]{0,127}")


class ToolTransportKind(StrEnum):
    COMPACT_JSON = "compact_json"
    NATIVE_REQUIRED_ONE = "native_required_one"
    NATIVE_AUTO = "native_auto"


class ToolResolutionCode(StrEnum):
    ACCEPTED = "accepted"
    ZERO_CALLS = "zero_tool_calls"
    MULTIPLE_CALLS = "multiple_tool_calls"
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_tool_arguments"
    STALE_CATALOG = "stale_tool_catalog"
    UNKNOWN_DESTINATION = "unknown_tool_destination"
    CATALOG_INVALID = "tool_catalog_invalid"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        if _TOOL_NAME.fullmatch(self.name) is None:
            raise ValueError("tool name is outside the bounded public vocabulary")
        if not self.description.strip() or len(self.description) > 500:
            raise ValueError("tool description must be bounded public text")
        validate_json_tree(self.input_schema)
        object.__setattr__(self, "input_schema", freeze_json(self.input_schema))


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        if _TOOL_NAME.fullmatch(self.name) is None:
            raise ValueError("tool call name is invalid")
        validate_json_tree(self.arguments)
        object.__setattr__(self, "arguments", freeze_json(self.arguments))


@dataclass(frozen=True)
class ToolCatalog:
    catalog_id: str
    context_id: str
    specs: tuple[ToolSpec, ...]
    bindings: tuple[object, ...]
    serialized_bytes: int

    def __post_init__(self) -> None:
        if _OPAQUE_ID.fullmatch(self.catalog_id) is None or not self.context_id.startswith("context:"):
            raise ValueError("tool catalog identity is invalid")
        specs = tuple(self.specs)
        bindings = tuple(self.bindings)
        if (
            not 1 <= len(specs) <= MAX_TOOL_CATALOG_SIZE
            or len(specs) != len(bindings)
            or len({item.name for item in specs}) != len(specs)
            or not 0 < self.serialized_bytes <= MAX_TOOL_CATALOG_BYTES
        ):
            raise ValueError("tool catalog bounds are invalid")
        object.__setattr__(self, "specs", specs)
        object.__setattr__(self, "bindings", bindings)


class ToolResolutionError(ValueError):
    def __init__(self, code: ToolResolutionCode) -> None:
        self.code = code
        super().__init__(code.value)
