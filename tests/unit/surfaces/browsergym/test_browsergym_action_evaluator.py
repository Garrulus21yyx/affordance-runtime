import asyncio
from dataclasses import replace

import numpy as np
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from affordance_runtime.actions.capabilities import VerificationFamily
from affordance_runtime.agent.evaluation_control import validated_action_outcome
from affordance_runtime.evaluation import (
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    ProductionActionOutcomeProjector,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionResult, DispatchStatus, ExecutionTransition
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.surfaces.browsergym.semantics import MAX_SEMANTIC_TEXT
from affordance_runtime.surfaces.browsergym.transition import BrowserGymStabilityStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationConflict,
    ObservationSourceProfile,
    StateFact,
    WorldFusion,
    VALUE_TRUNCATED_STATE_KEY,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    FakeBrowserGym,
    ax_node,
    open_fake,
    raw_observation,
    request_for,
    reset_task_state,
    start_environment,
    task_info,
)
from tests.support.surfaces.browsergym.projection_support import (
    project_browsergym_observation,
)

_IDENTITY = BrowserGymEntityIdentityMap(b"browsergym-action-evaluator-tests")


def _task() -> TaskGoal:
    return TaskGoal(
        "task:local", "Enter a value", allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )


def _world(
    observation_id: str,
    semantic: str,
    value: str,
    *,
    coverage: CoverageState = CoverageState.COMPLETE,
    conflict: bool = False,
    weak: bool = False,
):
    if semantic == "type_text":
        nodes = (ax_node("private-text", "textbox", "Input", value=value),)
    else:
        nodes = (
            ax_node("private-list", "combobox", "Choice", value=value),
            ax_node("private-a", "option", "A"),
            ax_node("private-b", "option", "B"),
        )
    snapshot = reset_task_state(observation_id)
    world = project_browsergym_observation(
        raw_observation(*nodes), observation_id=observation_id,
        source_revision=f"revision:{observation_id}", page_identity="page:opaque",
        episode_identity="0", task_state=snapshot,
        entity_identity=_IDENTITY,
    ).world
    source = world.sources[0]
    if coverage != CoverageState.COMPLETE:
        source = replace(source, coverage=coverage)
    if weak:
        source = replace(
            source,
            source_profile=ObservationSourceProfile.visual(),
            visual_only_target_ids=tuple(target.target_id for target in source.targets),
        )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    world = fused.observation
    if conflict:
        target = next(item for item in world.targets if item.role in {"textbox", "combobox"})
        world = replace(world, conflicts=(
            ObservationConflict("conflict:value", target.target_id, "value", "material conflict"),
        ))
    return world


def _evaluate(before, after, semantic: str, requested: str, *, adapter_evidence=None):
    task = _task()
    parameter_name = "text" if semantic == "type_text" else "value"
    request = request_for(before, task, semantic, {parameter_name: requested})
    result = ActionResult(
        request.request_id, DispatchStatus.SENT, "browsergym", True,
        adapter_evidence=adapter_evidence or {},
    )
    return asyncio.run(validated_action_outcome(
        ProductionActionOutcomeProjector(), task, before, request, result, after,
    ))


def test_fill_empty_or_different_to_desired_is_changed_and_satisfied() -> None:
    for current in ("", "old"):
        before = _world("obs:before", "type_text", current)
        after = _world("obs:after", "type_text", "desired")
        evaluation = _evaluate(before, after, "type_text", "desired")
        assert evaluation.observed_change is ObservedChange.CHANGED
        assert evaluation.local_postcondition is LocalPostconditionStatus.SATISFIED
        assert evaluation.evidence_method is EvidenceMethod.NATIVE
        assert WorldEvidenceIndex.from_observation(after).resolve(evaluation.evidence_refs[0])
        assert "obs:after" in evaluation.evidence_refs[0]


