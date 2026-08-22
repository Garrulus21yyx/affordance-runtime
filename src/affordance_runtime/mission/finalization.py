"""Mechanical admission of an evidence-backed final response."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.schema_validation import validate_value
from affordance_runtime.agent.decisions import FinalResponse
from affordance_runtime.agent.working_facts import is_public_scalar
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.mission.contracts import EvidenceBundle


class FinalResponseRejection(StrEnum):
    FINAL_RESPONSE_INVALID = "final_response_invalid"
    EVIDENCE_LINEAGE_INVALID = "evidence_lineage_invalid"
    ALREADY_FINALIZED = "already_finalized"


@dataclass(frozen=True)
class FinalResponseBoundaryResult:
    admitted: bool
    response: FinalResponse | None = None
    rejection_code: FinalResponseRejection | None = None
    schema_digest: str = ""
    response_digest: str = ""


@dataclass(frozen=True)
class FinalResponseBoundary:
    """Validate public shape, evidence lineage, and the one-send latch without an LLM."""

    def admit(
        self,
        response: FinalResponse,
        schema: Mapping[str, object],
        bundle: EvidenceBundle,
        *,
        already_finalized: bool,
    ) -> FinalResponseBoundaryResult:
        schema_digest = _digest(schema)
        response_digest = _digest(response.content)
        if already_finalized:
            return _rejected(FinalResponseRejection.ALREADY_FINALIZED, schema_digest, response_digest)
        if not schema:
            return _rejected(FinalResponseRejection.FINAL_RESPONSE_INVALID, schema_digest, response_digest)
        if any(not _current_public_record(bundle, ref) for ref in response.evidence_refs):
            return _rejected(FinalResponseRejection.EVIDENCE_LINEAGE_INVALID, schema_digest, response_digest)
        try:
            _validate_final_response_schema(schema)
        except (TypeError, ValueError, re.error):
            return _rejected(FinalResponseRejection.FINAL_RESPONSE_INVALID, schema_digest, response_digest)
        try:
            value = json.loads(response.content, parse_constant=_reject_non_json_constant)
            _validate_finite_json_value(value)
        except (json.JSONDecodeError, ValueError):
            value = response.content
        try:
            validate_value(to_json_compatible(value), schema, path="final_response")
        except (TypeError, ValueError):
            return _rejected(FinalResponseRejection.FINAL_RESPONSE_INVALID, schema_digest, response_digest)
        return FinalResponseBoundaryResult(
            True,
            response,
            schema_digest=schema_digest,
            response_digest=response_digest,
        )


_FINAL_SCHEMA_KEYS = frozenset(
    {
        "type",
        "oneOf",
        "anyOf",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "const",
        "enum",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "description",
    }
)
_FINAL_SCHEMA_TYPES = frozenset({"object", "array", "null", "string", "boolean", "integer", "number"})


def _validate_final_response_schema(schema: Mapping[str, object], *, path: str = "final_response", depth: int = 0) -> None:
    """Close the finite public schema algebra before interpreting a final value."""

    if depth > 8 or not isinstance(schema, Mapping) or not schema or set(schema) - _FINAL_SCHEMA_KEYS:
        raise ValueError(f"{path} uses an unsupported schema shape")
    description = schema.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 1_000):
        raise ValueError(f"{path} description must be bounded text")
    unions = tuple(key for key in ("oneOf", "anyOf") if key in schema)
    if unions:
        if len(unions) != 1 or set(schema) - {unions[0], "description"}:
            raise ValueError(f"{path} union schema is ambiguous")
        variants = schema[unions[0]]
        if not isinstance(variants, list | tuple) or not 1 <= len(variants) <= 8:
            raise ValueError(f"{path} union schema is invalid")
        for index, variant in enumerate(variants):
            if not isinstance(variant, Mapping):
                raise ValueError(f"{path} union member is invalid")
            _validate_final_response_schema(variant, path=f"{path}.{unions[0]}[{index}]", depth=depth + 1)
        return
    schema_type = schema.get("type")
    if schema_type not in _FINAL_SCHEMA_TYPES:
        raise ValueError(f"{path} uses unsupported schema type: {schema_type}")
    scalar_constraints = {"const", "enum", "pattern", "minLength", "maxLength", "minimum", "maximum"}
    if schema_type in {"object", "array", "null"} and scalar_constraints.intersection(schema):
        raise ValueError(f"{path} container schema contains unsupported scalar constraints")
    if schema_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", ())
        additional = schema.get("additionalProperties", False)
        if not isinstance(properties, Mapping) or len(properties) > 64:
            raise ValueError(f"{path} properties are invalid")
        if (
            not isinstance(required, list | tuple)
            or any(not isinstance(item, str) for item in required)
            or len(set(required)) != len(required)
            or not set(required).issubset(properties)
            or not isinstance(additional, bool)
        ):
            raise ValueError(f"{path} object contract is invalid")
        if any(key in schema for key in ("items", "minItems", "maxItems")):
            raise ValueError(f"{path} object schema contains array fields")
        for name, child in properties.items():
            if not isinstance(name, str) or not name or not isinstance(child, Mapping):
                raise ValueError(f"{path} property is invalid")
            _validate_final_response_schema(child, path=f"{path}.{name}", depth=depth + 1)
    elif schema_type == "array":
        items = schema.get("items")
        minimum = schema.get("minItems", 0)
        maximum = schema.get("maxItems")
        if (
            any(key in schema for key in ("properties", "required", "additionalProperties"))
            or not isinstance(items, Mapping)
            or not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or minimum < 0
            or (maximum is not None and (not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < minimum))
        ):
            raise ValueError(f"{path} array contract is invalid")
        _validate_final_response_schema(items, path=f"{path}.items", depth=depth + 1)
    elif any(key in schema for key in ("properties", "required", "additionalProperties", "items", "minItems", "maxItems")):
        raise ValueError(f"{path} primitive schema contains container fields")
    if "pattern" in schema:
        if schema_type != "string" or not isinstance(schema["pattern"], str) or len(schema["pattern"]) > 240:
            raise ValueError(f"{path} pattern is invalid")
        re.compile(schema["pattern"])
    for key in ("minLength", "maxLength"):
        if key in schema and (
            schema_type != "string"
            or not isinstance(schema[key], int)
            or isinstance(schema[key], bool)
            or schema[key] < 0
        ):
            raise ValueError(f"{path} {key} is invalid")
    for key in ("minimum", "maximum"):
        if key in schema and (
            schema_type not in {"integer", "number"}
            or not isinstance(schema[key], int | float)
            or isinstance(schema[key], bool)
            or not math.isfinite(schema[key])
        ):
            raise ValueError(f"{path} {key} is invalid")
    if "minLength" in schema and "maxLength" in schema and schema["minLength"] > schema["maxLength"]:
        raise ValueError(f"{path} string bounds are inconsistent")
    if "minimum" in schema and "maximum" in schema and schema["minimum"] > schema["maximum"]:
        raise ValueError(f"{path} numeric bounds are inconsistent")
    if "enum" in schema:
        enum = schema["enum"]
        if (
            not isinstance(enum, list | tuple)
            or not 1 <= len(enum) <= 32
            or any(not _strict_scalar_type(item, schema_type) for item in enum)
            or len({(type(item), repr(item)) for item in enum}) != len(enum)
        ):
            raise ValueError(f"{path} enum is invalid")
    if "const" in schema and not _strict_scalar_type(schema["const"], schema_type):
        raise ValueError(f"{path} const is invalid")


def _strict_scalar_type(value: object, schema_type: object) -> bool:
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
    return False


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant is unsupported: {value}")


def _validate_finite_json_value(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON numbers are unsupported")
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_finite_json_value(item)
    elif isinstance(value, list):
        for item in value:
            _validate_finite_json_value(item)


def _current_public_record(bundle: EvidenceBundle, evidence_ref: str) -> bool:
    record = bundle.resolve(evidence_ref)
    if record is not None and record.evidence_ref in bundle.pinned_evidence_refs:
        return bool(record.kind == "fact" and is_public_scalar(record.value) and record.has_typed_source)
    return bool(
        record is not None
        and record.observation_id == bundle.observation_id
        and record.source_observation_id in set(bundle.source_observation_ids)
        and record.has_typed_source
        and bundle.source_coverages.get(record.source_observation_id, "") != "stale"
    )


def _digest(value: object) -> str:
    encoded = json.dumps(to_json_compatible(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(encoded.encode()).hexdigest()}"


def _rejected(
    code: FinalResponseRejection,
    schema_digest: str,
    response_digest: str,
) -> FinalResponseBoundaryResult:
    return FinalResponseBoundaryResult(False, rejection_code=code, schema_digest=schema_digest, response_digest=response_digest)
