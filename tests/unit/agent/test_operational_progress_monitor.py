from __future__ import annotations

import asyncio
from dataclasses import replace

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
    ReadRegionResult,
    RequestActionPage,
    RequestObservation,
    SearchPageContentResult,
    SelectAction,
    ToolRejectedResult,
)
from affordance_runtime.agent import monitor as monitor_module
from affordance_runtime.agent.attempt_signature import PublicAttemptSignature
from affordance_runtime.agent.context.compact_world_renderer import (
    Empty,
    InvalidCursor,
    inspect_outcome_public,
)
from affordance_runtime.agent.context.observation_delivery import (
    InformationDeltaKind,
    ObservationDeliveryStore,
    current_findings_digest,
)
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.evaluation_control import validated_action_outcome
from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.profile import AgentLoopProfile
from affordance_runtime.agent.recovery import (
    EpisodeMonitorEvent,
    EpisodeMonitorRecommendation,
    RecoveryKind,
    RecoveryLifecycleTransition,
)
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation import (
    ActionOutcome,
    EvidenceMethod,
    LocalPostconditionStatus,
    ObservedChange,
    ProductionActionOutcomeProjector,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.execution import (
    ActionResult,
    DispatchStatus,
    ExecutionOutcome,
    ExecutionReceiptBatch,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import AcquisitionOrigin, SemanticTarget, StateFact
from affordance_runtime.world.observation_needs import ObservationPurpose
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    ObservationObservedItem,
    ObservationQueryDisposition,
    ObservationQueryOutcome,
    ObservationUnknownItem,
    QueryScopeLocator,
    ResultLocator,
    VisualQueryFailureReason,
    VisualUnknownReason,
)
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


def _rekeyed_world(observation_id: str, prefix: str):
    document_id = f"{prefix}:document"
    go_id = f"{prefix}:go"
    targets = (
        SemanticTarget(document_id, "document", "Map", {"page.route": "/map"}),
        SemanticTarget(go_id, "button", "Go"),
    )
    facts = (
        StateFact(
            f"fact:{observation_id}:route",
            document_id,
            "page.route",
            "/map",
            observation_id,
        ),
    )
    binding = ActionBinding(
        f"binding:{observation_id}:go",
        observation_id,
        observation_id,
        f"revision:{observation_id}",
        "fingerprint:go",
        go_id,
        go_id,
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
    return fused_world(observation_id, targets, facts, (binding,))


def _multi_route_world(
    observation_id: str,
    route: str,
    controls: tuple[str, ...],
):
    targets = (
        SemanticTarget("document", "document", "Routes", {"page.route": route}),
        *(SemanticTarget(control, "button", control.replace("_", " ").title()) for control in controls),
    )
    facts = (
        StateFact(
            f"fact:{observation_id}:route",
            "document",
            "page.route",
            route,
            observation_id,
        ),
    )
    bindings = tuple(
        ActionBinding(
            f"binding:{observation_id}:{control}",
            observation_id,
            observation_id,
            f"revision:{observation_id}",
            f"fingerprint:{control}",
            control,
            control,
            "fixture",
            "fixture",
            "activate",
            "click",
            "local_reversible",
            ("external_ui_interaction",),
            {"type": "object", "properties": {}, "additionalProperties": False},
            {"fixture": control},
            risk=ActionRisk.LOW,
        )
        for control in controls
    )
    return fused_world(observation_id, targets, facts, bindings)


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


def _producer_inspection_step(world, query: str, outcome) -> StepResult:
    return StepResult(
        SearchPageContentResult(
            "context:test",
            "search_page_content",
            {"query": query},
            inspect_outcome_public(outcome),
        ),
        world,
        world,
        _evaluation(world),
        feedback="local_tool_result",
    )


def _producer_empty_search_step(world, query: str) -> StepResult:
    return _producer_inspection_step(
        world,
        query,
        Empty(query, "partial", ("broaden the query",)),
    )


def _tool_rejected_step(world) -> StepResult:
    return StepResult(
        ToolRejectedResult(
            "context:test",
            "tool_rejected",
            {
                "operation": "submit_final_response",
                "arguments": {"response": {"status": "SUCCESS"}},
            },
            {
                "kind": "invalid_arguments",
                "failure_kind": "invalid_arguments",
                "dispatch": "not_sent",
                "world_changed": False,
            },
            "call:rejected",
        ),
        world,
        world,
        _evaluation(world),
        feedback="local_tool_result",
    )


def _dispatched_step(world, after=None, *, target_id: str | None = None) -> StepResult:
    after = after or world
    options = ActionSpaceBuilder().build(_task(), world).options
    option = options[0] if target_id is None else next(item for item in options if item.target_id == target_id)
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


def _with_projected_outcome(step: StepResult) -> StepResult:
    assert step.execution_receipts is not None
    receipt = step.execution_receipts.receipts[-1]
    outcome = asyncio.run(
        validated_action_outcome(
            ProductionActionOutcomeProjector(),
            _task(),
            step.before_world,
            receipt.request,
            receipt.result,
            step.after_world,
            step.public_world_delta,
        )
    )
    return replace(step, action_outcome=outcome)


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


def _unknown_observation_step(
    world,
    query: str,
    index: int,
    reason: VisualUnknownReason = VisualUnknownReason.TARGET_NOT_VISIBLE,
) -> StepResult:
    decision = RequestObservation(
        "context:test",
        f"observation-query:unknown:{index}",
        ObservationPurpose.ENTITY_DISCOVERY,
        atomic_query=query,
        max_results=5,
        tool_call_id=f"call:unknown:{index}",
    )
    return StepResult(
        decision,
        world,
        world,
        _evaluation(world),
        feedback="observation_unknown",
        observation_outcome=ObservationQueryOutcome(
            decision.query_id,
            decision.purpose,
            ObservationQueryDisposition.UNKNOWN,
            unknown_items=(
                ObservationUnknownItem(
                    QueryScopeLocator(),
                    reason,
                ),
            ),
        ),
    )


def _failed_observation_step(world, query: str, index: int) -> StepResult:
    decision = RequestObservation(
        "context:test",
        f"observation-query:failed:{index}",
        ObservationPurpose.ENTITY_DISCOVERY,
        atomic_query=query,
        max_results=5,
        tool_call_id=f"call:failed:{index}",
    )
    return StepResult(
        decision,
        world,
        world,
        _evaluation(world),
        feedback="observation_unavailable",
        observation_outcome=ObservationQueryOutcome(
            decision.query_id,
            decision.purpose,
            ObservationQueryDisposition.FAILED,
            failure_reason=VisualQueryFailureReason.PROVIDER_ERROR,
        ),
    )


def _informative_observation_step(before, after) -> StepResult:
    decision = RequestObservation(
        "context:test",
        "observation-query:observed",
        ObservationPurpose.ENTITY_DISCOVERY,
        atomic_query="visible result records",
        max_results=5,
        tool_call_id="call:observed",
    )
    fact = next(item for item in after.facts if item.subject_id == "result")
    return StepResult(
        decision,
        before,
        after,
        _evaluation(after),
        feedback="observation_acquired",
        observation_outcome=ObservationQueryOutcome(
            decision.query_id,
            decision.purpose,
            ObservationQueryDisposition.OBSERVED,
            observed_items=(
                ObservationObservedItem(
                    ResultLocator(0),
                    ("result",),
                    (fact.fact_id,),
                ),
            ),
        ),
    )


def test_two_no_usable_perception_results_trigger_one_deliberate_recovery() -> None:
    world = _world("observation:perception-unknown")
    monitor = EpisodeMonitor()
    monitor.start_episode(world, _evaluation(world))
    store = ObservationDeliveryStore()

    first_step = _unknown_observation_step(world, "locate the hidden target", 1)
    first = store.reduce(first_step, step_index=1)
    first_monitor = monitor.evaluate(
        first_step,
        current_findings_digest(world),
        first.information_delta,
    )
    second_step = _unknown_observation_step(world, "find that target visually", 2)
    second = first.next_store.reduce(second_step, step_index=2)
    recovery = monitor.evaluate(
        second_step,
        current_findings_digest(world),
        second.information_delta,
    )

    assert first.information_delta is not None
    assert first.information_delta.kind is InformationDeltaKind.NO_USABLE_INFORMATION
    assert second.information_delta is not None
    assert second.information_delta.kind is InformationDeltaKind.NO_USABLE_INFORMATION
    assert first_monitor.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert "not a task answer" in recovery.recovery_signal.human_instruction
    assert len(recovery.recovery_signal.prohibited_attempt_signatures) == 1
    assert monitor.recovery_count == 1


@given(reason=st.sampled_from(tuple(VisualUnknownReason)))
def test_every_typed_unknown_reason_is_no_usable_information(
    reason: VisualUnknownReason,
) -> None:
    world = _world("observation:perception-unknown-algebra")
    step = _unknown_observation_step(world, "locate visible evidence", 1, reason)

    transition = ObservationDeliveryStore().reduce(step, step_index=1)

    assert transition.information_delta is not None
    assert transition.information_delta.kind is InformationDeltaKind.NO_USABLE_INFORMATION
    assert transition.information_delta.new_information_count == 0


def test_typed_perception_failure_is_no_usable_information() -> None:
    world = _world("observation:perception-failed")
    step = _failed_observation_step(world, "locate visible evidence", 1)

    transition = ObservationDeliveryStore().reduce(step, step_index=1)

    assert transition.information_delta is not None
    assert transition.information_delta.kind is InformationDeltaKind.NO_USABLE_INFORMATION
    assert transition.information_delta.new_information_count == 0


def test_new_observation_fact_closes_local_perception_recovery() -> None:
    before = _world("observation:perception-before")
    after = _world(
        "observation:perception-after",
        result_text="new visible record",
    )
    monitor = EpisodeMonitor()
    monitor.start_episode(before, _evaluation(before))
    store = ObservationDeliveryStore()

    first_step = _unknown_observation_step(before, "locate target", 1)
    first = store.reduce(first_step, step_index=1)
    monitor.evaluate(first_step, current_findings_digest(before), first.information_delta)
    second_step = _unknown_observation_step(before, "find target visually", 2)
    second = first.next_store.reduce(second_step, step_index=2)
    recovery = monitor.evaluate(
        second_step,
        current_findings_digest(before),
        second.information_delta,
    )
    observed_step = _informative_observation_step(before, after)
    observed = second.next_store.reduce(observed_step, step_index=3)
    resolved = monitor.evaluate(
        observed_step,
        current_findings_digest(after),
        observed.information_delta,
    )

    assert recovery.recovery_lifecycle is RecoveryLifecycleTransition.STARTED
    assert observed.information_delta is not None
    assert observed.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert observed.information_delta.new_information_count == 2
    assert resolved.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert resolved.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert resolved.recovery_signal is None


def test_point_grounding_route_is_new_information_without_a_new_fact() -> None:
    before = replace(_world("observation:point-before"), bindings=())
    after = _world("observation:point-after")
    decision = RequestObservation(
        "context:test",
        "observation-query:point",
        ObservationPurpose.POINT_GROUNDING,
        candidate_ids=("go",),
        atomic_query="the visible Go control",
        tool_call_id="call:point",
    )
    step = StepResult(
        decision,
        before,
        after,
        _evaluation(after),
        feedback="observation_acquired",
        observation_outcome=ObservationQueryOutcome(
            decision.query_id,
            decision.purpose,
            ObservationQueryDisposition.OBSERVED,
            observed_items=(
                ObservationObservedItem(InputLocator((0,)), ("go",)),
            ),
        ),
    )

    transition = ObservationDeliveryStore().reduce(step, step_index=1)

    assert transition.information_delta is not None
    assert transition.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert transition.information_delta.new_information_count == 1


def test_existing_point_grounding_route_is_not_new_information() -> None:
    before = _world("observation:point-existing-before")
    after = _world("observation:point-existing-after")
    decision = RequestObservation(
        "context:test",
        "observation-query:point-existing",
        ObservationPurpose.POINT_GROUNDING,
        candidate_ids=("go",),
        atomic_query="the visible Go control",
        tool_call_id="call:point-existing",
    )
    step = StepResult(
        decision,
        before,
        after,
        _evaluation(after),
        feedback="observation_acquired",
        observation_outcome=ObservationQueryOutcome(
            decision.query_id,
            decision.purpose,
            ObservationQueryDisposition.OBSERVED,
            observed_items=(
                ObservationObservedItem(InputLocator((0,)), ("go",)),
            ),
        ),
    )

    transition = ObservationDeliveryStore().reduce(step, step_index=1)

    assert transition.information_delta is not None
    assert transition.information_delta.kind is InformationDeltaKind.NO_NEW_INFORMATION
    assert transition.information_delta.new_information_count == 0


def test_control_discovery_recovery_is_consumed_by_the_next_decision() -> None:
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
    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert continued.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert continued.recovery_signal is None
    assert monitor.recovery_count == 0


def test_first_typed_tool_rejection_opens_deliberate_recovery_immediately() -> None:
    world = _world("observation:typed-tool-rejection")
    monitor = EpisodeMonitor()
    monitor.start_episode(world, _evaluation(world))

    transition = _evaluate(monitor, _tool_rejected_step(world))

    assert transition.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert transition.recovery_lifecycle is RecoveryLifecycleTransition.STARTED
    assert transition.recovery_signal is not None
    assert transition.recovery_signal.kind is RecoveryKind.CONTROL_STALL
    assert transition.recovery_signal.recovery_attempt == 1
    assert monitor.recovery_count == 1


def test_supported_recovery_budget_reaches_a_typed_block_within_the_signal_algebra() -> None:
    world = _world("observation:typed-tool-rejection-bound")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(world, _evaluation(world))

    transitions = tuple(_evaluate(monitor, _tool_rejected_step(world)) for _ in range(3))

    assert tuple(item.recommendation for item in transitions) == (
        EpisodeMonitorRecommendation.RECOVER,
        EpisodeMonitorRecommendation.BLOCK,
        EpisodeMonitorRecommendation.BLOCK,
    )
    assert tuple(item.recovery_signal.recovery_attempt for item in transitions if item.recovery_signal is not None) == (
        1,
        1,
        1,
    )


def test_control_discovery_blocks_only_the_repeated_recovery_query() -> None:
    world = _world("observation:control-discovery-repeat")
    monitor = EpisodeMonitor()
    monitor.start_episode(world, _evaluation(world))

    first = _evaluate(monitor, _control_discovery_step(world, "search", "Search Wikipedia"))
    recovery = _evaluate(
        monitor,
        _control_discovery_step(world, "address bar", "Search Wikipedia"),
    )
    constrained = _evaluate(
        monitor,
        _control_discovery_step(world, "address bar", "Search Wikipedia"),
    )
    blocked = _evaluate(
        monitor,
        _control_discovery_step(world, "address bar", "Search Wikipedia"),
    )

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert constrained.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert constrained.recovery_signal is not None
    assert constrained.recovery_signal.prohibited_attempt_signatures
    assert constrained.recovery_signal.recovery_attempt == 1
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
    assert recovery.recovery_signal.prohibited_attempt_signatures == (monitor.latest_attempt_signature,)
    assert "Follow continuation.cursor only when has_more is true" in recovery.recovery_signal.human_instruction
    assert "one materially different current route" in recovery.recovery_signal.human_instruction
    assert "do not repeat control discovery" not in recovery.recovery_signal.human_instruction
    assert stalled.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert stalled.reason == "control_stalled"


def test_exact_replay_recovery_is_consumed_by_a_different_region_decision() -> None:
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
    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert continued.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert continued.recovery_signal is None
    assert monitor.recovery_count == 0


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


def test_local_delivery_closed_algebra_covers_empty_cross_world_overlap_and_new_semantics() -> None:
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
    changed_semantics = changed_world.next_store.reduce(
        step(second_world, "changed beta", (item_a, {"label": "beta", "value": "three"})),
        step_index=5,
    )

    assert empty.information_delta is not None
    assert empty.information_delta.kind is InformationDeltaKind.NO_MATCHES
    assert overlap.information_delta is not None
    assert overlap.information_delta.kind is InformationDeltaKind.NO_NEW_INFORMATION
    assert overlap.information_delta.new_information_count == 0
    assert changed_world.information_delta is not None
    assert changed_world.information_delta.kind is InformationDeltaKind.NO_NEW_INFORMATION
    assert changed_world.information_delta.new_information_count == 0
    assert changed_semantics.information_delta is not None
    assert changed_semantics.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert changed_semantics.information_delta.new_information_count == 1


def test_real_empty_search_results_accumulate_no_progress_instead_of_false_novelty() -> None:
    world = _world("observation:producer-empty-results")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))
    store = ObservationDeliveryStore()

    first_step = _producer_empty_search_step(world, "missing one")
    first = store.reduce(first_step, step_index=1)
    first_monitor = monitor.evaluate(
        first_step,
        current_findings_digest(world),
        first.information_delta,
    )
    second_step = _producer_empty_search_step(world, "missing two")
    second = first.next_store.reduce(second_step, step_index=2)
    second_monitor = monitor.evaluate(
        second_step,
        current_findings_digest(world),
        second.information_delta,
    )

    assert first.information_delta is not None
    assert first.information_delta.kind is InformationDeltaKind.NO_MATCHES
    assert second.information_delta is not None
    assert second.information_delta.kind is InformationDeltaKind.NO_MATCHES
    assert first_monitor.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second_monitor.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second_monitor.recovery_lifecycle is RecoveryLifecycleTransition.STARTED


