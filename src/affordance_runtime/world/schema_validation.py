"""Finite JSON-schema subset used at the semantic action boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from affordance_runtime.world.admission_issue import AdmissionIssue, invalid_parameters_issue

_PRIVATE_PARAMETER_PARTS = frozenset(
    {"selector", "coordinate", "bbox", "point", "href", "method", "backend", "executor", "credential", "security"}
)
_SCHEMA_TYPES = frozenset({"object", "string", "boolean", "integer", "number"})
_SCHEMA_KEYS = frozenset(
    {"type", "properties", "required", "additionalProperties", "enum", "minimum", "maximum", "description"}
)
_MAX_DESCRIPTION = 240
_MAX_ENUM_ITEMS = 12


def validate_parameter_schema_contract(schema: Mapping[str, Any]) -> None:
    """Validate the exact finite schema subset accepted at the action boundary."""

    _validate_schema_node(schema, path="parameters", root=True)


def validate_parameter_schema_names(schema: Mapping[str, Any], *, path: str = "parameters") -> None:
    """Compatibility alias for the now-complete schema contract validation."""

    _validate_schema_node(schema, path=path, root=path == "parameters")


def reject_private_parameter_values(value: Any, *, path: str = "parameters") -> None:
    if isinstance(value, Mapping):
        for name, child in value.items():
            if _private_name(str(name)):
                raise ValueError(f"{path} contains a runtime-private execution field: {name}")
            reject_private_parameter_values(child, path=f"{path}.{name}")
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, child in enumerate(value):
            reject_private_parameter_values(child, path=f"{path}[{index}]")


def _validate_schema_node(schema: Mapping[str, Any], *, path: str, root: bool) -> None:
    if not isinstance(schema, Mapping) or set(schema) - _SCHEMA_KEYS:
        raise ValueError(f"{path} uses an unsupported schema shape")
    schema_type = schema.get("type")
    if schema_type not in _SCHEMA_TYPES or (root and schema_type != "object"):
        raise ValueError(f"{path} uses unsupported schema type: {schema_type}")
    description = schema.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > _MAX_DESCRIPTION):
        raise ValueError(f"{path} description must be a bounded string")
    if schema_type == "object":
        _validate_object_schema(schema, path)
    else:
        _validate_primitive_schema(schema, path)


def _validate_object_schema(schema: Mapping[str, Any], path: str) -> None:
    properties = schema.get("properties", {})
    required = schema.get("required", ())
    additional = schema.get("additionalProperties", False)
    if not isinstance(properties, Mapping):
        raise ValueError(f"{path} properties must be an object")
    if not isinstance(required, Sequence) or isinstance(required, str | bytes):
        raise ValueError(f"{path} required must be a string array")
    if any(not isinstance(item, str) for item in required) or len(set(required)) != len(required):
        raise ValueError(f"{path} required must contain unique strings")
    if not set(required).issubset(properties):
        raise ValueError(f"{path} required must reference declared properties")
    if not isinstance(additional, bool):
        raise ValueError(f"{path} additionalProperties must be boolean")
    for name, child in properties.items():
        if not isinstance(name, str) or not name or _private_name(name):
            raise ValueError(f"{path} contains a runtime-private parameter name: {name}")
        _validate_schema_node(child, path=f"{path}.{name}", root=False)


def _validate_primitive_schema(schema: Mapping[str, Any], path: str) -> None:
    if any(key in schema for key in ("properties", "required", "additionalProperties")):
        raise ValueError(f"{path} primitive schema contains object fields")
    enum = schema.get("enum")
    if enum is not None:
        if (
            not isinstance(enum, Sequence)
            or isinstance(enum, str | bytes)
            or not 1 <= len(enum) <= _MAX_ENUM_ITEMS
            or any(not isinstance(item, str | bool | int | float) for item in enum)
        ):
            raise ValueError(f"{path} enum must be a bounded scalar array")
    for key in ("minimum", "maximum"):
        if key in schema and (not isinstance(schema[key], int | float) or isinstance(schema[key], bool)):
            raise ValueError(f"{path} {key} must be numeric")
    if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
        raise ValueError(f"{path} numeric bounds are inconsistent")


def _private_name(name: str) -> bool:
    normalized = name.casefold().replace("-", "_")
    return bool(_PRIVATE_PARAMETER_PARTS.intersection(normalized.split("_")))


def validate_value(value: Any, schema: Mapping[str, Any], *, path: str = "parameters") -> None:
    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants is not None:
        if not isinstance(variants, Sequence) or isinstance(variants, str | bytes):
            raise ValueError(f"{path} union schema is invalid")
        matches = 0
        for variant in variants:
            try:
                validate_value(value, variant, path=path)
            except ValueError:
                continue
            matches += 1
        required_matches = 1 if "oneOf" in schema else None
        if matches == 0 or (required_matches is not None and matches != required_matches):
            raise ValueError(f"{path} does not match the declared union")
        return
    expected = schema.get("type")
    if expected is not None and expected not in {"object", "array", "null", "string", "boolean", "integer", "number"}:
        raise ValueError(f"{path} uses unsupported schema type: {expected}")
    if expected == "null":
        if value is not None:
            raise ValueError(f"{path} must be null")
        return
    if expected == "array":
        if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
            raise ValueError(f"{path} must be an array")
        if len(value) < int(schema.get("minItems", 0)):
            raise ValueError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValueError(f"{path} has too many items")
        item_schema = schema.get("items", {})
        if not isinstance(item_schema, Mapping):
            raise ValueError(f"{path} item schema is invalid")
        for index, item in enumerate(value):
            validate_value(item, item_schema, path=f"{path}[{index}]")
        return
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
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path} does not match the required constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is not in the allowed enum")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"{path} is shorter than minimum length")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path} exceeds maximum length")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} exceeds maximum")


def validate_value_issue(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str = "parameters",
) -> AdmissionIssue | None:
    """Return the public rejection fact without exposing a value or private path."""

    violation = _value_violation(value, schema, path)
    if violation is None:
        return None
    field_path, expected, actual = violation
    return invalid_parameters_issue(
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _value_violation(
    value: Any,
    schema: Mapping[str, Any],
    path: str,
) -> tuple[str, Mapping[str, object], Mapping[str, object]] | None:
    if isinstance(value, Mapping):
        private = next((str(key) for key in value if _private_name(str(key))), None)
        if private is not None:
            return path, {"private_fields_allowed": False}, {"contains_private_field": True}
    variants = schema.get("oneOf") or schema.get("anyOf")
    if isinstance(variants, Sequence) and not isinstance(variants, str | bytes):
        if any(_value_violation(value, item, path) is None for item in variants):
            return None
        return path, {"union_match": True}, {"union_match": False}
    expected_type = schema.get("type")
    actual_type = _json_type(value)
    if expected_type != actual_type and not (expected_type == "number" and actual_type == "integer"):
        return path, {"type": expected_type}, {"type": actual_type}
    if expected_type == "object":
        assert isinstance(value, Mapping)
        properties = schema.get("properties") or {}
        required = tuple(schema.get("required", ()))
        missing = next((str(key) for key in required if key not in value), None)
        if missing is not None:
            child = properties.get(missing, {}) if isinstance(properties, Mapping) else {}
            return f"{path}.{missing}", dict(child), {"missing": True}
        if not isinstance(properties, Mapping):
            return path, {"type": "object"}, {"schema_invalid": True}
        unknown = next((str(key) for key in value if key not in properties), None)
        if unknown is not None and schema.get("additionalProperties", False) is not True:
            safe_path = f"{path}.{unknown}" if not _private_name(unknown) else path
            return safe_path, {"declared_property": True}, {"unknown_property": True}
        for key, item in value.items():
            if key in properties:
                issue = _value_violation(item, properties[key], f"{path}.{key}")
                if issue is not None:
                    return issue
        return None
    if expected_type == "array":
        if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
            return path, {"type": "array"}, {"type": actual_type}
        if len(value) < int(schema.get("minItems", 0)):
            return path, {"minItems": schema.get("minItems")}, {"too_few_items": True}
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            return path, {"maxItems": schema["maxItems"]}, {"too_many_items": True}
        item_schema = schema.get("items", {})
        for index, item in enumerate(value):
            issue = _value_violation(item, item_schema, f"{path}[{index}]")
            if issue is not None:
                return issue
        return None
    if "const" in schema and value != schema["const"]:
        return path, {"const": schema["const"]}, {"constant_match": False}
    if "enum" in schema and value not in schema["enum"]:
        return path, {"enum": tuple(schema["enum"])}, {"type": actual_type, "enum_member": False}
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return path, {"minimum": schema["minimum"]}, {"below_minimum": True}
        if "maximum" in schema and value > schema["maximum"]:
            return path, {"maximum": schema["maximum"]}, {"above_maximum": True}
    return None


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return "array"
    return type(value).__name__
