"""Finite BrowserGym AX observation roles and interaction offers."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.world.interaction_capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    AdapterCapabilitySupport,
    AdapterInteractionProfile,
    CapabilityComposer,
    InteractionSubjectKind,
    PrimitiveTranslator,
)

BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID = "browsergym-ax-target-inventory.v3"

_RECOGNIZED_UNPROJECTED_TARGET_ROLES: frozenset[str] = frozenset()
_DOMAIN_CHILD_ROLES = frozenset({"option"})
_INFORMATIONAL_ROLES = frozenset(
    {
        "StaticText", "cell", "columnheader", "heading", "list", "listitem",
        "row", "rowheader", "table", "generic",
    }
)


@dataclass(frozen=True)
class RoleCapabilityOffer:
    semantic_action: str
    primitive_action: str
    currentness_fields: tuple[str, ...]
    availability_requirements: tuple[str, ...]


@dataclass(frozen=True)
class BrowserGymRoleSpec:
    role: str
    observable: bool
    offers: tuple[RoleCapabilityOffer, ...]

    def __post_init__(self) -> None:
        keys = tuple((item.semantic_action, item.primitive_action) for item in self.offers)
        if len(keys) != len(set(keys)):
            raise ValueError("BrowserGym role capability offers must be unique")
        object.__setattr__(self, "offers", tuple(self.offers))

    @property
    def executable(self) -> bool:
        return bool(self.offers)

    @property
    def currentness_fields(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            field for offer in self.offers for field in offer.currentness_fields
        ))


def _role(
    role: str,
    semantic_action: str,
    primitive_action: str,
    currentness_fields: tuple[str, ...],
    availability_requirements: tuple[str, ...],
) -> BrowserGymRoleSpec:
    return BrowserGymRoleSpec(
        role,
        True,
        (RoleCapabilityOffer(
            semantic_action,
            primitive_action,
            currentness_fields,
            availability_requirements,
        ),),
    )


_COMMON_ACTIVATION_AVAILABILITY = ("attached", "visible", "enabled")
_COMMON_EDIT_AVAILABILITY = (
    "attached", "visible", "enabled", "not_readonly", "editable",
)

_ROLE_SPECS = {
    "button": _role("button", "activate", "click", ("expanded",), _COMMON_ACTIVATION_AVAILABILITY),
    "link": _role("link", "activate", "click", ("expanded",), _COMMON_ACTIVATION_AVAILABILITY),
    "textbox": _role("textbox", "type_text", "fill", ("value", "required"), _COMMON_EDIT_AVAILABILITY),
    "searchbox": _role("searchbox", "type_text", "fill", ("value", "required"), _COMMON_EDIT_AVAILABILITY),
    "combobox": _role(
        "combobox", "select_option", "select_option",
        ("value", "expanded", "required", "selected_options"),
        _COMMON_EDIT_AVAILABILITY,
    ),
    "listbox": _role(
        "listbox", "select_option", "select_option",
        ("value", "expanded", "required", "selected_options"),
        _COMMON_EDIT_AVAILABILITY,
    ),
    "checkbox": _role("checkbox", "activate", "click", ("checked",), _COMMON_ACTIVATION_AVAILABILITY),
    "radio": _role("radio", "activate", "click", ("checked",), _COMMON_ACTIVATION_AVAILABILITY),
    "tab": _role("tab", "activate", "click", ("selected",), _COMMON_ACTIVATION_AVAILABILITY),
    "menuitem": _role("menuitem", "activate", "click", ("expanded", "checked"), _COMMON_ACTIVATION_AVAILABILITY),
    "clickable": _role("clickable", "activate", "click", (), _COMMON_ACTIVATION_AVAILABILITY),
    "slider": BrowserGymRoleSpec("slider", True, ()),
    "spinbutton": BrowserGymRoleSpec("spinbutton", True, ()),
    **{role: BrowserGymRoleSpec(role, True, ()) for role in _INFORMATIONAL_ROLES},
}


BROWSERGYM_INTERACTION_PROFILE = AdapterInteractionProfile(
    "browsergym-interactions.v1",
    "browsergym",
    "browsergym",
    (
        AdapterCapabilitySupport("activate", ("click",), (InteractionSubjectKind.ENTITY,)),
        AdapterCapabilitySupport("type_text", ("fill",), (InteractionSubjectKind.ENTITY,)),
        AdapterCapabilitySupport("select_option", ("select_option",), (InteractionSubjectKind.ENTITY,)),
    ),
)

BROWSERGYM_PRIMITIVE_TRANSLATORS = (
    PrimitiveTranslator("activate", "click"),
    PrimitiveTranslator("type_text", "fill"),
    PrimitiveTranslator("select_option", "select_option"),
)

BROWSERGYM_INTERACTION_CAPABILITIES = CapabilityComposer(
    INTERACTION_CAPABILITY_REGISTRY
).compose(BROWSERGYM_INTERACTION_PROFILE, BROWSERGYM_PRIMITIVE_TRANSLATORS)


def browsergym_role_spec(role: str) -> BrowserGymRoleSpec | None:
    return _ROLE_SPECS.get(role)


def observable_browsergym_roles() -> frozenset[str]:
    return frozenset(role for role, spec in _ROLE_SPECS.items() if spec.observable)


def executable_browsergym_roles() -> frozenset[str]:
    return frozenset(role for role, spec in _ROLE_SPECS.items() if spec.executable)


def informational_browsergym_roles() -> frozenset[str]:
    return _INFORMATIONAL_ROLES


def inventory_target_browsergym_roles() -> frozenset[str]:
    return observable_browsergym_roles() | _RECOGNIZED_UNPROJECTED_TARGET_ROLES


def diagnostic_browsergym_roles() -> frozenset[str]:
    return inventory_target_browsergym_roles() | _DOMAIN_CHILD_ROLES


def is_inventory_target_browsergym_role(role: str) -> bool:
    return role in inventory_target_browsergym_roles()


def primitive_is_compatible(role: str, primitive: str) -> bool:
    spec = browsergym_role_spec(role)
    if spec is None:
        return False
    matches = tuple(item for item in spec.offers if item.primitive_action == primitive)
    if len(matches) != 1:
        return False
    translator = BROWSERGYM_INTERACTION_CAPABILITIES.resolve_primitive(primitive)
    return translator.semantic_action == matches[0].semantic_action
