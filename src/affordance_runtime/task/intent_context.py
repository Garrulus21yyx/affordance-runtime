"""Optional context-only intent excerpts retained outside TaskGoal authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class IntentSourceKind(StrEnum):
    USER = "user"
    SYSTEM = "system"
    EXTERNAL = "external"
    TASK_SOURCE = "task_source"


@dataclass(frozen=True)
class IntentExcerpt:
    text: str
    source_kind: IntentSourceKind
    source_ref: str
    digest: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.text, self.source_ref, self.digest)):
            raise ValueError("intent excerpt requires text, source identity, and digest")


@dataclass(frozen=True)
class IntentContext:
    excerpts: tuple[IntentExcerpt, ...]
    authority: str = field(default="context_only", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "excerpts", tuple(self.excerpts))
