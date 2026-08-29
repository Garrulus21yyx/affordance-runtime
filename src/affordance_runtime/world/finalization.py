"""Optional environment finalization capability."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.world.acquisition import ObservationAcquisition

FINAL_RESPONSE_MODEL_GUIDANCE_MAX_CHARS = 700
MAX_FINAL_RESPONSE_CHARS = 8_000


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
            "maxLength": MAX_FINAL_RESPONSE_CHARS,
        }
    )
    contract_id: str = ""

    def __post_init__(self) -> None:
        encoding = FinalResponsePayloadEncoding(self.encoding)
        schema = freeze_json(self.payload_schema)
        expected_type = "string" if encoding is FinalResponsePayloadEncoding.TEXT else "object"
        if not isinstance(schema, Mapping) or schema.get("type") != expected_type:
            raise ValueError("final response payload schema does not match its encoding")
        expected_id = schema_digest(
            {
                "encoding": encoding.value,
                "argument_name": self.argument_name,
                "payload_schema": schema,
            }
        )
        if self.contract_id and self.contract_id != expected_id:
            raise ValueError("final response tool contract identity is invalid")
        object.__setattr__(self, "encoding", encoding)
        object.__setattr__(self, "payload_schema", schema)
        object.__setattr__(self, "contract_id", expected_id)

    @property
    def argument_name(self) -> str:
        return "content" if self.encoding is FinalResponsePayloadEncoding.TEXT else "response"

    def encode(self, value: object) -> str:
        if self.encoding is FinalResponsePayloadEncoding.TEXT:
            if not isinstance(value, str):
                raise TypeError("plain-text final response payload must be text")
            return value
        return json.dumps(
            to_json_compatible(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


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
