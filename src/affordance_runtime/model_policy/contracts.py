"""Immutable request and response contracts for one structured model decision."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_boundary.context import AgentImageInput

if TYPE_CHECKING:
    from affordance_runtime.model_boundary.context import AgentContext

MAX_MODEL_RESPONSE_BYTES = 32 * 1024
_MAX_CONTEXT_BYTES = 64 * 1024
_MAX_INSTRUCTIONS = 8 * 1024
_SAFE_METADATA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")


@dataclass(frozen=True)
class ModelMetadata:
    provider_id: str = ""
    model_id: str = ""
    response_id: str = ""
    endpoint_class: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    rate_limit_retry_count: int = 0
    transient_retry_count: int = 0
    grounding_variant: str = ""
    grounding_profile_version: str = ""
    grounding_guide_schema_version: str = ""
    grounding_guide_digest: str = ""
    decision_schema_digest: str = ""
    result_summary_max_chars: int = 0
    perception_profile: str = ""

    def __post_init__(self) -> None:
        for value in (
            self.provider_id,
            self.model_id,
            self.response_id,
            self.endpoint_class,
            self.prompt_version,
            self.schema_version,
            self.grounding_variant,
            self.grounding_profile_version,
            self.grounding_guide_schema_version,
            self.grounding_guide_digest,
            self.decision_schema_digest,
            self.perception_profile,
        ):
            if value and (_SAFE_METADATA.fullmatch(value) is None or "://" in value):
                raise ValueError("model metadata must contain only bounded public identifiers")
        counters = (
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
            self.rate_limit_retry_count,
            self.transient_retry_count,
            self.result_summary_max_chars,
        )
        if self.latency_ms < 0 or any(value < 0 for value in counters):
            raise ValueError("model metadata counters must be nonnegative")


@dataclass(frozen=True)
class ModelDecisionRequest:
    request_id: str
    serialized_context: str
    schema_version: str
    instructions: str
    decision_schema: Mapping[str, object]
    image_inputs: tuple[AgentImageInput, ...] = ()
    policy_context: "AgentContext | None" = field(default=None, repr=False, compare=False)

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
        object.__setattr__(self, "image_inputs", tuple(self.image_inputs))
        if len(self.image_inputs) > 2 or any(
            not isinstance(item, AgentImageInput) for item in self.image_inputs
        ):
            raise TypeError("model request image inputs must be bounded and typed")
        if self.policy_context is not None:
            from affordance_runtime.model_boundary.context import AgentContext

            if not isinstance(self.policy_context, AgentContext):
                raise TypeError("model decision request policy context must be typed")


@dataclass(frozen=True)
class ModelDecisionResponse:
    raw_payload: str
    metadata: ModelMetadata = field(default_factory=ModelMetadata)

    def __post_init__(self) -> None:
        if not isinstance(self.raw_payload, str) or not self.raw_payload.strip():
            raise ValueError("model decision response payload cannot be blank")
        if len(self.raw_payload.encode()) > MAX_MODEL_RESPONSE_BYTES:
            raise ValueError("model decision response exceeds its byte bound")
