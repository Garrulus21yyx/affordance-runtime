"""Provider-independent model-visible tool contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from affordance_runtime.actions.schema_validation import validate_parameter_schema_contract
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.policy.strict_json import validate_json_tree

_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_CALL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}")
_TOOL_DESCRIPTION_MAX_CHARS = 1024


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        if _TOOL_NAME.fullmatch(self.name) is None:
            raise ValueError("tool name is outside the bounded transport vocabulary")
        if not self.description.strip() or len(self.description) > _TOOL_DESCRIPTION_MAX_CHARS:
            raise ValueError("tool description must be bounded public text")
        validate_json_tree(self.input_schema)
        validate_parameter_schema_contract(self.input_schema)
        object.__setattr__(self, "input_schema", freeze_json(self.input_schema))


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, object]
    call_id: str = ""

    def __post_init__(self) -> None:
        if _TOOL_NAME.fullmatch(self.name) is None:
            raise ValueError("tool call name is invalid")
        if self.call_id and _CALL_ID.fullmatch(self.call_id) is None:
            raise ValueError("tool call identity is invalid")
        validate_json_tree(self.arguments)
        object.__setattr__(self, "arguments", freeze_json(self.arguments))
