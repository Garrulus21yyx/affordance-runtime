from __future__ import annotations

from dataclasses import fields

from affordance_runtime.actions import ActionBinder, ActionBinding, ActionRisk, ActionSpaceBuilder
from affordance_runtime.agent import ReadRegionResult, SearchPageContentResult, SelectAction
from affordance_runtime.agent.attempt_signature import public_attempt_signature
from affordance_runtime.agent.context import AgentTurnView
from affordance_runtime.agent.core_loop import _repeats_recovery_signature
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import (
    ActionResult,
    DispatchStatus,
    ExecutionOutcome,
    ExecutionReceiptBatch,
)
from affordance_runtime.mission import (
    EpisodeMonitor,
    EpisodeMonitorEvent,
    EpisodeMonitorRecommendation,
    Milestone,
    PlannerRecoveryView,
    RecoveryKind,
    RecoverySignal,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import AcquisitionOrigin, SemanticTarget, StateFact
from affordance_runtime.world.public_semantic_digest import public_page_semantic_digest
from tests.support.observation_acquisition import acquired_acquisition
from tests.support.world import fused_world


def _task() -> TaskGoal:
    return TaskGoal(
        "task:operational-progress",
        "Produce a visible result",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )


def _world(
    observation_id: str,
    *,
    focused: bool = False,
    route: str = "/map",
    result_text: str = "",
    target_id: str = "go",
    target_label: str = "Go",
    appearance: str = "gray",
    extra_control: bool = False,
):
    document = SemanticTarget("document", "document", "Map", {"page.route": route})
    button = SemanticTarget(
        target_id,
        "button",
        target_label,
        {"focused": focused, "appearance.color_family": appearance},
    )
    targets = [document, button]
    facts = [
        StateFact(f"fact:{observation_id}:route", "document", "page.route", route, observation_id),
        StateFact(f"fact:{observation_id}:focus", target_id, "focused", focused, observation_id),
        StateFact(
            f"fact:{observation_id}:appearance",
            target_id,
            "appearance.color_family",
            appearance,
            observation_id,
        ),
    ]
    if result_text:
        targets.append(SemanticTarget("route-result", "status", result_text, {"content": result_text}))
        facts.append(
            StateFact(
                f"fact:{observation_id}:result",
                "route-result",
                "content",
                result_text,
                observation_id,
            )
        )
    binding = ActionBinding(
        f"binding:{observation_id}:{target_id}",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        f"fingerprint:{target_id}",
        target_id,
        target_id,
        "fixture",
        "fixture",
        "activate",
        "click",
        "local_reversible",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"fixture": target_id},
        risk=ActionRisk.LOW,
    )
    bindings = [binding]
    if extra_control:
        targets.append(SemanticTarget("route-details", "button", "Route details"))
        bindings.append(
            ActionBinding(
                f"binding:{observation_id}:route-details",
                observation_id,
                observation_id,
                f"revision:{observation_id}",
                "fingerprint:route-details",
                "route-details",
                "route-details",
                "fixture",
                "fixture",
                "activate",
                "click",
                "local_reversible",
                ("external_ui_interaction",),
                {"type": "object", "properties": {}, "additionalProperties": False},
                {"fixture": "route-details"},
                risk=ActionRisk.LOW,
            )
        )
    return fused_world(
        observation_id,
        tuple(targets),
        tuple(facts),
        tuple(bindings),
    )


def _step(
    before,
    after,
    *,
    observed_change: ObservedChange,
    postcondition: LocalPostconditionStatus,
    method: EvidenceMethod,
    target_id: str = "go",
) -> StepResult:
    task = _task()
    option = next(item for item in ActionSpaceBuilder().build(task, before).options if item.target_id == target_id)
    selection = ActionSpaceBuilder().admit(option, {})
    request = ActionBinder().bind(selection, before, "context:test", tool_call_id="call:test")
    execution = ExecutionOutcome(
        request,
        ActionResult(request.request_id, DispatchStatus.SENT, "fixture", True),
        acquired_acquisition(
            after,
            AcquisitionOrigin.POST_ACTION,
            acquisition_id=f"acquisition:{after.observation_id}",
        ),
    )
    evidence_ref = after.facts[0].fact_id
    outcome = ActionOutcome(
        request.request_id,
        before.observation_id,
        after.observation_id,
        observed_change,
        postcondition,
        method,
        "fixture action outcome",
        (evidence_ref,),
        {
            "screenshot_changed": method is EvidenceMethod.VISUAL_DIFF,
            "target_changed": False,
        },
    )
    return StepResult(
        SelectAction("context:test", option.action_id, tool_call_id="call:test"),
        before,
        after,
        TaskEvaluation(
            task.task_id,
            after.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "result not yet complete",
        ),
        execution_receipts=ExecutionReceiptBatch.from_atomic(
            execution,
            after.observation_id,
        ),
        action_outcome=outcome,
        feedback="action_outcome_unknown",
    )


