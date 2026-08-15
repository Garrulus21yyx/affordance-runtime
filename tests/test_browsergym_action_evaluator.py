import asyncio
from dataclasses import replace

import numpy as np
from browsergym_adapter_support import ax_node, raw_observation, request_for, reset_task_state

from affordance_runtime.agent.evaluation_control import validated_action_evaluation
from affordance_runtime.evaluation import (
    ActionEvaluationStatus,
    ProductionActionEvaluator,
)
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.surfaces.browsergym.entity_identity import (
    BrowserGymEntityIdentityMap,
)
from affordance_runtime.surfaces.browsergym.projection import (
    project_browsergym_observation,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import CoverageState, ObservationConflict, ObservationSourceProfile

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
        world = replace(world, coverage={"browsergym": coverage}, sources=(source,))
    if weak:
        source = replace(source, source_profile=ObservationSourceProfile.visual())
        world = replace(world, sources=(source,))
    if conflict:
        target = world.targets[0]
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
    return asyncio.run(validated_action_evaluation(
        ProductionActionEvaluator(), task, before, request, result, after,
    ))


def test_fill_empty_or_different_to_desired_is_effect_confirmed() -> None:
    for current in ("", "old"):
        before = _world("obs:before", "type_text", current)
        after = _world("obs:after", "type_text", "desired")
        evaluation = _evaluate(before, after, "type_text", "desired")
        assert evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED
        assert WorldEvidenceIndex.from_observation(after).resolve(evaluation.evidence_refs[0])
        assert "obs:after" in evaluation.evidence_refs[0]


def test_fill_already_desired_or_unchanged_wrong_is_no_effect_confirmed() -> None:
    desired_before = _world("obs:before", "type_text", "desired")
    desired_after = _world("obs:after", "type_text", "desired")
    assert _evaluate(
        desired_before, desired_after, "type_text", "desired",
    ).status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED

    wrong_before = _world("obs:before", "type_text", "wrong")
    wrong_after = _world("obs:after", "type_text", "wrong")
    assert _evaluate(
        wrong_before, wrong_after, "type_text", "desired",
    ).status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED


def test_fill_uncertain_or_conflicting_post_state_is_unknown() -> None:
    before = _world("obs:before", "type_text", "old")
    cases = (
        _world("obs:after", "type_text", "desired", coverage=CoverageState.TRUNCATED),
        _world("obs:after", "type_text", "desired", conflict=True),
        _world("obs:after", "type_text", "desired", weak=True),
    )
    for after in cases:
        assert _evaluate(before, after, "type_text", "desired").status is ActionEvaluationStatus.UNKNOWN

    missing = project_browsergym_observation(
        raw_observation(ax_node("private-button", "button", "Submit")),
        observation_id="obs:after", source_revision="revision:after",
        page_identity="page:opaque", episode_identity="0",
        task_state=reset_task_state("obs:after"),
        entity_identity=_IDENTITY,
    ).world
    assert _evaluate(before, missing, "type_text", "desired").status is ActionEvaluationStatus.UNKNOWN


def test_select_transition_and_already_selected_are_symmetric() -> None:
    before = _world("obs:before", "select_option", "A")
    after = _world("obs:after", "select_option", "B")
    assert _evaluate(before, after, "select_option", "B").status is ActionEvaluationStatus.EFFECT_CONFIRMED

    satisfied_before = _world("obs:before", "select_option", "B")
    satisfied_after = _world("obs:after", "select_option", "B")
    assert _evaluate(
        satisfied_before, satisfied_after, "select_option", "B",
    ).status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED


def test_changed_to_unrequested_value_is_unknown_and_receipt_cannot_promote_it() -> None:
    before = _world("obs:before", "type_text", "old")
    after = _world("obs:after", "type_text", "other")
    evaluation = _evaluate(
        before, after, "type_text", "desired",
        adapter_evidence={"value": "desired", "receipt": "private"},
    )
    assert evaluation.status is ActionEvaluationStatus.UNKNOWN
    assert not evaluation.evidence_refs
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
    after = replace(before, observation_id="obs:after", bindings=(), sources=())
    request = request_for(before, task, "activate")
    result = ActionResult(request.request_id, DispatchStatus.SENT, "browsergym", True)
    evaluation = asyncio.run(ProductionActionEvaluator().evaluate(
        task, before, request, result, after,
    ))
    assert evaluation.status is ActionEvaluationStatus.UNKNOWN
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


def _evaluate_activate(before, after):
    task = _task()
    request = request_for(before, task, "activate")
    result = ActionResult(request.request_id, DispatchStatus.SENT, "browsergym", True)
    return asyncio.run(validated_action_evaluation(
        ProductionActionEvaluator(), task, before, request, result, after,
    ))


def test_activate_visual_change_is_effect_confirmed_with_public_diff_evidence() -> None:
    evaluation = _evaluate_activate(
        _activate_world("obs:before", 255),
        _activate_world("obs:after", 0),
    )
    assert evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED
    assert evaluation.evidence == {
        "verification_profile": "visual_diff_v1",
        "expected_effects": ["external_ui_interaction"],
        "observed_effect": "effect_confirmed",
        "screenshot_changed": True,
        "target_changed": False,
    }


def test_activate_unchanged_visual_state_is_no_effect_confirmed() -> None:
    evaluation = _evaluate_activate(
        _activate_world("obs:before", 255),
        _activate_world("obs:after", 255),
    )
    assert evaluation.status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED
    assert evaluation.evidence["screenshot_changed"] is False
    assert evaluation.evidence["target_changed"] is False
