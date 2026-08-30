"""Optional environment finalization capability."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from affordance_runtime.actions.schema_validation import (
    validate_parameter_schema_contract,
    validate_value,
)
from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.world.acquisition import ObservationAcquisition

FINAL_RESPONSE_MODEL_GUIDANCE_MAX_CHARS = 700
MAX_PLAIN_TEXT_FINAL_RESPONSE_CHARS = 8_000
MAX_FINAL_RESPONSE_CHARS = 128 * 1_024
_NONBLANK_FINAL_RESPONSE_PATTERN = r"[\s\S]*\S[\s\S]*"


class FinalResponsePayloadEncoding(StrEnum):
    TEXT = "text"
    JSON = "json"


@dataclass(frozen=True)
class FinalResponseToolContract:
    """Codec-owned model payload shape and its deterministic wire encoding."""

    encoding: FinalResponsePayloadEncoding = FinalResponsePayloadEncoding.TEXT
    payload_schema: Mapping[str, object] = field(
        default_factory=lambda: {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_PLAIN_TEXT_FINAL_RESPONSE_CHARS,
            "pattern": _NONBLANK_FINAL_RESPONSE_PATTERN,
        }
    )
    contract_id: str = ""

    def __post_init__(self) -> None:
        encoding = FinalResponsePayloadEncoding(self.encoding)
        schema = freeze_json(self.payload_schema)
        expected_type = "string" if encoding is FinalResponsePayloadEncoding.TEXT else "object"
        if not isinstance(schema, Mapping) or not _declares_payload_type(schema, expected_type):
            raise ValueError("final response payload schema does not match its encoding")
        object.__setattr__(self, "encoding", encoding)
        validate_parameter_schema_contract(
            {
                "type": "object",
                "properties": {self.argument_name: schema},
                "required": [self.argument_name],
                "additionalProperties": False,
            }
        )
        maximum_chars = (
            _maximum_text_chars(schema)
            if encoding is FinalResponsePayloadEncoding.TEXT
            else _maximum_json_chars(schema)
        )
        if maximum_chars > MAX_FINAL_RESPONSE_CHARS:
            raise ValueError("final response payload schema exceeds its encoded response bound")
        expected_id = schema_digest(
            {
                "encoding": encoding.value,
                "argument_name": self.argument_name,
                "max_encoded_chars": MAX_FINAL_RESPONSE_CHARS,
                "payload_schema": schema,
            }
        )
        if self.contract_id and self.contract_id != expected_id:
            raise ValueError("final response tool contract identity is invalid")
        object.__setattr__(self, "payload_schema", schema)
        object.__setattr__(self, "contract_id", expected_id)

    @property
    def argument_name(self) -> str:
        return "content" if self.encoding is FinalResponsePayloadEncoding.TEXT else "response"

    def encode(self, value: object) -> str:
        validate_value(value, self.payload_schema, path=self.argument_name)
        if self.encoding is FinalResponsePayloadEncoding.TEXT:
            encoded = str(value)
        else:
            encoded = json.dumps(
                to_json_compatible(value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        if not encoded.strip() or len(encoded) > MAX_FINAL_RESPONSE_CHARS:
            raise ValueError("encoded final response is outside its bounded contract")
        return encoded


def _declares_payload_type(schema: Mapping[str, object], expected_type: str) -> bool:
    if schema.get("type") == expected_type:
        return True
    variants = schema.get("oneOf") or schema.get("anyOf")
    return bool(
        "type" not in schema
        and isinstance(variants, Sequence)
        and not isinstance(variants, str | bytes)
        and variants
        and all(
            isinstance(item, Mapping) and _declares_payload_type(item, expected_type)
            for item in variants
        )
    )


def _maximum_text_chars(schema: Mapping[str, object]) -> int:
    maximum = schema.get("maxLength")
    minimum = schema.get("minLength")
    if (
        type(maximum) is not int
        or type(minimum) is not int
        or minimum < 1
        or maximum > MAX_PLAIN_TEXT_FINAL_RESPONSE_CHARS
        or schema.get("pattern") != _NONBLANK_FINAL_RESPONSE_PATTERN
    ):
        raise ValueError("plain-text final response schema must declare its nonblank bounded domain")
    return maximum


def _maximum_json_chars(schema: Mapping[str, object]) -> int:
    """Conservatively bound compact JSON emitted for every schema-valid value."""

    variants = schema.get("oneOf") or schema.get("anyOf")
    if isinstance(variants, Sequence) and not isinstance(variants, str | bytes):
        return max(_maximum_json_chars(item) for item in variants)

    schema_type = schema.get("type")
    if "const" in schema:
        return len(json.dumps(schema["const"], ensure_ascii=False, separators=(",", ":")))
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, str | bytes):
        return max(len(json.dumps(item, ensure_ascii=False, separators=(",", ":"))) for item in enum)
    if schema_type == "null":
        return 4
    if schema_type == "boolean":
        return 5
    if schema_type == "string":
        maximum = schema.get("maxLength")
        if type(maximum) is not int:
            raise ValueError("structured final response strings must declare maxLength")
        # A single JSON string code point can expand to a six-character
        # control escape. Quotes are included separately.
        return 2 + (6 * maximum)
    if schema_type == "integer":
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if type(minimum) is not int or type(maximum) is not int:
            raise ValueError("structured final response integers must be bounded")
        return max(len(str(minimum)), len(str(maximum)))
    if schema_type == "number":
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if not isinstance(minimum, int | float) or not isinstance(maximum, int | float):
            raise ValueError("structured final response numbers must be bounded")
        # The number schema also admits Python ints.  A float endpoint such as
        # 1e308 can therefore admit a 309-digit integer even though its own
        # repr is only five characters.  Converting each finite endpoint to
        # int conservatively captures that integral wire width; 32 covers
        # ordinary finite float reprs and fractional syntax.
        return max(32, len(str(int(minimum))), len(str(int(maximum))))
    if schema_type == "array":
        maximum = schema.get("maxItems")
        items = schema.get("items")
        if type(maximum) is not int or not isinstance(items, Mapping):
            raise ValueError("structured final response arrays must be bounded")
        item_chars = _maximum_json_chars(items)
        return 2 if maximum == 0 else 2 + (maximum * item_chars) + (maximum - 1)
    if schema_type == "object":
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", False)
        if not isinstance(properties, Mapping):
            raise ValueError("structured final response object schema is invalid")
        fixed = [
            len(json.dumps(name, ensure_ascii=False)) + 1 + _maximum_json_chars(child)
            for name, child in properties.items()
        ]
        if isinstance(additional, Mapping):
            maximum = schema.get("maxProperties")
            property_names = schema.get("propertyNames")
            if type(maximum) is not int or not isinstance(property_names, Mapping):
                raise ValueError("structured final response dynamic objects must be bounded")
            dynamic = _maximum_json_chars(property_names) + 1 + _maximum_json_chars(additional)
            contributions = sorted((*fixed, *((dynamic,) * maximum)), reverse=True)[:maximum]
        elif additional is False:
            maximum = schema.get("maxProperties", len(fixed))
            if type(maximum) is not int:
                raise ValueError("structured final response object bound is invalid")
            contributions = sorted(fixed, reverse=True)[:maximum]
        else:
            raise ValueError("structured final response object values must be bounded")
        return 2 if not contributions else 2 + sum(contributions) + len(contributions) - 1
    raise ValueError("structured final response schema uses an unsupported type")


PLAIN_TEXT_FINAL_RESPONSE_TOOL_CONTRACT = FinalResponseToolContract()


class FinalResponseCodec(Protocol):
    """Environment-owned representation adapter applied before one STOP."""

    def normalize(self, content: str) -> str: ...


def final_response_model_guidance(codec: FinalResponseCodec) -> str:
    """Return optional bounded tool guidance owned by the response codec."""

    guidance = getattr(codec, "model_guidance", "")
    if not isinstance(guidance, str):
        raise TypeError("final response model guidance must be text")
    guidance = " ".join(guidance.split())
    if len(guidance) > FINAL_RESPONSE_MODEL_GUIDANCE_MAX_CHARS:
        raise ValueError("final response model guidance exceeds its tool-contract bound")
    return guidance


def final_response_tool_contract(codec: FinalResponseCodec) -> FinalResponseToolContract:
    """Return the codec-owned model payload contract or the stable text default."""

    contract = getattr(codec, "model_tool_contract", PLAIN_TEXT_FINAL_RESPONSE_TOOL_CONTRACT)
    if not isinstance(contract, FinalResponseToolContract):
        raise TypeError("final response model tool contract must be typed")
    return contract


@dataclass(frozen=True)
class PlainTextFinalResponseCodec:
    """Identity codec for environments whose native response is plain text."""

    def normalize(self, content: str) -> str:
        return content

    @property
    def model_tool_contract(self) -> FinalResponseToolContract:
        return PLAIN_TEXT_FINAL_RESPONSE_TOOL_CONTRACT


PLAIN_TEXT_FINAL_RESPONSE_CODEC = PlainTextFinalResponseCodec()


@dataclass(frozen=True)
class EnvironmentFinalization:
    result: ActionResult
    post_acquisition: ObservationAcquisition | None = None


class FinalizingEnvironment(Protocol):
    @property
    def final_response_codec(self) -> FinalResponseCodec: ...

    @property
    def supports_finalization(self) -> bool: ...

    async def finalize(self, content: str) -> EnvironmentFinalization: ...