def _local_step(before, after, name: str = "search_page_content", *, result=None) -> StepResult:
    task = _task()
    return StepResult(
        (SearchPageContentResult if name == "search_page_content" else ReadRegionResult)(
            "context:test",
            name,
            {"query": "route"},
            result or {"kind": "NoMatches", "items": (), "total_count": 0},
        ),
        before,
        after,
        TaskEvaluation(
            task.task_id,
            after.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "result not yet complete",
        ),
        feedback="local_tool_result",
    )


def test_page_fingerprint_ignores_textbox_value_focus_and_appearance() -> None:
    empty = _world("observation:empty", focused=False, appearance="gray")
    edited = _world("observation:edited", focused=True, appearance="blue")

    assert public_page_semantic_digest(empty) == public_page_semantic_digest(edited)


def test_route_regression_survives_interleaved_local_and_rejected_steps() -> None:
    page_a = _world("observation:a", route="/map")
    page_b = _world("observation:b", route="/map/search")
    page_c = _world("observation:c", route="/map/place")
    monitor = EpisodeMonitor()

    monitor.evaluate(
        _step(
            page_a,
            page_b,
            observed_change=ObservedChange.CHANGED,
            postcondition=LocalPostconditionStatus.SATISFIED,
            method=EvidenceMethod.STRUCTURAL,
        ),
        (),
        "full:b",
    )
    monitor.evaluate(_local_step(page_b, page_b, "read_region"), (), "full:b")
    monitor.evaluate(
        _step(
            page_b,
            page_c,
            observed_change=ObservedChange.CHANGED,
            postcondition=LocalPostconditionStatus.SATISFIED,
            method=EvidenceMethod.STRUCTURAL,
        ),
        (),
        "full:c",
    )
    monitor.evaluate(_local_step(page_c, page_c, "search_page_content"), (), "full:c")
    monitor.evaluate(
        _local_step(
            page_c,
            page_c,
            "tool_rejected",
            result={
                "kind": "operation_mismatch",
                "dispatch": "not_sent",
                "supported_operations": ("type_text", "press_key"),
            },
        ),
        (),
        "full:c",
    )
    transition = monitor.evaluate(
        _step(
            page_c,
            page_a,
            observed_change=ObservedChange.CHANGED,
            postcondition=LocalPostconditionStatus.SATISFIED,
            method=EvidenceMethod.STRUCTURAL,
        ),
        (),
        "full:a",
    )

    assert transition.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert EpisodeMonitorEvent.ROUTE_REGRESSION in transition.events
    assert len(monitor.route_history) == 7


def test_return_to_page_with_new_retained_result_is_not_regression() -> None:
    page_a = _world("observation:a", route="/map")
    page_b = _world(
        "observation:b",
        route="/map/result",
        result_text="Driving distance 33 km",
    )
    monitor = EpisodeMonitor()

    monitor.evaluate(
        _step(
            page_a,
            page_b,
            observed_change=ObservedChange.CHANGED,
            postcondition=LocalPostconditionStatus.SATISFIED,
            method=EvidenceMethod.STRUCTURAL,
        ),
        (),
        "full:b",
    )
    transition = monitor.evaluate(
        _step(
            page_b,
            page_a,
            observed_change=ObservedChange.CHANGED,
            postcondition=LocalPostconditionStatus.SATISFIED,
            method=EvidenceMethod.STRUCTURAL,
        ),
        (),
        "full:a",
    )

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.ROUTE_REGRESSION not in transition.events


def test_typed_attempt_signature_blocks_exact_rejected_repeat() -> None:
    world = _world("observation:attempt")
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    signature = public_attempt_signature(
        selection.semantic_action,
        selection.target_id,
        selection.destination_id,
        selection.parameters,
        world,
    )
    signal = RecoverySignal(
        RecoveryKind.GROUNDING_STALL,
        "operation-mismatch",
        {"kind": "operation_mismatch"},
        prohibited_attempt_signature=signature,
        human_instruction="Change the operation before the next dispatch.",
    )

    assert _repeats_recovery_signature(signal, selection, world)
    assert not _repeats_recovery_signature(
        RecoverySignal(
            RecoveryKind.GROUNDING_STALL,
            "different-operation",
            {},
            prohibited_attempt_signature=public_attempt_signature(
                "press_key",
                selection.target_id,
                selection.destination_id,
                {"key": "Enter"},
                world,
            ),
        ),
        selection,
        world,
    )


