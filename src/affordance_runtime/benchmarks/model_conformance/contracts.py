"""Immutable contracts for exact model-profile conformance evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

_PUBLIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,239}$")


class ModelConformanceStage(StrEnum):
    UNAVAILABLE = "unavailable"
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    STRUCTURED_OUTPUT = "structured_output"
    STRICT_JSON = "strict_json"
    PAYLOAD_SCHEMA = "payload_schema"
    CONTEXT_ID = "context_id"
    DECISION_VARIANT = "decision_variant"
    ACTION_ID = "action_id"
    DESTINATION_ID = "destination_id"
    PARAMETERS = "parameters"
    RUNTIME_ADMISSION = "runtime_admission"
    MODEL_ABORT = "model_abort"
    EXECUTION = "execution"
    TASK_EVALUATION = "task_evaluation"
    SUCCESS = "success"


class DestinationFailureShape(StrEnum):
    NONE = ""
    EMPTY_WHEN_REQUIRED = "empty_when_required"
    NONEMPTY_WHEN_FORBIDDEN = "nonempty_when_forbidden"
    EQUALS_TARGET_ID = "equals_target_id"
    EQUALS_ACTION_ID = "equals_action_id"
    BELONGS_TO_OTHER_ACTION = "belongs_to_other_action"
    UNKNOWN_PUBLIC_ID = "unknown_public_id"


@dataclass(frozen=True)
class ModelProfileIdentity:
    provider_id: str
    model_id: str
    endpoint_class: str
    runtime_name: str
    runtime_version: str
    model_digest: str
    family: str
    parameter_size: str
    quantization: str
    prompt_version: str
    schema_version: str
    context_budget_profile: str
    decision_schema_digest: str = ""
    result_summary_max_chars: int = 0
    grounding_variant: str = ""
    grounding_profile_version: str = ""
    execution_profile: str = ""

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if name == "result_summary_max_chars":
                if value < 0:
                    raise ValueError("model profile summary bound must be nonnegative")
                continue
            if value and (_PUBLIC_ID.fullmatch(value) is None or "://" in value):
                raise ValueError("model profile identity requires bounded public identifiers")


@dataclass(frozen=True)
class SecretFreeSalienceMetrics:
    selected_target_id_occurrences: int = 0
    allowed_destination_id_occurrences: int = 0
    selected_action_id_occurrences: int = 0
    last_target_id_distance_from_end_bytes: int | None = None
    last_destination_id_distance_from_end_bytes: int | None = None
    actions_block_distance_from_end_bytes: int | None = None
    context_bytes: int = 0
    facts_count: int = 0
    artifacts_count: int = 0
    target_count: int = 0

    def __post_init__(self) -> None:
        counts = (
            self.selected_target_id_occurrences,
            self.allowed_destination_id_occurrences,
            self.selected_action_id_occurrences,
            self.context_bytes,
            self.facts_count,
            self.artifacts_count,
            self.target_count,
        )
        distances = (
            self.last_target_id_distance_from_end_bytes,
            self.last_destination_id_distance_from_end_bytes,
            self.actions_block_distance_from_end_bytes,
        )
        if any(value < 0 for value in counts) or any(
            value is not None and value < 0 for value in distances
        ):
            raise ValueError("salience metrics must be nonnegative")


@dataclass(frozen=True)
class ConformanceAttempt:
    attempt_id: str
    level: str
    grounding_variant: str
    stage: ModelConformanceStage
    success: bool
    failure_kind: str
    decision_variant: str
    context_bytes: int
    system_prompt_bytes: int
    user_message_bytes: int
    schema_bytes: int
    total_input_bytes: int
    visible_actions: int
    visible_targets: int
    visible_facts: int
    history_turns: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    output_bytes: int
    output_sha256: str
    latency_ms: float
    destination_failure_shape: DestinationFailureShape = DestinationFailureShape.NONE
    salience_metrics: SecretFreeSalienceMetrics = field(default_factory=SecretFreeSalienceMetrics)

    def __post_init__(self) -> None:
        counters = (
            self.context_bytes, self.system_prompt_bytes, self.user_message_bytes,
            self.schema_bytes, self.total_input_bytes, self.visible_actions,
            self.visible_targets, self.visible_facts, self.history_turns,
            self.prompt_tokens, self.completion_tokens, self.total_tokens,
            self.output_bytes,
        )
        if any(value < 0 for value in counters) or self.latency_ms < 0:
            raise ValueError("conformance metrics must be nonnegative")
        if self.output_sha256 and not self.output_sha256.startswith("sha256:"):
            raise ValueError("output identity must use the sha256 namespace")
        object.__setattr__(
            self,
            "destination_failure_shape",
            DestinationFailureShape(self.destination_failure_shape),
        )
        if isinstance(self.salience_metrics, Mapping):
            object.__setattr__(
                self,
                "salience_metrics",
                SecretFreeSalienceMetrics(**self.salience_metrics),
            )


@dataclass(frozen=True)
class ConformanceCellSummary:
    level: str
    grounding_variant: str
    attempt_count: int
    success_count: int
    failure_shape_counts: tuple[tuple[str, int], ...]
    decision_variant_counts: tuple[tuple[str, int], ...]
    prompt_tokens: tuple[int, ...]
    completion_tokens: tuple[int, ...]
    latency_ms: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "failure_shape_counts", tuple(map(tuple, self.failure_shape_counts)))
        object.__setattr__(self, "decision_variant_counts", tuple(map(tuple, self.decision_variant_counts)))
        object.__setattr__(self, "prompt_tokens", tuple(self.prompt_tokens))
        object.__setattr__(self, "completion_tokens", tuple(self.completion_tokens))
        object.__setattr__(self, "latency_ms", tuple(self.latency_ms))
        if not 0 <= self.success_count <= self.attempt_count:
            raise ValueError("cell success count exceeds attempts")


@dataclass(frozen=True)
class ModelInputComplexity:
    serialized_context_bytes: int
    system_prompt_bytes: int
    schema_bytes: int
    schema_defs: int
    schema_variants: int
    schema_max_depth: int
    actions: int
    destinations: int
    targets: int
    facts: int
    conflicts: int
    artifacts: int
    history_turns: int
    total_input_bytes: int


@dataclass(frozen=True)
class ModelProfileConformanceResult:
    identity: ModelProfileIdentity
    attempts: tuple[ConformanceAttempt, ...]
    passed_levels: tuple[str, ...]
    failed_levels: tuple[str, ...]
    classification: str
    classification_reasons: tuple[str, ...]
    input_complexity: ModelInputComplexity
    cell_summaries: tuple[ConformanceCellSummary, ...] = ()
    structured_output_status: str = ""
    action_selection_status: str = ""
    full_recurrent_decision_status: str = ""
