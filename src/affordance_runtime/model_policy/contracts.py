"""Immutable request and response contracts for one structured model decision."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from affordance_runtime.immutable import freeze_json

MAX_MODEL_RESPONSE_BYTES = 32 * 1024
_MAX_CONTEXT_BYTES = 64 * 1024
_MAX_INSTRUCTIONS = 8 * 1024
_SAFE_METADATA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")


@dataclass(frozen=True)
class ModelMetadata:
    provider_id: str = ""
    model_id: str = ""
    response_id: str = ""

    def __post_init__(self) -> None:
        for value in (self.provider_id, self.model_id, self.response_id):
            if value and (_SAFE_METADATA.fullmatch(value) is None or "://" in value):
                raise ValueError("model metadata must contain only bounded public identifiers")


@dataclass(frozen=True)
class ModelDecisionRequest:
    request_id: str
    serialized_context: str
    schema_version: str
    instructions: str
    decision_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        if _SAFE_METADATA.fullmatch(self.request_id) is None:
            raise ValueError("model decision request requires a bounded opaque identifier")
        if not self.schema_version.strip() or len(self.schema_version) > 80:
            raise ValueError("model decision schema version is invalid")
        if not self.instructions.strip() or len(self.instructions.encode()) > _MAX_INSTRUCTIONS:
            raise ValueError("model policy instructions exceed their bound")
        if not self.serialized_context.strip() or len(self.serialized_context.encode()) > _MAX_CONTEXT_BYTES:
            raise ValueError("serialized AgentContext exceeds the model request bound")
        object.__setattr__(self, "decision_schema", freeze_json(self.decision_schema))


@dataclass(frozen=True)
class ModelDecisionResponse:
    raw_payload: str
    metadata: ModelMetadata = field(default_factory=ModelMetadata)

    def __post_init__(self) -> None:
        if not isinstance(self.raw_payload, str) or not self.raw_payload.strip():
            raise ValueError("model decision response payload cannot be blank")
        if len(self.raw_payload.encode()) > MAX_MODEL_RESPONSE_BYTES:
            raise ValueError("model decision response exceeds its byte bound")