def test_zero_record_inspection_failure_consumes_the_old_signal_without_claiming_progress() -> None:
    world = _world("observation:producer-zero-record-failures")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))
    store = ObservationDeliveryStore()

    for index, query in enumerate(("missing one", "missing two"), start=1):
        step = _producer_empty_search_step(world, query)
        delivery = store.reduce(step, step_index=index)
        transition = monitor.evaluate(
            step,
            current_findings_digest(world),
            delivery.information_delta,
        )
        store = delivery.next_store
    assert transition.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert monitor.active_recovery is not None
    old_epoch_id = monitor.active_recovery.epoch_id

    step = _producer_inspection_step(world, "failure 3", InvalidCursor("cursor:stale"))
    delivery = store.reduce(step, step_index=3)
    consumed = monitor.evaluate(
        step,
        current_findings_digest(world),
        delivery.information_delta,
    )

    assert delivery.information_delta is not None
    assert delivery.information_delta.kind is InformationDeltaKind.NO_MATCHES
    assert consumed.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert consumed.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert consumed.recovery_signal is None
    assert monitor.active_recovery is None
    assert old_epoch_id


def test_tool_rejection_has_no_information_novelty_receipt() -> None:
    world = _world("observation:tool-rejection-no-novelty")

    transition = ObservationDeliveryStore().reduce(
        _tool_rejected_step(world),
        step_index=1,
    )

    assert transition.information_delta is None
    assert transition.next_store == ObservationDeliveryStore()


