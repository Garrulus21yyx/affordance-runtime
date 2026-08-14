"""Bounded model-authored task state with no Runtime authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MAX_WORKING_MEMORY_ITEMS = 12
MAX_WORKING_MEMORY_DESCRIPTION_CHARS = 240
MAX_WORKING_MEMORY_GOAL_CHARS = 480
MAX_WORKING_MEMORY_DERIVED_FACTS = 8
MAX_WORKING_MEMORY_BLOCKERS = 8
MAX_WORKING_MEMORY_NEXT_STEP_CHARS = 240


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
    """Advisory task belief authored by cognition and scoped to one run."""

    items: tuple[WorkingMemoryItem, ...] = ()
    goal: str = ""
    derived_facts: tuple[str, ...] = ()
    next_step: str = ""
    ready_to_finalize: bool = False
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.goal) > MAX_WORKING_MEMORY_GOAL_CHARS:
            raise ValueError("working-memory goal exceeds its bound")
        items = tuple(self.items)
        if len(items) > MAX_WORKING_MEMORY_ITEMS:
            raise ValueError("working memory exceeds its item bound")
        if any(not isinstance(item, WorkingMemoryItem) for item in items):
            raise TypeError("working memory requires typed items")
        derived_facts = _bounded_statements(
            self.derived_facts,
            MAX_WORKING_MEMORY_DERIVED_FACTS,
            "derived facts",
        )
        blockers = _bounded_statements(
            self.blockers,
            MAX_WORKING_MEMORY_BLOCKERS,
            "blockers",
        )
        if len(self.next_step) > MAX_WORKING_MEMORY_NEXT_STEP_CHARS:
            raise ValueError("working-memory next step exceeds its bound")
        if type(self.ready_to_finalize) is not bool:
            raise TypeError("working-memory readiness must be boolean")
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "derived_facts", derived_facts)
        object.__setattr__(self, "blockers", blockers)


def _bounded_statements(values: tuple[str, ...], limit: int, field_name: str) -> tuple[str, ...]:
    values = tuple(values)
    if len(values) > limit:
        raise ValueError(f"working-memory {field_name} exceed their bound")
    if any(not value.strip() or len(value) > MAX_WORKING_MEMORY_DESCRIPTION_CHARS for value in values):
        raise ValueError(f"working-memory {field_name} are invalid")
    return values
