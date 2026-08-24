from __future__ import annotations

from dataclasses import replace

import pytest

from affordance_runtime.agent import ContinueDeliveryResult
from affordance_runtime.agent.context.action_candidate_projection import (
    ActionDeliveryPlan,
    DeliveryObligation,
    DeliveryObligationKind,
)
from affordance_runtime.agent.context.observation_delivery import (
    DeliveryContinuationOutcomeKind,
    DeliveryInventorySnapshot,
    ObservationDeliveryStore,
    PublicResultRecord,
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
        progress = store.cursor(incoming.scope)
        inventory = (
            replace(incoming, offset=progress.offset)
            if progress is not None
            and (
                progress.world_lineage,
                progress.action_lineage,
                progress.result_lineage,
                progress.order_digest,
            )
            == (
                incoming.world_lineage,
                incoming.action_lineage,
                incoming.result_lineage,
                incoming.order_digest,
            )
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
    requested = store.requested_continuation_scope
    foreground = next(
        (
            item.continuation_scope
            for item in obligations
            if item.continuation_scope == requested and item.remaining
        ),
        None,
    ) or next((item.continuation_scope for item in obligations if item.remaining), None)
    return ActionDeliveryPlan(
        f"actions:{inventories[0].world_lineage}",
        inventories[0].world_lineage,
        tuple(obligations),
        foreground,
        requested_scope=requested,
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

    assert store.continue_delivery(capability).kind is DeliveryContinuationOutcomeKind.READY
    next_store = _commit(store, capability, world, step_index=1)

    assert next_store.cursor("effect").offset == 0
    assert next_store.requested_continuation_scope == "effect"
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
    with pytest.raises(ValueError, match="stale World"):
        _commit(store, effect_capability, fresh_world, step_index=step_index)
