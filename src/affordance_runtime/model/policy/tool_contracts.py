"""Provider-independent model-visible tool contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    ephemeral_argument_paths: tuple[tuple[str, ...], ...] = field(
        default=(),
        repr=False,
        compare=False,
        metadata={"serialize": False},
    )

    def __post_init__(self) -> None:
        if _TOOL_NAME.fullmatch(self.name) is None:
            raise ValueError("tool name is outside the bounded transport vocabulary")
        if not self.description.strip() or len(self.description) > _TOOL_DESCRIPTION_MAX_CHARS:
            raise ValueError("tool description must be bounded public text")
        validate_json_tree(self.input_schema)
        validate_parameter_schema_contract(self.input_schema)
        paths = tuple(tuple(segment for segment in path) for path in self.ephemeral_argument_paths)
        if (
            len(paths) != len(set(paths))
            or any(not path for path in paths)
            or any(
                not segment or (segment != "*" and _TOOL_NAME.fullmatch(segment) is None)
                for path in paths
                for segment in path
            )
            or any(not _schema_contains_path(self.input_schema, path) for path in paths)
        ):
            raise ValueError("tool ephemeral argument paths must identify schema-owned fields")
        object.__setattr__(self, "input_schema", freeze_json(self.input_schema))
        object.__setattr__(self, "ephemeral_argument_paths", paths)


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


def _schema_contains_path(schema: Mapping[str, object], path: tuple[str, ...]) -> bool:
    """Return whether one typed path exists in any legal schema branch."""

    if not path:
        return True
    variants = tuple(
        item
        for keyword in ("oneOf", "anyOf", "allOf")
        for item in (schema.get(keyword, ()) if isinstance(schema.get(keyword), tuple | list) else ())
        if isinstance(item, Mapping)
    )
    if any(_schema_contains_path(item, path) for item in variants):
        return True
    head, *tail = path
    if head == "*":
        items = schema.get("items")
        return isinstance(items, Mapping) and _schema_contains_path(items, tuple(tail))
    properties = schema.get("properties")
    child = properties.get(head) if isinstance(properties, Mapping) else None
    return isinstance(child, Mapping) and _schema_contains_path(child, tuple(tail))
