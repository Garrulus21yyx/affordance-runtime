from __future__ import annotations

from dataclasses import fields

from affordance_runtime.agent.context.context import AgentContext
from affordance_runtime.agent.context.observation_delivery import (
    InformationDeltaKind,
    ObservationDeliveryStore,
)
from affordance_runtime.agent.decisions import SearchPageContentResult
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from tests.support.agent.core_loop_support import _task, _world


def _step(result: dict[str, object], *, suffix: str = "one") -> StepResult:
    task = _task()
    world = _world(f"direct-result-{suffix}", False)
    return StepResult(
        SearchPageContentResult(
            "context:test",
            "search_page_content",
            {"query": "reviewer"},
            result,
            f"call:{suffix}",
        ),
        world,
        world,
        TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "direct result fixture",
        ),
        feedback="local_tool_result",
    )


def test_store_has_no_result_body_or_generic_cursor_authority() -> None:
    assert tuple(item.name for item in fields(ObservationDeliveryStore)) == (
        "local_deliveries",
    )


def test_agent_context_has_no_store_or_historical_effect_input() -> None:
    context_fields = {item.name for item in fields(AgentContext)}
    assert "delivery_store" not in context_fields
    assert "observation_delivery" not in context_fields
    store = ObservationDeliveryStore()
    assert not any(
        hasattr(store, name)
        for name in (
            "public_result_inventory",
            "active_read",
            "cursor_progress",
            "action_query",
            "search_follow_ups",
            "foreground_request",
        )
    )


def test_store_reducer_keeps_only_monitor_digests_and_detects_replay() -> None:
    body = {
        "kind": "Matches",
        "items": (
            {"region_ref": "R9", "nested": {"reviewer": "完整🙂"}},
            {"region_ref": "R10", "nested": {"reviewer": "suffix"}},
        ),
        "next_cursor": None,
    }
    step = _step(body)
    first = ObservationDeliveryStore().reduce(step, step_index=1)

    assert first.information_delta is not None
    assert first.information_delta.kind is InformationDeltaKind.NEW_INFORMATION
    assert first.information_delta.new_information_count == 2
    assert len(first.next_store.local_deliveries) == 1
    receipt = first.next_store.local_deliveries[0]
    assert len(receipt.item_digests) == 2
    assert "完整" not in repr(receipt)
    assert not hasattr(receipt, "records")

    replay = first.next_store.reduce(step, step_index=2)
    assert replay.information_delta is not None
    assert replay.information_delta.kind is InformationDeltaKind.EXACT_REPLAY
    assert replay.next_store is first.next_store


def test_store_has_no_world_lineage_or_cursor_lifecycle() -> None:
    store = ObservationDeliveryStore()
    assert not hasattr(store, "for_world")
    assert not hasattr(store, "cursor")
