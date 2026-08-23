from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.actions import ActionBinder, ActionBinding, ActionRisk, ActionSpaceBuilder
from affordance_runtime.agent import SearchPageContentResult, SelectAction
from affordance_runtime.agent.context.observation_delivery import (
    InformationDeltaKind,
    ObservationDeliveryStore,
    current_findings_digest,
)
from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.profile import AgentLoopProfile
from affordance_runtime.agent.recovery import (
    EpisodeMonitorEvent,
    EpisodeMonitorRecommendation,
    RecoveryKind,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.workspace import AgentWorkspace, working_facts_digest
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import (
    ActionResult,
    DispatchStatus,
    ExecutionOutcome,
    ExecutionReceiptBatch,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import AcquisitionOrigin, SemanticTarget, StateFact
from tests.support.observation_acquisition import acquired_acquisition
from tests.support.world import fused_world


def _task() -> TaskGoal:
    return TaskGoal(
        "task:operational-progress",
        "Produce a visible result",
        allowed_effects=("external_ui_interaction",),
        risk_profile=RiskProfile.LOW,
    )


def _world(observation_id: str, *, route: str = "/map", result_text: str = ""):
    targets = [
        SemanticTarget("document", "document", "Map", {"page.route": route}),
        SemanticTarget("go", "button", "Go"),
    ]
    facts = [StateFact(f"fact:{observation_id}:route", "document", "page.route", route, observation_id)]
    if result_text:
        targets.append(SemanticTarget("result", "status", result_text, {"content": result_text}))
        facts.append(StateFact(f"fact:{observation_id}:result", "result", "content", result_text, observation_id))
    binding = ActionBinding(
        f"binding:{observation_id}:go",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        "fingerprint:go",
        "go",
        "go",
        "fixture",
        "fixture",
        "activate",
        "click",
        "local_reversible",
        ("external_ui_interaction",),
        {"type": "object", "properties": {}, "additionalProperties": False},
        {"fixture": "go"},
        risk=ActionRisk.LOW,
    )
    return fused_world(observation_id, tuple(targets), tuple(facts), (binding,))


def _evaluation(world, status: TaskEvaluationStatus = TaskEvaluationStatus.INCOMPLETE) -> TaskEvaluation:
    return TaskEvaluation(_task().task_id, world.observation_id, status, "fixture evaluation")


def _local_step(before, after=None, *, query: str = "route", region: str = "") -> StepResult:
    after = after or before
    arguments = {"query": query}
    if region:
        arguments["region_ref"] = region
    return StepResult(
        SearchPageContentResult(
            "context:test",
            "search_page_content",
            arguments,
            {"kind": "NoMatches", "items": (), "total_count": 0},
        ),
        before,
        after,
        _evaluation(after),
        feedback="local_tool_result",
    )


def _dispatched_step(world) -> StepResult:
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    request = ActionBinder().bind(selection, world, "context:test", tool_call_id="call:test")
    execution = ExecutionOutcome(
        request,
        ActionResult(request.request_id, DispatchStatus.SENT, "fixture", True),
        acquired_acquisition(
            world,
            AcquisitionOrigin.POST_ACTION,
            acquisition_id="acquisition:after-dispatch",
        ),
    )
    return StepResult(
        SelectAction("context:test", option.action_id, tool_call_id="call:test"),
        world,
        world,
        _evaluation(world),
        execution_receipts=ExecutionReceiptBatch.from_atomic(execution, world.observation_id),
        feedback="action_outcome_unknown",
    )


def _evaluate(monitor: EpisodeMonitor, step: StepResult):
    return monitor.evaluate(
        step,
        current_findings_digest(step.after_world),
        working_facts_digest(AgentWorkspace()),
    )


def _search_with_items(world) -> StepResult:
    return StepResult(
        SearchPageContentResult(
            "context:test",
            "search_page_content",
            {"query": "airport"},
            {
                "kind": "Matches",
                "items": (
                    {"label": "Pittsburgh International Airport", "value": "33 km"},
                    {"label": "postcode", "value": "15231"},
                ),
                "total_count": 2,
            },
        ),
        world,
        world,
        _evaluation(world),
        feedback="local_tool_result",
    )


def test_exact_local_result_replay_recovers_then_stalls() -> None:
    world = _world("observation:stable")
    step = _search_with_items(world)
    store = ObservationDeliveryStore()
    monitor = EpisodeMonitor(AgentLoopProfile(30, 8, 1))
    monitor.start_episode(world, _evaluation(world))

    first = store.reduce(step, step_index=1)
    store = first.next_store
    first_monitor = monitor.evaluate(
        step,
        current_findings_digest(world),
        working_facts_digest(AgentWorkspace()),
        first.information_delta,
    )
    replay = store.reduce(step, step_index=2)
    recovery = monitor.evaluate(
        step,
        current_findings_digest(world),
        working_facts_digest(AgentWorkspace()),
        replay.information_delta,
    )
    stalled = monitor.evaluate(
        step,
        current_findings_digest(world),
        working_facts_digest(AgentWorkspace()),
        replay.information_delta,
    )

    assert first.information_delta is not None
    assert first.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert first.information_delta.new_information_count == 2
    assert first_monitor.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert replay.information_delta is not None
    assert replay.information_delta.kind is InformationDeltaKind.EXACT_REPLAY
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert stalled.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert stalled.reason == "control_stalled"


@given(
    query=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20),
    values=st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ", min_size=1, max_size=30),
        min_size=1,
        max_size=8,
        unique=True,
    ),
)
def test_local_delivery_novelty_is_stable_for_generated_nonempty_results(query, values) -> None:
    world = _world("observation:generated-stable")
    step = StepResult(
        SearchPageContentResult(
            "context:test",
            "search_page_content",
            {"query": query},
            {
                "kind": "Matches",
                "items": tuple({"label": f"result-{index}", "value": value} for index, value in enumerate(values)),
                "total_count": len(values),
            },
        ),
        world,
        world,
        _evaluation(world),
        feedback="local_tool_result",
    )
    first = ObservationDeliveryStore().reduce(step, step_index=1)
    replay = first.next_store.reduce(step, step_index=2)

    assert first.information_delta is not None
    assert first.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert first.information_delta.new_information_count == len(values)
    assert replay.information_delta is not None
    assert replay.information_delta.kind is InformationDeltaKind.EXACT_REPLAY
    assert replay.information_delta.new_information_count == 0


