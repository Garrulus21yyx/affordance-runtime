"""Finite JSON-schema subset used at the semantic action boundary."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from affordance_runtime.actions.admission import AdmissionIssue, invalid_parameters_issue

_PRIVATE_PARAMETER_PARTS = frozenset(
    {"selector", "coordinate", "bbox", "point", "href", "method", "backend", "executor", "credential", "security"}
)
_ADMISSION_PRIVATE_PATH_PARTS = _PRIVATE_PARAMETER_PARTS | frozenset(
    {"password", "secret", "token", "authorization", "api", "key"}
)
_SCHEMA_TYPES = frozenset({"object", "array", "null", "string", "boolean", "integer", "number"})
_SCHEMA_KEYS = frozenset({
    "type", "properties", "required", "additionalProperties", "maxProperties", "propertyNames",
    "items", "minItems", "maxItems",
    "enum", "const", "minimum", "maximum", "minLength", "maxLength", "pattern", "description",
    "oneOf", "anyOf",
})
_MAX_DESCRIPTION = 240
MAX_OPTION_DOMAIN_ITEMS = 512
_MAX_SCHEMA_DEPTH = 8
_MAX_PROPERTIES = 128
_MAX_UNION_BRANCHES = 128
_MAX_PATTERN_LENGTH = 240


def validate_parameter_schema_contract(schema: Mapping[str, Any]) -> None:
    """Validate the exact finite schema subset accepted at the action boundary."""

    _validate_schema_node(schema, path="parameters", root=True, depth=0)


def validate_parameter_schema_names(schema: Mapping[str, Any], *, path: str = "parameters") -> None:
    """Compatibility alias for the now-complete schema contract validation."""

    _validate_schema_node(schema, path=path, root=path == "parameters", depth=0)


def reject_private_parameter_values(value: Any, *, path: str = "parameters") -> None:
    if isinstance(value, Mapping):
        for name, child in value.items():
            if _private_name(str(name)):
                raise ValueError(f"{path} contains a runtime-private execution field: {name}")
            reject_private_parameter_values(child, path=f"{path}.{name}")
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, child in enumerate(value):
            reject_private_parameter_values(child, path=f"{path}[{index}]")


def _validate_schema_node(schema: Mapping[str, Any], *, path: str, root: bool, depth: int) -> None:
    if depth > _MAX_SCHEMA_DEPTH:
        raise ValueError(f"{path} exceeds the schema nesting bound")
    if not isinstance(schema, Mapping) or set(schema) - _SCHEMA_KEYS:
        raise ValueError(f"{path} uses an unsupported schema shape")
    union_key = "oneOf" if "oneOf" in schema else "anyOf" if "anyOf" in schema else ""
    if "oneOf" in schema and "anyOf" in schema:
        raise ValueError(f"{path} cannot combine oneOf and anyOf")
    if union_key:
        _validate_union_schema(schema, path=path, root=root, depth=depth, union_key=union_key)
        return
    schema_type = schema.get("type")
    if schema_type not in _SCHEMA_TYPES or (root and schema_type != "object"):
        raise ValueError(f"{path} uses unsupported schema type: {schema_type}")
    description = schema.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > _MAX_DESCRIPTION):
        raise ValueError(f"{path} description must be a bounded string")
    if schema_type == "object":
        _validate_object_schema(schema, path, depth)
    elif schema_type == "array":
        _validate_array_schema(schema, path, depth)
    else:
        _validate_primitive_schema(schema, path)


def _validate_union_schema(
    schema: Mapping[str, Any], *, path: str, root: bool, depth: int, union_key: str
) -> None:
    allowed = {union_key, "description", "type"} if root else {union_key, "description"}
    if set(schema) - allowed:
        raise ValueError(f"{path} union cannot combine sibling validation keywords")
    if root and schema.get("type") != "object":
        raise ValueError(f"{path} root union must declare type object")
    variants = schema[union_key]
    if (
        not isinstance(variants, Sequence)
        or isinstance(variants, str | bytes)
        or not 1 <= len(variants) <= _MAX_UNION_BRANCHES
    ):
        raise ValueError(f"{path} union must contain bounded schema branches")
    for index, variant in enumerate(variants):
        _validate_schema_node(variant, path=f"{path}.{union_key}[{index}]", root=root, depth=depth + 1)
    if union_key == "oneOf" and len(variants) > 1:
        discriminants = tuple(_finite_discriminants(variant) for variant in variants)
        if any(not item for item in discriminants) or any(
            not _finite_branches_are_disjoint(left, right)
            for index, left in enumerate(discriminants)
            for right in discriminants[index + 1 :]
        ):
            raise ValueError(f"{path} oneOf branches require a unique finite discriminant")


def _finite_branches_are_disjoint(
    left: Mapping[str, frozenset[str]],
    right: Mapping[str, frozenset[str]],
) -> bool:
    """Two branches are exclusive when one shared finite field is disjoint."""

    return any(left[name].isdisjoint(right[name]) for name in set(left).intersection(right))


def _finite_discriminants(schema: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), Mapping):
        return {}
    required = set(schema.get("required", ()))
    result: dict[str, frozenset[str]] = {}
    for name, child in schema["properties"].items():
        if name not in required or not isinstance(child, Mapping):
            continue
        values = (child["const"],) if "const" in child else child.get("enum", ())
        if isinstance(values, Sequence) and not isinstance(values, str | bytes) and values:
            result[str(name)] = frozenset(_scalar_identity(value) for value in values)
    return result


def _validate_object_schema(schema: Mapping[str, Any], path: str, depth: int) -> None:
    properties = schema.get("properties", {})
    required = schema.get("required", ())
    additional = schema.get("additionalProperties", False)
    maximum = schema.get("maxProperties")
    property_names = schema.get("propertyNames")
    if not isinstance(properties, Mapping):
        raise ValueError(f"{path} properties must be an object")
    if len(properties) > _MAX_PROPERTIES:
        raise ValueError(f"{path} exceeds the property-count bound")
    if not isinstance(required, Sequence) or isinstance(required, str | bytes):
        raise ValueError(f"{path} required must be a string array")
    if any(not isinstance(item, str) for item in required) or len(set(required)) != len(required):
        raise ValueError(f"{path} required must contain unique strings")
    if not set(required).issubset(properties):
        raise ValueError(f"{path} required must reference declared properties")
    if maximum is not None and (type(maximum) is not int or not 0 <= maximum <= _MAX_PROPERTIES):
        raise ValueError(f"{path} maxProperties must close the bounded object domain")
    if maximum is not None and len(required) > maximum:
        raise ValueError(f"{path} maxProperties cannot exclude required properties")
    if additional is True:
        raise ValueError(f"{path} additionalProperties must have a bounded value schema")
    if not isinstance(additional, bool | Mapping):
        raise ValueError(f"{path} additionalProperties must be false or a bounded schema")
    if isinstance(additional, Mapping):
        if maximum is None or not isinstance(property_names, Mapping):
            raise ValueError(f"{path} dynamic properties require maxProperties and propertyNames")
        _validate_schema_node(additional, path=f"{path}.additionalProperties", root=False, depth=depth + 1)
        _validate_schema_node(property_names, path=f"{path}.propertyNames", root=False, depth=depth + 1)
        if property_names.get("type") != "string" or "maxLength" not in property_names:
            raise ValueError(f"{path} propertyNames must bound dynamic key length")
    elif property_names is not None:
        raise ValueError(f"{path} propertyNames requires dynamic additionalProperties")
    for name, child in properties.items():
        if not isinstance(name, str) or not name or _private_name(name):
            raise ValueError(f"{path} contains a runtime-private parameter name: {name}")
        _validate_schema_node(child, path=f"{path}.{name}", root=False, depth=depth + 1)


def _validate_array_schema(schema: Mapping[str, Any], path: str, depth: int) -> None:
    if any(
        key in schema
        for key in ("properties", "required", "additionalProperties", "maxProperties", "propertyNames")
    ):
        raise ValueError(f"{path} array schema contains object fields")
    items = schema.get("items")
    minimum = schema.get("minItems", 0)
    maximum = schema.get("maxItems")
    if not isinstance(items, Mapping):
        raise ValueError(f"{path} array requires an item schema")
    if type(minimum) is not int or minimum < 0:
        raise ValueError(f"{path} minItems must be a non-negative integer")
    if type(maximum) is not int or not minimum <= maximum <= MAX_OPTION_DOMAIN_ITEMS:
        raise ValueError(f"{path} maxItems must close the bounded array domain")
    _validate_schema_node(items, path=f"{path}.items", root=False, depth=depth + 1)


def _validate_primitive_schema(schema: Mapping[str, Any], path: str) -> None:
    if any(
        key in schema
        for key in (
            "properties",
            "required",
            "additionalProperties",
            "maxProperties",
            "propertyNames",
            "items",
            "minItems",
            "maxItems",
        )
    ):
        raise ValueError(f"{path} scalar schema contains container fields")
    enum = schema.get("enum")
    if enum is not None:
        if (
            not isinstance(enum, Sequence)
            or isinstance(enum, str | bytes)
            or not 1 <= len(enum) <= MAX_OPTION_DOMAIN_ITEMS
            or any(not _scalar_matches_type(item, str(schema["type"])) for item in enum)
            or len({_scalar_identity(item) for item in enum}) != len(enum)
        ):
            raise ValueError(f"{path} enum must be a bounded scalar array")
    if "const" in schema and not _scalar_matches_type(schema["const"], str(schema["type"])):
        raise ValueError(f"{path} const does not match the declared type")
    if enum is not None and "const" in schema and schema["const"] not in enum:
        raise ValueError(f"{path} const must belong to enum")
    for key in ("minimum", "maximum"):
        if key in schema and (
            not isinstance(schema[key], int | float)
            or isinstance(schema[key], bool)
            or not _finite_number(schema[key])
        ):
            raise ValueError(f"{path} {key} must be numeric")
    if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
        raise ValueError(f"{path} numeric bounds are inconsistent")
    if any(key in schema for key in ("minimum", "maximum")) and schema["type"] not in {"integer", "number"}:
        raise ValueError(f"{path} numeric bounds require a numeric type")
    for key in ("minLength", "maxLength"):
        if key in schema and (type(schema[key]) is not int or schema[key] < 0):
            raise ValueError(f"{path} {key} must be a non-negative integer")
    if "minLength" in schema and "maxLength" in schema and schema["minLength"] > schema["maxLength"]:
        raise ValueError(f"{path} string bounds are inconsistent")
    if any(key in schema for key in ("minLength", "maxLength", "pattern")) and schema["type"] != "string":
        raise ValueError(f"{path} string constraints require a string type")
    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str) or len(pattern) > _MAX_PATTERN_LENGTH:
            raise ValueError(f"{path} pattern must be bounded text")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{path} pattern is invalid") from exc


def _scalar_matches_type(value: Any, schema_type: str) -> bool:
    return {
        "null": value is None,
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and _finite_number(value)
        ),
    }.get(schema_type, False)


def _scalar_identity(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _finite_number(value: int | float) -> bool:
    return not isinstance(value, float) or math.isfinite(value)


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
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise ValueError(f"{path} has too many properties")
        required = tuple(schema.get("required", ()))
        missing = [str(key) for key in required if key not in value]
        if missing:
            raise ValueError(f"missing required semantic parameters: {', '.join(missing)}")
        properties = schema.get("properties") or {}
        if not isinstance(properties, Mapping):
            raise ValueError(f"{path} properties schema is invalid")
        unknown = set(value) - set(properties)
        additional = schema.get("additionalProperties", False)
        if unknown and additional is False:
            raise ValueError(f"unknown semantic parameters: {', '.join(sorted(str(key) for key in unknown))}")
        property_names = schema.get("propertyNames")
        if property_names is not None:
            for key in value:
                validate_value(key, property_names, path=f"{path}.property_name")
        for key, item in value.items():
            if key in properties:
                validate_value(item, properties[key], path=f"{path}.{key}")
            elif isinstance(additional, Mapping):
                validate_value(item, additional, path=f"{path}.{key}")
        return
    if expected == "string" and not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    if expected == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(f"{path} must be an integer")
    if expected == "number" and (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not _finite_number(value)
    ):
        raise ValueError(f"{path} must be a number")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path} does not match the required constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is not in the allowed enum")
    if isinstance(value, str):
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            raise ValueError(f"{path} does not match the required pattern")
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"{path} is shorter than minimum length")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path} exceeds maximum length")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if not _finite_number(value):
            raise ValueError(f"{path} must be finite")
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
        field_path=_public_issue_path(field_path),
        expected=expected,
        actual=actual,
    )


def invalid_value_paths(
    value: Any,
    schema: Mapping[str, Any],
) -> tuple[tuple[str, ...], ...]:
    """Locate provided values that have no meaning in one valid schema.

    The result is an at-rest history contract, not a repair instruction.  It
    preserves every schema-owned semantic sibling and marks only unsupported
    provided values.  Containers whose legal subset is ambiguous (arrays,
    unions, or overfull objects) expire as a whole.  A missing required field
    has no provided value to remove, so valid present siblings remain useful
    evidence for why the rejected attempt was made.
    """

    validate_parameter_schema_contract(schema)
    if _value_violation(value, schema, "parameters") is None:
        return ()
    return _minimal_paths(_invalid_value_paths(value, schema, ()))


def _invalid_value_paths(
    value: Any,
    schema: Mapping[str, Any],
    path: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    variants = schema.get("oneOf") or schema.get("anyOf")
    if variants is not None:
        return (path,)

    expected_type = schema.get("type")
    actual_type = _json_type(value)
    if expected_type != actual_type and not (expected_type == "number" and actual_type == "integer"):
        return (path,)

    if expected_type == "array":
        # History paths intentionally have no positional array edits.  Keeping
        # a selectively shortened array could invent a different semantic call.
        return (path,)

    if expected_type == "object":
        assert isinstance(value, Mapping)
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            return (path,)
        properties = schema.get("properties") or {}
        if not isinstance(properties, Mapping):  # validated schemas cannot reach this
            return (path,)
        additional = schema.get("additionalProperties", False)
        property_names = schema.get("propertyNames")
        paths: list[tuple[str, ...]] = []
        for raw_key, item in value.items():
            key = str(raw_key)
            if not key:
                return (path,)
            child_path = (*path, key)
            if _private_name(key):
                paths.append(child_path)
                continue
            if isinstance(property_names, Mapping) and _value_violation(
                key,
                property_names,
                "parameters.property_name",
            ) is not None:
                paths.append(child_path)
                continue
            child_schema = properties.get(raw_key)
            if isinstance(child_schema, Mapping):
                if _value_violation(item, child_schema, "parameters") is not None:
                    paths.extend(_invalid_value_paths(item, child_schema, child_path))
                continue
            if additional is False:
                paths.append(child_path)
                continue
            if isinstance(additional, Mapping) and _value_violation(
                item,
                additional,
                "parameters",
            ) is not None:
                paths.extend(_invalid_value_paths(item, additional, child_path))
        return tuple(paths)

    return (path,)


def _minimal_paths(paths: Sequence[tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    unique = set(paths)
    return tuple(
        sorted(
            path
            for path in unique
            if not any(
                parent != path and path[: len(parent)] == parent
                for parent in unique
            )
        )
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
        matches = sum(_value_violation(value, item, path) is None for item in variants)
        if matches and ("oneOf" not in schema or matches == 1):
            return None
        return path, {"union_match": True}, {"union_match": False}
    expected_type = schema.get("type")
    actual_type = _json_type(value)
    if expected_type != actual_type and not (expected_type == "number" and actual_type == "integer"):
        return path, {"type": expected_type}, {"type": actual_type}
    if expected_type == "object":
        assert isinstance(value, Mapping)
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            return path, {"maxProperties": schema["maxProperties"]}, {"too_many_properties": True}
        properties = schema.get("properties") or {}
        required = tuple(schema.get("required", ()))
        missing = next((str(key) for key in required if key not in value), None)
        if missing is not None:
            child = properties.get(missing, {}) if isinstance(properties, Mapping) else {}
            return f"{path}.{missing}", dict(child), {"missing": True}
        if not isinstance(properties, Mapping):
            return path, {"type": "object"}, {"schema_invalid": True}
        additional = schema.get("additionalProperties", False)
        unknown = next((str(key) for key in value if key not in properties), None)
        if unknown is not None and additional is False:
            safe_path = f"{path}.{unknown}" if not _private_name(unknown) else path
            return safe_path, {"declared_property": True}, {"unknown_property": True}
        property_names = schema.get("propertyNames")
        if isinstance(property_names, Mapping):
            for key in value:
                issue = _value_violation(key, property_names, f"{path}.property_name")
                if issue is not None:
                    return issue
        for key, item in value.items():
            if key in properties:
                issue = _value_violation(item, properties[key], f"{path}.{key}")
                if issue is not None:
                    return issue
            elif isinstance(additional, Mapping):
                issue = _value_violation(item, additional, f"{path}.{key}")
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
    if isinstance(value, str):
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            return path, {"pattern_match": True}, {"pattern_match": False}
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            return path, {"minLength": schema["minLength"]}, {"too_short": True}
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            return path, {"maxLength": schema["maxLength"]}, {"too_long": True}
    if isinstance(value, int | float) and not isinstance(value, bool):
        if not _finite_number(value):
            return path, {"finite": True}, {"finite": False}
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


def _public_issue_path(path: str) -> str:
    # Array positions are validation-local detail, not stable public fields.
    # Project them to the schema field so every supported bounded array can
    # still produce a public typed rejection.
    path = re.sub(r"\[[0-9]+\]", "", path)
    parts = {
        part.casefold()
        for item in path.split(".")
        for part in item.replace("-", "_").split("_")
    }
    if parts & _ADMISSION_PRIVATE_PATH_PARTS:
        return "parameters"
    return path
