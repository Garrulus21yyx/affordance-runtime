from __future__ import annotations

import copy

import pytest
from browsergym_adapter_support import ax_node, raw_observation
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.benchmarks.external_smoke.browsergym_entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import (
    project_browsergym_observation,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
    BrowserGymSemanticError,
    BrowserGymSemanticErrorCode,
    analyze_browsergym_semantics,
    canonical_control_for_bid,
    canonicalize_browsergym_controls,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    BrowserGymVerifierSnapshot,
)
from affordance_runtime.benchmarks.external_smoke.environment import (
    ExternalVerifierReason,
    ExternalVerifierStatus,
    VerifierFactSource,
)
from affordance_runtime.world import SemanticInventoryStatus

_IDENTITY = BrowserGymEntityIdentityMap(b"browsergym-canonical-semantics-tests")


def _snapshot() -> BrowserGymVerifierSnapshot:
    return BrowserGymVerifierSnapshot(
        "run:opaque", "obs:1", "obs:1", VerifierFactSource.RESET,
        ExternalVerifierStatus.INCOMPLETE, ExternalVerifierReason.VERIFIED_RUNNING,
    )


def _projection(raw):
    return project_browsergym_observation(
        raw,
        observation_id="obs:1",
        source_revision="revision:1",
        page_identity="page:opaque",
        episode_identity="0",
        verifier=_snapshot(),
        entity_identity=_IDENTITY,
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
    assert inventory.recognized_target_count == inventory.omitted_target_count == 1
    assert projection.world.targets == projection.world.bindings == ()


def test_dom_heuristic_fields_cannot_change_canonical_ax_equality() -> None:
    raw = raw_observation(ax_node("control", "link", "Canonical AX name"))
    raw["dom_object"] = {"role": "button", "aria-label": "conflicting DOM label"}
    first = canonical_control_for_bid(raw, "control")
    raw["dom_object"] = {"role": "textbox", "innerText": "another heuristic"}

    assert canonical_control_for_bid(raw, "control") == first


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
    assert control is not None and not control.executable
    assert not _projection(raw).world.bindings

    for field, value in (
        ("visible", False), ("enabled", False), ("readonly", True), ("editable", None),
    ):
        unavailable = raw_observation(ax_node("field", "textbox", "Name"))
        unavailable[PRIVATE_CONTROL_PROPERTIES_KEY]["field"][field] = value
        projection = _projection(unavailable)
        assert len(projection.world.targets) == 1
        assert not projection.world.bindings


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

    assert control is not None and not control.executable
    assert control.private_options == ()
    assert not _projection(raw).world.bindings


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
    serialized = repr(projection.world.bindings[0].parameter_schema)

    for forbidden in (
        "private-select", "private-option", "native-secret-value", "selector",
        projection.private_bindings[0].canonical_control.currentness_fingerprint,
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
