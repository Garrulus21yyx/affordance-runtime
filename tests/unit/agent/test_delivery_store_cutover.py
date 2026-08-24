from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent import ContinueDeliveryResult
from affordance_runtime.agent.context.action_candidate_projection import (
    ActionDeliveryPlan,
    DeliveryObligation,
    DeliveryObligationKind,
)
from affordance_runtime.agent.context.observation_delivery import (
    DeliveryContinuationCapability,
    DeliveryContinuationOutcomeKind,
    DeliveryInventorySnapshot,
    LocalSearchHit,
    ObservationDeliveryStore,
    PublicResultInventory,
    PublicResultRecord,
    StoredActionQuery,
)
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.run_state import StepResult
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from tests.support.agent.core_loop_support import _task, _world


def _inventory(scope: str, kind: str, records: tuple[str, ...], *, world: str):
    atoms = tuple(PublicResultRecord(kind, scope, {"label": item}) for item in records)
    return DeliveryInventorySnapshot(
        scope,
        kind,
        world,
        f"actions:{world}",
        f"result:{scope}:{world}",
        f"order:{scope}:{world}",
        atoms,
    )


def _plan(
    inventories: tuple[DeliveryInventorySnapshot, ...],
    store: ObservationDeliveryStore,
) -> ActionDeliveryPlan:
    obligations = []
    for priority, incoming in enumerate(inventories):
        progress = store.cursor(incoming.key)
        inventory = (
            replace(incoming, offset=progress.offset)
            if progress is not None
            else incoming
        )
        kind = DeliveryObligationKind(inventory.kind)
        obligations.append(
            DeliveryObligation(
                kind,
                inventory.records,
                priority,
                inventory,
                inventory.scope,
            )
        )
    requested = (
        store.foreground_request
        if any(
            item.inventory.key == store.foreground_request and item.remaining
            for item in obligations
        )
        else None
    )
    foreground = next(
        (
            item.continuation_scope
            for item in obligations
            if item.inventory.key == requested and item.remaining
        ),
        None,
    ) or next((item.continuation_scope for item in obligations if item.remaining), None)
    return ActionDeliveryPlan(
        f"actions:{inventories[0].world_lineage}",
        inventories[0].world_lineage,
        tuple(obligations),
        foreground,
        requested_key=requested,
    )


def _commit(
    store: ObservationDeliveryStore,
    capability,
    world,
    *,
    step_index: int,
) -> ObservationDeliveryStore:
    task = _task()
    decision = ContinueDeliveryResult(
        "context:test",
        "action_results_next_page",
        {"scope": capability.scope},
        {"continuation_available": True, "items": ()},
        f"call:continuation:{step_index}",
        continuation=capability,
    )
    step = StepResult(
        decision,
        world,
        world,
        TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "cursor progress fixture",
        ),
        feedback="local_tool_result",
    )
    return store.reduce(step, step_index=step_index).next_store


def test_zero_prefix_suffix_is_callable_and_becomes_foreground_without_advancing() -> None:
    world = _world("cursor-zero-prefix", False)
    inventory = _inventory(
        "effect",
        DeliveryObligationKind.PUBLIC_EFFECT.value,
        ("effect-1", "effect-2"),
        world=world.observation_id,
    )
    store = ObservationDeliveryStore()
    capability = _plan((inventory,), store).continuation_capabilities(
        {DeliveryObligationKind.PUBLIC_EFFECT.value: 0}
    )[0]

    assert store.continue_delivery(
        capability,
        world_observation_id=world.observation_id,
    ).kind is DeliveryContinuationOutcomeKind.READY
    next_store = _commit(store, capability, world, step_index=1)

    assert next_store.cursor(capability.key).offset == 0
    assert next_store.foreground_request == capability.key
    resumed = _plan((inventory,), next_store)
    assert resumed.obligations[0].remaining == inventory.records
    assert resumed.foreground_scope == "effect"