def test_local_delivery_closed_algebra_covers_empty_overlap_and_new_world() -> None:
    first_world = _world("observation:algebra-first")
    second_world = _world("observation:algebra-second", route="/other")

    def step(world, query, items):
        return StepResult(
            SearchPageContentResult(
                "context:test",
                "search_page_content",
                {"query": query},
                {"kind": "Matches" if items else "NoMatches", "items": items, "total_count": len(items)},
            ),
            world,
            world,
            _evaluation(world),
            feedback="local_tool_result",
        )

    item_a = {"label": "alpha", "value": "one"}
    item_b = {"label": "beta", "value": "two"}
    store = ObservationDeliveryStore()

    empty = store.reduce(step(first_world, "missing", ()), step_index=1)
    first = empty.next_store.reduce(step(first_world, "both", (item_a, item_b)), step_index=2)
    overlap = first.next_store.reduce(step(first_world, "only beta", (item_b,)), step_index=3)
    changed_world = overlap.next_store.reduce(step(second_world, "both", (item_a, item_b)), step_index=4)

    assert empty.information_delta is not None
    assert empty.information_delta.kind is InformationDeltaKind.NO_MATCHES
    assert overlap.information_delta is not None
    assert overlap.information_delta.kind is InformationDeltaKind.NO_NEW_INFORMATION
    assert overlap.information_delta.new_information_count == 0
    assert changed_world.information_delta is not None
    assert changed_world.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert changed_world.information_delta.new_information_count == 2


def test_different_queries_and_regions_share_one_no_progress_family() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(30, 3, 1))
    monitor.start_episode(world, _evaluation(world))

    first = _evaluate(monitor, _local_step(world, query="route", region="R1"))
    second = _evaluate(monitor, _local_step(world, query="distance", region="R2"))
    recovery = _evaluate(monitor, _local_step(world, query="directions", region="R3"))

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.kind is RecoveryKind.CONTROL_STALL
    assert monitor.observation_only_streak == 0
    assert monitor.recovery_count == 1