def test_local_delivery_novelty_expires_refs_but_preserves_ref_shaped_business_text() -> None:
    first_world = _world("observation:semantic-record-first")
    second_world = _world("observation:semantic-record-second", route="/page/2")

    def step(world, *, region_ref: str, node_ref: str, text: str) -> StepResult:
        return StepResult(
            ReadRegionResult(
                "context:test",
                "read_region",
                {"region_ref": region_ref},
                {
                    "kind": "Opened",
                    "items": (
                        {
                            "kind": "complete_item",
                            "region_ref": region_ref,
                            "content": ({"node_ref": node_ref, "role": "StaticText", "text": text},),
                        },
                    ),
                    "has_more": False,
                    "next_cursor": None,
                    "source_coverage": "partial",
                    "region_membership": "complete",
                    "result_page": "1/1",
                    "scope": {"role": "list", "heading": "Results"},
                },
                ephemeral_argument_paths=(("region_ref",),),
                ephemeral_result_paths=(
                    ("next_cursor",),
                    ("items", "*", "region_ref"),
                    ("items", "*", "content", "*", "node_ref"),
                ),
            ),
            world,
            world,
            _evaluation(world),
            feedback="local_tool_result",
        )

    first_step = step(first_world, region_ref="R1", node_ref="N1", text="Product code E6")
    duplicate_step = step(second_world, region_ref="R9", node_ref="N8", text="Product code E6")
    changed_step = step(second_world, region_ref="R9", node_ref="N7", text="Product code R2")

    first = ObservationDeliveryStore().reduce(first_step, step_index=1)
    duplicate = first.next_store.reduce(duplicate_step, step_index=2)
    changed = duplicate.next_store.reduce(changed_step, step_index=3)

    assert first.information_delta is not None
    assert first.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert duplicate.information_delta is not None
    assert duplicate.information_delta.kind is InformationDeltaKind.NO_NEW_INFORMATION
    assert changed.information_delta is not None
    assert changed.information_delta.kind is InformationDeltaKind.NEW_INFORMATION