def test_finite_multi_scope_sequence_conserves_suffixes_and_stales_old_capability() -> None:
    world = _world("cursor-multi-scope", False)
    inventories = (
        _inventory("effect", DeliveryObligationKind.PUBLIC_EFFECT.value, ("e1", "e2", "e3"), world=world.observation_id),
        _inventory("page_directory", DeliveryObligationKind.PAGE_DIRECTORY.value, ("r1", "r2"), world=world.observation_id),
        _inventory("base", DeliveryObligationKind.BASE_ACTIONS.value, ("a1", "a2", "a3"), world=world.observation_id),
        _inventory("query", DeliveryObligationKind.EXPLICIT_QUERY.value, ("q1", "q2"), world=world.observation_id),
    )
    store = ObservationDeliveryStore()
    first_plan = _plan(inventories, store)
    first_capabilities = first_plan.continuation_capabilities(
        {item.kind.value: 1 for item in first_plan.obligations}
    )
    effect_capability = next(item for item in first_capabilities if item.scope == "effect")
    store = _commit(store, effect_capability, world, step_index=1).with_active_read(
        WorldDeliveryLens(world.observation_id, "find", query="public query", next_cursor="private-next")
    )

    current_plan = _plan(inventories, store)
    scopes = {
        item.scope
        for item in (
            *current_plan.continuation_capabilities({item.kind.value: 0 for item in current_plan.obligations}),
            *store.active_read_continuation_capabilities(),
        )
    }
    assert {"effect", "page_directory", "active_read", "base", "query"} <= scopes

    delivered: dict[str, list[str]] = {
        scope: [] for scope in ("effect", "page_directory", "base", "query")
    }
    step_index = 2
    for scope in delivered:
        while True:
            current_plan = _plan(inventories, store)
            obligation = next(item for item in current_plan.obligations if item.continuation_scope == scope)
            if not obligation.remaining:
                break
            record = obligation.remaining[0]
            assert isinstance(record, PublicResultRecord)
            delivered[scope].append(str(record.public_value["label"]))
            if len(obligation.remaining) == 1:
                break
            capability = next(
                item
                for item in current_plan.continuation_capabilities({obligation.kind.value: 1})
                if item.scope == scope
            )
            store = _commit(store, capability, world, step_index=step_index)
            step_index += 1

    assert delivered == {
        "effect": ["e2", "e3"],
        "page_directory": ["r1", "r2"],
        "base": ["a1", "a2", "a3"],
        "query": ["q1", "q2"],
    }

    fresh_world = _world("cursor-fresh-world", False)
    assert store.continue_delivery(
        effect_capability,
        world_observation_id=fresh_world.observation_id,
    ).kind is DeliveryContinuationOutcomeKind.STALE
    with pytest.raises(ValueError, match="committed continuation is stale"):
        _commit(store, effect_capability, fresh_world, step_index=step_index)


@given(
    retained=st.booleans(),
    requested=st.booleans(),
    offset=st.integers(min_value=0, max_value=8),
    stale_active_read=st.booleans(),
    stale_search=st.booleans(),
    stale_results=st.booleans(),
    stale_query=st.booleans(),
)
def test_for_world_totally_normalizes_cursor_and_foreground_state(
    retained: bool,
    requested: bool,
    offset: int,
    stale_active_read: bool,
    stale_search: bool,
    stale_results: bool,
    stale_query: bool,
) -> None:
    current_world = "world:B"
    cursor_world = current_world if retained else "world:A"
    active_world = "world:A" if stale_active_read else current_world
    hit_world = "world:A" if stale_search else current_world
    result_world = "world:A" if stale_results else current_world
    query_world = "world:A" if stale_query else current_world
    result_record = PublicResultRecord("read_region", "R1", {"label": "one"})
    progress = DeliveryContinuationCapability(
        "action_base",
        True,
        0,
        16,
        cursor_world,
        f"actions:{cursor_world}",
        "result:base",
        "order:base",
        offset,
        DeliveryObligationKind.BASE_ACTIONS.value,
    )
    store = ObservationDeliveryStore(
        public_result_inventory=PublicResultInventory(
            result_world,
            "sha256:" + "1" * 64,
            (result_record,),
        ),
        active_read=WorldDeliveryLens(active_world),
        cursor_progress=(progress,),
        action_query=StoredActionQuery("query", query_world, f"actions:{query_world}", ()),
        search_follow_ups=(LocalSearchHit(hit_world, "N1", "R1"),),
        foreground_request=progress.key if requested else None,
    )

    normalized = store.for_world(current_world)

    assert all(item.world_lineage == current_world for item in normalized.cursor_progress)
    assert normalized.foreground_request is None or any(
        item.key == normalized.foreground_request for item in normalized.cursor_progress
    )
    assert normalized.cursor_progress == ((progress,) if retained else ())
    assert normalized.foreground_request == (progress.key if retained and requested else None)
    assert (normalized.active_read is None) is stale_active_read
    assert (not normalized.search_follow_ups) is stale_search
    assert (normalized.public_result_inventory is None) is stale_results
    assert (normalized.action_query is None) is stale_query


def test_same_world_continuation_survives_but_same_scope_new_world_restarts() -> None:
    world_a = _world("cursor-world-a", False)
    inventory_a = _inventory(
        "action_base",
        DeliveryObligationKind.BASE_ACTIONS.value,
        ("a1", "a2", "a3"),
        world=world_a.observation_id,
    )
    capability = _plan((inventory_a,), ObservationDeliveryStore()).continuation_capabilities(
        {DeliveryObligationKind.BASE_ACTIONS.value: 1}
    )[0]
    store_a = _commit(ObservationDeliveryStore(), capability, world_a, step_index=1)

    same_world_plan = _plan((inventory_a,), store_a.for_world(world_a.observation_id))
    assert same_world_plan.obligations[0].inventory.offset == 1
    assert same_world_plan.requested_key == capability.key

    world_b = _world("cursor-world-b", False)
    inventory_b = _inventory(
        "action_base",
        DeliveryObligationKind.BASE_ACTIONS.value,
        ("b1", "b2"),
        world=world_b.observation_id,
    )
    store_b = store_a.for_world(world_b.observation_id)
    changed_world_plan = _plan((inventory_b,), store_b)
    assert store_b.cursor_progress == ()
    assert store_b.foreground_request is None
    assert changed_world_plan.obligations[0].inventory.offset == 0
    assert changed_world_plan.requested_key is None