def test_fill_exact_echo_is_satisfied_but_unequal_text_echo_remains_unknown() -> None:
    desired_before = _world("obs:before", "type_text", "desired")
    desired_after = _world("obs:after", "type_text", "desired")
    assert _evaluate(
        desired_before, desired_after, "type_text", "desired",
    ).observed_change is ObservedChange.UNCHANGED
    assert _evaluate(
        desired_before, desired_after, "type_text", "desired",
    ).local_postcondition is LocalPostconditionStatus.SATISFIED

    wrong_before = _world("obs:before", "type_text", "wrong")
    wrong_after = _world("obs:after", "type_text", "wrong")
    wrong = _evaluate(
        wrong_before, wrong_after, "type_text", "desired",
    )
    assert wrong.observed_change is ObservedChange.UNCHANGED
    assert wrong.local_postcondition is LocalPostconditionStatus.UNKNOWN


def test_fill_uncertain_or_conflicting_post_state_is_unknown() -> None:
    before = _world("obs:before", "type_text", "old")
    cases = (
        _world("obs:after", "type_text", "desired", coverage=CoverageState.TRUNCATED),
        _world("obs:after", "type_text", "desired", conflict=True),
        _world("obs:after", "type_text", "desired", weak=True),
    )
    for after in cases:
        evaluation = _evaluate(before, after, "type_text", "desired")
        assert evaluation.observed_change is ObservedChange.UNKNOWN
        assert evaluation.local_postcondition is LocalPostconditionStatus.UNKNOWN

    missing = project_browsergym_observation(
        raw_observation(ax_node("private-button", "button", "Submit")),
        observation_id="obs:after", source_revision="revision:after",
        page_identity="page:opaque", episode_identity="0",
        task_state=reset_task_state("obs:after"),
        entity_identity=_IDENTITY,
    ).world
    evaluation = _evaluate(before, missing, "type_text", "desired")
    assert evaluation.observed_change is ObservedChange.UNKNOWN
    assert evaluation.local_postcondition is LocalPostconditionStatus.UNKNOWN


def test_select_transition_and_already_selected_are_symmetric() -> None:
    before = _world("obs:before", "select_option", "A")
    after = _world("obs:after", "select_option", "B")
    selected = _evaluate(before, after, "select_option", "B")
    assert selected.observed_change is ObservedChange.CHANGED
    assert selected.local_postcondition is LocalPostconditionStatus.SATISFIED

    satisfied_before = _world("obs:before", "select_option", "B")
    satisfied_after = _world("obs:after", "select_option", "B")
    already = _evaluate(
        satisfied_before, satisfied_after, "select_option", "B",
    )
    assert already.observed_change is ObservedChange.UNCHANGED
    assert already.local_postcondition is LocalPostconditionStatus.SATISFIED

    wrong_before = _world("obs:before", "select_option", "A")
    wrong_after = _world("obs:after", "select_option", "A")
    wrong = _evaluate(wrong_before, wrong_after, "select_option", "B")
    assert wrong.observed_change is ObservedChange.UNCHANGED
    assert wrong.local_postcondition is LocalPostconditionStatus.UNSATISFIED


def test_changed_to_unrequested_value_is_unknown_and_receipt_cannot_promote_it() -> None:
    before = _world("obs:before", "type_text", "old")
    after = _world("obs:after", "type_text", "other")
    evaluation = _evaluate(
        before, after, "type_text", "desired",
        adapter_evidence={"value": "desired", "receipt": "private"},
    )
    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.UNKNOWN
    assert evaluation.evidence_refs
    assert "private" not in repr(evaluation)


@given(
    requested=st.text(min_size=1, max_size=40),
    observed=st.text(max_size=40),
)
@settings(max_examples=24)
def test_unequal_text_echo_never_becomes_a_hard_local_failure(
    requested: str,
    observed: str,
) -> None:
    assume(requested != observed)
    before = _world("obs:before", "type_text", observed)
    after = _world("obs:after", "type_text", observed)

    evaluation = _evaluate(before, after, "type_text", requested)

    assert evaluation.local_postcondition is LocalPostconditionStatus.UNKNOWN


def test_truncated_value_prefix_cannot_prove_exact_text_satisfaction() -> None:
    raw_value = "x" * (MAX_SEMANTIC_TEXT + 1)
    requested = raw_value[:MAX_SEMANTIC_TEXT]
    before = _world("obs:before", "type_text", "old")
    after = _world("obs:after", "type_text", raw_value)
    target = next(item for item in after.targets if item.role == "textbox")

    assert target.state["value"] == requested
    assert target.state[VALUE_TRUNCATED_STATE_KEY] is True
    evaluation = _evaluate(before, after, "type_text", requested)
    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.UNKNOWN


