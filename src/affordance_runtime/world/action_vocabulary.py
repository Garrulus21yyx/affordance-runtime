"""Small canonical semantic-action vocabulary shared by surface adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affordance_runtime.immutable import freeze_json

_CANONICAL_BY_PRIMITIVE = {
    ("dom", "click"): "activate",
    ("dom", "type"): "type_text",
    ("dom", "fill"): "type_text",
    ("dom", "select"): "select_option",
    ("visual", "point_activate"): "activate",
    ("visual", "type"): "type_text",
    ("visual", "drag"): "drag",
    ("wot", "invoke"): "activate",
    ("wot", "write_property"): "set_value",
    ("wot", "read_property"): "read",
}


@dataclass(frozen=True)
class SemanticActionMetadata:
    semantic_action: str
    primitive_action: str
    parameter_schema: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))


def action_metadata(surface: str, primitive_action: str, source_schema: dict[str, Any] | None = None) -> SemanticActionMetadata:
    semantic_action = _CANONICAL_BY_PRIMITIVE.get((surface, primitive_action))
    if semantic_action is None:
        raise ValueError(f"unsupported surface primitive: {surface}.{primitive_action}")
    return SemanticActionMetadata(
        semantic_action,
        primitive_action,
        _parameter_schema(semantic_action, source_schema or {}),
    )


def _parameter_schema(action: str, source_schema: dict[str, Any]) -> dict[str, Any]:
    if action == "type_text":
        return {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    if action == "select_option":
        return {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}
    if action == "set_value":
        return {"type": "object", "properties": {"value": source_schema}, "required": ["value"]}
    return {"type": "object", "properties": {}, "additionalProperties": False}
