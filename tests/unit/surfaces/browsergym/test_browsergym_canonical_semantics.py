from __future__ import annotations

import copy

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.surfaces.browsergym import backend as browsergym_backend
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    ACCESSIBLE_NAME_TRUNCATED_STATE_KEY,
    MAX_SEMANTIC_TEXT,
    PRIVATE_CONTROL_PROPERTIES_KEY,
    BrowserGymSemanticError,
    BrowserGymSemanticErrorCode,
    analyze_browsergym_semantics,
    canonical_control_for_bid,
    canonicalize_browsergym_controls,
)
from affordance_runtime.world import SemanticInventoryStatus
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    ax_node,
    dom_snapshot,
    raw_observation,
    reset_task_state,
)
from tests.support.surfaces.browsergym.projection_support import (
    project_browsergym_observation,
)

_IDENTITY = BrowserGymEntityIdentityMap(b"browsergym-canonical-semantics-tests")


def _snapshot():
    return reset_task_state("obs:1")


def _projection(raw):
    return project_browsergym_observation(
        raw,
        observation_id="obs:1",
        source_revision="revision:1",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=_snapshot(),
        entity_identity=_IDENTITY,
    )


def _page_targets(world):
    return tuple(
        target for target in world.targets
        if target.role not in {"viewport", "focused_context"}
    )


def _page_bindings(world):
    return tuple(
        binding for binding in world.bindings
        if binding.semantic_action not in {"scroll"}
        and binding.target_id != "focused-context:current"
    )


def _binding(world, semantic_action: str):
    return next(
        binding for binding in world.bindings
        if binding.semantic_action == semantic_action
    )


@given(st.permutations((0, 1, 2, 3)))
def test_canonical_record_is_invariant_to_ax_permutation_and_unrelated_nodes(permutation) -> None:
    raw = raw_observation(
        ax_node("control", "textbox", "Name", value="Ada", properties=(("required", True),)),
        ax_node("other", "button", "Save"),
        ax_node("ignored", "button", "Ignore me"),
        ax_node("static", "StaticText", "informational"),
    )
    raw["axtree_object"]["nodes"][2]["ignored"] = True
    expected = canonical_control_for_bid(raw, "control")
    shuffled = copy.deepcopy(raw)
    nodes = shuffled["axtree_object"]["nodes"]
    shuffled["axtree_object"]["nodes"] = [nodes[index] for index in permutation]

    actual = canonical_control_for_bid(shuffled, "control")

    assert actual == expected
    assert actual is not None
    assert actual.public_fingerprint == expected.public_fingerprint
    assert actual.currentness_fingerprint == expected.currentness_fingerprint


@given(st.permutations((0, 1, 2, 3, 4)))
def test_inventory_analysis_is_permutation_duplicate_and_option_invariant(permutation) -> None:
    button = ax_node("button", "button", "Save")
    checkbox = ax_node("check", "checkbox", "Remember")
    option = ax_node("option", "option", "Choice")
    ignored = ax_node("ignored", "radio", "Ignored")
    ignored["ignored"] = True
    raw = raw_observation(button, copy.deepcopy(button), checkbox, option, ignored)
    nodes = raw["axtree_object"]["nodes"]
    raw["axtree_object"]["nodes"] = [nodes[index] for index in permutation]

    analysis = analyze_browsergym_semantics(raw)

    assert len(analysis.controls) == 2
    assert analysis.inventory.recognized_target_count == 2
    assert dict(analysis.diagnostic_role_distribution) == {
        "button": 1,
        "checkbox": 1,
        "option": 1,
    }


def test_bidless_recognized_interactive_unit_is_not_empty_or_projected() -> None:
    missing_identity = ax_node("missing", "tab", "Details")
    raw = raw_observation(missing_identity)
    raw["axtree_object"]["nodes"][0].pop("browsergym_id")
    raw[PRIVATE_CONTROL_PROPERTIES_KEY].pop("missing")

    analysis = analyze_browsergym_semantics(raw)
    projection = _projection(raw)
    inventory = projection.world.sources[0].semantic_inventory

    assert analysis.inventory.recognized_target_count == 1
    assert inventory.status is SemanticInventoryStatus.PARTIAL
    assert inventory.omitted_target_count == 1
    assert inventory.recognized_target_count == 3
    assert _page_targets(projection.world) == ()
    assert all(binding.semantic_action in {"scroll", "press_key"} for binding in projection.world.bindings)