def test_activate_remains_unknown_without_terminal_evidence() -> None:
    task = _task()
    before = project_browsergym_observation(
        raw_observation(ax_node("private-button", "button", "Submit")),
        observation_id="obs:before", source_revision="revision:before",
        page_identity="page:opaque", episode_identity="0",
        task_state=reset_task_state("obs:before"),
        entity_identity=_IDENTITY,
    ).world
    after = project_browsergym_observation(
        raw_observation(ax_node("private-button", "button", "Submit")),
        observation_id="obs:after", source_revision="revision:after",
        page_identity="page:opaque", episode_identity="0",
        task_state=reset_task_state("obs:after"),
        entity_identity=_IDENTITY,
    ).world
    request = request_for(before, task, "activate")
    result = ActionResult(request.request_id, DispatchStatus.SENT, "browsergym", True)
    evaluation = asyncio.run(ProductionActionOutcomeProjector().evaluate(
        task, before, request, result, after,
    ))
    assert evaluation.observed_change is ObservedChange.UNKNOWN
    assert evaluation.local_postcondition is LocalPostconditionStatus.UNKNOWN
    assert not evaluation.evidence_refs


def test_typed_stable_navigation_selects_current_world_verification_for_semantic_keypress() -> None:
    task = _task()
    before = _activate_structural_world("obs:before", False)
    after = _activate_structural_world("obs:after", True)
    request = request_for(before, task, "press_key", {"key": "Enter"})
    assert request.selection.verification_contract.family is VerificationFamily.SEMANTIC

    private_trace_only = ActionResult(
        request.request_id,
        DispatchStatus.SENT,
        "browsergym",
        True,
        adapter_evidence={"browsergym_transition": {"stability_status": "stable_navigation"}},
    )
    unknown = asyncio.run(
        validated_action_outcome(
            ProductionActionOutcomeProjector(),
            task,
            before,
            request,
            private_trace_only,
            after,
        )
    )
    assert unknown.observed_change is ObservedChange.UNKNOWN

    stable_navigation = replace(
        private_trace_only,
        causal_transition=ExecutionTransition.STABLE_NAVIGATION,
    )
    evaluation = asyncio.run(
        validated_action_outcome(
            ProductionActionOutcomeProjector(),
            task,
            before,
            request,
            stable_navigation,
            after,
        )
    )

    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.NOT_APPLICABLE
    assert evaluation.evidence_method is EvidenceMethod.STRUCTURAL
    assert evaluation.evidence_refs
    assert all(
        WorldEvidenceIndex.from_observation(after).resolve(ref) is not None
        for ref in evaluation.evidence_refs
    )


def test_browsergym_stable_navigation_reaches_projector_with_fresh_world_evidence() -> None:
    before_raw = raw_observation(ax_node("button", "button", "Search"))
    before_raw["screenshot"] = np.full((40, 80, 3), 255, dtype=np.uint8)
    after_raw = raw_observation(
        ax_node("button", "button", "Search"),
        url="https://example.invalid/search?q=Acadia",
    )
    after_raw["screenshot"] = np.zeros((40, 80, 3), dtype=np.uint8)
    fake = FakeBrowserGym(before_raw, after_raw)
    fake.step_stability_status = BrowserGymStabilityStatus.STABLE_NAVIGATION
    fake.probe_override = {
        "raw": before_raw,
        "task": {**task_info(), "url": before_raw["url"]},
        "latency_ms": 0.1,
    }
    environment, task = open_fake(fake)
    before = start_environment(environment, task)
    request = request_for(before, task, "press_key", {"key": "Enter"})
    assert request.selection.verification_contract.family is VerificationFamily.SEMANTIC

    execution = asyncio.run(environment.execute(request))
    assert execution.post_acquisition is not None
    assert execution.post_acquisition.observation is not None
    after = execution.post_acquisition.observation
    evaluation = asyncio.run(
        validated_action_outcome(
            ProductionActionOutcomeProjector(),
            task,
            before,
            request,
            execution.result,
            after,
        )
    )

    assert execution.result.causal_transition is ExecutionTransition.STABLE_NAVIGATION
    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.evidence_method is EvidenceMethod.VISUAL_DIFF
    assert WorldEvidenceIndex.from_observation(after).resolve(evaluation.evidence_refs[0])
    asyncio.run(environment.close())


