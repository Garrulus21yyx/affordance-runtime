from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.actions import (
    ActionBinder,
    ActionBinding,
    ActionDiscoveryMatch,
    ActionDiscoveryResult,
    ActionRisk,
    ActionSpaceBuilder,
)
from affordance_runtime.agent import (
    RequestActionPage,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
)
from affordance_runtime.agent import monitor as monitor_module
from affordance_runtime.agent.attempt_signature import PublicAttemptSignature
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


def _dispatched_step(world, after=None) -> StepResult:
    after = after or world
    option = ActionSpaceBuilder().build(_task(), world).options[0]
    selection = ActionSpaceBuilder().admit(option, {})
    request = ActionBinder().bind(selection, world, "context:test", tool_call_id="call:test")
    execution = ExecutionOutcome(
        request,
        ActionResult(request.request_id, DispatchStatus.SENT, "fixture", True),
        acquired_acquisition(
            after,
            AcquisitionOrigin.POST_ACTION,
            acquisition_id="acquisition:after-dispatch",
        ),
    )
    return StepResult(
        SelectAction("context:test", option.action_id, tool_call_id="call:test"),
        world,
        after,
        _evaluation(after),
        execution_receipts=ExecutionReceiptBatch.from_atomic(execution, after.observation_id),
        feedback="action_outcome_unknown",
    )


