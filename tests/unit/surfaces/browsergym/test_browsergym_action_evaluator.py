import asyncio
from dataclasses import replace

import numpy as np

from affordance_runtime.agent.evaluation_control import validated_action_outcome
from affordance_runtime.evaluation import (
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    ProductionActionOutcomeProjector,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationConflict,
    ObservationSourceProfile,
    StateFact,
    WorldFusion,
)
from tests.support.surfaces.browsergym.browsergym_adapter_support import (
    ax_node,
    raw_observation,
    request_for,
    reset_task_state,
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


def test_fill_already_desired_or_unchanged_wrong_splits_effect_and_postcondition() -> None:
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
    assert wrong.local_postcondition is LocalPostconditionStatus.UNSATISFIED


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


def test_changed_to_unrequested_value_is_unknown_and_receipt_cannot_promote_it() -> None:
    before = _world("obs:before", "type_text", "old")
    after = _world("obs:after", "type_text", "other")
    evaluation = _evaluate(
        before, after, "type_text", "desired",
        adapter_evidence={"value": "desired", "receipt": "private"},
    )
    assert evaluation.observed_change is ObservedChange.CHANGED
    assert evaluation.local_postcondition is LocalPostconditionStatus.UNSATISFIED
    assert evaluation.evidence_refs
    assert "private" not in repr(evaluation)


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


def _activate_world(observation_id: str, shade: int):
    raw = raw_observation(ax_node("private-button", "button", "Target"))
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


def _activate_structural_world(observation_id: str, active: bool):
    world = _activate_world(observation_id, 255)
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
            "subject_id": button.target_id,
            "predicate": "active",
            "before": False,
            "after": True,
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
