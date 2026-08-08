"""Immutable bounds and truthful truncation metadata for AgentContext."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")
DEFAULT_MAX_TOTAL_WAIT_MS = 120_000


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
    max_targets: int = 64
    max_facts: int = 128
    max_facts_per_target: int = 8
    max_relations_per_target: int = 8
    max_conflicts: int = 16
    max_action_options: int = 32
    max_destinations_per_option: int = 16
    max_history_turns: int = 12
    max_artifact_summaries: int = 16
    max_unresolved_items: int = 32
    max_total_serialized_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.__dict__.values()):
            raise ValueError("context projection budgets must be positive")


def serialized_size(value: object) -> int:
    return len(json.dumps(_serializable(value), sort_keys=True, separators=(",", ":")).encode())


def _serializable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _serializable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    return value