def _evaluate(monitor: EpisodeMonitor, step: StepResult):
    return monitor.evaluate(
        step,
        current_findings_digest(step.after_world),
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


def _control_discovery_step(world, query: str, label: str) -> StepResult:
    return StepResult(
        RequestActionPage("context:test", query),
        world,
        world,
        _evaluation(world),
        feedback="action_page",
        action_page_result=ActionDiscoveryResult(
            (
                ActionDiscoveryMatch(
                    "E1",
                    label,
                    "textbox",
                    "type_text",
                    match_kinds=("lexical",),
                ),
            ),
            query,
            "complete",
            "complete",
        ),
    )


def test_control_discovery_recovery_is_not_cleared_by_a_different_query() -> None:
    world = _world("observation:control-discovery")
    monitor = EpisodeMonitor()
    monitor.start_episode(world, _evaluation(world))
    store = ObservationDeliveryStore()

    first_step = _control_discovery_step(world, "search", "Search Wikipedia")
    first = store.reduce(first_step, step_index=1)
    first_monitor = monitor.evaluate(
        first_step,
        current_findings_digest(world),
        first.information_delta,
    )
    second_step = _control_discovery_step(world, "address bar", "Search Wikipedia")
    second = first.next_store.reduce(second_step, step_index=2)
    recovery = monitor.evaluate(
        second_step,
        current_findings_digest(world),
        second.information_delta,
    )
    third_step = _control_discovery_step(world, "navigation", "Search Wikipedia")
    third = second.next_store.reduce(third_step, step_index=3)
    continued = monitor.evaluate(
        third_step,
        current_findings_digest(world),
        third.information_delta,
    )

    assert first.information_delta is None
    assert second.information_delta is None
    assert first.next_store is store
    assert second.next_store is store
    assert first_monitor.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert "do not repeat control discovery" in recovery.recovery_signal.human_instruction
    assert third.information_delta is None
    assert continued.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert continued.recovery_signal is not None
    assert continued.recovery_signal.recovery_attempt == 2
    assert monitor.recovery_count == 2


def test_control_discovery_blocks_only_the_repeated_recovery_query() -> None:
    world = _world("observation:control-discovery-repeat")
    monitor = EpisodeMonitor()
    monitor.start_episode(world, _evaluation(world))

    first = _evaluate(monitor, _control_discovery_step(world, "search", "Search Wikipedia"))
    recovery = _evaluate(
        monitor,
        _control_discovery_step(world, "address bar", "Search Wikipedia"),
    )
    blocked = _evaluate(
        monitor,
        _control_discovery_step(world, "address bar", "Search Wikipedia"),
    )

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert blocked.reason == "control_stalled"


def test_exact_local_result_replay_recovers_then_stalls() -> None:
    world = _world("observation:stable")
    step = _search_with_items(world)
    store = ObservationDeliveryStore()
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(world, _evaluation(world))

    first = store.reduce(step, step_index=1)
    store = first.next_store
    first_monitor = monitor.evaluate(
        step,
        current_findings_digest(world),
        first.information_delta,
    )
    replay = store.reduce(step, step_index=2)
    recovery = monitor.evaluate(
        step,
        current_findings_digest(world),
        replay.information_delta,
    )
    stalled = monitor.evaluate(
        step,
        current_findings_digest(world),
        replay.information_delta,
    )

    assert first.information_delta is not None
    assert first.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert first.information_delta.new_information_count == 2
    assert first_monitor.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert replay.information_delta is not None
    assert replay.information_delta.kind is InformationDeltaKind.EXACT_REPLAY
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert "returned next_cursor" in recovery.recovery_signal.human_instruction
    assert "find a current executable control" in recovery.recovery_signal.human_instruction
    assert "do not repeat control discovery" not in recovery.recovery_signal.human_instruction
    assert stalled.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert stalled.reason == "control_stalled"


def test_exact_replay_recovery_is_not_cleared_by_a_no_match_region_result() -> None:
    world = _world("observation:replay-then-different-region")
    replayed_step = _search_with_items(world)
    different_step = _local_step(world, query="different", region="R10")
    store = ObservationDeliveryStore()
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(world, _evaluation(world))

    first = store.reduce(replayed_step, step_index=1)
    monitor.evaluate(
        replayed_step,
        current_findings_digest(world),
        first.information_delta,
    )
    replay = first.next_store.reduce(replayed_step, step_index=2)
    recovery = monitor.evaluate(
        replayed_step,
        current_findings_digest(world),
        replay.information_delta,
    )
    different = replay.next_store.reduce(different_step, step_index=3)
    continued = monitor.evaluate(
        different_step,
        current_findings_digest(world),
        different.information_delta,
    )

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert different.information_delta is not None
    assert different.information_delta.kind is InformationDeltaKind.NO_MATCHES
    assert continued.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert continued.recovery_signal is not None
    assert continued.recovery_signal.recovery_attempt == 2
    assert monitor.recovery_count == 2


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
    monitor = EpisodeMonitor(AgentLoopProfile(3, 1))
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


def test_different_no_progress_attempt_after_recovery_remains_in_episode() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))

    _evaluate(monitor, _local_step(world, query="one"))
    recovery = _evaluate(monitor, _local_step(world, query="two"))
    continued = _evaluate(monitor, _local_step(world, query="three"))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert continued.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert continued.recovery_signal is not None
    assert continued.recovery_signal.recovery_attempt == 2
    assert monitor.recovery_count == 2


def test_monitor_profile_bounds_alternate_recovery_retries() -> None:
    world = _world("observation:bounded-recovery-retries")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))

    first_recovery = _evaluate(monitor, _local_step(world, query="one"))
    retry = _evaluate(monitor, _local_step(world, query="two"))
    blocked = _evaluate(monitor, _local_step(world, query="three"))

    assert first_recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert retry.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert retry.recovery_signal is not None
    assert retry.recovery_signal.recovery_attempt == 2
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert blocked.reason == "control_stalled"


def test_new_information_is_the_local_tool_event_that_clears_recovery() -> None:
    world = _world("observation:new-information-reset")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))
    recovery = _evaluate(monitor, _local_step(world))
    informative_step = _search_with_items(world)
    transition = ObservationDeliveryStore().reduce(informative_step, step_index=2)

    continued = monitor.evaluate(
        informative_step,
        current_findings_digest(world),
        transition.information_delta,
    )

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert transition.information_delta is not None
    assert transition.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert monitor.recovery_count == 0


