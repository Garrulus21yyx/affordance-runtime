"""Finite BrowserGym AX role and execution profile for the pinned adapter."""

from __future__ import annotations

from dataclasses import dataclass

BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID = "browsergym-ax-target-inventory.v1"

_RECOGNIZED_UNPROJECTED_TARGET_ROLES = frozenset({
    "checkbox",
    "menuitem",
    "radio",
    "slider",
    "spinbutton",
    "tab",
})
_DOMAIN_CHILD_ROLES = frozenset({"option"})


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


def inventory_target_browsergym_roles() -> frozenset[str]:
    """Target-like roles recognized by the bounded BrowserGym AX inventory v1."""

    return observable_browsergym_roles() | _RECOGNIZED_UNPROJECTED_TARGET_ROLES


def diagnostic_browsergym_roles() -> frozenset[str]:
    return inventory_target_browsergym_roles() | _DOMAIN_CHILD_ROLES


def is_inventory_target_browsergym_role(role: str) -> bool:
    return role in inventory_target_browsergym_roles()


def primitive_is_compatible(role: str, primitive: str) -> bool:
    spec = browsergym_role_spec(role)
    return bool(spec and spec.executable and spec.primitive == primitive)
