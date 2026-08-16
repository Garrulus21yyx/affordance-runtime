from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.surfaces.browsergym.currentness import (
    BrowserGymCurrentnessContext,
    BrowserGymCurrentnessReason,
    BrowserGymCurrentnessStatus,
    compare_browsergym_currentness,
)
from affordance_runtime.surfaces.browsergym.semantics import (
    PRIVATE_CONTROL_PROPERTIES_KEY,
    canonical_control_for_bid,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import ax_node, raw_observation


def _control(raw=None):
    value = raw or raw_observation(
        ax_node("control", "textbox", "Name", value="Ada", properties=(("required", True),)),
    )
    control = canonical_control_for_bid(value, "control")
    assert control is not None
    return control


def _context(**changes):
    value = BrowserGymCurrentnessContext(
        True, "page", "page", "episode", "episode", True, False, "fill",
    )
    return replace(value, **changes)


@given(st.sampled_from((
    ("button", "click"),
    ("link", "click"),
    ("textbox", "fill"),
    ("searchbox", "fill"),
    ("combobox", "select_option"),
    ("listbox", "select_option"),
)))
def test_every_admitted_canonical_role_is_immediately_current(role_and_primitive) -> None:
    role, primitive = role_and_primitive
    nodes = [ax_node("control", role, "Control", value="A")]
    if primitive == "select_option":
        nodes.append(ax_node("option", "option", "A", properties=(("selected", True),)))
    raw = raw_observation(*nodes)
    captured = _control(raw)
    context = replace(_context(), requested_primitive=primitive)

    decision = compare_browsergym_currentness(captured, _control(copy.deepcopy(raw)), context)

    assert decision.status is BrowserGymCurrentnessStatus.CURRENT


def test_unchanged_canonical_control_is_current_and_unrelated_ax_fields_are_ignored() -> None:
    raw = raw_observation(
        ax_node("control", "textbox", "Name", value="Ada", properties=(("required", True),)),
    )
    captured = _control(raw)
    raw["axtree_object"]["nodes"][0]["properties"].append(
        {"name": "focused", "value": {"value": True}},
    )
    live = _control(raw)

    assert compare_browsergym_currentness(captured, live, _context()).status is (
        BrowserGymCurrentnessStatus.CURRENT
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"binding_epoch_matches": False}, BrowserGymCurrentnessReason.BINDING_EPOCH_CHANGED),
        ({"live_page_identity": "other"}, BrowserGymCurrentnessReason.PAGE_CHANGED),
        ({"live_episode_identity": "other"}, BrowserGymCurrentnessReason.EPISODE_CHANGED),
        ({"task_ready": False}, BrowserGymCurrentnessReason.TASK_NOT_READY),
        ({"task_done": True}, BrowserGymCurrentnessReason.TASK_DONE),
        ({"requested_primitive": "click"}, BrowserGymCurrentnessReason.PRIMITIVE_CHANGED),
    ),
)
def test_context_drift_is_typed_stale(changes, reason) -> None:
    control = _control()
    decision = compare_browsergym_currentness(control, control, _context(**changes))
    assert (decision.status, decision.reason) == (BrowserGymCurrentnessStatus.STALE, reason)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("role", BrowserGymCurrentnessReason.ROLE_CHANGED),
        ("label", BrowserGymCurrentnessReason.LABEL_CHANGED),
        ("state", BrowserGymCurrentnessReason.STATE_CHANGED),
        ("availability", BrowserGymCurrentnessReason.NOT_EXECUTABLE),
    ),
)
def test_canonical_semantic_or_availability_drift_is_typed_stale(mutation, reason) -> None:
    raw = raw_observation(
        ax_node("control", "textbox", "Name", value="Ada", properties=(("required", True),)),
    )
    captured = _control(raw)
    live_raw = copy.deepcopy(raw)
    node = live_raw["axtree_object"]["nodes"][0]
    if mutation == "role":
        node["role"]["value"] = "searchbox"
    elif mutation == "label":
        node["name"]["value"] = "Changed"
    elif mutation == "state":
        node["value"]["value"] = "Grace"
    else:
        live_raw[PRIVATE_CONTROL_PROPERTIES_KEY]["control"]["readonly"] = True
    live = _control(live_raw)
    decision = compare_browsergym_currentness(captured, live, _context())
    assert (decision.status, decision.reason) == (BrowserGymCurrentnessStatus.STALE, reason)


def test_same_count_different_select_domain_is_stale_but_order_is_not() -> None:
    captured_raw = raw_observation(
        ax_node("control", "combobox", "Choice", value="A"),
        ax_node("a", "option", "A"),
        ax_node("b", "option", "B"),
    )
    captured = _control(captured_raw)
    reordered = copy.deepcopy(captured_raw)
    reordered[PRIVATE_CONTROL_PROPERTIES_KEY]["control"]["options"].reverse()
    assert compare_browsergym_currentness(
        captured, _control(reordered), replace(_context(), requested_primitive="select_option"),
    ).status is BrowserGymCurrentnessStatus.CURRENT

    changed = raw_observation(
        ax_node("control", "combobox", "Choice", value="A"),
        ax_node("a", "option", "A"),
        ax_node("c", "option", "C"),
    )
    decision = compare_browsergym_currentness(
        captured, _control(changed), replace(_context(), requested_primitive="select_option"),
    )
    assert decision.reason is BrowserGymCurrentnessReason.OPTION_DOMAIN_CHANGED

    private_changed = copy.deepcopy(captured_raw)
    private_changed[PRIVATE_CONTROL_PROPERTIES_KEY]["control"]["options"][1]["value"] = "private-b"
    decision = compare_browsergym_currentness(
        captured,
        _control(private_changed),
        replace(_context(), requested_primitive="select_option"),
    )
    assert decision.reason is BrowserGymCurrentnessReason.OPTION_DOMAIN_CHANGED


def test_select_currentness_uses_its_execution_requirements_not_visual_drift() -> None:
    captured_raw = raw_observation(
        ax_node("control", "combobox", "Choice", value="A"),
        ax_node("a", "option", "A"),
        ax_node("b", "option", "B"),
    )
    captured_raw[PRIVATE_CONTROL_PROPERTIES_KEY]["control"].update({
        "visible": False,
        "editable": False,
    })
    live_raw = copy.deepcopy(captured_raw)
    live_raw[PRIVATE_CONTROL_PROPERTIES_KEY]["control"].update({
        "visible": True,
        "editable": True,
    })

    decision = compare_browsergym_currentness(
        _control(captured_raw),
        _control(live_raw),
        replace(_context(), requested_primitive="select_option"),
    )

    assert decision.status is BrowserGymCurrentnessStatus.CURRENT


def test_missing_element_is_typed_stale() -> None:
    decision = compare_browsergym_currentness(_control(), None, _context())
    assert (decision.status, decision.reason) == (
        BrowserGymCurrentnessStatus.STALE,
        BrowserGymCurrentnessReason.ELEMENT_MISSING,
    )


def test_replaced_bid_is_typed_stale_even_when_public_semantics_match() -> None:
    captured = _control()
    live = replace(captured, private_bid="replacement")

    decision = compare_browsergym_currentness(captured, live, _context())

    assert (decision.status, decision.reason) == (
        BrowserGymCurrentnessStatus.STALE,
        BrowserGymCurrentnessReason.ELEMENT_MISSING,
    )
