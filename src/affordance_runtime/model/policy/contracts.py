"""Immutable request and response contracts for one typed model decision."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from affordance_runtime.agent.context.context import AgentContext, AgentImageInput
from affordance_runtime.agent.decisions import AgentDecision

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
    agent_context: AgentContext = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if _SAFE_METADATA.fullmatch(self.request_id) is None:
            raise ValueError("model decision request requires a bounded opaque identifier")
        if not isinstance(self.agent_context, AgentContext):
            raise TypeError("model decision request AgentContext must be typed")
        if _SAFE_METADATA.fullmatch(self.agent_context.context_id) is None:
            raise ValueError("model decision request context identity is invalid")

    @property
    def context_id(self) -> str:
        return self.agent_context.context_id

    @property
    def image_inputs(self) -> tuple[AgentImageInput, ...]:
        return self.agent_context.image_inputs


@dataclass(frozen=True)
class ResolvedModelDecision:
    """A provider response parsed exactly once by its protocol adapter."""

    decision: AgentDecision
    metadata: ModelMetadata = field(default_factory=ModelMetadata)

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AgentDecision):
            raise TypeError("resolved model outcome requires one typed AgentDecision")