def test_same_attempt_after_recovery_is_control_stalled() -> None:
    world = _world("observation:stable-repeat")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))

    _evaluate(monitor, _local_step(world, query="one"))
    recovery = _evaluate(monitor, _local_step(world, query="two"))
    blocked = _evaluate(monitor, _local_step(world, query="two"))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert blocked.reason == "control_stalled"
    assert blocked.recovery_signal is not None
    assert recovery.recovery_signal is not None
    assert blocked.recovery_signal.stable_signature == recovery.recovery_signal.stable_signature


def test_typed_recovery_replay_rejection_gets_one_bounded_fallback_turn() -> None:
    world = _world("observation:typed-recovery-rejection")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))

    _evaluate(monitor, _local_step(world, query="one"))
    recovery = _evaluate(monitor, _local_step(world, query="two"))
    assert recovery.recovery_signal is not None
    prohibited = recovery.recovery_signal.prohibited_attempt_signature
    assert prohibited is not None
    rejected = StepResult(
        ToolRejectedResult(
            "context:test",
            "search_page_content",
            {"query": "two"},
            {
                "kind": "recovery_repeat_rejected",
                "dispatch": "not_sent",
                "world_changed": False,
            },
            rejected_attempt_signature=prohibited,
        ),
        world,
        world,
        _evaluation(world),
        feedback="local_tool_result",
    )

    fallback = _evaluate(monitor, rejected)
    blocked = _evaluate(monitor, rejected)

    assert fallback.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert fallback.recovery_signal is not None
    assert fallback.recovery_signal.recovery_attempt == 2
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert blocked.reason == "control_stalled"


def test_untyped_world_increment_does_not_clear_a_no_progress_episode() -> None:
    first_world = _world("observation:first")
    changed_world = _world("observation:changed", route="/map/results", result_text="33 km")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(first_world, _evaluation(first_world))
    _evaluate(monitor, _local_step(first_world))
    _evaluate(monitor, _local_step(first_world))

    transition = _evaluate(monitor, _local_step(first_world, changed_world))

    assert transition.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert EpisodeMonitorEvent.STATE_CHANGED in transition.events
    assert monitor.observation_only_streak == 1
    assert monitor.recovery_count == 1


def test_findings_increment_resets_streak() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(3, 1))
    monitor.start_episode(world, _evaluation(world))
    step = _local_step(world)
    _evaluate(monitor, step)

    finding_transition = monitor.evaluate(step, "new-findings")

    assert finding_transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in finding_transition.events


def test_first_gui_dispatch_without_information_increment_records_no_progress() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))
    _evaluate(monitor, _local_step(world))

    transition = _evaluate(monitor, _dispatched_step(world))

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert monitor.observation_only_streak == 0
    assert monitor.recovery_count == 0
    assert monitor.same_attempt_streak == 1
    assert monitor.no_progress_count == 2
    assert monitor.latest_attempt_signature is not None


def test_second_same_gui_no_progress_recovers_with_existing_prohibited_signature() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(world, _evaluation(world))

    first = _evaluate(monitor, _dispatched_step(world))
    second = _evaluate(monitor, _dispatched_step(world))
    third = _evaluate(monitor, _dispatched_step(world))

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second.recovery_signal is not None
    assert third.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert second.recovery_signal.prohibited_attempt_signature == monitor.latest_attempt_signature
    assert monitor.same_attempt_streak == 3
    assert monitor.no_progress_count == 3
    assert monitor.latest_attempt_signature is not None
    assert monitor.latest_attempt_signature.digest.startswith("sha256:")


