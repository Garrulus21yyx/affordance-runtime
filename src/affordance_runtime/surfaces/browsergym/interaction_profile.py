"""Finite BrowserGym AX observation roles and interaction offers."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.actions.capabilities import (
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
    execution_requirements: tuple[str, ...]


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


def _offer(
    semantic_action: str,
    primitive_action: str,
    currentness_fields: tuple[str, ...],
) -> RoleCapabilityOffer:
    return RoleCapabilityOffer(
        semantic_action,
        primitive_action,
        currentness_fields,
        _PRIMITIVE_EXECUTION_REQUIREMENTS[primitive_action],
    )


def _role(
    role: str,
    *offers: RoleCapabilityOffer,
) -> BrowserGymRoleSpec:
    return BrowserGymRoleSpec(role, True, offers)


_COMMON_ACTIVATION_AVAILABILITY = ("attached", "visible", "enabled")
_COMMON_EDIT_AVAILABILITY = (
    "attached", "visible", "enabled", "not_readonly", "editable",
)
_PRIMITIVE_EXECUTION_REQUIREMENTS = {
    "click": _COMMON_ACTIVATION_AVAILABILITY,
    "fill": _COMMON_EDIT_AVAILABILITY,
    # BrowserGym's select_option route is a closed adapter composite over an
    # attached native <select>: the current option domain fixes the physical
    # route, Playwright performs the internal interaction, and the binding's
    # observation barrier requests one fresh World afterward.  No intermediate
    # semantic choice or generic navigation macro is involved.
    "select_option": ("attached", "enabled", "not_readonly"),
    "drag_and_drop": _COMMON_ACTIVATION_AVAILABILITY,
    "press": ("attached", "visible", "enabled", "focusable"),
    "scroll": (),
    "keyboard_press": (),
    "keyboard_hotkey": (),
    "goto": (),
    "go_back": (),
    "go_forward": (),
    "new_tab": (),
    "tab_focus": (),
    "tab_close": (),
}

BROWSERGYM_BROWSER_GLOBAL_PRIMITIVES = (
    "goto",
    "go_back",
    "go_forward",
    "new_tab",
    "tab_focus",
    "tab_close",
)

_ROLE_SPECS = {
    "button": _role(
        "button",
        _offer("activate", "click", ("expanded",)),
        _offer("press_key", "press", ()),
    ),
    "link": _role(
        "link",
        _offer("activate", "click", ("expanded",)),
        _offer("press_key", "press", ()),
    ),
    "textbox": _role(
        "textbox",
        _offer("type_text", "fill", ("value", "required")),
        _offer("press_key", "press", ()),
    ),
    "searchbox": _role(
        "searchbox",
        _offer("type_text", "fill", ("value", "required")),
        _offer("press_key", "press", ()),
    ),
    "combobox": _role(
        "combobox",
        _offer("select_option", "select_option", ("value", "expanded", "required", "selected_options")),
        _offer("press_key", "press", ()),
    ),
    "listbox": _role(
        "listbox",
        _offer("select_option", "select_option", ("value", "expanded", "required", "selected_options")),
        _offer("press_key", "press", ()),
    ),
    "checkbox": _role(
        "checkbox",
        _offer("activate", "click", ("checked",)),
        _offer("press_key", "press", ()),
    ),
    "radio": _role(
        "radio",
        _offer("activate", "click", ("checked",)),
        _offer("press_key", "press", ()),
    ),
    "tab": _role(
        "tab",
        _offer("activate", "click", ("selected",)),
        _offer("press_key", "press", ()),
    ),
    "menuitem": _role(
        "menuitem",
        _offer("activate", "click", ("expanded", "checked")),
        _offer("press_key", "press", ()),
    ),
    "clickable": _role(
        "clickable",
        _offer("activate", "click", ()),
        _offer("press_key", "press", ()),
    ),
    "draggable": _role(
        "draggable",
        _offer("drag_to", "drag_and_drop", ()),
    ),
    "drop_target": BrowserGymRoleSpec("drop_target", True, ()),
    "slider": _role(
        "slider",
        _offer("press_key", "press", ("value",)),
    ),
    "spinbutton": _role(
        "spinbutton",
        _offer("press_key", "press", ("value",)),
    ),
    **{role: BrowserGymRoleSpec(role, True, ()) for role in _INFORMATIONAL_ROLES},
}


BROWSERGYM_INTERACTION_PROFILE = AdapterInteractionProfile(
    "browsergym-interactions.v2",
    "browsergym",
    "browsergym",
    (
        AdapterCapabilitySupport("activate", ("click",), (InteractionSubjectKind.ENTITY,)),
        AdapterCapabilitySupport("type_text", ("fill",), (InteractionSubjectKind.ENTITY,)),
        AdapterCapabilitySupport("select_option", ("select_option",), (InteractionSubjectKind.ENTITY,)),
        AdapterCapabilitySupport("drag_to", ("drag_and_drop",), (InteractionSubjectKind.ENTITY,)),
        AdapterCapabilitySupport("scroll", ("scroll",), (InteractionSubjectKind.VIEWPORT,)),
        AdapterCapabilitySupport(
            "press_key",
            ("press", "keyboard_press"),
            (InteractionSubjectKind.ENTITY, InteractionSubjectKind.FOCUSED_CONTEXT),
        ),
        AdapterCapabilitySupport(
            "hotkey",
            ("keyboard_hotkey",),
            (InteractionSubjectKind.FOCUSED_CONTEXT,),
        ),
        *(
            AdapterCapabilitySupport(
                primitive,
                (primitive,),
                (InteractionSubjectKind.BROWSER_CONTEXT,),
            )
            for primitive in BROWSERGYM_BROWSER_GLOBAL_PRIMITIVES
        ),
    ),
)

BROWSERGYM_PRIMITIVE_TRANSLATORS = (
    PrimitiveTranslator("activate", "click"),
    PrimitiveTranslator("type_text", "fill"),
    PrimitiveTranslator("select_option", "select_option"),
    PrimitiveTranslator("drag_to", "drag_and_drop"),
    PrimitiveTranslator("scroll", "scroll"),
    PrimitiveTranslator("press_key", "press"),
    PrimitiveTranslator("press_key", "keyboard_press"),
    PrimitiveTranslator("hotkey", "keyboard_hotkey"),
    *(PrimitiveTranslator(primitive, primitive) for primitive in BROWSERGYM_BROWSER_GLOBAL_PRIMITIVES),
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
