"""Finite JSON-schema subset used at the semantic action boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_PRIVATE_PARAMETER_PARTS = frozenset(
    {"selector", "coordinate", "bbox", "point", "href", "method", "backend", "executor", "credential", "security"}
)


def validate_parameter_schema_names(schema: Mapping[str, Any], *, path: str = "parameters") -> None:
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        return
    for name, child in properties.items():
        normalized = str(name).casefold().replace("-", "_")
        if _PRIVATE_PARAMETER_PARTS.intersection(normalized.split("_")):
            raise ValueError(f"{path} contains a runtime-private parameter name: {name}")
        if isinstance(child, Mapping):
            validate_parameter_schema_names(child, path=f"{path}.{name}")


def validate_value(value: Any, schema: Mapping[str, Any], *, path: str = "parameters") -> None:
    expected = schema.get("type")
    if expected is not None and expected not in {"object", "string", "boolean", "integer", "number"}:
        raise ValueError(f"{path} uses unsupported schema type: {expected}")
    if expected == "object":
        if not isinstance(value, Mapping):
            raise ValueError(f"{path} must be an object")
        required = tuple(schema.get("required", ()))
        missing = [str(key) for key in required if key not in value]
        if missing:
            raise ValueError(f"missing required semantic parameters: {', '.join(missing)}")
        properties = schema.get("properties") or {}
        if not isinstance(properties, Mapping):
            raise ValueError(f"{path} properties schema is invalid")
        unknown = set(value) - set(properties)
        if unknown and schema.get("additionalProperties", False) is not True:
            raise ValueError(f"unknown semantic parameters: {', '.join(sorted(str(key) for key in unknown))}")
        for key, item in value.items():
            if key in properties:
                validate_value(item, properties[key], path=f"{path}.{key}")
        return
    if expected == "string" and not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    if expected == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(f"{path} must be an integer")
    if expected == "number" and (not isinstance(value, int | float) or isinstance(value, bool)):
        raise ValueError(f"{path} must be a number")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is not in the allowed enum")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} exceeds maximum")
