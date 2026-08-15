"""Immutable request and response contracts for one structured model decision."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model.context.context import AgentImageInput

if TYPE_CHECKING:
    from affordance_runtime.model.context.context import AgentContext

_MAX_CONTEXT_BYTES = 64 * 1024
_MAX_INSTRUCTIONS = 8 * 1024
_SAFE_METADATA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
MAX_MODEL_RESPONSE_BYTES = 32 * 1024


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
    agent_context: "AgentContext | None" = field(default=None, repr=False, compare=False)
    context_id: str = field(init=False)

    def __post_init__(self) -> None:
        if _SAFE_METADATA.fullmatch(self.request_id) is None:
            raise ValueError("model decision request requires a bounded opaque identifier")
        if not self.schema_version.strip() or len(self.schema_version) > 80:
            raise ValueError("model decision schema version is invalid")
        if not self.instructions.strip() or len(self.instructions.encode()) > _MAX_INSTRUCTIONS:
            raise ValueError("model policy instructions exceed their bound")
        if len(self.serialized_context.encode()) > _MAX_CONTEXT_BYTES:
            raise ValueError("serialized AgentContext exceeds the model request bound")
        context_id: object = None
        if self.serialized_context.strip():
            try:
                public_context = json.loads(self.serialized_context)
                context_id = public_context["context_id"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError("model decision request requires one public context identity") from exc
        elif self.agent_context is not None:
            context_id = self.agent_context.context_id
        if not isinstance(context_id, str) or _SAFE_METADATA.fullmatch(context_id) is None:
            raise ValueError("model decision request context identity is invalid")
        object.__setattr__(self, "context_id", context_id)
        object.__setattr__(self, "decision_schema", freeze_json(self.decision_schema))
        object.__setattr__(self, "image_inputs", tuple(self.image_inputs))
        if len(self.image_inputs) > 2 or any(not isinstance(item, AgentImageInput) for item in self.image_inputs):
            raise TypeError("model request image inputs must be bounded and typed")
        if self.agent_context is not None:
            from affordance_runtime.model.context.context import AgentContext

            if not isinstance(self.agent_context, AgentContext):
                raise TypeError("model decision request AgentContext must be typed")
            if self.agent_context.context_id != self.context_id:
                raise ValueError("AgentContext does not match its public projection")


@dataclass(frozen=True)
class ResolvedModelDecision:
    """A provider response parsed exactly once by its protocol adapter."""

    decision: AgentDecision
    metadata: ModelMetadata = field(default_factory=ModelMetadata)

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AgentDecision):
            raise TypeError("resolved model outcome requires one typed AgentDecision")