def test_effectful_gui_cycle_recovers_across_fresh_worlds_then_blocks_recurrence() -> None:
    portland = _world("observation:portland", route="/wiki/Portland_Maine")
    acadia = _world("observation:acadia", route="/wiki/Acadia_National_Park")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(portland, _evaluation(portland))

    first = _evaluate(monitor, _dispatched_step(portland, acadia))
    second = _evaluate(monitor, _dispatched_step(acadia, portland))
    third = _evaluate(monitor, _dispatched_step(portland, acadia))
    recovery = _evaluate(monitor, _dispatched_step(acadia, portland))

    assert all(
        item.recommendation is EpisodeMonitorRecommendation.CONTINUE
        for item in (first, second, third)
    )
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert EpisodeMonitorEvent.STATE_CHANGED in recovery.events
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.kind is RecoveryKind.STATE_OSCILLATION
    assert recovery.recovery_signal.observed_evidence["cycle_period"] == 2
    assert "short cycle across fresh Worlds" in recovery.recovery_signal.human_instruction

    # A local inspection does not make the effectful navigation cycle disappear.
    local = _evaluate(monitor, _local_step(portland, query="coordinates"))
    blocked = _evaluate(monitor, _dispatched_step(portland, acadia))

    assert local.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert blocked.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert blocked.reason == "state_oscillation"
    assert blocked.recovery_signal is not None
    assert blocked.recovery_signal.stable_signature == recovery.recovery_signal.stable_signature
    assert len(monitor.recent_gui_attempts) <= 6


@given(period=st.integers(min_value=2, max_value=3), rotation=st.integers(min_value=0, max_value=2))
def test_short_gui_cycle_identity_is_phase_independent(period: int, rotation: int) -> None:
    values = tuple(
        PublicAttemptSignature(
            f"operation-{index}",
            f"{index + 1:064x}",
            "",
            "",
            f"{index + 11:064x}",
        )
        for index in range(period)
    )
    shifted_by = rotation % period
    shifted = values[shifted_by:] + values[:shifted_by]

    original_digest, original_period = monitor_module._short_gui_cycle(values + values)
    shifted_digest, shifted_period = monitor_module._short_gui_cycle(shifted + shifted)

    assert original_period == shifted_period == period
    assert original_digest == shifted_digest


def test_ineffectual_gui_attempt_after_local_recovery_remains_in_episode() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))
    recovery = _evaluate(monitor, _local_step(world))

    continued = _evaluate(monitor, _dispatched_step(world))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert continued.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert continued.recovery_signal is not None
    assert continued.recovery_signal.recovery_attempt == 2
    assert continued.recovery_signal.observed_evidence["dispatch"] == "sent"
    assert monitor.recovery_count == 2


def test_causal_changed_gui_attempt_starts_fresh_episode_after_control_recovery() -> None:
    world = _world("observation:control-recovery")
    changed = _world("observation:changed-by-gui", route="/map/next")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))
    recovery = _evaluate(monitor, _local_step(world, query="first"))
    second_recovery = _evaluate(monitor, _local_step(world, query="second"))

    continued = _evaluate(monitor, _dispatched_step(world, changed))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second_recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second_recovery.recovery_signal is not None
    assert second_recovery.recovery_signal.recovery_attempt == 2
    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in continued.events
    assert continued.recovery_signal is None
    assert monitor.recovery_count == 0
    assert monitor.latest_attempt_signature is not None
    assert monitor.latest_attempt_signature.operation == "activate"
    assert monitor.same_attempt_streak == 1


def test_monitor_never_overrides_native_terminal_evaluation() -> None:
    world = _world("observation:stable")
    step = _local_step(world)
    step = StepResult(step.decision, world, world, _evaluation(world, TaskEvaluationStatus.BLOCKED), feedback=step.feedback)
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, step.task_evaluation)

    transition = _evaluate(monitor, step)

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert monitor.recovery_count == 0


def test_monitor_runtime_state_has_one_information_and_attempt_identity_contract() -> None:
    monitor = EpisodeMonitor()

    assert {
        "world_digest",
        "current_findings_digest",
        "observation_only_streak",
        "recovery_count",
        "latest_attempt_signature",
        "same_attempt_streak",
        "no_progress_count",
        "recent_gui_attempts",
        "active_gui_cycle_digest",
    } == set(vars(monitor)) - {"profile"}