def test_cross_world_duplicate_records_open_recovery_without_prohibiting_a_new_route() -> None:
    first_world = _world("observation:duplicate-page-one")
    second_world = _world("observation:duplicate-page-two", route="/page/2")

    def step(world, *, region_ref: str, node_ref: str) -> StepResult:
        return StepResult(
            ReadRegionResult(
                "context:test",
                "read_region",
                {"region_ref": region_ref},
                {
                    "kind": "Opened",
                    "items": (
                        {
                            "kind": "complete_item",
                            "region_ref": region_ref,
                            "content": ({"node_ref": node_ref, "role": "StaticText", "text": "same record"},),
                        },
                    ),
                    "has_more": False,
                    "next_cursor": None,
                    "source_coverage": "partial",
                    "region_membership": "complete",
                    "result_page": "1/1",
                    "scope": {"role": "list", "heading": "Results"},
                },
                ephemeral_argument_paths=(("region_ref",),),
                ephemeral_result_paths=(
                    ("next_cursor",),
                    ("items", "*", "region_ref"),
                    ("items", "*", "content", "*", "node_ref"),
                ),
            ),
            world,
            world,
            _evaluation(world),
            feedback="local_tool_result",
        )

    first = ObservationDeliveryStore().reduce(
        step(first_world, region_ref="R1", node_ref="N1"),
        step_index=1,
    )
    repeated_step = step(second_world, region_ref="R8", node_ref="N9")
    repeated = first.next_store.reduce(repeated_step, step_index=2)
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(second_world, _evaluation(second_world))

    transition = monitor.evaluate(
        repeated_step,
        current_findings_digest(second_world),
        repeated.information_delta,
    )

    assert repeated.information_delta is not None
    assert repeated.information_delta.kind is InformationDeltaKind.NO_NEW_INFORMATION
    assert transition.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert transition.recovery_lifecycle is RecoveryLifecycleTransition.STARTED
    assert transition.recovery_signal is not None
    assert transition.recovery_signal.prohibited_attempt_signatures == ()
    assert "added no semantic record" in transition.recovery_signal.human_instruction


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


