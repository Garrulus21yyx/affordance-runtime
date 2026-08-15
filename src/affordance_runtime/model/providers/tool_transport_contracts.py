"""Provider-neutral contracts for bounded model tool-call transport."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.policy.strict_json import validate_json_tree

NATIVE_TOOL_CALLS_TRANSPORT = "native_tool_calls.v1"
_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")


class ToolTransportKind(StrEnum):
    COMPACT_JSON = "compact_json"
    NATIVE_REQUIRED_ONE = "native_required_one"
    NATIVE_AUTO = "native_auto"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        if _TOOL_NAME.fullmatch(self.name) is None:
            raise ValueError("tool name is outside the bounded transport vocabulary")
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
