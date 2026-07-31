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
    ExecutionReceipt,
    GestureBinding,
    Observation,
    ProgressEvidenceScope,
    Surface,
)
from affordance_runtime.planning import PlannerActionKind, PlannerProposal, bind_active_subgoal_verifiers
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
from affordance_runtime.verification import VerifierLadder, VerifierSpec


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


def _active_typed_outcome_state(
    *,
    value: str = "Myron",
    relation: SubgoalOutcomeRelation = SubgoalOutcomeRelation.EQUALS,
) -> StateKernel:
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
                    objective=f"search box value {relation.value} {value}",
                    success_criteria=(f"search box value {relation.value} {value}",),
                    evidence_requirements=("current search box value",),
                    operation_class=OperationClass.READ_ONLY,
                    action_family=TaskPlanActionFamily.TYPE_TEXT,
                    outcome=SubgoalOutcome(
                        subject="search box value",
                        relation=relation,
                        value=value,
                    ),
                ),
            ),
        )
    )
    state.activate_next_step()
    return state


def _active_completed_click_outcome_state(
    *,
    action_family: TaskPlanActionFamily | None = TaskPlanActionFamily.ACTIVATE,
) -> StateKernel:
    state = StateKernel("task-1", "Click button ONE, then click button TWO")
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
                    subgoal_id="button-one-completed",
                    objective="button ONE is completed",
                    success_criteria=("button ONE is completed",),
                    evidence_requirements=("post-click observation for button ONE",),
                    operation_class=OperationClass.NAVIGATION,
                    action_family=action_family,
                    outcome=SubgoalOutcome(
                        subject="button ONE",
                        relation=SubgoalOutcomeRelation.IS_COMPLETED,
                    ),
                ),
            ),
        )
    )
    state.activate_next_step()
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


def test_browsergym_has_changed_text_value_declares_active_subgoal_evidence() -> None:
    state = _active_typed_outcome_state(
        value="Kanesha",
        relation=SubgoalOutcomeRelation.HAS_CHANGED,
    )
    affordance = _affordance(
        "tt",
        action="fill",
        locator={"backend_handle": "14"},
        role="textbox",
        label="tt",
    )
    proposal = PlannerProposal(
        proposal_id="fill-tt",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.TYPE_TEXT,
        target_affordance_id=affordance.id,
        parameters={"text": "Kanesha"},
    )
    verifiers = [
        VerifierSpec(
            "dom_attribute",
            "14",
            {"target_attribute": "bid", "attribute": "value", "value": "Kanesha"},
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        )
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=BrowserGymAction("fill", {"bid": "14", "value": "Kanesha"}),
        affordance=affordance,
    )

    assert declared[-1].progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL


@pytest.mark.parametrize(
    ("outcome_value", "expected_scope"),
    (
        ("Myron", ProgressEvidenceScope.ACTIVE_SUBGOAL),
        ("Myr.*", ProgressEvidenceScope.TASK_TERMINAL),
        ("myron", ProgressEvidenceScope.TASK_TERMINAL),
    ),
)
def test_browsergym_typed_match_requires_exact_normalized_value(
    outcome_value: str,
    expected_scope: ProgressEvidenceScope,
) -> None:
    state = _active_typed_outcome_state(
        value=outcome_value,
        relation=SubgoalOutcomeRelation.MATCHES,
    )
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
        action=BrowserGymAction("fill", {"bid": "search", "value": "Myron"}),
        affordance=affordance,
    )

    assert declared[-1].progress_scope == expected_scope


def test_browsergym_slider_handle_progress_declares_active_subgoal_evidence() -> None:
    state = _active_typed_outcome_state(
        value="7",
        relation=SubgoalOutcomeRelation.HAS_CHANGED,
    )
    state.task_plan = state.task_plan.model_copy(
        update={
            "subgoals": (
                state.task_plan.subgoals[0].model_copy(
                    update={
                        "objective": "slider_value_7 has changed",
                        "success_criteria": ("slider_value_7 has changed",),
                        "evidence_requirements": ("current slider value",),
                        "action_family": TaskPlanActionFamily.PRESS_KEY,
                        "outcome": SubgoalOutcome(
                            subject="slider_value_7",
                            relation=SubgoalOutcomeRelation.HAS_CHANGED,
                            value="7",
                        ),
                    },
                ),
            )
        },
    )
    affordance = _affordance(
        "semantic:ui-slider-handle:123",
        action="press_key",
        locator={"backend_handle": "17"},
        role="slider",
        label="ui-slider-handle",
    )
    proposal = PlannerProposal(
        proposal_id="press-slider",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id=affordance.id,
        parameters={"key": "ArrowRight"},
    )
    verifiers = [
        VerifierSpec("evidence", "last_action_error", ""),
        VerifierSpec(
            "control_state",
            "17",
            {"field": "context_text", "changed_from": "6"},
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        ),
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=BrowserGymAction("press", {"bid": "17", "key_comb": "ArrowRight"}),
        affordance=affordance,
    )

    assert declared[-1].progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL
    assert declared[-1].expected == {"field": "context_text", "value": "7"}
    assert declared[-1].strict is False