def _activate_world(observation_id: str, shade: int, *, private_id: str = "private-button"):
    raw = raw_observation(ax_node(private_id, "button", "Target"))
    raw["screenshot"] = np.full((40, 80, 3), shade, dtype=np.uint8)
    return project_browsergym_observation(
        raw,
        observation_id=observation_id,
        source_revision=f"revision:{observation_id}",
        page_identity="page:opaque",
        episode_identity="0",
        task_state=reset_task_state(observation_id),
        entity_identity=_IDENTITY,
    ).world


def _activate_structural_world(
    observation_id: str,
    active: bool,
    *,
    private_id: str = "private-button",
):
    world = _activate_world(observation_id, 255, private_id=private_id)
    source = world.sources[0]
    target = next(item for item in source.targets if item.role == "button")
    active_fact = StateFact(
        f"fact:{observation_id}:active",
        target.target_id,
        "active",
        active,
        source.observation_id,
    )
    facts = tuple(
        item
        for item in source.facts
        if not (item.subject_id == target.target_id and item.predicate == "active")
    ) + (active_fact,)
    source = replace(
        source,
        targets=tuple(
            replace(item, state={**item.state, "active": active})
            if item.target_id == target.target_id
            else item
            for item in source.targets
        ),
        facts=facts,
        entity_inventory=replace(
            source.entity_inventory,
            fact_count=len(facts),
            fact_total_count=len(facts),
        ),
    )
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return fused.observation


def _evaluate_activate(before, after):
    task = _task()
    request = request_for(before, task, "activate")
    result = ActionResult(request.request_id, DispatchStatus.SENT, "browsergym", True)
    return asyncio.run(validated_action_outcome(
        ProductionActionOutcomeProjector(), task, before, request, result, after,
    ))


def test_activate_visual_change_is_changed_with_public_diff_evidence() -> None:
    evaluation = _evaluate_activate(
        _activate_world("obs:before", 255),
        _activate_world("obs:after", 0),
    )
    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.NOT_APPLICABLE
    assert evaluation.evidence_method is EvidenceMethod.VISUAL_DIFF
    assert evaluation.evidence == {
        "verification_profile": "visual_diff_v1",
        "expected_effects": ["external_ui_interaction"],
        "observed_change": "changed",
        "local_postcondition": "not_applicable",
        "screenshot_changed": True,
        "target_changed": False,
    }


def test_activate_target_state_change_keeps_public_before_after_fact_delta() -> None:
    before = _activate_structural_world("obs:before", False)
    after = _activate_structural_world("obs:after", True)

    evaluation = _evaluate_activate(before, after)

    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.NOT_APPLICABLE
    assert evaluation.evidence_method is EvidenceMethod.STRUCTURAL
    assert evaluation.evidence["verification_profile"] == "structural_target_diff_v1"
    button = next(item for item in before.targets if item.role == "button")
    assert evaluation.evidence["fact_changes"] == (
        {
            "kind": "modified",
            "subject_id": button.target_id,
            "predicate": "active",
            "before": False,
            "after": True,
            "before_region_key": evaluation.public_world_delta.fact_changes[0].before_region_key,
            "after_region_key": evaluation.public_world_delta.fact_changes[0].after_region_key,
        },
    )


