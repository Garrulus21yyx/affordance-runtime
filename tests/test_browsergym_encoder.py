from __future__ import annotations

from dataclasses import replace

import pytest

import affordance_runtime.benchmarks.browsergym as browsergym_facade
from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.benchmarks.browsergym_action_schema import BrowserGymAction
from affordance_runtime.benchmarks.browsergym_dom import browsergym_dom_adapter
from affordance_runtime.benchmarks.browsergym_encoder import (
    BrowserGymContractBuilder,
    BrowserGymGestureEncoder,
    BrowserGymPointEncoder,
    GeneralistBrowserGymContractBuilder,
    browsergym_action_verifiers,
    browsergym_fill_value,
    browsergym_requires_keyboard_events,
    declare_browsergym_active_subgoal_evidence,
    is_sortable_list_binding,
    viewport_box,
)
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import (
    Affordance,
    AffordanceLease,
    GestureBinding,
    Observation,
    ProgressEvidenceScope,
    Surface,
)
from affordance_runtime.planning import PlannerActionKind, PlannerProposal
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
from affordance_runtime.task_planning import (
    SubgoalOutcome,
    SubgoalOutcomeRelation,
    SubgoalSpec,
    TaskPlan,
    TaskPlanActionFamily,
    TaskPlanSource,
)
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
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )


def _active_typed_outcome_state(*, value: str = "Myron") -> StateKernel:
    state = StateKernel("task-1", "Search for Myron")
    state.install_task_plan(
        TaskPlan(
            plan_id="plan-1",
            task_id=state.task_id,
            task_revision=1,
            plan_version=1,
            based_on_state_version=state.version,
            generated_by=TaskPlanSource.LLM,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="enter-search",
                    objective=f"search box value equals {value}",
                    success_criteria=(f"search box value equals {value}",),
                    evidence_requirements=("current search box value",),
                    operation_class=OperationClass.READ_ONLY,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                    outcome=SubgoalOutcome(
                        subject="search box value",
                        relation=SubgoalOutcomeRelation.EQUALS,
                        value=value,
                    ),
                ),
            ),
        )
    )
    state.active_subgoal()
    return state


def test_browsergym_exact_typed_value_declares_active_subgoal_evidence() -> None:
    state = _active_typed_outcome_state()
    affordance = _affordance(
        "search",
        action="fill",
        locator={"backend_handle": "search"},
        role="textbox",
        label="Search",
    )
    proposal = PlannerProposal(
        proposal_id="fill-search",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=affordance.id,
        parameters={"text": "Myron"},
    )
    action = BrowserGymAction("fill", {"bid": "search", "value": "Myron"})
    verifiers = [
        VerifierSpec(
            "dom_attribute",
            "search",
            {"target_attribute": "bid", "attribute": "value", "value": "Myron"},
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        )
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=action,
        affordance=affordance,
    )

    assert declared[-1].progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL
    assert verifiers[-1].progress_scope == ProgressEvidenceScope.TASK_TERMINAL


def test_generalist_builder_wires_exact_typed_value_scope() -> None:
    model = browsergym_dom_adapter().transduce(
        '<input bid="search" type="text" placeholder="Search"/>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )
    state = _active_typed_outcome_state()
    state.remember_observation(observation)
    task = TaskSpec(
        task_id=state.task_id,
        revision=1,
        objective="Search for Myron",
        operation_class=OperationClass.READ_ONLY,
        targets=("Search",),
        success_criteria=("search results are shown",),
        source_request_ref="test",
    )
    proposal = PlannerProposal(
        proposal_id="fill-search",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=model.affordances[0].id,
        parameters={"text": "Myron"},
    )

    contract = GeneralistBrowserGymContractBuilder().build(
        proposal,
        task,
        state,
        BrowserSnapshot(observation, model),
    )

    assert contract.action == "fill"
    assert contract.verifier_plan[-1].progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL


def test_browsergym_generic_state_delta_cannot_advance_active_subgoal() -> None:
    state = _active_typed_outcome_state()
    affordance = _affordance(
        "search",
        action="activate",
        locator={"backend_handle": "search"},
        role="button",
        label="Search",
    )
    proposal = PlannerProposal(
        proposal_id="click-search",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=affordance.id,
    )
    verifiers = [
        VerifierSpec(
            "state_delta_or_terminal",
            "search",
            True,
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        )
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=BrowserGymAction("click", {"bid": "search"}),
        affordance=affordance,
    )

    assert declared[-1].progress_scope == ProgressEvidenceScope.TASK_TERMINAL


@pytest.mark.parametrize(
    ("outcome_value", "label"),
    [("Ada", "Search"), ("Myron", "Display name")],
)
def test_browsergym_mismatched_value_or_target_cannot_advance_typed_subgoal(
    outcome_value: str,
    label: str,
) -> None:
    state = _active_typed_outcome_state(value=outcome_value)
    affordance = _affordance(
        "input",
        action="fill",
        locator={"backend_handle": "input"},
        role="textbox",
        label=label,
    )
    proposal = PlannerProposal(
        proposal_id="fill-input",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=affordance.id,
        parameters={"text": "Myron"},
    )
    action = BrowserGymAction("fill", {"bid": "input", "value": "Myron"})
    verifiers = [
        VerifierSpec(
            "dom_attribute",
            "input",
            {"target_attribute": "bid", "attribute": "value", "value": "Myron"},
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        )
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=action,
        affordance=affordance,
    )

    assert declared[-1].progress_scope == ProgressEvidenceScope.TASK_TERMINAL