def test_no_increment_after_recovery_is_control_stalled() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(30, 2, 1))
    monitor.start_episode(world, _evaluation(world))

    _evaluate(monitor, _local_step(world, query="one"))
    recovery = _evaluate(monitor, _local_step(world, query="two"))
    blocked = _evaluate(monitor, _local_step(world, query="three"))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert blocked.reason == "control_stalled"
    assert blocked.recovery_signal is not None
    assert recovery.recovery_signal is not None
    assert blocked.recovery_signal.stable_signature == recovery.recovery_signal.stable_signature


def test_world_increment_resets_streak_and_recovery_count() -> None:
    first_world = _world("observation:first")
    changed_world = _world("observation:changed", route="/map/results", result_text="33 km")
    monitor = EpisodeMonitor(AgentLoopProfile(30, 2, 1))
    monitor.start_episode(first_world, _evaluation(first_world))
    _evaluate(monitor, _local_step(first_world))
    _evaluate(monitor, _local_step(first_world))

    transition = _evaluate(monitor, _local_step(first_world, changed_world))

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in transition.events
    assert monitor.observation_only_streak == 0
    assert monitor.recovery_count == 0


def test_findings_or_working_fact_increment_resets_streak() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(30, 3, 1))
    monitor.start_episode(world, _evaluation(world))
    step = _local_step(world)
    _evaluate(monitor, step)

    finding_transition = monitor.evaluate(step, "new-findings", working_facts_digest(AgentWorkspace()))
    _evaluate(monitor, step)
    facts_transition = monitor.evaluate(step, current_findings_digest(world), "new-working-facts")

    assert finding_transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert facts_transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in finding_transition.events
    assert EpisodeMonitorEvent.STATE_CHANGED in facts_transition.events


def test_first_gui_dispatch_without_information_increment_records_no_progress() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(30, 2, 1))
    monitor.start_episode(world, _evaluation(world))
    _evaluate(monitor, _local_step(world))

    transition = _evaluate(monitor, _dispatched_step(world))

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert monitor.observation_only_streak == 0
    assert monitor.recovery_count == 0
    assert monitor.same_attempt_streak == 1
    assert monitor.no_progress_count == 1
    assert monitor.latest_attempt_signature is not None


def test_second_same_gui_no_progress_recovers_with_existing_prohibited_signature() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(30, 8, 1))
    monitor.start_episode(world, _evaluation(world))

    first = _evaluate(monitor, _dispatched_step(world))
    second = _evaluate(monitor, _dispatched_step(world))

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second.recovery_signal is not None
    assert second.recovery_signal.prohibited_attempt_signature == monitor.latest_attempt_signature
    assert monitor.same_attempt_streak == 2
    assert monitor.no_progress_count == 2
    assert monitor.latest_attempt_signature is not None
    assert monitor.latest_attempt_signature.digest.startswith("sha256:")


def test_dispatched_recovery_without_information_increment_is_control_stalled() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(30, 1, 1))
    monitor.start_episode(world, _evaluation(world))
    recovery = _evaluate(monitor, _local_step(world))

    blocked = _evaluate(monitor, _dispatched_step(world))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert blocked.reason == "control_stalled"


def test_monitor_never_overrides_native_terminal_evaluation() -> None:
    world = _world("observation:stable")
    step = _local_step(world)
    step = StepResult(step.decision, world, world, _evaluation(world, TaskEvaluationStatus.BLOCKED), feedback=step.feedback)
    monitor = EpisodeMonitor(AgentLoopProfile(30, 1, 1))
    monitor.start_episode(world, step.task_evaluation)

    transition = _evaluate(monitor, step)

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert monitor.recovery_count == 0


def test_monitor_runtime_state_has_one_information_and_attempt_identity_contract() -> None:
    monitor = EpisodeMonitor()

    assert {
        "world_digest",
        "current_findings_digest",
        "working_facts_digest",
        "visible_public_result_digest",
        "observation_only_streak",
        "recovery_count",
        "latest_attempt_signature",
        "same_attempt_streak",
        "no_progress_count",
    } == set(vars(monitor)) - {"profile"}