def test_browsergym_slider_progress_uses_goal_value_when_active_step_lost_value() -> None:
    state = _active_typed_outcome_state(
        value="",
        relation=SubgoalOutcomeRelation.HAS_CHANGED,
    )
    state.goal = "Select -3 with the slider, click the 1st checkbox, then hit Submit."
    state.task_plan = state.task_plan.model_copy(
        update={
            "subgoals": (
                state.task_plan.subgoals[0].model_copy(
                    update={
                        "objective": "slider_value has changed",
                        "success_criteria": ("slider_value has changed",),
                        "evidence_requirements": ("current slider value",),
                        "action_family": TaskPlanActionFamily.PRESS_KEY,
                        "outcome": SubgoalOutcome(
                            subject="slider_value",
                            relation=SubgoalOutcomeRelation.HAS_CHANGED,
                            value="",
                        ),
                    },
                ),
            )
        },
    )
    affordance = _affordance(
        "semantic:ui-slider-handle:123",
        action="press_key",
        locator={"backend_handle": "17"},
        role="slider",
        label="ui-slider-handle",
    )
    proposal = PlannerProposal(
        proposal_id="press-slider",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.PRESS_KEY,
        target_affordance_id=affordance.id,
        parameters={"key": "ArrowRight"},
    )
    verifiers = [
        VerifierSpec("evidence", "last_action_error", ""),
        VerifierSpec(
            "control_state",
            "17",
            {"field": "context_text", "changed_from": "-9"},
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        ),
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=BrowserGymAction("press", {"bid": "17", "key_comb": "ArrowRight"}),
        affordance=affordance,
    )

    assert declared[-1] == VerifierSpec(
        "control_state",
        "17",
        {"field": "context_text", "value": "-3"},
        strict=False,
        evidence_key="slider_target:17",
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )


def test_browsergym_checkbox_click_uses_strong_control_state_progress_evidence() -> None:
    model = browsergym_dom_adapter().transduce(
        '<input bid="check-1" type="checkbox"/>',
        environment_revision="rev-1",
        snapshot_id="snapshot-1",
    )
    observation = Observation(
        "rev-1",
        snapshot_id="snapshot-1",
        page_revision=model.page_revision,
        metadata={"control_states": {"check-1": {"checked": False}}},
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
    )

    verifiers = browsergym_action_verifiers(
        BrowserGymAction("click", {"bid": "check-1"}),
        BrowserSnapshot(observation, model),
    )

    assert verifiers[-1] == VerifierSpec(
        "control_state",
        "check-1",
        {"field": "checked", "changed_from": False},
        progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
    )


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


def test_browsergym_click_completed_outcome_declares_independent_progress_evidence() -> None:
    state = _active_completed_click_outcome_state()
    affordance = _affordance(
        "semantic:one",
        action="activate",
        locator={"backend_handle": "12"},
        role="button",
        label="ONE",
    )
    proposal = PlannerProposal(
        proposal_id="click-one",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=affordance.id,
    )
    verifiers = [
        VerifierSpec("evidence", "last_action_error", ""),
        VerifierSpec(
            "state_delta_or_terminal",
            "12",
            True,
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        ),
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=BrowserGymAction("click", {"bid": "12"}),
        affordance=affordance,
    )

    assert declared[-1] == VerifierSpec(
        "observation_metadata",
        "active_control",
        "12",
        strict=False,
        progress_scope=ProgressEvidenceScope.ACTIVE_SUBGOAL,
    )
    assert declared[-2].strict is False
    assert declared[-2].progress_scope == ProgressEvidenceScope.TASK_TERMINAL


def test_browsergym_completed_click_progress_is_not_blocked_by_generic_delta_failure() -> None:
    state = _active_completed_click_outcome_state()
    affordance = _affordance(
        "semantic:one",
        action="activate",
        locator={"backend_handle": "12"},
        role="button",
        label="ONE",
    )
    proposal = PlannerProposal(
        proposal_id="click-one",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=affordance.id,
    )
    declared = declare_browsergym_active_subgoal_evidence(
        [
            VerifierSpec("evidence", "last_action_error", ""),
            VerifierSpec(
                "state_delta_or_terminal",
                "other-control",
                True,
                progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
            ),
        ],
        proposal=proposal,
        state=state,
        action=BrowserGymAction("click", {"bid": "12"}),
        affordance=affordance,
    )

    report = VerifierLadder().verify_report(
        bind_active_subgoal_verifiers(tuple(declared), state),
        ExecutionReceipt(
                "contract",
                "browsergym",
                True,
                "rev-2",
                "rev-2",
            1.0,
            evidence={"last_action_error": ""},
        ),
        Observation(
            "rev-2",
            snapshot_id="snapshot-post",
            metadata={"active_control": "12"},
        ),
    )

    assert report.passed
    assert not report.evidence[-2].passed
    assert report.evidence[-1].passed
    assert report.evidence[-1].criterion_ids == (
        "subgoal:button-one-completed:criterion:0",
    )


