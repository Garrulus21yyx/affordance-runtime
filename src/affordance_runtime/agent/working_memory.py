"""Bounded model-authored task continuity with no Runtime authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_WORKING_MEMORY_ITEMS = 12
MAX_WORKING_MEMORY_DESCRIPTION_CHARS = 240


class WorkingMemoryItemStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(frozen=True)
class WorkingMemoryItem:
    description: str
    status: WorkingMemoryItemStatus

    def __post_init__(self) -> None:
        if (
            not self.description.strip()
            or len(self.description) > MAX_WORKING_MEMORY_DESCRIPTION_CHARS
        ):
            raise ValueError("working-memory item description is invalid")
        if not isinstance(self.status, WorkingMemoryItemStatus):
            raise TypeError("working-memory item status must be typed")


@dataclass(frozen=True)
class AgentWorkingMemory:
    """Advisory checklist authored by the policy and scoped to one run."""

    items: tuple[WorkingMemoryItem, ...] = ()

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if len(items) > MAX_WORKING_MEMORY_ITEMS:
            raise ValueError("working memory exceeds its item bound")
        if any(not isinstance(item, WorkingMemoryItem) for item in items):
            raise TypeError("working memory requires typed items")
        object.__setattr__(self, "items", items)
