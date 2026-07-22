"""Typed, deliberately bounded BrowserGym action schema.

This is separate from environment execution so the benchmark's accepted action
language stays auditable without importing BrowserGym or a browser runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# This is deliberately narrower than BrowserGym's Python execution surface.
# Values are accepted argument names; arbitrary code and unknown arguments fail.
BROWSERGYM_ACTION_ARGUMENTS: dict[str, frozenset[str]] = {
    "noop": frozenset(),
    "click": frozenset({"bid", "button", "modifiers"}),
    "click_no_navigation": frozenset({"bid"}),
    "dblclick": frozenset({"bid", "button", "modifiers"}),
    "fill": frozenset({"bid", "value"}),
    "select_option": frozenset({"bid", "options"}),
    "hover": frozenset({"bid"}),
    "press": frozenset({"bid", "key_comb"}),
    "focus": frozenset({"bid"}),
    "clear": frozenset({"bid"}),
    "drag_and_drop": frozenset({"from_bid", "to_bid"}),
    "scroll": frozenset({"delta_x", "delta_y"}),
    "mouse_move": frozenset({"x", "y"}),
    "mouse_click": frozenset({"x", "y", "button"}),
    "mouse_dblclick": frozenset({"x", "y", "button"}),
    "mouse_drag_and_drop": frozenset({"from_x", "from_y", "to_x", "to_y", "from_bid", "to_bid"}),
    "mouse_down": frozenset({"button"}),
    "mouse_up": frozenset({"button"}),
    "keyboard_press": frozenset({"key"}),
    "keyboard_type": frozenset({"text"}),
    "type_text_with_events": frozenset({"bid", "text"}),
    "go_back": frozenset(),
    "go_forward": frozenset(),
    "goto": frozenset({"url"}),
    "new_tab": frozenset(),
    "tab_close": frozenset(),
    "tab_focus": frozenset({"index"}),
    "send_msg_to_user": frozenset({"text"}),
    "report_infeasible": frozenset({"reason"}),
}

_POSITIONAL_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "click": ("bid",),
    "click_no_navigation": ("bid",),
    "dblclick": ("bid",),
    "fill": ("bid", "value"),
    "select_option": ("bid", "options"),
    "hover": ("bid",),
    "press": ("bid", "key_comb"),
    "focus": ("bid",),
    "clear": ("bid",),
    "drag_and_drop": ("from_bid", "to_bid"),
    "scroll": ("delta_x", "delta_y"),
    "mouse_move": ("x", "y"),
    "mouse_click": ("x", "y"),
    "mouse_dblclick": ("x", "y"),
    "mouse_drag_and_drop": ("from_x", "from_y", "to_x", "to_y"),
    "keyboard_press": ("key",),
    "keyboard_type": ("text",),
    "type_text_with_events": ("bid", "text"),
    "goto": ("url",),
    "tab_focus": ("index",),
    "send_msg_to_user": ("text",),
    "report_infeasible": ("reason",),
}

_STRING_ARGUMENTS = {
    "bid", "from_bid", "to_bid", "button", "value", "key_comb", "key", "text", "url", "reason"
}
_NUMBER_ARGUMENTS = {"delta_x", "delta_y", "x", "y", "from_x", "from_y", "to_x", "to_y"}


@dataclass(frozen=True)
class BrowserGymAction:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        allowed = BROWSERGYM_ACTION_ARGUMENTS.get(self.name)
        if allowed is None:
            raise ValueError(f"unsupported BrowserGym action: {self.name}")
        unknown = sorted(set(self.arguments) - allowed)
        if unknown:
            raise ValueError(f"unsupported arguments for {self.name}: {', '.join(unknown)}")
        positional = _POSITIONAL_ARGUMENTS.get(self.name, ())
        missing = [name for name in positional if name not in self.arguments]
        if missing:
            raise ValueError(f"missing arguments for {self.name}: {', '.join(missing)}")
        for name, value in self.arguments.items():
            if name in _STRING_ARGUMENTS and not isinstance(value, str):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected string")
            if name in _NUMBER_ARGUMENTS and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected number")
            if name == "index" and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected integer")
            if name == "modifiers" and (
                not isinstance(value, list) or any(not isinstance(item, str) for item in value)
            ):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected string list")
            if name == "options" and not (
                isinstance(value, str) or (isinstance(value, list) and all(isinstance(item, str) for item in value))
            ):
                raise ValueError(f"invalid argument type for {self.name}.{name}: expected string or string list")
        rendered = [repr(self.arguments[name]) for name in positional]
        rendered.extend(f"{name}={self.arguments[name]!r}" for name in sorted(self.arguments) if name not in positional)
        return f"{self.name}({', '.join(rendered)})"
