"""DOM to Page Affordance Model adapter.

Migrated and simplified from A-Modular-Action-System-Architecture's
`DomTransducer`: raw HTML becomes compact, typed, lease-bound affordances.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from typing import Any

from affordance_runtime.actions.contracts import Affordance, AffordanceLease, RiskLevel, Surface
from affordance_runtime.immutable import FrozenSequence


def _authored_risk(attributes: dict[str, str]) -> RiskLevel:
    """Accept only an explicit typed source declaration; labels grant no risk semantics."""

    raw = attributes.get("data-runtime-risk", "").strip().casefold()
    try:
        return RiskLevel(raw) if raw else RiskLevel.LOW
    except ValueError:
        return RiskLevel.IRREVERSIBLE

_INTERACTIVE_TAGS = frozenset(["a", "button", "input", "select", "textarea", "label", "form", "option"])
_STRIP_TAGS = frozenset(["script", "style", "meta", "link", "noscript", "head", "svg"])
_VOID_STRIP_TAGS = frozenset(["meta", "link"])
_VOID_TAGS = frozenset(["area", "base", "br", "col", "embed", "hr", "img", "input", "source", "track", "wbr"])
_ARIA_ACTION_MAP = {
    "button": "click",
    "link": "click",
    "tab": "click",
    "textbox": "type",
    "combobox": "select",
    "checkbox": "click",
    "radio": "click",
}
_TAG_ACTION = {"button": "click", "a": "click", "select": "select", "textarea": "type"}
_INPUT_TYPE_ACTION = {
    "text": "type",
    "number": "type",
    "email": "type",
    "password": "type",
    "search": "type",
    "checkbox": "click",
    "radio": "click",
    "submit": "click",
    "button": "click",
}
_SELECTOR_CONFIDENCE = {
    "id": 1.0,
    "backend_handle": 0.99,
    "testid": 0.97,
    "name": 0.85,
    "class": 0.7,
    "positional": 0.55,
}
_CONTEXT_CONTAINER_TAGS = frozenset(["article", "dd", "div", "li", "section", "td", "tr"])
_DRAG_HANDLE_CLASSES = frozenset(["ui-draggable-handle", "ui-sortable-handle"])
_DESCRIPTIVE_PROXY_TAGS = frozenset(["form", "label"])
_LABELABLE_TAGS = frozenset(["input", "select", "textarea"])
_LABEL_CONTAINER_TAGS = frozenset(["div", "fieldset", "form", "li", "p", "section", "td"])


@dataclass(frozen=True)
class AuthoredInteractiveExtension:
    """Opt-in normalization contract for non-standard authored controls."""

    marker_attribute: str
    backend_handle_attribute: str
    marker_value: str = "1"
    visibility_ratio_attribute: str = ""
    semantic_patterns: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.marker_attribute or not self.backend_handle_attribute:
            raise ValueError("authored interactive extension fields must be non-empty")
        attribute_name = re.compile(r"^[A-Za-z_:][A-Za-z0-9_.:-]*$")
        if not all(
            attribute_name.fullmatch(value)
            for value in (self.marker_attribute, self.backend_handle_attribute)
        ):
            raise ValueError("authored interactive extension attributes must be valid HTML names")
        if self.visibility_ratio_attribute and not attribute_name.fullmatch(
            self.visibility_ratio_attribute
        ):
            raise ValueError("authored visibility attribute must be a valid HTML name")
        supported_patterns = {
            "calendar_range",
            "quantity_control",
            "owner_collection",
            "color_target",
        }
        if not self.semantic_patterns.issubset(supported_patterns):
            raise ValueError("authored interactive extension contains an unknown semantic pattern")


def _drag_capable(attr: dict[str, str]) -> bool:
    classes = set(attr.get("class", "").split())
    return (
        attr.get("draggable", "").lower() == "true"
        or attr.get("aria-grabbed", "").lower() in {"true", "false"}
        or bool(classes.intersection(_DRAG_HANDLE_CLASSES))
    )


def _style_hides(attr: dict[str, str]) -> bool:
    style = "".join(attr.get("style", "").casefold().split())
    return "display:none" in style or "visibility:hidden" in style


def _class_hides(attr: dict[str, str]) -> bool:
    """Honor explicit authored hide-state classes, including off viewport."""

    return bool(set(attr.get("class", "").casefold().split()).intersection({"hide", "hidden"}))


def _extension_hides(
    attr: dict[str, str],
    extension: AuthoredInteractiveExtension | None,
) -> bool:
    """Honor an opt-in rendered visibility annotation when present."""

    if extension is None or not extension.visibility_ratio_attribute:
        return False
    raw = attr.get(extension.visibility_ratio_attribute, "")
    if not raw:
        return False
    try:
        return float(raw) <= 0.0
    except ValueError:
        return False


def _calendar_slot_index(attr: dict[str, str], ancestors: list[dict[str, Any]]) -> int | None:
    """Return an authored half-hour slot only when its calendar structure is coherent."""

    classes = set(attr.get("class", "").split())
    match = re.fullmatch(r"hh-(\d+)", attr.get("id", ""))
    if "half-hour" not in classes or match is None:
        return None
    calendar_parent = next(
        (
            ancestor
            for ancestor in reversed(ancestors)
            if "calendar" in set(ancestor["attr"].get("class", "").split())
        ),
        None,
    )
    hour_parent = next(
        (ancestor for ancestor in reversed(ancestors) if "data-hour" in ancestor["attr"]),
        None,
    )
    if calendar_parent is None or hour_parent is None:
        return None
    try:
        slot_index = int(match.group(1))
        hour_index = int(hour_parent["attr"]["data-hour"])
    except ValueError:
        return None
    if not 0 <= slot_index < 48 or not 0 <= hour_index < 24 or slot_index // 2 != hour_index:
        return None
    return slot_index


def _calendar_slot_label(slot_index: int) -> str:
    minutes = slot_index * 30
    hour_24, minute = divmod(minutes, 60)
    meridiem = "am" if hour_24 < 12 else "pm"
    hour_12 = hour_24 % 12 or 12
    return f"{hour_12}:{minute:02d}{meridiem} calendar slot"


def _collection_action_context(
    tag: str,
    attr: dict[str, str],
    ancestors: list[dict[str, Any]],
    extension: AuthoredInteractiveExtension | None,
) -> dict[str, Any] | None:
    """Recognize one authored action inside an owner-labelled collection item.

    A coherent item/action-group structure and an opted-in backend handle are
    required; arbitrary classes do not become executable controls.
    """

    handle_attribute = extension.backend_handle_attribute if extension is not None else ""
    if tag not in {"span", "li"} or not handle_attribute or not attr.get(handle_attribute):
        return None
    action_tokens = [
        token for token in attr.get("class", "").split() if token not in {"active", "hide"}
    ]
    if len(action_tokens) != 1:
        return None
    controls_index = next(
        (
            index
            for index in range(len(ancestors) - 1, -1, -1)
            if "controls" in ancestors[index]["attr"].get("class", "").split()
        ),
        None,
    )
    item_index = next(
        (
            index
            for index in range(len(ancestors) - 1, -1, -1)
            if "data-result" in ancestors[index]["attr"]
        ),
        None,
    )
    if controls_index is None or item_index is None or item_index >= controls_index:
        return None
    item = ancestors[item_index]
    owners = list(
        dict.fromkeys(
            re.findall(
                r"@[A-Za-z0-9_.-]+",
                " ".join(str(part) for part in item.get("text_parts", ())),
            )
        )
    )
    if len(owners) != 1:
        return None
    try:
        position = int(item["attr"]["data-result"]) + 1
    except (TypeError, ValueError):
        return None
    if position <= 0:
        return None
    return {
        "collection_action_key": action_tokens[0],
        "collection_owner": owners[0],
        "collection_position": position,
        "toggle_selected": "active" in attr.get("class", "").split(),
    }


class _InteractiveParser(HTMLParser):
    def __init__(
        self,
        *,
        allow_offscreen: bool = False,
        extension: AuthoredInteractiveExtension | None = None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._allow_offscreen = allow_offscreen
        self._extension = extension
        self._skip_depth: int | None = None
        self._depth = 0
        self._tag_counts: dict[str, int] = {}
        self._open: list[dict[str, Any]] = []
        self._tree_open: list[dict[str, Any]] = []
        self.total_nodes = 0
        self.nodes: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth += 1
        self.total_nodes += 1
        if self._skip_depth is None and tag in _STRIP_TAGS:
            if tag in _VOID_STRIP_TAGS:
                self._depth = max(0, self._depth - 1)
                return
            self._skip_depth = self._depth
            return
        if self._skip_depth is not None:
            if tag in _VOID_STRIP_TAGS:
                self._depth = max(0, self._depth - 1)
            return

        attr = {key: (value or "") for key, value in attrs}
        tree_node: dict[str, Any] = {
            "tag": tag,
            "attr": attr,
            "text_parts": [],
            "semantic_types": [],
        }
        parent_tree = self._tree_open[-1] if self._tree_open else None
        if parent_tree is not None:
            tree_node["parent"] = parent_tree
        if tag not in _VOID_TAGS:
            self._tree_open.append(tree_node)
        ancestors = self._tree_open[:-1] if tag not in _VOID_TAGS else self._tree_open
        authored_type = (attr.get("alt") or attr.get("title") or "").strip()
        if tag == "img" and authored_type:
            for ancestor in ancestors:
                if ancestor["attr"].get("data-item"):
                    semantic_types = ancestor["semantic_types"]
                    if authored_type not in semantic_types:
                        semantic_types.append(authored_type)
        role = attr.get("role", "")
        self_hidden = (
            "hidden" in attr
            or attr.get("aria-hidden") == "true"
            or _style_hides(attr)
            or _class_hides(attr)
        )
        ancestor_hidden = any(
            "hidden" in ancestor["attr"]
            or ancestor["attr"].get("aria-hidden") == "true"
            or _style_hides(ancestor["attr"])
            or _class_hides(ancestor["attr"])
            for ancestor in ancestors
        )
        viewport_hidden = _extension_hides(attr, self._extension) or any(
            _extension_hides(ancestor["attr"], self._extension) for ancestor in ancestors
        )
        # An opted-in custom-rendered dropdown may retain a hidden native select
        # as its authoritative semantic value/control.
        if ancestor_hidden or (self_hidden and tag != "select"):
            return
        if viewport_hidden and not self._allow_offscreen and tag != "select":
            return
        focusable = attr.get("tabindex", "") not in {"", "-1"}
        programmatic_option = attr.get("tabindex") == "-1" and any(
            ancestor["tag"] in {"ul", "ol"} or ancestor["attr"].get("role") in {"listbox", "menu"}
            for ancestor in ancestors
        )
        authored_actionable = bool(
            self._extension is not None
            and attr.get(self._extension.marker_attribute) == self._extension.marker_value
            # Rendered-mark systems can annotate descriptive proxies as well
            # as controls. Native label/form semantics need independent
            # interaction evidence before they become executable targets.
            and tag not in _DESCRIPTIVE_PROXY_TAGS
        )
        drag_capable = _drag_capable(attr)
        semantic_color_target = bool(
            self._extension is not None
            and "color_target" in self._extension.semantic_patterns
            and attr.get("data-color")
        )
        calendar_slot_index = (
            _calendar_slot_index(attr, ancestors)
            if self._extension is not None
            and "calendar_range" in self._extension.semantic_patterns
            else None
        )
        semantic_calendar_slot = calendar_slot_index is not None
        quantity_ancestor = next(
            (
                ancestor
                for ancestor in reversed(ancestors)
                if ancestor["attr"].get("data-item")
                and "data-quantity" in ancestor["attr"]
            ),
            None,
        )
        quantity_classes = set(attr.get("class", "").split()).intersection({"add", "remove"})
        semantic_quantity_control = bool(
            self._extension is not None
            and "quantity_control" in self._extension.semantic_patterns
            and quantity_ancestor is not None
            and len(quantity_classes) == 1
        )
        collection_action_context = (
            _collection_action_context(tag, attr, ancestors, self._extension)
            if self._extension is not None
            and "owner_collection" in self._extension.semantic_patterns
            else None
        )
        semantic_collection_action = collection_action_context is not None
        if (
            tag not in _INTERACTIVE_TAGS
            and role not in _ARIA_ACTION_MAP
            and not focusable
            and not programmatic_option
            and not authored_actionable
            and not drag_capable
            and not semantic_color_target
            and not semantic_quantity_control
            and not semantic_calendar_slot
            and not semantic_collection_action
        ):
            return

        self._tag_counts[tag] = self._tag_counts.get(tag, 0) + 1
        parent = self._open[-1] if self._open else None
        node: dict[str, Any] = {
            "tag": tag,
            "attr": attr,
            "nth": self._tag_counts[tag],
            "text_parts": [],
            "parent_tag": parent["tag"] if parent else "",
            "parent_attr": dict(parent["attr"]) if parent else {},
            "parent_node": parent,
            "context_ancestors": tuple(reversed(self._tree_open[:-1] if tag not in _VOID_TAGS else self._tree_open)),
            "programmatic_option": programmatic_option,
            "authored_actionable": authored_actionable,
            "semantic_quantity_control": semantic_quantity_control,
            "semantic_calendar_slot": semantic_calendar_slot,
            "semantic_collection_action": semantic_collection_action,
        }
        if calendar_slot_index is not None:
            node["calendar_slot_index"] = calendar_slot_index
        if semantic_quantity_control and quantity_ancestor is not None:
            quantity_class = next(iter(quantity_classes))
            try:
                current_quantity = int(quantity_ancestor["attr"].get("data-quantity", "0"))
            except ValueError:
                current_quantity = 0
            node.update(
                {
                    "quantity_item_name": quantity_ancestor["attr"]["data-item"].strip(),
                    "quantity_current": max(0, current_quantity),
                    "quantity_delta": 1 if quantity_class == "add" else -1,
                    "quantity_item_types": tuple(quantity_ancestor["semantic_types"]),
                }
            )
        if collection_action_context is not None:
            node.update(collection_action_context)
        self.nodes.append(node)
        if tag not in _VOID_TAGS:
            self._open.append(node)

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth is not None and self._depth == self._skip_depth:
            self._skip_depth = None
        if self._open and self._open[-1]["tag"] == tag:
            self._open.pop()
        if self._tree_open and self._tree_open[-1]["tag"] == tag:
            self._tree_open.pop()
        self._depth = max(0, self._depth - 1)

    def handle_data(self, data: str) -> None:
        if self._skip_depth is None:
            text = data.strip()
            if text:
                if self._open:
                    self._open[-1]["text_parts"].append(text)
                for ancestor in self._tree_open:
                    ancestor["text_parts"].append(text)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_STRIP_TAGS:
            self.handle_endtag(tag)


@dataclass(frozen=True)
class PageAffordanceModel:
    page_id: str
    url: str
    environment_revision: str
    snapshot_id: str
    page_revision: str
    affordances: list[Affordance]
    raw_node_count: int
    kept_node_count: int
    acquisition_adapter_id: str = ""
    acquisition_exhaustive: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "affordances", FrozenSequence(self.affordances))


def _escape_attr(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _selector_for(
    node: dict[str, Any],
    extension: AuthoredInteractiveExtension | None,
) -> tuple[str, float]:
    attr, tag = node["attr"], node["tag"]
    if attr.get("id"):
        return f"#{attr['id']}", _SELECTOR_CONFIDENCE["id"]
    handle_attribute = extension.backend_handle_attribute if extension is not None else ""
    if handle_attribute and attr.get(handle_attribute):
        return (
            f"[{handle_attribute}='{_escape_attr(attr[handle_attribute])}']",
            _SELECTOR_CONFIDENCE["backend_handle"],
        )
    if attr.get("data-testid"):
        return f"[data-testid='{_escape_attr(attr['data-testid'])}']", _SELECTOR_CONFIDENCE["testid"]
    if attr.get("name"):
        return f"{tag}[name='{_escape_attr(attr['name'])}']", _SELECTOR_CONFIDENCE["name"]
    if attr.get("class"):
        return f"{tag}.{attr['class'].split()[0]}", _SELECTOR_CONFIDENCE["class"]
    return f"{tag}:nth-of-type({node['nth']})", _SELECTOR_CONFIDENCE["positional"]


def _label_for(node: dict[str, Any]) -> str:
    attr = node["attr"]
    if node.get("semantic_calendar_slot"):
        return _calendar_slot_label(int(node["calendar_slot_index"]))
    if node.get("semantic_quantity_control"):
        direction = "increase" if node.get("quantity_delta") == 1 else "decrease"
        return f"{direction} {node.get('quantity_item_name', 'item')} quantity"
    if node.get("semantic_collection_action"):
        text = " ".join(node["text_parts"]).strip()
        if text:
            return text
        return str(node["collection_action_key"]).replace("-", " ").replace("_", " ").title()
    parent = node.get("parent_node")
    if (
        node["tag"] == "input"
        and attr.get("type", "").lower() in {"checkbox", "radio"}
        and isinstance(parent, dict)
        and parent.get("tag") == "label"
    ):
        parent_text = " ".join(parent.get("text_parts", [])).strip()
        if parent_text:
            return parent_text
    for key in ("aria-label", "placeholder", "title", "alt", "data-color"):
        if attr.get(key):
            return attr[key].strip()
    if node.get("associated_label"):
        return str(node["associated_label"]).strip()
    if node["tag"] == "option" and attr.get("value"):
        return attr["value"].strip()
    if node["tag"] == "input" and attr.get("type", "text").lower() in {"submit", "button"} and attr.get("value"):
        return attr["value"].strip()
    text = " ".join(node["text_parts"]).strip()
    if text:
        return text
    for key in ("name", "id"):
        if attr.get(key):
            return attr[key].strip()
    if node["tag"] == "input" and attr.get("value"):
        return attr["value"].strip()
    if attr.get("class"):
        return attr["class"].split()[0]
    return node["tag"]


def _action_for(node: dict[str, Any]) -> str:
    attr, tag = node["attr"], node["tag"]
    if node.get("semantic_calendar_slot"):
        return "drag"
    role = attr.get("role", "")
    if role in _ARIA_ACTION_MAP:
        return _ARIA_ACTION_MAP[role]
    if tag == "a" and "download" in attr:
        return "download"
    if tag == "input":
        if "readonly" in attr:
            # Readonly text-like controls commonly own a picker/popover. They
            # are activatable but cannot satisfy a fill contract.
            return "click"
        return _INPUT_TYPE_ACTION.get(attr.get("type", "text").lower(), "type")
    if node.get("programmatic_option"):
        return "click"
    if _drag_capable(attr):
        return "drag"
    native_action = _TAG_ACTION.get(tag)
    if native_action is not None:
        return native_action
    if node.get("authored_actionable"):
        return "click"
    if attr.get("tabindex", "") not in {"", "-1"}:
        return "press"
    return "click"


def _nearby_context_text(node: dict[str, Any]) -> str:
    """Return concise visible ancestor text without making it planner authority."""

    for ancestor in node.get("context_ancestors", ()):  # nearest ancestor first
        if ancestor.get("tag") not in _CONTEXT_CONTAINER_TAGS:
            continue
        text = " ".join(ancestor["text_parts"]).strip()
        if text and text != _label_for(node):
            return text[:160]
    return ""


def _group_context_text(node: dict[str, Any], container_context: str) -> str:
    """Return the next distinct bounded ancestor for relational item binding."""

    for ancestor in node.get("context_ancestors", ()):
        if ancestor.get("tag") not in _CONTEXT_CONTAINER_TAGS:
            continue
        text = " ".join(ancestor["text_parts"]).strip()
        if text and text != _label_for(node) and text != container_context:
            return text[:240]
    return ""


def _semantic_scope(node: dict[str, Any]) -> tuple[str, str]:
    """Return the nearest explicitly named public structural container."""

    for ancestor in node.get("context_ancestors", ()):
        if ancestor.get("tag") not in _CONTEXT_CONTAINER_TAGS:
            continue
        attributes = ancestor.get("attr", {})
        label = str(attributes.get("aria-label") or "").strip()
        if label:
            return str(attributes.get("role") or ancestor.get("tag") or "group"), label[:160]
    return "", ""


def _annotate_pagination_nodes(nodes: list[dict[str, Any]]) -> None:
    """Attach structural pagination facts without interpreting task intent."""

    groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if node.get("tag") != "a":
            continue
        ancestors = tuple(node.get("context_ancestors", ()))
        pagination = next(
            (
                ancestor
                for ancestor in ancestors
                if ancestor.get("tag") in {"ul", "ol"}
                and "pagination" in str(ancestor.get("attr", {}).get("class", "")).split()
            ),
            None,
        )
        if pagination is None:
            continue
        owner = str(pagination.get("attr", {}).get("id") or "").strip()
        if not owner:
            continue
        item = next(
            (ancestor for ancestor in ancestors if ancestor.get("tag") == "li"),
            None,
        )
        classes = set(str((item or {}).get("attr", {}).get("class", "")).split())
        label = _label_for(node).strip()
        relation = (
            "next"
            if "next" in classes
            else "previous"
            if "prev" in classes or "previous" in classes
            else "page"
            if label.isdigit()
            else ""
        )
        if not relation:
            continue
        node["pagination_owner"] = owner
        node["pagination_relation"] = relation
        node["pagination_current"] = "active" in classes
        if relation == "page":
            node["pagination_page"] = int(label)
        groups.setdefault(owner, []).append(node)

    for group in groups.values():
        pages = [int(node["pagination_page"]) for node in group if "pagination_page" in node]
        if not pages:
            continue
        total_pages = max(pages)
        for node in group:
            node["pagination_total_pages"] = total_pages


def _collection_position(
    attr: dict[str, str],
    ancestors: tuple[dict[str, Any], ...] = (),
) -> int | None:
    """Normalize common DOM collection indices into a one-based position."""

    raw: str | None = None
    zero_based = False
    for candidate in (attr, *(item["attr"] for item in reversed(ancestors))):
        raw = candidate.get("aria-posinset")
        zero_based = False
        if raw is None:
            for key in ("data-index", "data-result"):
                if key in candidate:
                    raw = candidate[key]
                    zero_based = True
                    break
        if raw is not None:
            break
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    value = value + 1 if zero_based else value
    return value if value > 0 else None


def _has_independent_action_semantics(node: dict[str, Any]) -> bool:
    """Require more than a rendered marker for native descriptive proxies."""

    attr = node["attr"]
    return bool(
        attr.get("role", "") in _ARIA_ACTION_MAP
        or attr.get("tabindex", "") not in {"", "-1"}
        or "onclick" in attr
        or _drag_capable(attr)
        or node.get("semantic_quantity_control")
        or node.get("semantic_calendar_slot")
        or node.get("semantic_collection_action")
    )


def _label_container(node: dict[str, Any]) -> object | None:
    return next(
        (
            ancestor
            for ancestor in node.get("context_ancestors", ())
            if ancestor.get("tag") in _LABEL_CONTAINER_TAGS
        ),
        None,
    )


def _associate_control_labels(nodes: list[dict[str, Any]]) -> None:
    """Attach only unambiguous explicit, nested, or adjacent native labels."""

    controls_by_id = {
        node["attr"]["id"]: node
        for node in nodes
        if node["tag"] in _LABELABLE_TAGS and node["attr"].get("id")
    }
    for index, label_node in enumerate(nodes):
        if label_node["tag"] != "label":
            continue
        label = " ".join(label_node.get("text_parts", ())).strip()
        if not label:
            continue
        explicit_target = controls_by_id.get(label_node["attr"].get("for", ""))
        nested_target = next(
            (
                node
                for node in nodes
                if node["tag"] in _LABELABLE_TAGS and node.get("parent_node") is label_node
            ),
            None,
        )
        target = explicit_target or nested_target
        if target is None:
            container = _label_container(label_node)
            for candidate in nodes[index + 1 :]:
                if candidate["tag"] == "label" and _label_container(candidate) is container:
                    break
                if candidate["tag"] in _LABELABLE_TAGS and _label_container(candidate) is container:
                    target = candidate
                    break
        if target is not None and not any(
            target["attr"].get(key) for key in ("aria-label", "placeholder", "title")
        ):
            target["associated_label"] = label


@dataclass(frozen=True)
class DomAdapter:
    extension: AuthoredInteractiveExtension | None = None

    def transduce(
        self,
        html: str,
        *,
        environment_revision: str,
        page_id: str = "page",
        url: str = "",
        ttl_ms: int = 2_000,
        snapshot_id: str = "",
        page_revision: str = "",
        allow_offscreen: bool = False,
    ) -> PageAffordanceModel:
        parser = _InteractiveParser(
            allow_offscreen=allow_offscreen,
            extension=self.extension,
        )
        parser.feed(html or "")
        parser.close()
        _associate_control_labels(parser.nodes)
        _annotate_pagination_nodes(parser.nodes)
        nested_control_label_nodes = {
            id(parent)
            for node in parser.nodes
            if isinstance((parent := node.get("parent_node")), dict) and parent.get("tag") == "label"
        }
        control_ids = {
            node["attr"].get("id", "") for node in parser.nodes if node["tag"] in {"input", "select", "textarea"}
        }
        handle_attribute = self.extension.backend_handle_attribute if self.extension is not None else ""
        menu_owner_handles = {
            ancestor["attr"].get(handle_attribute, "")
            for node in parser.nodes
            if node.get("programmatic_option")
            for ancestor in node.get("context_ancestors", ())
            if handle_attribute and ancestor["tag"] in {"ul", "ol"}
        }
        planner_nodes = [
            node
            for node in parser.nodes
            if not (
                node["tag"] in _DESCRIPTIVE_PROXY_TAGS
                and not _has_independent_action_semantics(node)
            )
            and not (
                node["tag"] == "label"
                and (id(node) in nested_control_label_nodes or node["attr"].get("for", "") in control_ids)
            )
            and not (
                handle_attribute
                and node["attr"].get(handle_attribute, "") in menu_owner_handles
                and _action_for(node) == "press"
            )
        ]
        semantic_nodes = [
            {
                "tag": node["tag"],
                "role": node["attr"].get("role", ""),
                "id": node["attr"].get("id", ""),
                "backend_handle": node["attr"].get(handle_attribute, "") if handle_attribute else "",
                "name": node["attr"].get("name", ""),
                "disabled": "disabled" in node["attr"] or node["attr"].get("aria-disabled") == "true",
                "label": _label_for(node),
                "quantity_current": node.get("quantity_current"),
                "calendar_slot_index": node.get("calendar_slot_index"),
                "collection_action": (
                    _label_for(node) if node.get("semantic_collection_action") else None
                ),
                "collection_owner": node.get("collection_owner"),
                "toggle_selected": node.get("toggle_selected"),
                "aria_expanded": node["attr"].get("aria-expanded", ""),
                "aria_controls": node["attr"].get("aria-controls", ""),
                "pagination_owner": node.get("pagination_owner"),
                "pagination_relation": node.get("pagination_relation"),
                "pagination_page": node.get("pagination_page"),
                "pagination_current": node.get("pagination_current"),
                "pagination_total_pages": node.get("pagination_total_pages"),
            }
            for node in planner_nodes
        ]
        effective_page_revision = (
            page_revision
            or "page:sha256:"
            + hashlib.sha256(
                json.dumps({"url": url, "nodes": semantic_nodes}, sort_keys=True).encode("utf-8")
            ).hexdigest()
        )
        affordances: list[Affordance] = []
        for node in planner_nodes:
            attr = node["attr"]
            action = _action_for(node)
            selector, confidence = _selector_for(node, self.extension)
            disabled = "disabled" in attr or attr.get("aria-disabled") == "true"
            # Container context disambiguates repeated/custom items, but must
            # not make stable native form-control identity depend on mutable
            # sibling content elsewhere in the form or page.
            context_text = (
                _nearby_context_text(node)
                if node["tag"] == "a" or node["tag"] not in _INTERACTIVE_TAGS or action in {"drag", "press"}
                else ""
            )
            collection_position = node.get("collection_position") or _collection_position(
                attr,
                tuple(node.get("context_ancestors", ())),
            )
            group_context = _group_context_text(node, context_text) if context_text else ""
            semantic_scope_role, semantic_scope_label = _semantic_scope(node)
            affordance_id = f"dom_{node['tag']}_{node['nth']}"
            target_fingerprint = (
                "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        {
                            "id": affordance_id,
                            "role": attr.get("role") or node["tag"],
                            "label": _label_for(node),
                            "selector": selector,
                            "enabled": not disabled,
                            "quantity_current": node.get("quantity_current"),
                            "calendar_slot_index": node.get("calendar_slot_index"),
                            "collection_action": (
                                _label_for(node) if node.get("semantic_collection_action") else None
                            ),
                            "collection_owner": node.get("collection_owner"),
                            "toggle_selected": node.get("toggle_selected"),
                        },
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
            )
            lease = AffordanceLease.issue(
                environment_revision=environment_revision,
                ttl_ms=ttl_ms,
                provenance=["dom"],
                snapshot_id=snapshot_id,
                page_revision=effective_page_revision,
                target_fingerprint=target_fingerprint,
            )
            affordances.append(
                Affordance(
                    id=affordance_id,
                    surface=Surface.DOM,
                    role=(
                        "option"
                        if node["tag"] == "option" or node.get("programmatic_option")
                        else "checkbox"
                        if node["tag"] == "input" and attr.get("type", "").lower() == "checkbox"
                        else "radio"
                        if node["tag"] == "input" and attr.get("type", "").lower() == "radio"
                        else "picker"
                        if node["tag"] == "input" and "readonly" in attr
                        else "textbox"
                        if action == "type"
                        else "combobox"
                        if action == "select"
                        else "slider"
                        if action == "press" and "slider" in attr.get("class", "").lower()
                        else "link"
                        if node["tag"] == "a" or attr.get("role") == "link"
                        else "time_slot"
                        if node.get("semantic_calendar_slot")
                        else "button"
                    ),
                    label=_label_for(node),
                    action=action,
                    locator={
                        "selector": selector,
                        "strategy": "css",
                        **(
                            {"backend_handle": attr[handle_attribute]}
                            if self.extension is not None
                            and handle_attribute
                            and attr.get(handle_attribute)
                            else {}
                        ),
                        **(
                            {
                                "select_owner_backend_handle": node["parent_attr"][handle_attribute],
                                "select_option": attr.get("value") or _label_for(node),
                            }
                            if node["tag"] == "option"
                            and node["parent_tag"] == "select"
                            and self.extension is not None
                            and handle_attribute
                            and node["parent_attr"].get(handle_attribute)
                            else {}
                        ),
                    },
                    lease=lease,
                    backend_candidates=["dom"],
                    confidence=0.0 if disabled else confidence,
                    state={
                        "enabled": not disabled,
                        "visible": True,
                        "element_tag": node["tag"],
                        **({"input_type": attr.get("type", "text").lower()} if node["tag"] == "input" else {}),
                        **({"label_source": "native_label"} if node.get("associated_label") else {}),
                        **({"readonly": True} if node["tag"] == "input" and "readonly" in attr else {}),
                        **(
                            {"control_value": attr["value"]}
                            if node["tag"] == "input"
                            and attr.get("type", "text").lower() != "password"
                            and "value" in attr
                            else {}
                        ),
                        **(
                            {"autocomplete": True}
                            if node["tag"] == "input"
                            and (
                                "autocomplete" in attr.get("class", "").lower()
                                or attr.get("aria-autocomplete", "") in {"inline", "list", "both"}
                            )
                            else {}
                        ),
                        **({"multiple": True} if node["tag"] == "select" and "multiple" in attr else {}),
                        **(
                            {"programmatic_select": True, "rendered_visible": False}
                            if node["tag"] == "select" and _extension_hides(attr, self.extension)
                            else {}
                        ),
                        **({"programmatic_option": True} if node.get("programmatic_option") else {}),
                        **({"context_text": context_text} if action == "press" and context_text else {}),
                        **({"container_context": context_text} if context_text else {}),
                        **({"group_context": group_context} if group_context else {}),
                        **(
                            {
                                "semantic_scope_role": semantic_scope_role,
                                "semantic_scope_label": semantic_scope_label,
                            }
                            if semantic_scope_label
                            else {}
                        ),
                        **(
                            {
                                "disclosure": True,
                                "expanded": attr["aria-expanded"] == "true",
                                "aria_expanded": attr["aria-expanded"],
                                **(
                                    {"aria_controls": attr["aria-controls"]}
                                    if attr.get("aria-controls")
                                    else {}
                                ),
                            }
                            if attr.get("aria-expanded") in {"true", "false"}
                            else {}
                        ),
                        **({"collection_position": collection_position} if collection_position is not None else {}),
                        **({"href": attr["href"]} if node["tag"] == "a" and "href" in attr else {}),
                        **(
                            {
                                "pagination_owner": node["pagination_owner"],
                                "pagination_relation": node["pagination_relation"],
                                "pagination_current": bool(node.get("pagination_current")),
                                "pagination_total_pages": node["pagination_total_pages"],
                                **(
                                    {"pagination_page": node["pagination_page"]}
                                    if "pagination_page" in node
                                    else {}
                                ),
                            }
                            if node.get("pagination_owner")
                            and node.get("pagination_total_pages")
                            else {}
                        ),
                        **({"observed_color": attr["data-color"]} if attr.get("data-color") else {}),
                        **(
                            {
                                "collection_action": _label_for(node),
                                "collection_owner": node["collection_owner"],
                                "toggle_selected": bool(node["toggle_selected"]),
                            }
                            if node.get("semantic_collection_action")
                            else {}
                        ),
                        **(
                            {
                                "calendar_slot_index": node["calendar_slot_index"],
                                "calendar_time_minutes": node["calendar_slot_index"] * 30,
                                "accepts_drop": True,
                                "range_selectable": True,
                            }
                            if node.get("semantic_calendar_slot")
                            else {}
                        ),
                        **(
                            {
                                "item_name": node["quantity_item_name"],
                                "item_types": list(node["quantity_item_types"]),
                                "current_quantity": node["quantity_current"],
                                "quantity_delta": node["quantity_delta"],
                                "repeatable": True,
                            }
                            if node.get("semantic_quantity_control")
                            else {}
                        ),
                    },
                    risk=_authored_risk(attr),
                    risk_asserted=bool(attr.get("data-runtime-risk", "").strip()),
                    operation_ref=attr.get("data-runtime-operation", "").strip(),
                    effect_class=attr.get("data-runtime-effect-class", "").strip(),
                    externality=attr.get("data-runtime-externality", "").strip(),
                    reversibility=attr.get("data-runtime-reversibility", "").strip(),
                    resource_sensitivity=attr.get("data-runtime-resource-sensitivity", "").strip(),
                    # Page-authored metadata is observed DOM structure, never
                    # an authority source. A document may request a lower-risk
                    # interpretation but cannot promote itself to authoritative.
                    authority_source_assurance="structural",
                    evidence=[url] if url else [],
                )
            )
            if node.get("semantic_calendar_slot"):
                source = affordances[-1]
                source = replace(
                    source,
                    locator={**source.locator, "calendar_endpoint": "start"},
                    state={**source.state, "calendar_endpoint": "start", "accepts_drop": False},
                )
                affordances[-1] = source
                destination_fingerprint = "sha256:" + hashlib.sha256(
                    f"{source.target_fingerprint}\0calendar-end-boundary".encode("utf-8")
                ).hexdigest()
                affordances.append(
                    replace(
                        source,
                        id=f"{source.id}_end",
                        role="time_slot_end",
                        label=f"{source.label} end boundary",
                        action="drop",
                        locator={**source.locator, "calendar_endpoint": "end"},
                        lease=replace(source.lease, target_fingerprint=destination_fingerprint),
                        state={**source.state, "calendar_endpoint": "end", "accepts_drop": True},
                    )
                )
        return PageAffordanceModel(
            page_id=page_id,
            url=url,
            environment_revision=environment_revision,
            snapshot_id=snapshot_id,
            page_revision=effective_page_revision,
            affordances=affordances,
            raw_node_count=parser.total_nodes,
            kept_node_count=len(affordances),
            acquisition_adapter_id="dom-transducer@v1",
            acquisition_exhaustive=True,
        )
