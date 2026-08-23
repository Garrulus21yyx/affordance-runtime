"""Immutable bounds and truthful truncation metadata for AgentContext."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")
DEFAULT_MAX_TOTAL_WAIT_MS = 120_000
DEFAULT_MODEL_REQUEST_TOKEN_LIMIT = 64_000
DEFAULT_MODEL_REQUEST_SOFT_TARGET = 8_000


def _environment_admission_limit() -> int:
    raw = os.environ.get("AFFORDANCE_MODEL_REQUEST_TOKEN_LIMIT", "").strip()
    if not raw:
        return DEFAULT_MODEL_REQUEST_TOKEN_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MODEL_REQUEST_TOKEN_LIMIT
    return value if value > 0 else DEFAULT_MODEL_REQUEST_TOKEN_LIMIT


@dataclass(frozen=True)
class ModelRequestBudget:
    """Input limits plus one model context window shared by packing and admission."""

    soft_target_tokens: int = DEFAULT_MODEL_REQUEST_SOFT_TARGET
    model_context_window: int = 67_000
    max_output_tokens: int = 1_024
    protocol_reserve_tokens: int = 2_048
    safety_margin_tokens: int = 1_024
    admission_limit: int = field(default_factory=_environment_admission_limit)

    def __post_init__(self) -> None:
        counters = (
            self.soft_target_tokens,
            self.model_context_window,
            self.max_output_tokens,
            self.protocol_reserve_tokens,
            self.safety_margin_tokens,
            self.admission_limit,
        )
        if any(isinstance(value, bool) or value < 0 for value in counters):
            raise ValueError("model request budget counters must be non-negative")
        if self.soft_target_tokens < 1 or self.model_context_window < 1:
            raise ValueError("model request admission limit must be positive")
        derived = (
            self.model_context_window
            - self.max_output_tokens
            - self.protocol_reserve_tokens
            - self.safety_margin_tokens
        )
        limit = min(self.admission_limit or derived, derived)
        object.__setattr__(self, "admission_limit", max(1, limit))

    def effective_input_limit(self, output_reserve_tokens: int) -> int:
        """Return the input ceiling for an envelope whose reserve is counted separately."""

        if isinstance(output_reserve_tokens, bool) or output_reserve_tokens < 0:
            raise ValueError("model output reserve must be non-negative")
        return min(
            self.admission_limit,
            max(0, self.model_context_window - output_reserve_tokens),
        )


@dataclass(frozen=True)
class BoundedSection(Generic[T]):
    items: tuple[T, ...]
    total_count: int
    truncated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        if self.total_count < len(self.items):
            raise ValueError("bounded section total cannot be smaller than its projection")
        if self.truncated != (self.total_count > len(self.items)):
            raise ValueError("bounded section truncation metadata is untruthful")

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, index):
        return self.items[index]


@dataclass(frozen=True)
class ContextProjectionBudget:
    max_intent_excerpts: int = 6
    max_intent_chars: int = 2_400
    # None means that target capacity is governed by the serialized workspace
    # budget.  A numeric value remains available for deliberately bounded
    # tests/callers, but the product path must not truncate a short GUI by an
    # arbitrary object count before measuring its actual context size.
    max_targets: int | None = None
    min_observation_exploration_targets: int = 8
    max_facts: int = 128
    max_facts_per_target: int = 8
    max_relations_per_target: int = 8
    max_conflicts: int = 16
    max_action_options: int = 128
    max_transition_progress_changes: int = 32
    max_transition_evidence_refs: int = 16
    max_artifact_summaries: int = 16
    max_unresolved_items: int = 32
    # Legacy bound for explicitly bounded projection callers. ContextBuilder's
    # supported-public Actor is lossless; provider delivery has its own request
    # admission and WorldDeliveryView fitting boundary.
    max_total_serialized_bytes: int = 384 * 1024

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.__dict__.values() if value is not None):
            raise ValueError("context projection budgets must be positive")

    def observation_target_capacity(self, total_count: int) -> int:
        if total_count < 0:
            raise ValueError("observation target count cannot be negative")
        if self.max_targets is None:
            return max(1, total_count)
        return self.max_targets

    def observation_exploration_slots(self, total_count: int) -> int:
        capacity = self.observation_target_capacity(total_count)
        return min(
            self.min_observation_exploration_targets,
            max(1, capacity // 4),
        )

    def observation_pinned_capacity(self, total_count: int) -> int:
        if self.max_targets is None:
            return max(1, total_count)
        capacity = self.observation_target_capacity(total_count)
        if capacity == 1:
            return 1
        return capacity - self.observation_exploration_slots(total_count)


def serialized_size(value: object) -> int:
    return len(json.dumps(_serializable(value), sort_keys=True, separators=(",", ":")).encode())


def _serializable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _serializable(getattr(value, item.name))
            for item in fields(value)
            if item.metadata.get("serialize", True) is not False
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    return value
