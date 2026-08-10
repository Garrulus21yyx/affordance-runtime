import asyncio
from dataclasses import replace

from browsergym_adapter_support import ax_node, raw_observation, request_for

from affordance_runtime.agent.evaluation_control import validated_action_evaluation
from affordance_runtime.benchmarks.external_smoke.browsergym_action_evaluator import (
    BrowserGymMechanicalActionEvaluator,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_projection import (
    project_browsergym_observation,
)
from affordance_runtime.benchmarks.external_smoke.browsergym_verifier import (
    BrowserGymVerifierSnapshot,
)
from affordance_runtime.benchmarks.external_smoke.environment import ExternalVerifierStatus
from affordance_runtime.evaluation import ActionEvaluationStatus
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution import ActionResult, DispatchStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import CoverageState, ObservationConflict, ObservationSourceProfile


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
    if semantic == "fill":
        nodes = (ax_node("private-text", "textbox", "Input", value=value),)
    else:
        nodes = (
            ax_node("private-list", "combobox", "Choice", value=value),
            ax_node("private-a", "option", "A"),
            ax_node("private-b", "option", "B"),
        )
    snapshot = BrowserGymVerifierSnapshot(
        "run:opaque", observation_id, observation_id, ExternalVerifierStatus.INCOMPLETE, "",
    )
    world = project_browsergym_observation(
        raw_observation(*nodes), observation_id=observation_id,
        source_revision=f"revision:{observation_id}", page_identity="page:opaque",
        episode_identity="0", verifier=snapshot,
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
    request = request_for(before, task, semantic, {"value": requested})
    result = ActionResult(
        request.request_id, DispatchStatus.SENT, "browsergym", True,
        adapter_evidence=adapter_evidence or {},
    )
    return asyncio.run(validated_action_evaluation(
        BrowserGymMechanicalActionEvaluator(), task, before, request, result, after,
    ))


def test_fill_empty_or_different_to_desired_is_effect_confirmed() -> None:
    for current in ("", "old"):
        before = _world("obs:before", "fill", current)
        after = _world("obs:after", "fill", "desired")
        evaluation = _evaluate(before, after, "fill", "desired")
        assert evaluation.status is ActionEvaluationStatus.EFFECT_CONFIRMED
        assert WorldEvidenceIndex.from_observation(after).resolve(evaluation.evidence_refs[0])
        assert "obs:after" in evaluation.evidence_refs[0]


def test_fill_already_desired_or_unchanged_wrong_is_no_effect_confirmed() -> None:
    desired_before = _world("obs:before", "fill", "desired")
    desired_after = _world("obs:after", "fill", "desired")
    assert _evaluate(
        desired_before, desired_after, "fill", "desired",
    ).status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED

    wrong_before = _world("obs:before", "fill", "wrong")
    wrong_after = _world("obs:after", "fill", "wrong")
    assert _evaluate(
        wrong_before, wrong_after, "fill", "desired",
    ).status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED


def test_fill_uncertain_or_conflicting_post_state_is_unknown() -> None:
    before = _world("obs:before", "fill", "old")
    cases = (
        _world("obs:after", "fill", "desired", coverage=CoverageState.TRUNCATED),
        _world("obs:after", "fill", "desired", conflict=True),
        _world("obs:after", "fill", "desired", weak=True),
    )
    for after in cases:
        assert _evaluate(before, after, "fill", "desired").status is ActionEvaluationStatus.UNKNOWN

    missing = project_browsergym_observation(
        raw_observation(ax_node("private-button", "button", "Submit")),
        observation_id="obs:after", source_revision="revision:after",
        page_identity="page:opaque", episode_identity="0",
        verifier=BrowserGymVerifierSnapshot(
            "run:opaque", "obs:after", "obs:after", ExternalVerifierStatus.INCOMPLETE, "",
        ),
    ).world
    assert _evaluate(before, missing, "fill", "desired").status is ActionEvaluationStatus.UNKNOWN


def test_select_transition_and_already_selected_are_symmetric() -> None:
    before = _world("obs:before", "select", "A")
    after = _world("obs:after", "select", "B")
    assert _evaluate(before, after, "select", "B").status is ActionEvaluationStatus.EFFECT_CONFIRMED

    satisfied_before = _world("obs:before", "select", "B")
    satisfied_after = _world("obs:after", "select", "B")
    assert _evaluate(
        satisfied_before, satisfied_after, "select", "B",
    ).status is ActionEvaluationStatus.NO_EFFECT_CONFIRMED


def test_changed_to_unrequested_value_is_unknown_and_receipt_cannot_promote_it() -> None:
    before = _world("obs:before", "fill", "old")
    after = _world("obs:after", "fill", "other")
    evaluation = _evaluate(
        before, after, "fill", "desired",
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
        verifier=BrowserGymVerifierSnapshot(
            "run:opaque", "obs:before", "obs:before", ExternalVerifierStatus.INCOMPLETE, "",
        ),
    ).world
    after = replace(before, observation_id="obs:after", bindings=(), sources=())
    request = request_for(before, task, "activate")
    result = ActionResult(request.request_id, DispatchStatus.SENT, "browsergym", True)
    evaluation = asyncio.run(BrowserGymMechanicalActionEvaluator().evaluate(
        task, before, request, result, after,
    ))
    assert evaluation.status is ActionEvaluationStatus.UNKNOWN
    assert not evaluation.evidence_refs
