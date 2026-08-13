"""Closed Catalog directive for Runtime-owned current-step execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionCatalogMode(StrEnum):
    """Closed Catalog meaning for any active step-execution variant."""

    CONTROL_ONLY = "control_only"
    MEMBER_ACTIONS_ONLY = "member_actions_only"
    SUCCESSOR_ACTIONS = "successor_actions"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ExecutionCatalogDirective:
    """Private action authority projected from current Runtime execution state."""

    mode: ExecutionCatalogMode
    allowed_action_ids: frozenset[str] = frozenset()
    reason_code: str = ""