def test_different_no_progress_attempt_consumes_the_previous_signal() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))

    _evaluate(monitor, _local_step(world, query="one"))
    recovery = _evaluate(monitor, _local_step(world, query="two"))
    continued = _evaluate(monitor, _local_step(world, query="three"))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recovery_signal is not None
    assert continued.recovery_signal is None
    assert continued.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert monitor.recovery_count == 0


@given(
    queries=st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20),
        min_size=3,
        max_size=20,
        unique=True,
    )
)
def test_distinct_no_progress_attempts_never_become_a_runtime_semantic_budget(queries) -> None:
    world = _world("observation:distinct-recovery-attempts")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))

    transitions = tuple(_evaluate(monitor, _local_step(world, query=query)) for query in queries)

    assert transitions[0].recommendation is EpisodeMonitorRecommendation.RECOVER
    assert all(item.recommendation is EpisodeMonitorRecommendation.RECOVER for item in transitions)
    assert all(item.recovery_signal is not None for item in transitions)
    assert monitor.recovery_count == 1


def test_each_stall_signal_has_a_distinct_one_decision_identity() -> None:
    world = _world("observation:recovery-discovery-handoff")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))

    first_recovery = _evaluate(monitor, _local_step(world, query="first"))
    second_recovery = _evaluate(monitor, _local_step(world, query="second"))
    discovery_step = _control_discovery_step(world, "search", "Search Wikipedia")
    handoff = _evaluate(monitor, discovery_step)
    constrained = _evaluate(monitor, discovery_step)
    blocked = _evaluate(monitor, discovery_step)

    assert first_recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second_recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert handoff.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert handoff.recovery_signal is None
    assert handoff.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert constrained.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert constrained.recovery_signal is not None
    assert constrained.recovery_signal.prohibited_attempt_signatures
    assert constrained.recovery_signal.recovery_attempt == 1
    assert first_recovery.recovery_signal is not None
    assert second_recovery.recovery_signal is not None
    assert first_recovery.recovery_signal.epoch_id != second_recovery.recovery_signal.epoch_id
    assert second_recovery.recovery_signal.epoch_id != constrained.recovery_signal.epoch_id
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
    assert continued.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert continued.recovery_signal is None
    assert monitor.recovery_count == 0


def test_new_read_information_consumes_a_gui_stall_signal() -> None:
    first_world = _world("observation:gui-effect-stall-before")
    second_world = _world("observation:gui-effect-stall-after-1")
    third_world = _world("observation:gui-effect-stall-after-2")
    changed = _world(
        "observation:gui-effect-recovered",
        route="/map/results",
        result_text="33 km",
    )
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first_world, _evaluation(first_world))

    _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(first_world, second_world)),
    )
    recovery = _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(second_world, third_world)),
    )
    informative_step = _search_with_items(third_world)
    delivery = ObservationDeliveryStore().reduce(informative_step, step_index=3)
    carried = monitor.evaluate(
        informative_step,
        current_findings_digest(third_world),
        delivery.information_delta,
    )
    resolved = _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(third_world, changed)),
    )

    assert recovery.recovery_signal is not None
    assert recovery.recovery_lifecycle is RecoveryLifecycleTransition.STARTED
    assert delivery.information_delta is not None
    assert delivery.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert carried.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert carried.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert carried.recovery_signal is None
    assert resolved.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert resolved.recovery_lifecycle is RecoveryLifecycleTransition.NONE
    assert resolved.recovery_signal is None


def test_local_stall_after_gui_signal_opens_a_new_signal_and_replay_blocks() -> None:
    first_world = _world("observation:gui-local-phase-before")
    second_world = _world("observation:gui-local-phase-after-1")
    third_world = _world("observation:gui-local-phase-after-2")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first_world, _evaluation(first_world))

    _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(first_world, second_world)),
    )
    gui_recovery = _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(second_world, third_world)),
    )
    local_step = _search_with_items(third_world)
    first_delivery = ObservationDeliveryStore().reduce(local_step, step_index=3)
    assert first_delivery.information_delta is not None
    monitor.evaluate(
        local_step,
        current_findings_digest(third_world),
        first_delivery.information_delta,
    )
    replay_delivery = first_delivery.next_store.reduce(local_step, step_index=4)
    constrained = monitor.evaluate(
        local_step,
        current_findings_digest(third_world),
        replay_delivery.information_delta,
    )
    assert constrained.recovery_signal is not None
    prohibited = constrained.recovery_signal.prohibited_attempt_signatures[-1]
    rejected_step = StepResult(
        ToolRejectedResult(
            "context:test",
            "search_page_content",
            {"operation": "search_page_content", "attempt_signature": prohibited.digest},
            {
                "kind": "prohibited_attempt_rejected",
                "failure_kind": "recovery_prohibited_attempt_replay",
                "dispatch": "not_sent",
                "world_changed": False,
            },
            "call:local-rejected",
            rejected_attempt_signature=prohibited,
        ),
        third_world,
        third_world,
        _evaluation(third_world),
        feedback="recovery_repeat_rejected",
    )
    rejected = _evaluate(monitor, rejected_step)

    assert gui_recovery.recovery_signal is not None
    assert constrained.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert constrained.recovery_signal.epoch_id != gui_recovery.recovery_signal.epoch_id
    assert constrained.recovery_signal.recovery_attempt == 1
    assert rejected.recommendation is EpisodeMonitorRecommendation.BLOCK
    assert rejected.recovery_signal is not None
    assert rejected.recovery_signal.epoch_id != constrained.recovery_signal.epoch_id
    assert rejected.recovery_signal.recovery_attempt == 2


