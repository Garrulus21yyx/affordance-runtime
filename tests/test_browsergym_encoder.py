from __future__ import annotations

from dataclasses import replace

import pytest

import affordance_runtime.benchmarks.browsergym as browsergym_facade
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.benchmarks.browsergym_action_schema import BrowserGymAction
from affordance_runtime.benchmarks.browsergym_encoder import (
    BrowserGymContractBuilder,
    BrowserGymGestureEncoder,
    BrowserGymPointEncoder,
    GeneralistBrowserGymContractBuilder,
    browsergym_action_verifiers,
    browsergym_fill_value,
    browsergym_requires_keyboard_events,
    is_sortable_list_binding,
    viewport_box,
)
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import Affordance, AffordanceLease, GestureBinding, Observation, Surface
from affordance_runtime.verification import VerifierSpec


def _affordance(
    affordance_id: str,
    *,
    action: str,
    locator: dict[str, object],
    role: str = "region",
    label: str = "target",
) -> Affordance:
    return Affordance(
        affordance_id,
        Surface.DOM,
        role,
        label,
        action,
        locator,
        AffordanceLease.issue(environment_revision="rev-1"),
        backend_candidates=["browsergym"],
    )


def test_browsergym_facade_preserves_encoder_compatibility_exports() -> None:
    assert browsergym_facade.BrowserGymContractBuilder is BrowserGymContractBuilder
    assert browsergym_facade.BrowserGymGestureEncoder is BrowserGymGestureEncoder
    assert browsergym_facade.BrowserGymPointEncoder is BrowserGymPointEncoder
    assert browsergym_facade.GeneralistBrowserGymContractBuilder is GeneralistBrowserGymContractBuilder
    assert browsergym_facade._browsergym_action_verifiers is browsergym_action_verifiers
    assert browsergym_facade._browsergym_fill_value is browsergym_fill_value
    assert browsergym_facade._browsergym_requires_keyboard_events is browsergym_requires_keyboard_events
    assert browsergym_facade._is_sortable_list_binding is is_sortable_list_binding
    assert browsergym_facade._viewport_box is viewport_box


@pytest.mark.parametrize(
    "value",
    [None, [], [1, 2, 3], [0, 0, 0, 1], [-1, 0, 1, 1], [0, 0, "wide", 1]],
)
def test_viewport_box_rejects_incomplete_or_unsafe_geometry(value: object) -> None:
    assert viewport_box(value) is None


def test_gesture_encoder_uses_only_current_binding_handles_for_dom_drag() -> None:
    source = _affordance("source", action="drag", locator={"backend_handle": "from"})
    destination = _affordance("destination", action="drop", locator={"backend_handle": "to"})

    action = BrowserGymGestureEncoder().encode(GestureBinding(source, destination))

    assert action == BrowserGymAction("drag_and_drop", {"from_bid": "from", "to_bid": "to"})


def test_gesture_encoder_fails_closed_without_handles_or_viewport_geometry() -> None:
    source = _affordance("source", action="drag", locator={})
    destination = _affordance("destination", action="drop", locator={"bbox": [10, 10, 0, 20]})

    with pytest.raises(ValueError, match="requires bids or viewport geometry"):
        BrowserGymGestureEncoder().encode(GestureBinding(source, destination))


def test_point_encoder_prefers_a_bound_handle_and_rejects_invalid_geometry() -> None:
    bound = _affordance(
        "bound",
        action="point_activate",
        locator={"backend_handle": "current", "bbox": [10, 20, 30, 40]},
    )
    invalid = _affordance(
        "invalid",
        action="point_activate",
        locator={"bbox": [-1, 20, 30, 40]},
    )

    assert BrowserGymPointEncoder().encode(bound) == BrowserGymAction("click", {"bid": "current"})
    with pytest.raises(ValueError, match="requires a bid or viewport geometry"):
        BrowserGymPointEncoder().encode(invalid)


def test_native_value_encoding_is_generic_and_invalid_values_are_not_invented() -> None:
    assert browsergym_fill_value({"input_type": "date"}, "07/22/2026") == "2026-07-22"
    assert browsergym_fill_value({"input_type": "time"}, "7:05 PM") == "19:05"
    assert browsergym_fill_value({"input_type": "date"}, "not-a-date") == "not-a-date"
    assert browsergym_fill_value({}, "verbatim") == "verbatim"


def test_eventful_typing_requires_current_typed_search_state() -> None:
    search = replace(
        _affordance("search", action="fill", locator={"backend_handle": "search"}, label="Search items"),
        state={"focused": True, "element_tag": "input"},
    )

    assert browsergym_requires_keyboard_events(search) is True
    assert browsergym_requires_keyboard_events(replace(search, state={**search.state, "focused": False})) is False


def test_press_verifier_binds_the_pre_action_scroll_state() -> None:
    model = DomAdapter().transduce("<main></main>", environment_revision="rev-1")
    observation = Observation(
        "rev-1",
        page_revision=model.page_revision,
        metadata={
            "control_states": {
                "region": {"scroll_top": 25, "scroll_height": 500, "client_height": 100}
            }
        },
    )
    snapshot = BrowserSnapshot(observation, model)

    verifiers = browsergym_action_verifiers(
        BrowserGymAction("press", {"bid": "region", "key_comb": "PageDown"}),
        snapshot,
    )

    assert verifiers[-1].target == "region"
    assert verifiers[-1].expected == {"field": "scroll_top", "changed_from": 25}


def test_click_verifier_requires_the_observed_disclosure_toggle() -> None:
    model = DomAdapter().transduce("<main></main>", environment_revision="rev-1")
    snapshot = BrowserSnapshot(
        Observation(
            "rev-1",
            page_revision=model.page_revision,
            metadata={"control_states": {"section": {"aria_expanded": "false"}}},
        ),
        model,
    )

    verifiers = browsergym_action_verifiers(
        BrowserGymAction("click", {"bid": "section"}),
        snapshot,
    )

    assert verifiers[-1] == VerifierSpec(
        "control_state",
        "section",
        {"field": "aria_expanded", "value": "true"},
    )
