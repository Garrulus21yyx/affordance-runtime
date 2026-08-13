"""Closed private Catalog directive for a Runtime-owned set objective."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SetCatalogMode(StrEnum):
    """Closed Catalog meaning for one active quantified objective."""

    CONTROL_ONLY = "control_only"
    MEMBER_ACTIONS_ONLY = "member_actions_only"
    SUCCESSOR_ACTIONS = "successor_actions"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SetCatalogDirective:
    """Private action authority derived from Runtime-owned set state.

    An empty ``allowed_action_ids`` is an actual empty set. Absence of an active
    objective is represented by absence of this directive, never by an empty
    sentinel.
    """

    mode: SetCatalogMode
    allowed_action_ids: frozenset[str] = frozenset()
    reason_code: str = ""