def test_ax_name_remains_authoritative_while_dom_semantics_are_preserved() -> None:
    raw = raw_observation(ax_node("control", "link", "Canonical AX name"))
    raw["dom_object"] = dom_snapshot((
        "a",
        "control",
        {"class": "primary action", "aria-label": "conflicting DOM label"},
    ))

    control = canonical_control_for_bid(raw, "control")

    assert control is not None
    assert control.accessible_name == "Canonical AX name"
    assert dict(control.public_state) == {
        "semantic.dom.tag": "a",
        "semantic.dom.attribute.aria-label": "conflicting DOM label",
        "semantic.dom.attribute.class_tokens": ("primary", "action"),
    }


def test_informational_ax_text_is_not_reduced_to_the_control_label_limit() -> None:
    body = "long readable review " * 80
    analysis = analyze_browsergym_semantics(
        raw_observation(ax_node("body", "StaticText", body))
    )
    node = next(item for item in analysis.structure if item.role == "StaticText")

    assert len(body) > MAX_SEMANTIC_TEXT
    assert node.accessible_name == body
    assert ACCESSIBLE_NAME_TRUNCATED_STATE_KEY not in dict(node.public_state)


def test_executable_ax_label_bound_is_explicit() -> None:
    label = "action label " * 80
    control = canonical_control_for_bid(
        raw_observation(ax_node("control", "button", label)),
        "control",
    )

    assert control is not None
    assert control.accessible_name == label[:MAX_SEMANTIC_TEXT]
    assert dict(control.public_state)[ACCESSIBLE_NAME_TRUNCATED_STATE_KEY] is True


@given(st.permutations(("class", "title", "type")))
def test_dom_semantics_are_invariant_to_attribute_order(order: tuple[str, ...]) -> None:
    values = {"class": "like active", "title": "Like", "type": "button"}
    raw = raw_observation(ax_node("control", "generic", ""))
    raw["extra_element_properties"]["control"]["clickable"] = True
    raw["dom_object"] = dom_snapshot((
        "span",
        "control",
        {name: values[name] for name in order},
    ))

    control = canonical_control_for_bid(raw, "control")

    assert control is not None
    assert control.accessible_name == ""
    assert dict(control.public_state) == {
        "viewport.visible": True,
        "semantic.dom.tag": "span",
        "semantic.dom.attribute.title": "Like",
        "semantic.dom.attribute.type": "button",
        "semantic.dom.attribute.class_tokens": ("like", "active"),
        "semantic.name_status": "unknown",
    }


def test_physical_capture_preserves_false_for_an_absent_active_class() -> None:
    assert (
        "active: el.classList.contains('active')"
        in browsergym_backend._PHYSICAL_PROPERTIES_SCRIPT  # noqa: SLF001
    )
    raw = raw_observation(ax_node("control", "generic", ""))
    raw["extra_element_properties"]["control"]["clickable"] = True
    raw["dom_object"] = dom_snapshot(("span", "control", {"class": "like"}),)
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["control"]["active"] = False

    control = canonical_control_for_bid(raw, "control")

    assert control is not None
    assert dict(control.public_state)["active"] is False


def test_physical_capture_requires_explicit_html_drag_evidence() -> None:
    script = browsergym_backend._PHYSICAL_PROPERTIES_SCRIPT  # noqa: SLF001

    assert "el.draggable === true" not in script
    assert script.count("el.getAttribute('draggable') === 'true'") == 2


def test_native_link_role_is_not_replaced_without_explicit_drag_evidence() -> None:
    raw = raw_observation(ax_node("reports", "link", "REPORTS"))
    raw["dom_object"] = dom_snapshot(("a", "reports", {"title": "Reports"}),)
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["reports"].update({
        "gesture_role": "",
        "gesture_group": "",
        "gesture_kind": "",
    })

    projection = _projection(raw)

    assert [(item.role, item.label) for item in _page_targets(projection.world)] == [
        ("link", "REPORTS")
    ]
    activate = _binding(projection.world, "activate")
    assert activate.semantic_action == "activate"
    assert activate.primitive_action == "click"


