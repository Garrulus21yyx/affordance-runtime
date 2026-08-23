"""Immutable request and response contracts for one typed model decision."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Generic, Mapping, TypeVar

from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.failures import ModelFailure
from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.model.providers.port import StructuredOutputFailureKind

_SAFE_METADATA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
MAX_MODEL_RESPONSE_BYTES = 32 * 1024
T = TypeVar("T")


@dataclass(frozen=True)
class ModelGenerationAttempt:
    """One provider exchange, retained independently from the turn outcome."""

    attempt: int
    phase: str
    schema_name: str
    status: str
    violations: tuple[object, ...] = ()
    response_id: str = ""
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    exception_class: str = ""
    output_failure_kind: StructuredOutputFailureKind | None = None
    finish_reason: str = ""
    max_output_tokens: int = 0
    final_content_present: bool = False
    reasoning_content_present: bool = False
    response_fields: tuple[str, ...] = ()
    role: str = ""
    mode: str = ""
    schema_version: str = ""
    thinking_requested: str = "provider_default"
    thinking_effective: str = "provider_default"
    trigger: str = "ordinary"
    reasoning_tokens: int = 0
    final_content_tokens: int = 0
    final_tool_call_present: bool = False
    transcript: object | None = field(default=None, repr=False, compare=False)


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
    endpoint_host: str = ""

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
            self.endpoint_host,
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

@dataclass(frozen=True)
class ResolvedModelDecision:
    """A provider response parsed exactly once by its protocol adapter."""

    decision: AgentDecision
    metadata: ModelMetadata = field(default_factory=ModelMetadata)
    next_delivery_store: object | None = field(
        default=None, repr=False, compare=False, metadata={"serialize": False}
    )

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AgentDecision):
            raise TypeError("resolved model outcome requires one typed AgentDecision")
        if self.next_delivery_store is not None and type(self.next_delivery_store).__name__ != "ObservationDeliveryStore":
            raise TypeError("resolved local decision requires the delivery owner's next store")


@dataclass(frozen=True)
class ModelInvocationResult(Generic[T]):
    """The single formal result of one role-owned model invocation.

    Provider adapters own wire transport, physical attempts, transcripts, basic
    parsing, and transport retry. Role boundaries own the typed output contract
    and bounded semantic/schema repair. Runtime authority consumes only the
    role output or typed failure; trace observes this result.
    """

    output: T | None = None
    failure: ModelFailure | None = None
    metadata: ModelMetadata = field(default_factory=ModelMetadata)
    attempts: tuple[ModelGenerationAttempt, ...] = ()
    repair_diagnostics: tuple[Mapping[str, object], ...] = ()
    diagnostics: Mapping[str, object] = field(default_factory=dict)
    lineage: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.output is None) == (self.failure is None):
            raise ValueError("model invocation result requires exactly one output or typed failure")
        if self.failure is not None and not isinstance(self.failure, ModelFailure):
            raise TypeError("model invocation failure must be typed")
        if not isinstance(self.metadata, ModelMetadata):
            raise TypeError("model invocation metadata must be typed")
        if any(not isinstance(item, ModelGenerationAttempt) for item in self.attempts):
            raise TypeError("model invocation attempts must be typed")
        if any(not isinstance(item, Mapping) for item in self.repair_diagnostics):
            raise TypeError("repair diagnostics must be mappings")
        if not isinstance(self.diagnostics, Mapping):
            raise TypeError("model invocation diagnostics must be a mapping")
        if not isinstance(self.lineage, Mapping):
            raise TypeError("model invocation lineage must be a mapping")

    @property
    def accepted(self) -> bool:
        return self.output is not None

    @property
    def decision(self) -> AgentDecision:
        output = self.output
        if isinstance(output, ResolvedModelDecision):
            return output.decision
        raise AttributeError("model invocation output has no decision")