def test_visual_and_focus_only_change_recover_second_then_yield_after_recovery() -> None:
    before = _world("observation:before", focused=False)
    after = _world("observation:after", focused=True)
    step = _step(
        before,
        after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.NOT_APPLICABLE,
        method=EvidenceMethod.VISUAL_DIFF,
    )
    monitor = EpisodeMonitor()

    first = monitor.evaluate(step, (), "fresh:one")
    second = monitor.evaluate(step, (), "fresh:two")
    third = monitor.evaluate(step, (), "fresh:three")

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.NO_OBSERVED_CHANGE in first.events
    assert EpisodeMonitorEvent.STATE_CHANGED not in first.events
    assert second.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert third.recommendation is EpisodeMonitorRecommendation.YIELD
    assert second.recovery_signal is not None
    assert third.recovery_signal is not None
    assert second.recovery_signal.stable_signature == third.recovery_signal.stable_signature
    assert second.recovery_signal.observed_evidence["repeat_count"] == 2
    assert third.recovery_signal.observed_evidence["repeat_count"] == 3
    assert second.recovery_signal.observed_evidence["operational_progress"] is False
    assert second.recovery_signal.observed_evidence["new_structural_evidence"] is False
    assert second.recovery_signal.observed_evidence["attempt"] == {
        "operation": "activate",
        "target": {"role": "button", "label": "Go"},
        "destination": {},
        "parameters": {},
    }


def test_appearance_only_change_is_not_operational_progress() -> None:
    before = _world("observation:before", appearance="gray")
    after = _world("observation:after", appearance="blue")
    step = _step(
        before,
        after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.VISUAL_DIFF,
    )

    transition = EpisodeMonitor().evaluate(step, (), "fresh")

    assert EpisodeMonitorEvent.NO_OBSERVED_CHANGE in transition.events
    assert EpisodeMonitorEvent.STATE_CHANGED not in transition.events


def test_satisfied_postcondition_resets_visual_no_progress_streak() -> None:
    before = _world("observation:before", focused=False)
    focused = _world("observation:focused", focused=True)
    no_progress = _step(
        before,
        focused,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.VISUAL_DIFF,
    )
    satisfied = _step(
        before,
        focused,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.SATISFIED,
        method=EvidenceMethod.NATIVE,
    )
    monitor = EpisodeMonitor()

    assert monitor.evaluate(no_progress, (), "fresh:one").recommendation is EpisodeMonitorRecommendation.CONTINUE
    progress = monitor.evaluate(satisfied, (), "fresh:two")
    assert progress.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in progress.events
    assert monitor.evaluate(no_progress, (), "fresh:three").recommendation is EpisodeMonitorRecommendation.CONTINUE


def test_structural_result_and_navigation_reset_no_progress_streak() -> None:
    before = _world("observation:before")
    focused = _world("observation:focused", focused=True)
    no_progress = _step(
        before,
        focused,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.NOT_APPLICABLE,
        method=EvidenceMethod.VISUAL_DIFF,
    )
    result_world = _world("observation:result", result_text="Route distance 33.0 km")
    result_progress = _step(
        before,
        result_world,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.STRUCTURAL,
    )
    navigated = _world("observation:navigated", route="/map/directions")
    navigation_progress = _step(
        before,
        navigated,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.NOT_APPLICABLE,
        method=EvidenceMethod.STRUCTURAL,
    )
    monitor = EpisodeMonitor()

    monitor.evaluate(no_progress, (), "fresh:one")
    transition = monitor.evaluate(result_progress, (), "fresh:result")
    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in transition.events
    assert (
        monitor.evaluate(no_progress, (), "fresh:after-result").recommendation is EpisodeMonitorRecommendation.CONTINUE
    )

    transition = monitor.evaluate(navigation_progress, (), "fresh:navigation")
    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    regression = monitor.evaluate(no_progress, (), "fresh:after-navigation")
    assert regression.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert EpisodeMonitorEvent.ROUTE_REGRESSION in regression.events


def test_new_structured_executable_control_is_operational_progress() -> None:
    before = _world("observation:before")
    after = _world("observation:after", extra_control=True)
    step = _step(
        before,
        after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.STRUCTURAL,
    )

    transition = EpisodeMonitor().evaluate(step, (), "fresh")

    assert EpisodeMonitorEvent.STATE_CHANGED in transition.events
    assert EpisodeMonitorEvent.NO_OBSERVED_CHANGE not in transition.events