def test_browser_default_draggable_like_value_does_not_generate_drag_binding() -> None:
    raw = raw_observation(
        ax_node("reports", "link", "REPORTS"),
        ax_node("drop", "generic", "Drop zone"),
    )
    raw["dom_object"] = dom_snapshot(
        ("a", "reports", {"title": "Reports"}),
        ("div", "drop", {"class": "drop-zone"}),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["reports"].update({
        "draggable": True,
        "gesture_role": "",
        "gesture_group": "",
        "gesture_kind": "",
    })
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["drop"].update({
        "gesture_role": "drop_target",
        "gesture_group": "group:1",
        "gesture_kind": "",
    })

    projection = _projection(raw)

    assert "drag_to" not in {item.semantic_action for item in projection.world.bindings}
    assert "activate" in {item.semantic_action for item in projection.world.bindings}


def test_physical_active_class_is_public_true_without_inventing_selected_state() -> None:
    raw = raw_observation(ax_node("control", "generic", ""))
    raw["extra_element_properties"]["control"]["clickable"] = True
    raw["dom_object"] = dom_snapshot(("span", "control", {"class": "like active"}),)
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["control"].update({
        "active": True,
        "selected": None,
        "label_hint": "Like",
    })

    control = canonical_control_for_bid(raw, "control")

    assert control is not None
    assert control.accessible_name == "Like"
    assert dict(control.public_state)["active"] is True
    assert "selected" not in dict(control.public_state)


def test_explicit_toggle_convention_active_false_reaches_public_world() -> None:
    raw = raw_observation(ax_node("control", "button", "Like"))
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["control"]["active"] = False
    projection = _projection(raw)

    assert any(
            item.subject_id == _page_targets(projection.world)[0].target_id
        and item.predicate == "active"
        and item.value is False
        for item in projection.world.facts
    )


def test_dom_class_change_is_public_effect_evidence_without_exposing_bid() -> None:
    raw = raw_observation(ax_node("private-control", "generic", ""))
    raw["extra_element_properties"]["private-control"]["clickable"] = True
    raw["dom_object"] = dom_snapshot(("span", "private-control", {"class": "like"}),)
    before = canonical_control_for_bid(raw, "private-control")
    raw["dom_object"] = dom_snapshot(("span", "private-control", {"class": "like active"}),)
    after = canonical_control_for_bid(raw, "private-control")

    assert before is not None and after is not None
    assert before.public_fingerprint != after.public_fingerprint
    assert before.currentness_fingerprint != after.currentness_fingerprint
    assert dict(after.public_state)["semantic.dom.attribute.class_tokens"] == ("like", "active")
    assert "private-control" not in repr(_projection(raw).world)


def test_malformed_dom_snapshot_fails_typed() -> None:
    raw = raw_observation(ax_node("control", "button", "Save"))
    raw["dom_object"] = {"strings": ["BUTTON"], "documents": [{"nodes": {
        "nodeName": [0],
        "attributes": [[99, 0]],
    }}]}

    with pytest.raises(BrowserGymSemanticError) as error:
        analyze_browsergym_semantics(raw)

    assert error.value.code is BrowserGymSemanticErrorCode.MALFORMED_PRIVATE_PROPERTIES


def test_dom_clickable_svg_symbol_becomes_identity_bound_activate_control() -> None:
    raw = raw_observation(ax_node("svg-point", "graphics-symbol", ""))
    raw["extra_element_properties"]["svg-point"].update({
        "clickable": True,
        "visibility": 1.0,
        "bbox": [21.75, 96.75, 13.5, 13.5],
    })
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["svg-point"]["bbox"] = [21.75, 96.75, 13.5, 13.5]
    raw["screenshot"] = np.zeros((240, 320, 3), dtype=np.uint8)

    projection = _projection(raw)

    page_targets = _page_targets(projection.world)
    page_bindings = _page_bindings(projection.world)
    assert len(page_targets) == 1
    assert page_targets[0].role == "clickable"
    assert any(binding.semantic_action == "activate" for binding in page_bindings)
    assert any(binding.primitive_action == "click" for binding in page_bindings)
    element_private = next(item for item in projection.private_bindings if hasattr(item, "private_element_id"))
    assert element_private.private_element_id == "svg-point"
    assert projection.world.sources[0].media[0].grounding_regions[0].bbox == (22, 97, 14, 14)
    public = repr(projection.world)
    assert "svg-point" not in public
    assert "action_point_xy" not in public and "private_element_id" not in public


def test_dom_clickable_inventory_preserves_off_viewport_capability_and_deduplicates() -> None:
    raw = raw_observation(
        ax_node("slice", "graphics-symbol", "", parent_id="svg-root"),
        ax_node("title", "generic", "", parent_id="svg-root", child_ids=("title-text",)),
        ax_node("title-text", "StaticText", "+", parent_id="title"),
        ax_node("tiny", "graphics-symbol", "", parent_id="svg-root"),
        ax_node("occluded", "graphics-symbol", "", parent_id="svg-root"),
    )
    for bid, bbox, visibility in (
        ("slice", [87.0, 162.0, 66.0, 66.0], 1.0),
        ("title", [104.5, 166.5, 31.0, 57.0], 1.0),
        ("tiny", [120.0, 195.0, 1.0, 1.0], 1.0),
        ("occluded", [0.0, 75.0, 6.0, 6.0], 0.25),
    ):
        raw["extra_element_properties"][bid].update({
            "clickable": True,
            "visibility": visibility,
            "bbox": bbox,
        })
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["bbox"] = bbox

    controls = canonicalize_browsergym_controls(raw)
    clickables = [item for item in controls if item.role == "clickable"]

    assert [(item.private_bid, item.accessible_name) for item in clickables] == [
        ("title", "+"),
        ("occluded", ""),
    ]
    assert dict(clickables[1].public_state) == {
        "viewport.visible": True,
        "semantic.name_status": "unknown",
    }
    projection = _projection(raw)
    clickable_target_ids = {
        target.target_id for target in projection.world.targets if target.role == "clickable"
    }
    assert len(clickable_target_ids) == 2
    assert {
        binding.target_id for binding in _page_bindings(projection.world)
        if binding.semantic_action == "activate"
    } == clickable_target_ids
    structure_roles = {
        item.private_bid: item.role for item in analyze_browsergym_semantics(raw).structure
    }
    assert structure_roles["tiny"] == "generic"
    assert structure_roles["occluded"] == "clickable"


@given(
    visibility=st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_dom_clickable_action_inventory_is_invariant_to_viewport_visibility(
    visibility: float,
) -> None:
    raw = raw_observation(ax_node("control", "graphics-symbol", ""))
    raw["extra_element_properties"]["control"].update({
        "clickable": True,
        "visibility": visibility,
        "bbox": [20.0, 400.0, 24.0, 24.0],
    })
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["control"]["bbox"] = [20.0, 400.0, 24.0, 24.0]

    projection = _projection(raw)

    assert len(_page_targets(projection.world)) == 1
    assert any(binding.primitive_action == "click" for binding in _page_bindings(projection.world))
    assert _page_targets(projection.world)[0].state == {
        "viewport.visible": visibility > 0.0,
        "semantic.name_status": "unknown",
    }


def test_equal_unlabeled_dom_overlays_deduplicate_independently_of_ax_order() -> None:
    def controls(order: tuple[str, str]) -> tuple[str, ...]:
        raw = raw_observation(*(
            ax_node(bid, "graphics-symbol", "", parent_id="svg-root")
            for bid in order
        ))
        for bid in order:
            raw["extra_element_properties"][bid].update({
                "clickable": True,
                "visibility": 1.0,
                "bbox": [20, 40, 20, 20],
            })
        return tuple(
            item.private_bid
            for item in canonicalize_browsergym_controls(raw)
            if item.role == "clickable"
        )

    assert controls(("overlay-b", "overlay-a")) == ("overlay-a",)
    assert controls(("overlay-a", "overlay-b")) == ("overlay-a",)


def test_dom_clickable_wrapper_does_not_duplicate_one_native_control() -> None:
    raw = raw_observation(
        ax_node("wrapper", "generic", "", child_ids=("check",)),
        ax_node("check", "checkbox", "Remember me", parent_id="wrapper"),
    )
    raw["extra_element_properties"]["wrapper"]["clickable"] = True

    analysis = analyze_browsergym_semantics(raw)

    assert [(item.private_bid, item.role) for item in analysis.controls] == [
        ("check", "checkbox")
    ]
    assert {item.private_bid: item.role for item in analysis.structure}["wrapper"] == "generic"


def test_dom_clickable_wrapper_with_multiple_native_controls_is_not_collapsed() -> None:
    raw = raw_observation(
        ax_node("wrapper", "generic", "", child_ids=("one", "two")),
        ax_node("one", "button", "One", parent_id="wrapper"),
        ax_node("two", "button", "Two", parent_id="wrapper"),
    )
    raw["extra_element_properties"]["wrapper"]["clickable"] = True

    controls = canonicalize_browsergym_controls(raw)

    assert {(item.private_bid, item.role) for item in controls} == {
        ("wrapper", "clickable"),
        ("one", "button"),
        ("two", "button"),
    }


def test_nested_native_wrapper_and_anchor_project_one_semantic_action() -> None:
    raw = raw_observation(
        ax_node(
            "tab-wrapper",
            "tab",
            "Bestsellers",
            properties=(("selected", True),),
            child_ids=("tab-anchor",),
        ),
        ax_node(
            "tab-anchor",
            "link",
            "Bestsellers",
            parent_id="tab-wrapper",
        ),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["tab-wrapper"]["bbox"] = [10, 20, 120, 30]
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["tab-anchor"]["bbox"] = [10, 20, 120, 30]
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["tab-anchor"]["selected"] = False

    analysis = analyze_browsergym_semantics(raw)
    projection = _projection(raw)

    assert [(item.private_bid, item.role, item.accessible_name) for item in analysis.controls] == [
        ("tab-anchor", "tab", "Bestsellers")
    ]
    assert analysis.inventory.recognized_target_count == 1
    assert dict(analysis.controls[0].public_state)["selected"] is True
    assert [(item.role, item.label) for item in _page_targets(projection.world)] == [
        ("tab", "Bestsellers")
    ]
    assert len({
        item.target_id
        for item in _page_bindings(projection.world)
        if item.semantic_action == "activate"
    }) == 1
    private_ids = {
        item.private_element_id
        for item in projection.private_bindings
        if hasattr(item, "private_element_id")
    }
    assert private_ids == {"tab-anchor"}
    assert {item.private_bid for item in analysis.structure} >= {"tab-wrapper", "tab-anchor"}


def test_native_wrapper_with_two_independent_controls_is_not_collapsed() -> None:
    raw = raw_observation(
        ax_node(
            "tab-wrapper",
            "tab",
            "Bestsellers",
            child_ids=("primary", "secondary"),
        ),
        ax_node("primary", "link", "Bestsellers", parent_id="tab-wrapper"),
        ax_node("secondary", "button", "More", parent_id="tab-wrapper"),
    )
    for bid in ("tab-wrapper", "primary", "secondary"):
        raw[PRIVATE_CONTROL_PROPERTIES_KEY][bid]["bbox"] = [10, 20, 120, 30]

    controls = canonicalize_browsergym_controls(raw)

    assert {(item.private_bid, item.role) for item in controls} == {
        ("tab-wrapper", "tab"),
        ("primary", "link"),
        ("secondary", "button"),
    }


def test_exact_duplicate_is_merged_and_conflicting_same_bid_fails_typed() -> None:
    node = ax_node("same", "button", "Save")
    raw = raw_observation(node, copy.deepcopy(node))
    assert [item.private_bid for item in canonicalize_browsergym_controls(raw)] == ["same"]

    conflict = raw_observation(
        ax_node("same", "button", "Save"),
        ax_node("same", "button", "Delete"),
    )
    with pytest.raises(BrowserGymSemanticError) as raised:
        canonicalize_browsergym_controls(conflict)
    assert raised.value.code is BrowserGymSemanticErrorCode.CONFLICTING_BID


def test_bidless_controls_are_ignored_without_cross_record_conflict() -> None:
    retained = ax_node("retained", "button", "Retained")
    one = ax_node("missing-one", "button", "Missing one")
    two = ax_node("missing-two", "textbox", "Missing two")
    baseline = raw_observation(retained, one)
    extended = raw_observation(retained, one, two)
    baseline["axtree_object"]["nodes"][1].pop("browsergym_id")
    extended["axtree_object"]["nodes"][1].pop("browsergym_id")
    extended["axtree_object"]["nodes"][2].pop("browsergym_id")

    baseline_controls = canonicalize_browsergym_controls(baseline)
    extended_controls = canonicalize_browsergym_controls(extended)

    assert baseline_controls == extended_controls
    assert [item.private_bid for item in extended_controls] == ["retained"]


def test_select_option_domains_are_owner_scoped_and_order_insensitive() -> None:
    raw = raw_observation(
        ax_node("select-a", "combobox", "First", value="A1"),
        ax_node("a1", "option", "A1"),
        ax_node("a2", "option", "A2"),
        ax_node("select-b", "combobox", "Second", value="B1"),
        ax_node("b1", "option", "B1"),
        ax_node("b2", "option", "B2"),
    )
    physical = raw[PRIVATE_CONTROL_PROPERTIES_KEY]
    physical["select-a"]["options"] = [
        {"label": "A2", "value": "private-a2"},
        {"label": "A1", "value": "private-a1"},
    ]
    physical["select-b"]["options"] = [
        {"label": "B1", "value": "private-b1"},
        {"label": "B2", "value": "private-b2"},
    ]
    controls = {item.private_bid: item for item in canonicalize_browsergym_controls(raw)}

    assert controls["select-a"].public_options == ("A1", "A2")
    assert controls["select-b"].public_options == ("B1", "B2")
    assert controls["select-a"].private_options == (
        ("A1", "private-a1"), ("A2", "private-a2"),
    )
    reordered = copy.deepcopy(raw)
    reordered[PRIVATE_CONTROL_PROPERTIES_KEY]["select-a"]["options"].reverse()
    assert canonical_control_for_bid(reordered, "select-a") == controls["select-a"]


def test_shared_option_child_and_nested_owner_graph_fail_typed() -> None:
    first = ax_node("select-a", "combobox", "First", child_ids=("shared",))
    second = ax_node("select-b", "combobox", "Second", child_ids=("shared",))
    shared = ax_node("shared", "option", "Shared", parent_id="select-a")
    raw = raw_observation(first, second, shared)
    # Preserve the held-out malformed graph after the test helper establishes
    # ordinary adjacency ownership.
    raw["axtree_object"]["nodes"][0]["childIds"] = ["shared"]
    raw["axtree_object"]["nodes"][1]["childIds"] = ["shared"]
    raw["axtree_object"]["nodes"][2]["parentId"] = "select-a"

    with pytest.raises(BrowserGymSemanticError) as raised:
        canonicalize_browsergym_controls(raw)

    assert raised.value.code is BrowserGymSemanticErrorCode.CONFLICTING_OPTION_OWNER


def test_conflicting_bidless_option_records_fail_typed_in_any_ax_order() -> None:
    owner = ax_node("select", "combobox", "Choice", child_ids=("same-node",))
    alpha = ax_node("alpha", "option", "Alpha", parent_id="select")
    beta = ax_node("beta", "option", "Beta", parent_id="select")
    alpha["nodeId"] = beta["nodeId"] = "same-node"
    alpha.pop("browsergym_id")
    beta.pop("browsergym_id")
    for option_order in ((alpha, beta), (beta, alpha)):
        raw = raw_observation(owner)
        raw["axtree_object"]["nodes"].extend(copy.deepcopy(option_order))
        with pytest.raises(BrowserGymSemanticError) as raised:
            canonicalize_browsergym_controls(raw)
        assert raised.value.code is BrowserGymSemanticErrorCode.CONFLICTING_NODE_ID


def test_distinct_bids_cannot_share_one_semantic_node_id_in_any_ax_order() -> None:
    owner = ax_node("select", "combobox", "Choice", child_ids=("same-node",))
    alpha = ax_node("option-a", "option", "Alpha", parent_id="select")
    beta = ax_node("option-b", "option", "Beta", parent_id="select")
    alpha["nodeId"] = beta["nodeId"] = "same-node"
    for option_order in ((alpha, beta), (beta, alpha)):
        raw = raw_observation(owner)
        raw["axtree_object"]["nodes"].extend(copy.deepcopy(option_order))
        with pytest.raises(BrowserGymSemanticError) as raised:
            canonicalize_browsergym_controls(raw)
        assert raised.value.code is BrowserGymSemanticErrorCode.CONFLICTING_NODE_ID


def test_duplicate_public_option_labels_and_unknown_availability_fail_closed() -> None:
    raw = raw_observation(
        ax_node("select", "combobox", "Choice"),
        ax_node("first", "option", "Duplicate"),
        ax_node("second", "option", "Duplicate"),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["select"]["options"] = [
        {"label": "Duplicate", "value": "first"},
        {"label": "Duplicate", "value": "second"},
    ]
    control = canonical_control_for_bid(raw, "select")
    assert control is not None
    assert not any(offer.semantic_action == "select_option" for offer in control.executable_offers)
    assert not any(binding.semantic_action == "select_option" for binding in _projection(raw).world.bindings)

    for field, value in (
        ("visible", False), ("enabled", False), ("readonly", True), ("editable", None),
    ):
        unavailable = raw_observation(ax_node("field", "textbox", "Name"))
        unavailable[PRIVATE_CONTROL_PROPERTIES_KEY]["field"][field] = value
        projection = _projection(unavailable)
        assert len(_page_targets(projection.world)) == 1
        assert not any(binding.semantic_action == "type_text" for binding in projection.world.bindings)


def test_duplicate_private_option_values_cannot_receive_select_binding() -> None:
    raw = raw_observation(
        ax_node("select", "combobox", "Choice"),
        ax_node("alpha", "option", "Alpha"),
        ax_node("beta", "option", "Beta"),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["select"]["options"] = [
        {"label": "Alpha", "value": "same-native"},
        {"label": "Beta", "value": "same-native"},
    ]

    control = canonical_control_for_bid(raw, "select")

    assert control is not None
    assert control.private_options == ()
    assert not any(binding.semantic_action == "select_option" for binding in _projection(raw).world.bindings)


def test_named_physical_option_outside_public_domain_cannot_receive_select_binding() -> None:
    raw = raw_observation(
        ax_node("select", "combobox", "Choice"),
        ax_node("alpha", "option", "Alpha"),
        ax_node("beta", "option", "Beta"),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["select"]["options"].append(
        {"label": "Unprojected", "value": "private-unprojected"},
    )

    control = canonical_control_for_bid(raw, "select")

    assert control is not None
    assert control.private_options == ()
    assert not any(binding.semantic_action == "select_option" for binding in _projection(raw).world.bindings)


def test_public_projection_contains_no_private_route_value_or_fingerprint() -> None:
    raw = raw_observation(
        ax_node("private-select", "combobox", "Choice", value="Public A"),
        ax_node("private-option", "option", "Public A"),
    )
    raw[PRIVATE_CONTROL_PROPERTIES_KEY]["private-select"]["options"] = [
        {"label": "Public A", "value": "native-secret-value"},
    ]
    projection = _projection(raw)
    public = repr(projection.world)
    select_binding = _binding(projection.world, "select_option")
    serialized = repr(select_binding.parameter_schema)
    select_private = next(
        item for item in projection.private_bindings
        if getattr(item, "binding_id", "") == select_binding.binding_id
    )

    for forbidden in (
        "private-select", "private-option", "native-secret-value", "selector",
        select_private.canonical_control.currentness_fingerprint,
    ):
        assert forbidden not in public
        assert forbidden not in serialized
    assert "Public A" in serialized


def test_public_fingerprint_excludes_bid_and_native_option_value() -> None:
    first = raw_observation(
        ax_node("first-private-bid", "combobox", "Choice", value="A"),
        ax_node("first-option", "option", "A"),
    )
    second = raw_observation(
        ax_node("second-private-bid", "combobox", "Choice", value="A"),
        ax_node("second-option", "option", "A"),
    )
    first[PRIVATE_CONTROL_PROPERTIES_KEY]["first-private-bid"]["options"] = [
        {"label": "A", "value": "native-one"},
    ]
    second[PRIVATE_CONTROL_PROPERTIES_KEY]["second-private-bid"]["options"] = [
        {"label": "A", "value": "native-two"},
    ]
    first_control = canonical_control_for_bid(first, "first-private-bid")
    second_control = canonical_control_for_bid(second, "second-private-bid")

    assert first_control is not None and second_control is not None
    assert first_control.public_fingerprint == second_control.public_fingerprint
    assert first_control.currentness_fingerprint != second_control.currentness_fingerprint
