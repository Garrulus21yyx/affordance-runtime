from dataclasses import replace

from affordance_runtime.actions import (
    AdmittedActionSelection,
)
from affordance_runtime.agent.progress_control import (
    ProgressController,
    SelectionProgressDisposition,
    SemanticAttemptKey,
)
from affordance_runtime.evaluation import (
    ActionEvaluationStatus,
    CriterionEvaluation,
    CriterionEvaluationStatus,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.world import (
    CoverageState,
    ObservationConflict,
    ObservationSourceProfile,
    SemanticTarget,
    StateFact,
    SurfaceObservation,
    WorldFusion,
    WorldObservation,
)


def _selection(value: str = "desired", *, action_id: str = "action:one", semantic_action: str = "type_text"):
    return AdmittedActionSelection(
        action_id,
        "observation:one",
        semantic_action,
        "target:textbox",
        "local_reversible",
        ("value_changed",),
        "schema:digest",
        ("binding:one",),
        "low",
        True,
        {"text": value} if semantic_action == "type_text" else {"value": value},
    )


def _world(
    observation_id: str,
    value: str,
    *,
    coverage: CoverageState = CoverageState.COMPLETE,
    structural: bool = True,
    conflict: bool = False,
) -> WorldObservation:
    target = SemanticTarget("target:textbox", "textbox", "Text", {"value": value})
    fact = StateFact(f"fact:{observation_id}:value", target.target_id, "value", value, observation_id)
    profile = ObservationSourceProfile.dom() if structural else ObservationSourceProfile.visual()
    source = SurfaceObservation(
        observation_id,
        "dom" if structural else "visual",
        f"revision:{observation_id}",
        profile,
        (target,),
        (fact,),
        (),
        coverage,
        visual_only_target_ids=((target.target_id,) if not structural else ()),
    )
    conflicts = (
        ObservationConflict("conflict:value", target.target_id, "value", "material disagreement"),
    ) if conflict else ()
    fused = WorldFusion().fuse((source,))
    assert fused.observation is not None
    return replace(fused.observation, conflicts=conflicts)


def _task_evaluation(observation_id: str, *, satisfied: bool = False) -> TaskEvaluation:
    criterion = CriterionEvaluation(
        "criterion:one",
        CriterionEvaluationStatus.SATISFIED if satisfied else CriterionEvaluationStatus.UNSATISFIED,
        (f"fact:{observation_id}:value",) if satisfied else (),
        "evaluated",
    )
    return TaskEvaluation(
        "task:one",
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "incomplete",
        (criterion,),
    )


def test_semantic_attempt_key_is_stable_and_private_value_free() -> None:
    first = SemanticAttemptKey.from_selection(_selection("secret-user-value"))
    second = SemanticAttemptKey.from_selection(
        replace(
            _selection("secret-user-value", action_id="action:two"),
            observation_id="observation:two",
            eligible_binding_ids=("binding:two",),
        )
    )
    different = SemanticAttemptKey.from_selection(_selection("different"))

    assert first == second
    assert first != different
    assert first.canonical_parameter_digest.startswith("sha256:")
    assert "secret-user-value" not in repr(first)


def test_current_fill_and_select_are_suppressed_then_repeat_terminates() -> None:
    for semantic_action in ("type_text", "select_option"):
        controller = ProgressController()
        world = _world("observation:one", "desired")
        evaluation = _task_evaluation(world.observation_id)
        selection = _selection(semantic_action=semantic_action)

        first = controller.assess(selection, world, evaluation)
        second = controller.assess(selection, world, evaluation)

        assert first.disposition is SelectionProgressDisposition.ALREADY_SATISFIED
        assert first.event is not None
        assert first.event.strategy_transition_required is True
        assert second.disposition is SelectionProgressDisposition.TERMINATE_NO_PROGRESS
        assert controller.same_attempt_streak == 2


def test_incomplete_or_conflicting_public_state_does_not_suppress() -> None:
    selection = _selection()
    cases = (
        _world("observation:truncated", "desired", coverage=CoverageState.TRUNCATED),
        _world("observation:visual", "desired", structural=False),
        _world("observation:conflict", "desired", conflict=True),
        _world("observation:different", "other"),
    )
    for world in cases:
        result = ProgressController().assess(selection, world, _task_evaluation(world.observation_id))
        assert result.disposition is SelectionProgressDisposition.EXECUTE


def test_activate_is_never_pre_suppressed() -> None:
    world = _world("observation:one", "desired")
    result = ProgressController().assess(
        _selection(semantic_action="activate"), world, _task_evaluation(world.observation_id)
    )
    assert result.disposition is SelectionProgressDisposition.EXECUTE


def test_progress_change_different_attempt_and_effect_reset_streak() -> None:
    controller = ProgressController()
    world = _world("observation:one", "desired")
    initial = _task_evaluation(world.observation_id)
    controller.assess(_selection(), world, initial)

    progressed = _task_evaluation(world.observation_id, satisfied=True)
    assert controller.assess(_selection(), world, progressed).disposition is SelectionProgressDisposition.ALREADY_SATISFIED
    assert controller.same_attempt_streak == 1

    assert controller.assess(_selection("other"), world, initial).disposition is SelectionProgressDisposition.EXECUTE
    assert controller.same_attempt_streak == 0

    controller.assess(_selection(), world, initial)
    controller.record_action_outcome(_selection(), ActionEvaluationStatus.EFFECT_CONFIRMED, world, initial)
    assert controller.same_attempt_streak == 0


def test_no_effect_records_no_progress_but_unknown_alone_does_not() -> None:
    world = _world("observation:one", "other")
    evaluation = _task_evaluation(world.observation_id)
    selection = _selection()
    controller = ProgressController()

    controller.record_action_outcome(
        selection, ActionEvaluationStatus.NO_EFFECT_CONFIRMED, world, evaluation
    )
    assert controller.no_progress_count == 1
    assert controller.latest_attempt_key == SemanticAttemptKey.from_selection(selection)
    repeated = controller.assess(selection, world, evaluation)
    assert repeated.disposition is SelectionProgressDisposition.TERMINATE_NO_PROGRESS
    assert controller.same_attempt_streak == 2

    controller = ProgressController()
    controller.record_action_outcome(selection, ActionEvaluationStatus.UNKNOWN, world, evaluation)
    assert controller.no_progress_count == 0
    assert controller.latest_attempt_key is None

    satisfied = _world("observation:satisfied", "desired")
    controller.record_action_outcome(
        selection,
        ActionEvaluationStatus.UNKNOWN,
        satisfied,
        _task_evaluation(satisfied.observation_id),
    )
    assert controller.no_progress_count == 1


def test_controller_retains_only_digests_not_raw_parameter_values() -> None:
    controller = ProgressController()
    selection = _selection("do-not-retain-me")
    world = _world("observation:one", "do-not-retain-me")
    controller.assess(selection, world, _task_evaluation(world.observation_id))
    representation = repr(controller)
    assert "do-not-retain-me" not in representation
    assert "binding:one" not in representation
