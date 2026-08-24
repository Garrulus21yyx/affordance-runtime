from __future__ import annotations

from dataclasses import fields

from affordance_runtime.agent.context.observation_delivery import (
    InformationDeltaKind,
    ObservationDeliveryStore,
)
from affordance_runtime.agent.decisions import SearchPageContentResult, SelectAction
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.agent.tool_result_projection import project_committed_tool_return
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.immutable import to_json_compatible
from tests.support.agent.core_loop_support import shared_world


def _evaluation(observation_id: str) -> TaskEvaluation:
    return TaskEvaluation(
        "task:delivery-store",
        observation_id,
        TaskEvaluationStatus.INCOMPLETE,
        "delivery store fixture",
    )


def test_gui_action_never_creates_a_second_current_world_in_delivery_store() -> None:
    before = shared_world("observation:before-action", False)
    after = shared_world("observation:after-action", True)
    step = StepResult(
        SelectAction("context:action", "action:activate", tool_call_id="call:action"),
        before,
        after,
        _evaluation(after.observation_id),
        feedback="action_dispatched",
    )
    store = ObservationDeliveryStore()

    transition = store.reduce(step, step_index=1)

    assert transition.next_store is store
    assert transition.information_delta is None
    assert tuple(item.name for item in fields(transition.next_store)) == ("local_deliveries",)
    assert not hasattr(transition.next_store, "latest_effect")


def test_local_result_store_keeps_only_monitor_digests_and_same_call_return_keeps_body() -> None:
    world = shared_world("observation:local-result", False)
    result = {
        "kind": "Matches",
        "items": (
            {"record": "Review by Alice", "text": "完整🙂 record one"},
            {"record": "Review by Bob", "text": "完整🙂 record two"},
        ),
        "next_cursor": None,
    }
    decision = SearchPageContentResult(
        "context:local",
        "search_page_content",
        {"query": "Review by"},
        result,
        "call:local",
    )
    step = StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        feedback="local_tool_result",
    )

    transition = ObservationDeliveryStore().reduce(step, step_index=1)

    assert transition.information_delta is not None
    assert transition.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert len(transition.next_store.local_deliveries[-1].item_digests) == 2
    assert "完整🙂" not in repr(transition.next_store)
    assert to_json_compatible(project_committed_tool_return(step)) == to_json_compatible(result)


def test_replaying_the_same_local_result_is_monitor_novelty_only() -> None:
    world = shared_world("observation:replay", False)
    decision = SearchPageContentResult(
        "context:replay",
        "search_page_content",
        {"query": "Review by"},
        {"kind": "NoMatches", "items": (), "next_cursor": None},
        "call:replay",
    )
    step = StepResult(
        decision,
        world,
        world,
        _evaluation(world.observation_id),
        feedback="local_tool_result",
    )
    first = ObservationDeliveryStore().reduce(step, step_index=1)

    replay = first.next_store.reduce(step, step_index=2)

    assert replay.next_store is first.next_store
    assert replay.information_delta is not None
    assert replay.information_delta.kind is InformationDeltaKind.EXACT_REPLAY
