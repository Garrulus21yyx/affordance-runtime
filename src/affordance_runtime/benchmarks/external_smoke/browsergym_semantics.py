"""Canonical AX semantics shared by BrowserGym projection and currentness."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, replace
from enum import Enum
from typing import TypeAlias

from affordance_runtime.benchmarks.external_smoke.browsergym_semantic_profile import (
    BROWSERGYM_AX_TARGET_INVENTORY_PROFILE_ID,
    BrowserGymRoleSpec,
    browsergym_role_spec,
    diagnostic_browsergym_roles,
    is_inventory_target_browsergym_role,
)

PRIVATE_CONTROL_PROPERTIES_KEY = "_browsergym_private_control_properties"
MAX_SEMANTIC_TEXT = 240
MIN_DOM_CLICKABLE_VISIBILITY = 0.5
MIN_DOM_CLICKABLE_AREA = 20.0
SemanticScalar: TypeAlias = str | bool | int | float | None


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

    def allows(self, spec: BrowserGymRoleSpec) -> bool:
        conditions = {
            "attached": self.attached is True,
            "visible": self.visible is True,
            "enabled": self.enabled is True,
            "not_readonly": self.readonly is False,
            "editable": self.editable is True,
        }
        return all(conditions.get(name, False) for name in spec.required_availability)

    def as_tuple(self) -> tuple[tuple[str, bool | None], ...]:
        return (
            ("attached", self.attached),
            ("visible", self.visible),
            ("enabled", self.enabled),
            ("readonly", self.readonly),
            ("editable", self.editable),
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
    currentness_fingerprint: str
    private_node_id: str
    private_parent_id: str
    private_child_ids: tuple[str, ...]
    private_bbox: tuple[int, int, int, int] | None = None

    @property
    def role_spec(self) -> BrowserGymRoleSpec:
        spec = browsergym_role_spec(self.role)
        if spec is None:  # construction filters unsupported roles
            raise RuntimeError("canonical BrowserGym control has no role spec")
        return spec

    @property
    def executable(self) -> bool:
        spec = self.role_spec
        if not spec.executable or not self.availability.allows(spec):
            return False
        if spec.semantic_action == "select_option":
            return bool(
                self.public_options
                and len(self.public_options) == len(self.private_options)
                and tuple(label for label, _value in self.private_options) == self.public_options
            )
        return True


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
class CanonicalBrowserStructureNode:
    private_bid: str
    private_node_id: str
    private_parent_id: str
    private_child_ids: tuple[str, ...]
    role: str
    accessible_name: str
    public_state: tuple[tuple[str, SemanticScalar], ...]


def analyze_browsergym_semantics(raw: object) -> BrowserGymSemanticAnalysis:
    if not isinstance(raw, dict):
        raise BrowserGymSemanticError(
            BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES,
            "observation is not a mapping",
        )
    records = _normalized_records(raw, _ax_records(raw))
    physical = _physical_properties(raw)
    dom_properties = _dom_properties(raw)
    suppressed_clickable_bids = _suppressed_dom_clickable_bids(records, dom_properties)
    by_node_id: dict[str, list[_AxRecord]] = {}
    for record in records:
        by_node_id.setdefault(record.node_id, []).append(record)
    controls: list[CanonicalBrowserControl] = []
    seen_controls: set[str] = set()
    option_owners: dict[str, str] = {}
    for record in records:
        if record.bid in suppressed_clickable_bids:
            continue
        spec = browsergym_role_spec(record.role)
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
        controls.append(_canonical_control(record, spec, options, physical.get(record.bid)))
    diagnostic_roles = diagnostic_browsergym_roles()
    distribution = Counter(
        record.role
        for record in records
        if record.bid not in suppressed_clickable_bids and record.role in diagnostic_roles
    )
    recognized = sum(
        record.bid not in suppressed_clickable_bids and is_inventory_target_browsergym_role(record.role)
        for record in records
    )
    structure_by_node_id: dict[str, CanonicalBrowserStructureNode] = {}
    for record in records:
        if not record.node_id:
            continue
        structure_by_node_id.setdefault(
            record.node_id,
            CanonicalBrowserStructureNode(
                record.bid,
                record.node_id,
                record.parent_id,
                record.child_ids,
                record.role or "unknown",
                record.name,
                record.state,
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
        record = _AxRecord(
            node_id,
            parent_id,
            child_ids,
            bid,
            role,
            _typed_string(node.get("name"))[:MAX_SEMANTIC_TEXT],
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
    by_node_id = {item.node_id: item for item in records if item.node_id}
    normalized = []
    for record in records:
        properties = extra.get(record.bid)
        clickable = (
            record.bid
            and isinstance(properties, dict)
            and properties.get("clickable") is True
            and (record.role == "generic" or browsergym_role_spec(record.role) is None)
        )
        if clickable:
            normalized.append(
                replace(
                    record,
                    role="clickable",
                    name=_descendant_text(record, by_node_id),
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


def _suppressed_dom_clickable_bids(
    records: tuple[_AxRecord, ...],
    dom_properties: dict[str, object],
) -> frozenset[str]:
    """Reject non-hittable DOM fallbacks and collapse same-control drawing nodes.

    Native AX controls are never affected.  The filter is intentionally
    bounded to records normalized from DOM clickability.  When BrowserGym has
    no geometry (for example an older fixture), the record is retained and the
    ordinary availability contract remains authoritative.
    """

    candidates = [record for record in records if record.role == "clickable" and record.bid]
    suppressed: set[str] = set()
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for record in candidates:
        properties = dom_properties.get(record.bid)
        if not isinstance(properties, dict):
            continue
        bbox = _float_bbox(properties.get("bbox"))
        if bbox is None:
            continue
        visibility = properties.get("visibility")
        if (
            isinstance(visibility, int | float)
            and not isinstance(visibility, bool)
            and float(visibility) < MIN_DOM_CLICKABLE_VISIBILITY
        ):
            suppressed.add(record.bid)
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
) -> CanonicalBrowserControl:
    availability = _availability(physical)
    public_state: list[tuple[str, SemanticScalar | tuple[str, ...]]] = list(record.state)
    if isinstance(physical, dict) and isinstance(physical.get("selected"), bool):
        public_state.append(("selected", physical["selected"]))
    if isinstance(physical, dict) and isinstance(physical.get("color_family"), str):
        color = physical["color_family"]
        public_state.append(
            (
                "appearance.color_family",
                color if color in {"red", "yellow", "green", "cyan", "blue", "magenta", "gray"} else "other",
            )
        )
    labels = tuple(sorted(item.name for item in option_records if item.name))
    selected = tuple(
        sorted(item.name for item in option_records if dict(item.state).get("selected") is True and item.name)
    )
    if "selected_options" in spec.currentness_fields:
        public_state.append(("selected_options", selected))
    private_options = _private_options(labels, physical)
    public_options = labels
    public_name = record.name or _private_label_hint(physical)
    public_payload = (record.role, public_name, tuple(public_state), public_options)
    private_payload = (
        public_payload,
        availability.as_tuple(),
        private_options,
        spec.primitive,
    )
    return CanonicalBrowserControl(
        record.bid,
        record.role,
        public_name,
        tuple(public_state),
        availability,
        public_options,
        private_options,
        _fingerprint(public_payload),
        _fingerprint(private_payload),
        record.node_id,
        record.parent_id,
        record.child_ids,
        _private_bbox(physical),
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
        if not isinstance(label, str) or not isinstance(native, str) or not label:
            return ()
        mapped.append((label[:MAX_SEMANTIC_TEXT], native))
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