def test_different_semantic_target_does_not_fold_into_same_streak() -> None:
    first_before = _world("observation:first-before", target_id="go")
    first_after = _world("observation:first-after", focused=True, target_id="go")
    other_before = _world("observation:other-before", target_id="retry", target_label="Retry")
    other_after = _world(
        "observation:other-after",
        focused=True,
        target_id="retry",
        target_label="Retry",
    )
    first = _step(
        first_before,
        first_after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.VISUAL_DIFF,
        target_id="go",
    )
    other = _step(
        other_before,
        other_after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.VISUAL_DIFF,
        target_id="retry",
    )
    monitor = EpisodeMonitor()

    assert monitor.evaluate(first, (), "fresh:first").recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert monitor.evaluate(other, (), "fresh:other").recommendation is EpisodeMonitorRecommendation.CONTINUE


def test_recovery_signature_is_ref_free_bounded_and_deterministic() -> None:
    before = _world("observation:before")
    after = _world("observation:after", focused=True)
    step = _step(
        before,
        after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.VISUAL_DIFF,
    )

    signals = []
    for _ in range(2):
        monitor = EpisodeMonitor()
        monitor.evaluate(step, (), "fresh:one")
        transition = monitor.evaluate(step, (), "fresh:two")
        assert transition.recovery_signal is not None
        signals.append(transition.recovery_signal)

    assert signals[0].stable_signature == signals[1].stable_signature
    assert len(signals[0].stable_signature) < 100
    encoded = str(signals[0].observed_evidence)
    assert "observation:" not in encoded
    assert "binding:" not in encoded
    assert "request:" not in encoded


def test_planner_recovery_view_preserves_typed_signal_without_inventing_outcome_proposal() -> None:
    before = _world("observation:before")
    after = _world("observation:after", focused=True)
    step = _step(
        before,
        after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.UNKNOWN,
        method=EvidenceMethod.VISUAL_DIFF,
    )
    monitor = EpisodeMonitor()
    monitor.evaluate(step, (), "fresh:one")
    recovered = monitor.evaluate(step, (), "fresh:two")
    assert recovered.recovery_signal is not None
    milestone = Milestone("route_result", "Requested route result is available", "Route result is visible")

    view = PlannerRecoveryView(
        "needs_replan",
        True,
        milestone,
        recovered.recovery_signal,
    )

    assert view.recovery_signal is recovered.recovery_signal
    assert tuple(item.name for item in fields(PlannerRecoveryView)) == (
        "exit_kind",
        "world_changed",
        "prior_milestone",
        "recovery_signal",
        "attempted_modes",
        "audit_guidance",
        "outcome_proposal",
        "working_proposal_feedback",
    )
    assert view.outcome_proposal == ""
    encoded = str(view)
    assert "trajectory" not in encoded
    assert "screenshot" not in encoded
    assert "provider_reasoning" not in encoded


def test_model_history_world_fingerprints_are_not_route_authority() -> None:
    before = _world("observation:before", route="/map/a")
    after = _world("observation:after", route="/map/b")
    step = _step(
        before,
        after,
        observed_change=ObservedChange.CHANGED,
        postcondition=LocalPostconditionStatus.NOT_APPLICABLE,
        method=EvidenceMethod.STRUCTURAL,
    )
    recent = (
        AgentTurnView(
            "selectaction",
            "activate",
            transition={"before_world_fingerprint": "world:a", "after_world_fingerprint": "world:b"},
        ),
        AgentTurnView(
            "selectaction",
            "activate",
            transition={"before_world_fingerprint": "world:b", "after_world_fingerprint": "world:c"},
        ),
    )

    transition = EpisodeMonitor().evaluate(step, recent, "world:b")

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert transition.recovery_signal is None


def test_large_local_result_is_digest_only_in_recovery_signal() -> None:
    world = _world("observation:world")
    evaluation = TaskEvaluation(
        _task().task_id,
        world.observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "ongoing",
    )
    marker = "large-private-body-" + "x" * 20_000
    step = StepResult(
        SearchPageContentResult(
            "context:test",
            "search_page_content",
            {"query": "route"},
            {"kind": "Matches", "items": ({"content": marker},), "total_count": 1},
        ),
        world,
        world,
        evaluation,
        feedback="local_tool_result",
    )
    monitor = EpisodeMonitor()
    monitor.evaluate(step, (), "fresh:one")
    transition = monitor.evaluate(step, (), "fresh:two")

    assert transition.recovery_signal is not None
    signal_text = str(transition.recovery_signal)
    assert marker not in signal_text
    assert "result_digest" in signal_text
    assert len(transition.recovery_signal.stable_signature) < 100