def test_same_attempt_after_recovery_creates_a_new_exact_replay_prohibition() -> None:
    world = _world("observation:stable-repeat")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))

    _evaluate(monitor, _local_step(world, query="one"))
    recovery = _evaluate(monitor, _local_step(world, query="two"))
    replay = _evaluate(monitor, _local_step(world, query="two"))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert replay.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert replay.reason == RecoveryKind.CONTROL_STALL.value
    assert replay.recovery_signal is not None
    assert recovery.recovery_signal is not None
    assert replay.recovery_signal.epoch_id != recovery.recovery_signal.epoch_id
    assert replay.recovery_signal.prohibited_attempt_signatures


def test_observation_streak_recovery_without_an_exact_receipt_creates_no_hard_prohibition() -> None:
    world = _world("observation:local-recovery")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(world, _evaluation(world))

    _evaluate(monitor, _local_step(world, query="one"))
    recovery = _evaluate(monitor, _local_step(world, query="two"))

    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.prohibited_attempt_signatures == ()


def test_world_increment_consumes_recovery_without_calling_the_changed_world_a_replay() -> None:
    first_world = _world("observation:first")
    changed_world = _world("observation:changed", route="/map/results", result_text="33 km")
    monitor = EpisodeMonitor(AgentLoopProfile(2, 1))
    monitor.start_episode(first_world, _evaluation(first_world))
    _evaluate(monitor, _local_step(first_world))
    _evaluate(monitor, _local_step(first_world))

    transition = _evaluate(monitor, _local_step(first_world, changed_world))

    assert transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in transition.events
    assert transition.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert monitor.active_recovery is None
    assert monitor.recovery_count == 0


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


def test_unverified_same_gui_no_progress_prohibits_the_exact_replay() -> None:
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
    assert second.recovery_signal.prohibited_attempt_signatures == (monitor.latest_attempt_signature,)
    assert "entity_discovery" in second.recovery_signal.human_instruction
    assert monitor.same_attempt_streak == 3
    assert monitor.no_progress_count == 3
    assert monitor.latest_attempt_signature is not None
    assert monitor.latest_attempt_signature.digest.startswith("sha256:")


def test_verified_stable_gui_no_effect_creates_one_exact_hard_prohibition() -> None:
    first_world = _world("observation:verified-no-effect-before")
    second_world = _world("observation:verified-no-effect-after-1")
    third_world = _world("observation:verified-no-effect-after-2")

    def verified_no_effect(before, after):
        step = _dispatched_step(before, after)
        assert step.execution_receipts is not None
        receipt = step.execution_receipts.receipts[-1]
        return replace(
            step,
            action_outcome=ActionOutcome(
                receipt.request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.UNCHANGED,
                LocalPostconditionStatus.UNSATISFIED,
                EvidenceMethod.NATIVE,
                "native verifier observed a stable unsatisfied postcondition",
                ("artifact:verification:stable-no-effect",),
                {
                    "observed_change": "unchanged",
                    "local_postcondition": "unsatisfied",
                },
                step.public_world_delta,
            ),
        )

    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first_world, _evaluation(first_world))
    _evaluate(monitor, verified_no_effect(first_world, second_world))

    recovery = _evaluate(monitor, verified_no_effect(second_world, third_world))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.prohibited_attempt_signatures == (monitor.latest_attempt_signature,)


def test_screenshot_only_change_does_not_hide_repeated_gui_stall() -> None:
    first_world = _world("observation:visual-before")
    second_world = _world("observation:visual-after-1")
    third_world = _world("observation:visual-after-2")

    def visual_step(before, after):
        step = _dispatched_step(before, after)
        assert step.execution_receipts is not None
        receipt = step.execution_receipts.receipts[-1]
        return replace(
            step,
            action_outcome=ActionOutcome(
                receipt.request.request_id,
                before.observation_id,
                after.observation_id,
                ObservedChange.CHANGED,
                LocalPostconditionStatus.NOT_APPLICABLE,
                EvidenceMethod.VISUAL_DIFF,
                "the screenshot changed without a public semantic transition",
                ("artifact:visual:screenshot_semantic_state",),
                {"screenshot_changed": True},
                step.public_world_delta,
            ),
        )

    first_step = visual_step(first_world, second_world)
    second_step = visual_step(second_world, third_world)
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first_world, _evaluation(first_world))

    first = _evaluate(monitor, first_step)
    recovery = _evaluate(monitor, second_step)

    assert first_step.public_world_delta is not None
    assert not first_step.public_world_delta.semantic_changed
    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.prohibited_attempt_signatures == (monitor.latest_attempt_signature,)


def test_identity_rekeyed_fresh_world_does_not_hide_repeated_gui_stall() -> None:
    first_world = _rekeyed_world("observation:rekey-a", "a")
    second_world = _rekeyed_world("observation:rekey-b", "b")
    third_world = _rekeyed_world("observation:rekey-c", "c")
    first_step = _with_projected_outcome(_dispatched_step(first_world, second_world))
    second_step = _with_projected_outcome(_dispatched_step(second_world, third_world))
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first_world, _evaluation(first_world))

    first = _evaluate(monitor, first_step)
    recovery = _evaluate(monitor, second_step)

    assert first_step.public_world_delta is not None
    assert first_step.public_world_delta.changed
    assert not first_step.public_world_delta.semantic_changed
    assert first_step.action_outcome is not None
    assert first_step.action_outcome.observed_change is ObservedChange.UNKNOWN
    assert project_step_result(first_step).transition["semantic_change"] == "unchanged"
    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.prohibited_attempt_signatures == (monitor.latest_attempt_signature,)


