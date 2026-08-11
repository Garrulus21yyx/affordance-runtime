"""Finite BrowserGym AX role and execution profile for the pinned adapter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserGymRoleSpec:
    role: str
    observable: bool
    executable: bool
    semantic_action: str
    primitive: str
    currentness_fields: tuple[str, ...]
    required_availability: tuple[str, ...]


_ROLE_SPECS = {
    "button": BrowserGymRoleSpec(
        "button", True, True, "activate", "click", ("expanded",),
        ("attached", "visible", "enabled"),
    ),
    "link": BrowserGymRoleSpec(
        "link", True, True, "activate", "click", ("expanded",),
        ("attached", "visible", "enabled"),
    ),
    "textbox": BrowserGymRoleSpec(
        "textbox", True, True, "fill", "fill", ("value", "required"),
        ("attached", "visible", "enabled", "not_readonly", "editable"),
    ),
    "searchbox": BrowserGymRoleSpec(
        "searchbox", True, True, "fill", "fill", ("value", "required"),
        ("attached", "visible", "enabled", "not_readonly", "editable"),
    ),
    "combobox": BrowserGymRoleSpec(
        "combobox", True, True, "select", "select_option",
        ("value", "expanded", "required", "selected_options"),
        ("attached", "visible", "enabled", "not_readonly", "editable"),
    ),
    "listbox": BrowserGymRoleSpec(
        "listbox", True, True, "select", "select_option",
        ("value", "expanded", "required", "selected_options"),
        ("attached", "visible", "enabled", "not_readonly", "editable"),
    ),
}


def browsergym_role_spec(role: str) -> BrowserGymRoleSpec | None:
    return _ROLE_SPECS.get(role)


def observable_browsergym_roles() -> frozenset[str]:
    return frozenset(role for role, spec in _ROLE_SPECS.items() if spec.observable)


def executable_browsergym_roles() -> frozenset[str]:
    return frozenset(role for role, spec in _ROLE_SPECS.items() if spec.executable)


def primitive_is_compatible(role: str, primitive: str) -> bool:
    spec = browsergym_role_spec(role)
    return bool(spec and spec.executable and spec.primitive == primitive)
