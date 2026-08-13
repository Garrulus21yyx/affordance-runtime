"""Closed Catalog directive projected from Runtime-owned step execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionCatalogMode(StrEnum):
    CONTROL_ONLY = "control_only"
    MEMBER_ACTIONS_ONLY = "member_actions_only"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ExecutionCatalogDirective:
    mode: ExecutionCatalogMode
    allowed_action_ids: frozenset[str] = frozenset()
    reason_code: str = ""