def test_repeated_gui_operation_across_semantically_changed_worlds_is_not_a_same_world_stall() -> None:
    first_world = _world("observation:keyboard-before", result_text="suggestion 0")
    second_world = _world("observation:keyboard-step-1", result_text="suggestion 1")
    third_world = _world("observation:keyboard-step-2", result_text="suggestion 2")
    first_step = _dispatched_step(first_world, second_world)
    second_step = _dispatched_step(second_world, third_world)
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first_world, _evaluation(first_world))

    first = _evaluate(monitor, first_step)
    second = _evaluate(monitor, second_step)

    assert first_step.public_world_delta.semantic_changed
    assert second_step.public_world_delta.semantic_changed
    assert monitor_module._gui_attempt_signature(first_step) == monitor_module._gui_attempt_signature(second_step)
    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in second.events
    assert second.recovery_signal is None
    assert monitor.recovery_count == 0
    assert monitor.same_attempt_streak == 1


def test_same_gui_operation_reaching_a_seen_result_world_requests_new_route() -> None:
    first_world = _world("observation:cycle-a", result_text="state a")
    second_world = _world("observation:cycle-b", result_text="state b")
    third_world = _world("observation:cycle-c", result_text="state c")
    returned_second = _world("observation:cycle-b-return", result_text="state b")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first_world, _evaluation(first_world))

    first = _evaluate(monitor, _dispatched_step(first_world, second_world))
    second = _evaluate(monitor, _dispatched_step(second_world, third_world))
    recovery = _evaluate(monitor, _dispatched_step(third_world, returned_second))

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert recovery.recovery_signal is not None
    assert recovery.recovery_signal.kind is RecoveryKind.STATE_OSCILLATION
    assert recovery.recovery_signal.prohibited_attempt_signatures == ()
    assert recovery.recovery_signal.observed_evidence["repeated_result_world"] is True


def test_first_closed_gui_route_is_normal_information_acquisition() -> None:
    portland = _world("observation:portland", route="/wiki/Portland_Maine")
    acadia = _world("observation:acadia", route="/wiki/Acadia_National_Park")
    returned_portland = _world("observation:portland-returned", route="/wiki/Portland_Maine")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(portland, _evaluation(portland))

    first = _evaluate(monitor, _dispatched_step(portland, acadia))
    returned = _evaluate(monitor, _dispatched_step(acadia, returned_portland))

    assert first.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert returned.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in returned.events
    assert EpisodeMonitorEvent.ROUTE_REVIEW not in returned.events
    assert returned.recovery_signal is None
    assert monitor.closed_route_count == 1
    assert len(monitor.recent_gui_attempts) <= 16


@given(period=st.integers(min_value=2, max_value=8), rotation=st.integers(min_value=0, max_value=7))
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


def test_gui_cycle_detection_is_bounded_by_one_fixed_attempt_window() -> None:
    values = tuple(
        PublicAttemptSignature(
            f"operation-{index}",
            f"{index + 1:064x}",
            "",
            "",
            f"{index + 11:064x}",
        )
        for index in range(9)
    )

    digest, period = monitor_module._short_gui_cycle(values + values)

    assert digest == ""
    assert period == 0


def test_six_step_gui_excursion_is_not_declared_failed_on_first_return_to_origin() -> None:
    worlds = tuple(_world(f"observation:cycle-{index}", route=f"/state/{index}") for index in range(6))
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(worlds[0], _evaluation(worlds[0]))

    first_excursion = tuple(
        _evaluate(
            monitor,
            _dispatched_step(worlds[index % 6], worlds[(index + 1) % 6]),
        )
        for index in range(6)
    )

    assert all(item.recommendation is EpisodeMonitorRecommendation.CONTINUE for item in first_excursion)
    assert all(item.recovery_signal is None for item in first_excursion)
    assert monitor.closed_route_count == 1


def test_distinct_closed_routes_accumulate_one_strategy_recovery_episode() -> None:
    origin = _multi_route_world(
        "observation:origin",
        "/search",
        ("first_candidate", "second_candidate", "third_candidate"),
    )
    first_failed = _multi_route_world(
        "observation:first-failed",
        "/candidate/first",
        ("return_to_results",),
    )
    returned_once = _multi_route_world(
        "observation:returned-once",
        "/search",
        ("first_candidate", "second_candidate", "third_candidate"),
    )
    second_failed = _multi_route_world(
        "observation:second-failed",
        "/candidate/second",
        ("return_to_results",),
    )
    returned_twice = _multi_route_world(
        "observation:returned-twice",
        "/search",
        ("first_candidate", "second_candidate", "third_candidate"),
    )
    third_result = _multi_route_world(
        "observation:third-result",
        "/candidate/third",
        ("return_to_results",),
    )
    returned_thrice = _multi_route_world(
        "observation:returned-thrice",
        "/search",
        ("first_candidate", "second_candidate", "third_candidate"),
    )
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(origin, _evaluation(origin))

    _evaluate(monitor, _dispatched_step(origin, first_failed, target_id="first_candidate"))
    first_recovery = _evaluate(
        monitor,
        _dispatched_step(first_failed, returned_once, target_id="return_to_results"),
    )
    _evaluate(
        monitor,
        _dispatched_step(returned_once, second_failed, target_id="second_candidate"),
    )
    second_recovery = _evaluate(
        monitor,
        _dispatched_step(second_failed, returned_twice, target_id="return_to_results"),
    )
    resolved = _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(returned_twice, third_result, target_id="third_candidate")),
    )
    third_return = _evaluate(
        monitor,
        _dispatched_step(third_result, returned_thrice, target_id="return_to_results"),
    )

    assert first_recovery.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert first_recovery.recovery_signal is None
    assert second_recovery.recovery_signal is not None
    assert second_recovery.recovery_signal.kind is RecoveryKind.STRATEGY_REVIEW
    assert second_recovery.recovery_signal.recovery_attempt == 2
    assert second_recovery.recovery_signal.observed_evidence["closed_route_count"] == 2
    assert EpisodeMonitorEvent.ROUTE_REVIEW in second_recovery.events
    assert resolved.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert resolved.recovery_signal is None
    assert third_return.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert third_return.recovery_signal is None
    assert EpisodeMonitorEvent.ROUTE_REVIEW not in third_return.events
    assert monitor.closed_route_count == 3


