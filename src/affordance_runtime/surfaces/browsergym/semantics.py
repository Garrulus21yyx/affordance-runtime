"""Canonical AX semantics shared by BrowserGym projection and currentness."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, replace
from enum import Enum
from typing import TypeAlias
from urllib.parse import urljoin, urlsplit

from affordance_runtime.surfaces.browsergym.interaction_profile import (
    BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
    BrowserGymRoleSpec,
    RoleCapabilityOffer,
    browsergym_role_spec,
    diagnostic_browsergym_roles,
    is_inventory_target_browsergym_role,
)

PRIVATE_CONTROL_PROPERTIES_KEY = "_browsergym_private_control_properties"
MAX_SEMANTIC_TEXT = 240
MAX_LINK_DESTINATION_TEXT = 2048
ACCESSIBLE_NAME_TRUNCATED_STATE_KEY = "semantic.accessible_name.truncated"
MAX_DOM_ATTRIBUTE_TOKENS = 32
MIN_DOM_CLICKABLE_AREA = 20.0
SemanticScalar: TypeAlias = str | bool | int | float | None

_DOM_SCALAR_ATTRIBUTES = frozenset({
    "aria-description",
    "aria-label",
    "alt",
    "id",
    "name",
    "placeholder",
    "role",
    "title",
    "type",
})
_DOM_TOKEN_ATTRIBUTES = frozenset({"class"})


class BrowserGymSemanticErrorCode(str, Enum):
    CONFLICTING_BID = "conflicting_bid"
    CONFLICTING_OPTION_OWNER = "conflicting_option_owner"
    CONFLICTING_NODE_ID = "conflicting_node_id"
    MALFORMED_PRIVATE_PROPERTIES = "malformed_private_properties"


class BrowserGymSemanticError(ValueError):
    def __init__(self, code: BrowserGymSemanticErrorCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code


@dataclass(frozen=True)
class BrowserGymControlAvailability:
    attached: bool | None
    visible: bool | None
    enabled: bool | None
    readonly: bool | None
    editable: bool | None
    focusable: bool | None

    def allows(self, offer: RoleCapabilityOffer) -> bool:
        conditions = {
            "attached": self.attached is True,
            "visible": self.visible is True,
            "enabled": self.enabled is True,
            "not_readonly": self.readonly is False,
            "editable": self.editable is True,
            "focusable": self.focusable is True,
        }
        return all(conditions.get(name, False) for name in offer.execution_requirements)

    def as_tuple(self) -> tuple[tuple[str, bool | None], ...]:
        return (
            ("attached", self.attached),
            ("visible", self.visible),
            ("enabled", self.enabled),
            ("readonly", self.readonly),
            ("editable", self.editable),
            ("focusable", self.focusable),
        )


@dataclass(frozen=True)
class CanonicalBrowserControl:
    private_bid: str
    role: str
    accessible_name: str
    public_state: tuple[tuple[str, SemanticScalar | tuple[str, ...]], ...]
    availability: BrowserGymControlAvailability
    public_options: tuple[str, ...]
    private_options: tuple[tuple[str, str], ...]
    public_fingerprint: str
    private_node_id: str
    private_parent_id: str
    private_child_ids: tuple[str, ...]
    private_bbox: tuple[int, int, int, int] | None = None
    private_gesture_group: str = ""
    private_gesture_kind: str = ""
    private_navigation_potential: bool = False

    @property
    def role_spec(self) -> BrowserGymRoleSpec:
        spec = browsergym_role_spec(self.role)
        if spec is None:  # construction filters unsupported roles
            raise RuntimeError("canonical BrowserGym control has no role spec")
        return spec

    @property
    def executable_offers(self) -> tuple[RoleCapabilityOffer, ...]:
        result = []
        for offer in self.role_spec.offers:
            if not self.availability.allows(offer):
                continue
            if offer.semantic_action == "select_option" and not (
                self.public_options
                and len(self.public_options) == len(self.private_options)
                and tuple(label for label, _value in self.private_options) == self.public_options
            ):
                continue
            result.append(offer)
        return tuple(result)

    @property
    def executable(self) -> bool:
        return bool(self.executable_offers)


@dataclass(frozen=True)
class BrowserGymInventoryAnalysis:
    profile_id: str
    recognized_target_count: int


@dataclass(frozen=True)
class BrowserGymSemanticAnalysis:
    controls: tuple[CanonicalBrowserControl, ...]
    structure: tuple[CanonicalBrowserStructureNode, ...]
    inventory: BrowserGymInventoryAnalysis
    diagnostic_role_distribution: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class _AxRecord:
    node_id: str
    parent_id: str
    child_ids: tuple[str, ...]
    bid: str
    role: str
    name: str
    state: tuple[tuple[str, SemanticScalar], ...]


@dataclass(frozen=True)
class _DomSemanticEvidence:
    tag: str
    state: tuple[tuple[str, SemanticScalar | tuple[str, ...]], ...]


@dataclass(frozen=True)
class CanonicalBrowserStructureNode:
    private_bid: str
    private_node_id: str
    private_parent_id: str
    private_child_ids: tuple[str, ...]
    role: str
    accessible_name: str
    public_state: tuple[tuple[str, SemanticScalar | tuple[str, ...]], ...]


def analyze_browsergym_semantics(raw: object) -> BrowserGymSemanticAnalysis:
    if not isinstance(raw, dict):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "observation is not a mapping",
        )
    records = _normalized_records(raw, _ax_records(raw))
    dom_semantics = _dom_semantic_evidence(raw)
    physical = _physical_properties(raw)
    dom_properties = _dom_properties(raw)
    suppressed_clickable_bids = _suppressed_dom_clickable_bids(records, dom_properties)
    suppressed_native_bids, native_alias_records = _nested_native_control_aliases(
        records,
        physical,
        dom_semantics,
    )
    by_node_id: dict[str, list[_AxRecord]] = {}
    for record in records:
        by_node_id.setdefault(record.node_id, []).append(record)
    controls: list[CanonicalBrowserControl] = []
    seen_controls: set[str] = set()
    option_owners: dict[str, str] = {}
    for record in records:
        if record.bid in suppressed_clickable_bids or record.bid in suppressed_native_bids:
            continue
        canonical_record = native_alias_records.get(record.bid, record)
        spec = browsergym_role_spec(canonical_record.role)
        if spec is None or not spec.observable or not record.node_id or (spec.executable and not record.bid):
            continue
        identity = record.bid or f"node:{record.node_id}"
        if identity in seen_controls:
            continue
        same_bid = [item for item in records if record.bid and item.bid == record.bid and _is_semantic_record(item)]
        if any(_record_signature(item) != _record_signature(record) for item in same_bid):
            raise BrowserGymSemanticError(
                BrowserGymSemanticErrorCode.CONFLICTING_BID,
                f"BID {record.bid!r} has conflicting AX records",
            )
        seen_controls.add(identity)
        options = _owned_options(record, by_node_id)
        for option in options:
            identity = option.bid or option.node_id
            previous = option_owners.setdefault(identity, record.bid)
            if previous != record.bid:
                raise BrowserGymSemanticError(
                    BrowserGymSemanticErrorCode.CONFLICTING_OPTION_OWNER,
                    f"option {identity!r} is reachable from multiple owners",
                )
        controls.append(
            _canonical_control(
                canonical_record,
                spec,
                options,
                _alias_physical_state(
                    physical.get(record.bid),
                    canonical_record.state,
                ) if canonical_record is not record else physical.get(record.bid),
                dom_semantics.get(record.bid),
            )
        )
    diagnostic_roles = diagnostic_browsergym_roles()
    distribution = Counter(
        record.role
        for record in records
        if record.bid not in suppressed_clickable_bids and record.role in diagnostic_roles
    )
    recognized = sum(
        record.bid not in suppressed_clickable_bids
        and record.bid not in suppressed_native_bids
        and is_inventory_target_browsergym_role(record.role)
        for record in records
    )
    structure_by_node_id: dict[str, CanonicalBrowserStructureNode] = {}
    for record in records:
        if not record.node_id:
            continue
        dom_evidence = dom_semantics.get(record.bid)
        structure_by_node_id.setdefault(
            record.node_id,
            CanonicalBrowserStructureNode(
                record.bid,
                record.node_id,
                record.parent_id,
                record.child_ids,
                (
                    "generic"
                    if record.bid in suppressed_clickable_bids and record.role == "clickable"
                    else record.role or "unknown"
                ),
                record.name,
                (
                    *record.state,
                    *(dom_evidence.state if dom_evidence is not None else ()),
                ),
            ),
        )
    return BrowserGymSemanticAnalysis(
        tuple(controls),
        tuple(structure_by_node_id.values()),
        BrowserGymInventoryAnalysis(
            BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
            recognized,
        ),
        tuple(sorted(distribution.items())),
    )


def canonicalize_browsergym_controls(raw: object) -> tuple[CanonicalBrowserControl, ...]:
    return analyze_browsergym_semantics(raw).controls


def canonical_control_for_bid(raw: object, bid: str) -> CanonicalBrowserControl | None:
    return next(
        (item for item in analyze_browsergym_semantics(raw).controls if item.private_bid == bid),
        None,
    )


def _ax_records(raw: dict[str, object]) -> tuple[_AxRecord, ...]:
    tree = raw.get("axtree_object")
    nodes = tree.get("nodes") if isinstance(tree, dict) else None
    if not isinstance(nodes, list):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "AX tree nodes are unavailable",
        )
    records: list[_AxRecord] = []
    bid_signatures: dict[str, tuple[object, ...]] = {}
    semantic_node_signatures: dict[str, tuple[object, ...]] = {}
    exact: set[tuple[object, ...]] = set()
    for node in nodes:
        if not isinstance(node, dict) or node.get("ignored") is True:
            continue
        role = _typed_string(node.get("role"))
        bid_value = node.get("browsergym_id")
        bid = bid_value if isinstance(bid_value, str) else ""
        node_id_value = node.get("nodeId")
        node_id = str(node_id_value) if isinstance(node_id_value, str | int) else ""
        parent_value = node.get("parentId")
        parent_id = str(parent_value) if isinstance(parent_value, str | int) else ""
        children_value = node.get("childIds")
        child_ids = (
            tuple(str(value) for value in children_value if isinstance(value, str | int))
            if isinstance(children_value, list)
            else ()
        )
        spec = browsergym_role_spec(role)
        state = _role_state(node, spec) if spec is not None else _option_state(node, role)
        name = _typed_string(node.get("name"))
        # BrowserGym's AX tree is the readable source.  Preserve informational
        # text for the observation/tool owners to project and bound.  The
        # compact control-label bound only protects executable routing labels.
        if (spec is not None and spec.executable) or role == "option":
            bounded_name = name[:MAX_SEMANTIC_TEXT]
            if len(name) > MAX_SEMANTIC_TEXT:
                state = (*state, (ACCESSIBLE_NAME_TRUNCATED_STATE_KEY, True))
        else:
            bounded_name = name
        record = _AxRecord(
            node_id,
            parent_id,
            child_ids,
            bid,
            role,
            bounded_name,
            state,
        )
        signature = _record_signature(record)
        if bid and _is_semantic_record(record):
            previous = bid_signatures.setdefault(bid, signature)
            if previous != signature:
                raise BrowserGymSemanticError(
                    BrowserGymSemanticErrorCode.CONFLICTING_BID,
                    f"BID {bid!r} has conflicting AX records",
                )
        if node_id and _is_semantic_record(record):
            previous = semantic_node_signatures.setdefault(node_id, signature)
            if previous != signature:
                raise BrowserGymSemanticError(
                    BrowserGymSemanticErrorCode.CONFLICTING_NODE_ID,
                    f"semantic node {node_id!r} has conflicting AX records",
                )
        if signature in exact:
            continue
        exact.add(signature)
        records.append(record)
    return tuple(records)


def _normalized_records(
    raw: dict[str, object],
    records: tuple[_AxRecord, ...],
) -> tuple[_AxRecord, ...]:
    extra = raw.get("extra_element_properties")
    extra = extra if isinstance(extra, dict) else {}
    physical = _physical_properties(raw)
    by_node_id = {item.node_id: item for item in records if item.node_id}
    normalized = []
    for record in records:
        private = physical.get(record.bid)
        gesture_role = private.get("gesture_role") if isinstance(private, dict) else None
        if gesture_role in {"draggable", "drop_target"}:
            normalized.append(
                replace(
                    record,
                    role=gesture_role,
                    name=record.name or _private_label_hint(private),
                )
            )
            continue
        properties = extra.get(record.bid)
        clickable = (
            record.bid
            and isinstance(properties, dict)
            and properties.get("clickable") is True
            and (record.role == "generic" or browsergym_role_spec(record.role) is None)
        )
        if clickable:
            assert isinstance(properties, dict)
            viewport_visibility = properties.get("visibility")
            viewport_state = (
                (("viewport.visible", float(viewport_visibility) > 0.0),)
                if isinstance(viewport_visibility, int | float)
                and not isinstance(viewport_visibility, bool)
                else ()
            )
            normalized.append(
                replace(
                    record,
                    role="clickable",
                    name=_descendant_text(record, by_node_id),
                    state=(*record.state, *viewport_state),
                )
            )
        else:
            normalized.append(record)
    return tuple(normalized)


def _dom_properties(raw: dict[str, object]) -> dict[str, object]:
    value = raw.get("extra_element_properties")
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _dom_semantic_evidence(raw: dict[str, object]) -> dict[str, _DomSemanticEvidence]:
    """Decode bounded public semantics from BrowserGym's raw DOMSnapshot.

    BrowserGym already aligns DOM and AX nodes with one private BID.  AX
    remains authoritative for accessible role/name/state; salient DOM
    attributes are preserved as parallel, explicitly-provenanced evidence. Raw
    routing/rendering attributes remain private. For links, this owner exposes
    one normalized HTTP(S) destination as read-only page semantics; it is not an
    executable binding and never extends the lifetime of a BrowserGym BID.
    """

    snapshot = raw.get("dom_object")
    if snapshot is None:
        return {}
    if not isinstance(snapshot, dict):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "DOM snapshot is not a mapping",
        )
    strings = snapshot.get("strings")
    documents = snapshot.get("documents")
    if not isinstance(strings, list) or not all(isinstance(item, str) for item in strings):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "DOM snapshot string table is malformed",
        )
    if not isinstance(documents, list):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "DOM snapshot documents are unavailable",
        )

    result: dict[str, _DomSemanticEvidence] = {}
    for document in documents:
        document_base_url = _dom_document_base_url(document, strings, raw)
        nodes = document.get("nodes") if isinstance(document, dict) else None
        attributes = nodes.get("attributes") if isinstance(nodes, dict) else None
        node_names = nodes.get("nodeName") if isinstance(nodes, dict) else None
        if not isinstance(attributes, list) or not isinstance(node_names, list):
            raise BrowserGymSemanticError(
                BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
                "DOM snapshot node attributes are malformed",
            )
        if len(attributes) != len(node_names):
            raise BrowserGymSemanticError(
                BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
                "DOM snapshot node tables have conflicting lengths",
            )
        for node_index, encoded_attributes in enumerate(attributes):
            if not isinstance(encoded_attributes, list) or len(encoded_attributes) % 2:
                raise BrowserGymSemanticError(
                    BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
                    "DOM snapshot attribute vector is malformed",
                )
            decoded: dict[str, str] = {}
            for offset in range(0, len(encoded_attributes), 2):
                name = _dom_string(strings, encoded_attributes[offset])
                value = _dom_string(strings, encoded_attributes[offset + 1], allow_missing=True)
                decoded[name.casefold()] = value
            bid = decoded.get("bid", "").strip()
            if not bid:
                continue
            tag = _dom_string(strings, node_names[node_index]).casefold()
            state: list[tuple[str, SemanticScalar | tuple[str, ...]]] = []
            if tag:
                state.append(("semantic.dom.tag", tag[:MAX_SEMANTIC_TEXT]))
            if tag in {"a", "area"}:
                destination = _public_link_destination(
                    decoded.get("href", ""),
                    document_base_url,
                )
                if destination:
                    state.append((
                        "semantic.link.destination",
                        destination[:MAX_LINK_DESTINATION_TEXT],
                    ))
                    if len(destination) > MAX_LINK_DESTINATION_TEXT:
                        state.append(("semantic.link.destination.truncated", True))
            for name in sorted(_DOM_SCALAR_ATTRIBUTES):
                value = " ".join(decoded.get(name, "").split())
                if value:
                    state.append((f"semantic.dom.attribute.{name}", value[:MAX_SEMANTIC_TEXT]))
                    if len(value) > MAX_SEMANTIC_TEXT:
                        state.append((f"semantic.dom.attribute.{name}.truncated", True))
            for name in sorted(_DOM_TOKEN_ATTRIBUTES):
                tokens = tuple(dict.fromkeys(decoded.get(name, "").split()))
                if tokens:
                    state.append((
                        f"semantic.dom.attribute.{name}_tokens",
                        tokens[:MAX_DOM_ATTRIBUTE_TOKENS],
                    ))
                    if len(tokens) > MAX_DOM_ATTRIBUTE_TOKENS:
                        state.append((f"semantic.dom.attribute.{name}.truncated", True))
            evidence = _DomSemanticEvidence(tag, tuple(state))
            previous = result.setdefault(bid, evidence)
            if previous != evidence:
                raise BrowserGymSemanticError(
                    BrowserGymSemanticErrorCode.CONFLICTING_BID,
                    f"BID {bid!r} has conflicting DOM semantic evidence",
                )
    return result


def _dom_document_base_url(
    document: object,
    strings: list[str],
    raw: dict[str, object],
) -> str:
    if isinstance(document, dict):
        for key in ("baseURL", "documentURL"):
            value = document.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, int) and not isinstance(value, bool):
                return _dom_string(strings, value)
    current_url = raw.get("url")
    return current_url if isinstance(current_url, str) else ""


def _public_link_destination(href: str, base_url: str) -> str:
    href = href.strip()
    if not href:
        return ""
    try:
        destination = urljoin(base_url, href)
        parsed = urlsplit(destination)
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return ""
    except ValueError:
        return ""
    return destination


def _dom_string(strings: list[str], value: object, *, allow_missing: bool = False) -> str:
    if allow_missing and value == -1:
        return ""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value >= len(strings)
    ):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "DOM snapshot contains an invalid string-table reference",
        )
    return strings[value]


def _suppressed_dom_clickable_bids(
    records: tuple[_AxRecord, ...],
    dom_properties: dict[str, object],
) -> frozenset[str]:
    """Reject geometry-less DOM fallbacks and collapse duplicate controls.

    Native AX controls are never affected.  The filter is intentionally
    bounded to records normalized from DOM clickability. BrowserGym viewport
    visibility is presentation state, not action-inventory authority: BID
    actions use Playwright locators, which scroll into view before dispatch.
    Therefore an off-viewport control remains in the canonical inventory and
    its ordinary live availability contract remains authoritative.
    """

    candidates = [record for record in records if record.role == "clickable" and record.bid]
    suppressed: set[str] = {
        record.bid
        for record in candidates
        if len(_owned_native_executable_controls(record, records)) == 1
    }
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for record in candidates:
        properties = dom_properties.get(record.bid)
        if not isinstance(properties, dict):
            continue
        bbox = _float_bbox(properties.get("bbox"))
        if bbox is None:
            continue
        if bbox[2] * bbox[3] < MIN_DOM_CLICKABLE_AREA:
            suppressed.add(record.bid)
            continue
        boxes[record.bid] = bbox

    retained = [record for record in candidates if record.bid in boxes and record.bid not in suppressed]
    for index, left in enumerate(retained):
        if left.bid in suppressed:
            continue
        for right in retained[index + 1 :]:
            if right.bid in suppressed or left.parent_id != right.parent_id:
                continue
            if not _same_control_overlap(boxes[left.bid], boxes[right.bid]):
                continue
            left_label, right_label = left.name.strip(), right.name.strip()
            if left_label and right_label and left_label.casefold() != right_label.casefold():
                continue
            winner = _preferred_clickable_record(left, right, boxes)
            loser = right if winner is left else left
            suppressed.add(loser.bid)
            if loser is left:
                break
    return frozenset(suppressed)


def _owned_native_executable_controls(
    owner: _AxRecord,
    records: tuple[_AxRecord, ...],
) -> frozenset[str]:
    """Return native executable descendants owned by one DOM fallback.

    DOM clickability is a lower-authority fallback.  A wrapper around exactly
    one native AX control represents the same interaction and must not become
    a second public action.  Wrappers containing multiple controls remain
    observable because they cannot be losslessly collapsed to one target.
    """

    by_node_id: dict[str, tuple[_AxRecord, ...]] = {}
    for record in records:
        by_node_id[record.node_id] = (*by_node_id.get(record.node_id, ()), record)
    pending = list(owner.child_ids)
    visited: set[str] = set()
    native: set[str] = set()
    while pending:
        node_id = pending.pop()
        if not node_id or node_id in visited:
            continue
        visited.add(node_id)
        for record in by_node_id.get(node_id, ()):
            spec = browsergym_role_spec(record.role)
            if record.role != "clickable" and record.bid and spec is not None and spec.executable:
                native.add(record.bid)
                continue
            pending.extend(record.child_ids)
    return frozenset(native)


def _nested_native_control_aliases(
    records: tuple[_AxRecord, ...],
    physical: dict[str, object],
    dom_semantics: dict[str, _DomSemanticEvidence],
) -> tuple[frozenset[str], dict[str, _AxRecord]]:
    """Collapse one proven native wrapper/anchor interaction.

    The descendant BID remains the physical identity. The wrapper contributes
    its stronger semantic role and state only when ancestry, label/title,
    geometry, operation algebra, and single-control ownership all agree.
    """

    by_bid = {item.bid: item for item in records if item.bid}
    suppressed: set[str] = set()
    aliases: dict[str, _AxRecord] = {}
    for wrapper in records:
        wrapper_spec = browsergym_role_spec(wrapper.role)
        if (
            not wrapper.bid
            or wrapper_spec is None
            or not wrapper_spec.executable
            or wrapper.role == "clickable"
        ):
            continue
        owned = _all_native_executable_descendants(wrapper, records)
        if len(owned) != 1:
            continue
        anchor_bid = next(iter(owned))
        anchor = by_bid.get(anchor_bid)
        anchor_spec = browsergym_role_spec(anchor.role) if anchor is not None else None
        if (
            anchor is None
            or anchor_spec is None
            or anchor.role == "clickable"
            or anchor_bid in aliases
            or _offer_signature(wrapper_spec) != _offer_signature(anchor_spec)
            or not _same_public_control_label(wrapper, anchor, dom_semantics)
        ):
            continue
        wrapper_box = _float_physical_bbox(physical.get(wrapper.bid))
        anchor_box = _float_physical_bbox(physical.get(anchor_bid))
        if (
            wrapper_box is None
            or anchor_box is None
            or not _same_control_overlap(wrapper_box, anchor_box)
        ):
            continue
        merged_state = dict(anchor.state)
        merged_state.update(dict(wrapper.state))
        aliases[anchor_bid] = replace(
            anchor,
            role=wrapper.role,
            name=anchor.name or wrapper.name,
            state=tuple(merged_state.items()),
        )
        suppressed.add(wrapper.bid)
    return frozenset(suppressed), aliases


def _offer_signature(spec: BrowserGymRoleSpec) -> tuple[tuple[str, str], ...]:
    return tuple((item.semantic_action, item.primitive_action) for item in spec.offers)


def _same_public_control_label(
    left: _AxRecord,
    right: _AxRecord,
    dom_semantics: dict[str, _DomSemanticEvidence],
) -> bool:
    left_evidence = dom_semantics.get(left.bid)
    right_evidence = dom_semantics.get(right.bid)
    left_label = _normalized_control_label(left, left_evidence)
    right_label = _normalized_control_label(right, right_evidence)
    if not left_label or left_label != right_label:
        return False
    left_title = _normalized_dom_title(left_evidence)
    right_title = _normalized_dom_title(right_evidence)
    return not (left_title and right_title) or left_title == right_title


def _normalized_control_label(
    record: _AxRecord,
    dom_evidence: _DomSemanticEvidence | None,
) -> str:
    values = dict(dom_evidence.state) if dom_evidence is not None else {}
    label = record.name or str(values.get("semantic.dom.attribute.title", ""))
    return " ".join(label.split()).casefold()


def _normalized_dom_title(dom_evidence: _DomSemanticEvidence | None) -> str:
    values = dict(dom_evidence.state) if dom_evidence is not None else {}
    return " ".join(str(values.get("semantic.dom.attribute.title", "")).split()).casefold()


def _all_native_executable_descendants(
    owner: _AxRecord,
    records: tuple[_AxRecord, ...],
) -> frozenset[str]:
    by_node_id = {item.node_id: item for item in records if item.node_id}
    pending = list(owner.child_ids)
    visited: set[str] = set()
    result: set[str] = set()
    while pending:
        node_id = pending.pop()
        if not node_id or node_id in visited:
            continue
        visited.add(node_id)
        record = by_node_id.get(node_id)
        if record is None:
            continue
        spec = browsergym_role_spec(record.role)
        if record.role != "clickable" and record.bid and spec is not None and spec.executable:
            result.add(record.bid)
        pending.extend(record.child_ids)
    return frozenset(result)


def _alias_physical_state(
    physical: object,
    merged_state: tuple[tuple[str, SemanticScalar], ...],
) -> object:
    if not isinstance(physical, dict):
        return physical
    result = dict(physical)
    state = dict(merged_state)
    for key in ("selected", "active", "focused"):
        if isinstance(state.get(key), bool):
            result[key] = state[key]
    return result


def _float_physical_bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, dict):
        return None
    return _float_bbox(value.get("bbox"))


def _preferred_clickable_record(
    left: _AxRecord,
    right: _AxRecord,
    boxes: dict[str, tuple[float, float, float, float]],
) -> _AxRecord:
    left_label, right_label = left.name.strip(), right.name.strip()
    if bool(left_label) != bool(right_label):
        return left if left_label else right
    left_area = boxes[left.bid][2] * boxes[left.bid][3]
    right_area = boxes[right.bid][2] * boxes[right.bid][3]
    if left_area != right_area:
        return left if left_area > right_area else right
    # BIDs are Runtime-private but stable for one page incarnation.  They make
    # equal unlabeled overlays deterministic under AX record permutation.
    return min((left, right), key=lambda item: (item.bid, item.node_id))


def _float_bbox(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = (float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _same_control_overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    intersection_width = max(
        0.0,
        min(left_x + left_width, right_x + right_width) - max(left_x, right_x),
    )
    intersection_height = max(
        0.0,
        min(left_y + left_height, right_y + right_height) - max(left_y, right_y),
    )
    intersection = intersection_width * intersection_height
    if intersection <= 0:
        return False
    smaller = min(left_width * left_height, right_width * right_height)
    return intersection / smaller >= 0.9


def _descendant_text(
    owner: _AxRecord,
    by_node_id: dict[str, _AxRecord],
) -> str:
    pending = list(reversed(owner.child_ids))
    visited: set[str] = set()
    labels: list[str] = []
    while pending and len(labels) < 8:
        node_id = pending.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        record = by_node_id.get(node_id)
        if record is None:
            continue
        if record.name and record.role in {"StaticText", "InlineTextBox"}:
            labels.append(record.name)
        pending.extend(reversed(record.child_ids))
    return " ".join(dict.fromkeys(labels))[:MAX_SEMANTIC_TEXT]


def _record_signature(record: _AxRecord) -> tuple[object, ...]:
    return (
        record.node_id,
        record.parent_id,
        record.child_ids,
        record.bid,
        record.role,
        record.name,
        record.state,
    )


def _is_semantic_record(record: _AxRecord) -> bool:
    return is_inventory_target_browsergym_role(record.role) or record.role == "option"


def _role_state(
    node: dict[str, object],
    spec: BrowserGymRoleSpec,
) -> tuple[tuple[str, SemanticScalar], ...]:
    properties = _properties(node)
    result: list[tuple[str, SemanticScalar]] = []
    for name in spec.currentness_fields:
        if name == "selected_options":
            continue
        if name == "value":
            value: SemanticScalar = _typed_string(node.get("value"))[:MAX_SEMANTIC_TEXT]
        elif name in properties:
            value = _semantic_scalar(properties[name])
        else:
            continue
        result.append((name, value))
    return tuple(result)


def _option_state(node: dict[str, object], role: str) -> tuple[tuple[str, SemanticScalar], ...]:
    if role != "option":
        return ()
    properties = _properties(node)
    selected = properties.get("selected")
    return (("selected", _semantic_scalar(selected)),) if isinstance(selected, bool) else ()


def _owned_options(
    owner: _AxRecord,
    by_node_id: dict[str, list[_AxRecord]],
) -> tuple[_AxRecord, ...]:
    pending = [(child_id, owner.node_id) for child_id in owner.child_ids]
    visited: set[str] = set()
    options: list[_AxRecord] = []
    seen_bids: set[str] = set()
    while pending:
        node_id, expected_parent = pending.pop()
        edge = f"{expected_parent}\0{node_id}"
        if edge in visited:
            continue
        visited.add(edge)
        for record in by_node_id.get(node_id, ()):
            if record.parent_id and record.parent_id != expected_parent:
                if record.role == "option":
                    raise BrowserGymSemanticError(
                        BrowserGymSemanticErrorCode.CONFLICTING_OPTION_OWNER,
                        f"option {record.bid or record.node_id!r} has an ambiguous parent",
                    )
                continue
            nested_spec = browsergym_role_spec(record.role)
            if nested_spec is not None and record.bid != owner.bid:
                continue
            pending.extend((child_id, record.node_id) for child_id in record.child_ids)
            if record.role != "option":
                continue
            option_identity = record.bid or record.node_id
            if option_identity in seen_bids:
                continue
            seen_bids.add(option_identity)
            options.append(record)
    return tuple(options)


def _canonical_control(
    record: _AxRecord,
    spec: BrowserGymRoleSpec,
    option_records: tuple[_AxRecord, ...],
    physical: object,
    dom_evidence: _DomSemanticEvidence | None,
) -> CanonicalBrowserControl:
    availability = _availability(physical)
    public_state: list[tuple[str, SemanticScalar | tuple[str, ...]]] = list(record.state)
    if dom_evidence is not None:
        public_state.extend(dom_evidence.state)
    if isinstance(physical, dict) and isinstance(physical.get("selected"), bool):
        public_state.append(("selected", physical["selected"]))
    if isinstance(physical, dict) and isinstance(physical.get("active"), bool):
        public_state.append(("active", physical["active"]))
    if isinstance(physical, dict) and physical.get("focused") is True:
        public_state.append(("focused", physical["focused"]))
    if isinstance(physical, dict) and isinstance(physical.get("color_family"), str):
        color = physical["color_family"]
        public_state.append(
            (
                "appearance.color_family",
                color if color in {"red", "yellow", "green", "cyan", "blue", "magenta", "gray"} else "other",
            )
        )
    if spec.role in {"draggable", "drop_target"}:
        bbox = _private_bbox(physical)
        if bbox is not None:
            public_state.extend((
                ("size.width", bbox[2]),
                ("size.height", bbox[3]),
            ))
        if isinstance(physical, dict):
            horizontal = physical.get("spatial_horizontal")
            vertical = physical.get("spatial_vertical")
            if horizontal in {"left", "center", "right"}:
                public_state.append(("position.horizontal", horizontal))
            if vertical in {"top", "middle", "bottom"}:
                public_state.append(("position.vertical", vertical))
    labels = tuple(sorted(item.name for item in option_records if item.name))
    selected = tuple(
        sorted(item.name for item in option_records if dict(item.state).get("selected") is True and item.name)
    )
    if "selected_options" in spec.currentness_fields:
        public_state.append(("selected_options", selected))
    private_options = _private_options(labels, physical)
    public_options = labels
    public_name = record.name or _private_label_hint(physical)
    if spec.executable and not public_name:
        public_state.append(("semantic.name_status", "unknown"))
    public_payload = (record.role, public_name, tuple(public_state), public_options)
    return CanonicalBrowserControl(
        record.bid,
        record.role,
        public_name,
        tuple(public_state),
        availability,
        public_options,
        private_options,
        _fingerprint(public_payload),
        record.node_id,
        record.parent_id,
        record.child_ids,
        _private_bbox(physical),
        _private_gesture_group(physical),
        _private_gesture_kind(physical),
        _private_navigation_potential(physical),
    )


def _physical_properties(raw: dict[str, object]) -> dict[str, object]:
    value = raw.get(PRIVATE_CONTROL_PROPERTIES_KEY)
    if value is None:
        return {}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "private control properties are malformed",
        )
    return value


def _availability(value: object) -> BrowserGymControlAvailability:
    mapping = value if isinstance(value, dict) else {}
    return BrowserGymControlAvailability(
        *(
            item if isinstance(item, bool) else None
            for item in (
                mapping.get("attached"),
                mapping.get("visible"),
                mapping.get("enabled"),
                mapping.get("readonly"),
                mapping.get("editable"),
                mapping.get("focusable"),
            )
        )
    )


def _private_options(public_labels: tuple[str, ...], physical: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(physical, dict):
        return ()
    values = physical.get("options")
    if not isinstance(values, list):
        return ()
    mapped: list[tuple[str, str]] = []
    for item in values:
        if not isinstance(item, dict):
            return ()
        label = item.get("label")
        native = item.get("value")
        if not isinstance(label, str) or not isinstance(native, str):
            return ()
        public_label = label[:MAX_SEMANTIC_TEXT]
        # Native selects commonly carry an unlabeled placeholder that the AX
        # option domain intentionally omits.  It is not an agent-addressable
        # choice, so exclude it from the private mapping while keeping exact
        # equality for every named option.
        if not public_label:
            continue
        mapped.append((public_label, native))
    labels = [label for label, _native in mapped]
    native_values = [native for _label, native in mapped]
    if (
        len(labels) != len(set(labels))
        or len(native_values) != len(set(native_values))
        or tuple(sorted(labels)) != public_labels
    ):
        return ()
    return tuple(sorted(mapped))


def _private_bbox(physical: object) -> tuple[int, int, int, int] | None:
    if not isinstance(physical, dict):
        return None
    value = physical.get("bbox")
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = (int(round(float(item))) for item in value)
    except (TypeError, ValueError):
        return None
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _private_label_hint(physical: object) -> str:
    if not isinstance(physical, dict):
        return ""
    value = physical.get("label_hint")
    return value[:MAX_SEMANTIC_TEXT] if isinstance(value, str) else ""


def _private_gesture_group(physical: object) -> str:
    if not isinstance(physical, dict):
        return ""
    value = physical.get("gesture_group")
    return value if isinstance(value, str) else ""


def _private_gesture_kind(physical: object) -> str:
    if not isinstance(physical, dict):
        return ""
    value = physical.get("gesture_kind")
    return value if isinstance(value, str) else ""


def _private_navigation_potential(physical: object) -> bool:
    return isinstance(physical, dict) and physical.get("navigation_potential") is True


def _properties(node: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    value = node.get("properties")
    for item in value if isinstance(value, list) else ():
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            result[str(item["name"])] = _raw_typed_value(item.get("value"))
    return result


def _typed_string(value: object) -> str:
    raw = _raw_typed_value(value)
    return raw if isinstance(raw, str) else ""


def _raw_typed_value(value: object) -> object:
    return value.get("value") if isinstance(value, dict) else None


def _semantic_scalar(value: object) -> SemanticScalar:
    return value if isinstance(value, str | bool | int | float) or value is None else None


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