def test_activate_target_feedback_excludes_unrelated_world_changes() -> None:
    before = _activate_structural_world("obs:before", False)
    after = _activate_structural_world("obs:after", True)
    before_source = before.sources[0]
    after_source = after.sources[0]
    unrelated_before = replace(
        next(item for item in before_source.targets if item.role == "button"),
        target_id="target:unrelated",
        role="generic",
        label="Other",
        state={"viewport.visible": True},
    )
    unrelated_after = replace(
        unrelated_before,
        state={"viewport.visible": False},
    )
    before_fact = StateFact(
        "fact:before:unrelated",
        unrelated_before.target_id,
        "viewport.visible",
        True,
        before_source.observation_id,
    )
    after_fact = replace(
        before_fact,
        fact_id="fact:after:unrelated",
        value=False,
        source_id=after_source.observation_id,
    )
    before_source = replace(
        before_source,
        targets=(*before_source.targets, unrelated_before),
        facts=(*before_source.facts, before_fact),
        semantic_inventory=replace(
            before_source.semantic_inventory,
            recognized_target_count=4,
            projected_target_count=4,
            actionable_target_count=3,
            non_executable_target_count=1,
            informational_target_count=1,
        ),
        entity_inventory=replace(
            before_source.entity_inventory,
            entity_count=4,
            entity_total_count=4,
            fact_count=2,
            fact_total_count=2,
        ),
    )
    after_source = replace(
        after_source,
        targets=(*after_source.targets, unrelated_after),
        facts=(*after_source.facts, after_fact),
        semantic_inventory=replace(
            after_source.semantic_inventory,
            recognized_target_count=4,
            projected_target_count=4,
            actionable_target_count=3,
            non_executable_target_count=1,
            informational_target_count=1,
        ),
        entity_inventory=replace(
            after_source.entity_inventory,
            entity_count=4,
            entity_total_count=4,
            fact_count=2,
            fact_total_count=2,
        ),
    )
    before = WorldFusion().fuse((before_source,)).observation
    after = WorldFusion().fuse((after_source,)).observation
    assert before is not None and after is not None

    evaluation = _evaluate_activate(before, after)

    assert evaluation.evidence["verification_profile"] == "structural_target_diff_v1"
    button = next(item for item in before.targets if item.role == "button")
    assert all(
        change["subject_id"] == button.target_id
        for change in evaluation.evidence["fact_changes"]
    )


def test_activate_unchanged_visual_state_reports_unchanged_not_applicable() -> None:
    evaluation = _evaluate_activate(
        _activate_world("obs:before", 255),
        _activate_world("obs:after", 255),
    )
    assert evaluation.observed_change is ObservedChange.UNCHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.NOT_APPLICABLE
    assert evaluation.evidence["screenshot_changed"] is False
    assert evaluation.evidence["target_changed"] is False


def test_activate_identity_churn_with_same_semantics_and_screenshot_is_unchanged() -> None:
    before = _activate_world("obs:before-rekey", 255, private_id="before-private-button")
    after = _activate_world("obs:after-rekey", 255, private_id="after-private-button")

    evaluation = _evaluate_activate(before, after)

    assert evaluation.public_world_delta is not None
    assert evaluation.public_world_delta.changed
    assert not evaluation.public_world_delta.semantic_changed
    assert evaluation.observed_change is ObservedChange.UNCHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.NOT_APPLICABLE
    assert evaluation.evidence_method is EvidenceMethod.VISUAL_DIFF
    assert evaluation.evidence["screenshot_changed"] is False
    assert evaluation.evidence["target_changed"] is False
    assert len(evaluation.evidence_refs) == 1


def test_activate_semantic_change_with_rekeyed_target_uses_structural_evidence_without_screenshot() -> None:
    before = _activate_structural_world(
        "obs:before-rekeyed-change",
        False,
        private_id="before-private-button",
    )
    after = _activate_structural_world(
        "obs:after-rekeyed-change",
        True,
        private_id="after-private-button",
    )
    before = replace(
        before,
        sources=tuple(replace(source, media=()) for source in before.sources),
    )
    after = replace(
        after,
        sources=tuple(replace(source, media=()) for source in after.sources),
    )

    evaluation = _evaluate_activate(before, after)

    assert evaluation.public_world_delta is not None
    assert evaluation.public_world_delta.semantic_changed
    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.evidence_method is EvidenceMethod.STRUCTURAL
    assert evaluation.evidence["verification_profile"] == "structural_world_diff_v2"
    assert evaluation.evidence["target_changed"] is True
    assert evaluation.evidence["structural_world_changed"] is True
    assert evaluation.evidence["fact_changes"]