def test_new_public_information_does_not_erase_an_open_gui_route() -> None:
    first = _world("observation:cycle-info-a", route="/state/a")
    second = _world("observation:cycle-info-b", route="/state/b")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first, _evaluation(first))
    store = ObservationDeliveryStore()

    outbound = _evaluate(monitor, _dispatched_step(first, second))
    assert outbound.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert len(monitor.recent_gui_attempts) == 1

    information_step = _search_with_items(second)
    delivery = store.reduce(information_step, step_index=2)
    continued = monitor.evaluate(
        information_step,
        current_findings_digest(second),
        delivery.information_delta,
    )

    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert delivery.information_delta is not None
    assert delivery.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert len(monitor.recent_gui_attempts) == 1
    assert monitor.active_gui_cycle_digest == ""

    returned = _evaluate(monitor, _dispatched_step(second, first))

    assert returned.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert returned.recovery_signal is None
    assert monitor.closed_route_count == 1


def test_forward_only_gui_route_does_not_invent_a_regression() -> None:
    first = _world("observation:forward-a", route="/state/a")
    second = _world("observation:forward-b", route="/state/b")
    third = _world("observation:forward-c", route="/state/c")
    monitor = EpisodeMonitor(AgentLoopProfile(8, 1))
    monitor.start_episode(first, _evaluation(first))

    first_transition = _evaluate(monitor, _dispatched_step(first, second))
    second_transition = _evaluate(monitor, _dispatched_step(second, third))

    assert first_transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert second_transition.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.ROUTE_REVIEW not in second_transition.events


def test_ineffectual_gui_attempt_consumes_local_recovery_for_one_decision() -> None:
    world = _world("observation:stable")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))
    recovery = _evaluate(monitor, _local_step(world))

    continued = _evaluate(monitor, _dispatched_step(world))

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert continued.recovery_signal is None
    assert continued.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert monitor.recovery_count == 0


def test_causal_changed_gui_attempt_consumes_local_recovery() -> None:
    world = _world("observation:control-recovery")
    changed = _world("observation:changed-by-gui", route="/map/next")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(world, _evaluation(world))
    recovery = _evaluate(monitor, _local_step(world, query="first"))
    second_recovery = _evaluate(monitor, _local_step(world, query="second"))

    continued_step = _with_projected_outcome(_dispatched_step(world, changed))
    continued = _evaluate(monitor, continued_step)

    assert recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second_recovery.recommendation is EpisodeMonitorRecommendation.RECOVER
    assert second_recovery.recovery_signal is not None
    assert second_recovery.recovery_signal.recovery_attempt == 1
    assert continued.recommendation is EpisodeMonitorRecommendation.CONTINUE
    assert EpisodeMonitorEvent.STATE_CHANGED in continued.events
    assert continued.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert continued.recovery_signal is None
    assert monitor.recovery_count == 0
    assert monitor.latest_attempt_signature is None
    assert monitor.same_attempt_streak == 0


def test_each_followup_transition_consumes_or_replaces_the_previous_signal() -> None:
    first = _world("observation:information-origin")
    changed_once = _world("observation:information-route-1", route="/reviews?page=2")
    changed_twice = _world("observation:information-route-2", route="/reviews?page=2&view=all")
    monitor = EpisodeMonitor(AgentLoopProfile(1, 1))
    monitor.start_episode(first, _evaluation(first))
    recovery = _evaluate(monitor, _local_step(first, query="reviews"))

    first_route = _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(first, changed_once)),
    )
    rejected = _evaluate(monitor, _tool_rejected_step(changed_once))
    second_route = _evaluate(
        monitor,
        _with_projected_outcome(_dispatched_step(changed_once, changed_twice)),
    )

    assert recovery.recovery_signal is not None
    assert first_route.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert first_route.recovery_signal is None
    assert rejected.recovery_lifecycle is RecoveryLifecycleTransition.STARTED
    assert rejected.recovery_signal is not None
    assert rejected.recovery_signal.epoch_id != recovery.recovery_signal.epoch_id
    assert second_route.recovery_lifecycle is RecoveryLifecycleTransition.CLOSED
    assert second_route.recovery_signal is None


def test_monitor_never_overrides_native_terminal_evaluation() -> None:
    world = _world("observation:stable")
    step = _local_step(world)
    step = StepResult(
        step.decision, world, world, _evaluation(world, TaskEvaluationStatus.BLOCKED), feedback=step.feedback
    )
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
        "recent_gui_results",
        "active_gui_cycle_digest",
        "active_recovery",
        "recovery_epoch_counter",
        "closed_route_count",
    } == set(vars(monitor)) - {"profile"}