def test_browsergym_terminal_completed_click_does_not_require_active_control() -> None:
    state = _active_completed_click_outcome_state()
    affordance = _affordance(
        "semantic:close",
        action="activate",
        locator={"backend_handle": "12"},
        role="button",
        label="Close",
    )
    proposal = PlannerProposal(
        proposal_id="click-close",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=affordance.id,
    )
    declared = declare_browsergym_active_subgoal_evidence(
        [
            VerifierSpec("evidence", "last_action_error", ""),
            VerifierSpec(
                "state_delta_or_terminal",
                "12",
                True,
                progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
            ),
        ],
        proposal=proposal,
        state=state,
        action=BrowserGymAction("click", {"bid": "12"}),
        affordance=affordance,
    )

    report = VerifierLadder().verify_report(
        bind_active_subgoal_verifiers(tuple(declared), state),
        ExecutionReceipt(
            "contract",
            "browsergym",
            True,
            "rev-1",
            "rev-2",
            1.0,
            evidence={"last_action_error": "", "terminal_success": True},
        ),
        Observation("rev-2", snapshot_id="snapshot-post", metadata={}),
    )

    assert report.passed


def test_browsergym_click_completed_outcome_does_not_require_task_plan_action_family() -> None:
    state = _active_completed_click_outcome_state(action_family=None)
    affordance = _affordance(
        "semantic:one",
        action="activate",
        locator={"backend_handle": "12"},
        role="button",
        label="ONE",
    )
    proposal = PlannerProposal(
        proposal_id="click-one",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=affordance.id,
    )

    declared = declare_browsergym_active_subgoal_evidence(
        [
            VerifierSpec("evidence", "last_action_error", ""),
            VerifierSpec(
                "state_delta_or_terminal",
                "12",
                True,
                progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
            ),
        ],
        proposal=proposal,
        state=state,
        action=BrowserGymAction("click", {"bid": "12"}),
        affordance=affordance,
    )

    assert declared[-1].kind == "observation_metadata"
    assert declared[-1].target == "active_control"
    assert declared[-1].expected == "12"
    assert declared[-1].progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL


def test_browsergym_checkbox_has_changed_click_declares_active_subgoal_progress() -> None:
    state = StateKernel("task-1", "Move slider, then check the requested box")
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
                    subgoal_id="slider-changed",
                    objective="slider value has changed",
                    success_criteria=("slider value has changed",),
                    evidence_requirements=("post-slider observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.PRESS_KEY,
                    outcome=SubgoalOutcome(
                        subject="slider value",
                        relation=SubgoalOutcomeRelation.HAS_CHANGED,
                    ),
                ),
                SubgoalSpec(
                    subgoal_id="checkbox-changed",
                    objective="checkbox state has changed",
                    depends_on=("slider-changed",),
                    success_criteria=("checkbox state has changed",),
                    evidence_requirements=("post-checkbox observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    action_family=TaskPlanActionFamily.ACTIVATE,
                    outcome=SubgoalOutcome(
                        subject="checkbox state",
                        relation=SubgoalOutcomeRelation.HAS_CHANGED,
                    ),
                ),
            ),
        )
    )
    state.activate_next_step()
    state.complete_step("slider-changed", ("evidence:slider",))
    state.activate_next_step()
    affordance = _affordance(
        "checkbox",
        action="activate",
        locator={"backend_handle": "17"},
        role="checkbox",
        label="Checkbox state",
    )
    proposal = PlannerProposal(
        proposal_id="click-checkbox",
        based_on_task_revision=1,
        based_on_state_version=state.version,
        snapshot_id="snapshot-1",
        action_kind=PlannerActionKind.ACTIVATE,
        target_affordance_id=affordance.id,
    )
    verifiers = [
        VerifierSpec("evidence", "last_action_error", ""),
        VerifierSpec(
            "control_state",
            "17",
            {"field": "checked", "changed_from": False},
            progress_scope=ProgressEvidenceScope.TASK_TERMINAL,
        ),
    ]

    declared = declare_browsergym_active_subgoal_evidence(
        verifiers,
        proposal=proposal,
        state=state,
        action=BrowserGymAction("click", {"bid": "17"}),
        affordance=affordance,
    )

    assert declared[-1].progress_scope == ProgressEvidenceScope.ACTIVE_SUBGOAL


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
