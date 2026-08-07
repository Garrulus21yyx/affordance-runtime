"""Small canonical action-family semantics shared by transaction owners."""

from __future__ import annotations

from typing import Protocol


class ActionKindLike(Protocol):
    @property
    def value(self) -> str: ...


def action_compatible(kind: ActionKindLike, affordance_action: str) -> bool:
    """Check provider action compatibility without importing planner internals."""

    allowed = {
        "activate": {"activate", "click", "download", "invoke", "point_activate", "write_property"},
        "focus": {"focus", "fill", "type"},
        "point_activate": {"point_activate"},
        "type_text": {"fill", "type"},
        "select_option": {"select", "select_option"},
        "press_key": {"press"},
        "drag": {"drag"},
        "navigate": {"navigate"},
        "scroll": {"scroll"},
        "wait": {"wait"},
        "ask_user": set(),
        "finish": set(),
    }
    return affordance_action in allowed.get(kind.value, set())
