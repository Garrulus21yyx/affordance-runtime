from __future__ import annotations

from affordance_runtime.agent.context.observation_delivery import (
    DeliveryContinuationOutcomeKind,
    DeliveryInventorySnapshot,
    ObservationDeliveryStore,
)
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens


def _inventory(scope: str, kind: str, records: tuple[str, ...], *, world: str = "world:1"):
    return DeliveryInventorySnapshot(
        scope,
        kind,
        world,
        f"actions:{world}",
        f"result:{scope}:{world}",
        f"order:{scope}:{world}",
        records,
    )


def test_zero_prefix_suffix_is_callable_and_becomes_foreground_without_advancing() -> None:
    store = ObservationDeliveryStore().install_inventories((
        _inventory("effect", "effect_actions", ("effect-1", "effect-2")),
    ))

    capability = store.continuation_capabilities({"effect_actions": 0})[0]
    outcome = store.continue_delivery(capability)

    assert capability.continuation_available is True
    assert capability.admitted_count == 0
    assert outcome.kind is DeliveryContinuationOutcomeKind.READY
    assert outcome.next_store is not None
    assert outcome.next_store.inventory("effect").offset == 0
    assert outcome.next_store.requested_continuation_scope == "effect"


def test_finite_multi_scope_sequence_conserves_suffixes_and_stales_old_capability() -> None:
    store = ObservationDeliveryStore().install_inventories((
        _inventory("effect", "effect_actions", ("e1", "e2", "e3")),
        _inventory("page_directory", "page_directory", ("r1", "r2")),
        _inventory("base", "base", ("a1", "a2", "a3")),
        _inventory("query", "query", ("q1", "q2")),
    ))
    first_capabilities = store.continuation_capabilities(
        {"effect_actions": 1, "page_directory": 1, "base": 1, "query": 1}
    )
    effect_capability = next(item for item in first_capabilities if item.scope == "effect")
    effect_step = store.continue_delivery(effect_capability)
    assert effect_step.next_store is not None
    store = effect_step.next_store.with_active_read(
        WorldDeliveryLens("world:1", "find", query="public query", next_cursor="private-next")
    )

    scopes = {item.scope for item in store.continuation_capabilities(
        {"effect_actions": 1, "page_directory": 0, "base": 0, "query": 0}
    )}
    assert {"effect", "page_directory", "active_read", "base", "query"} <= scopes

    delivered: dict[str, list[str]] = {scope: [] for scope in ("effect", "page_directory", "base", "query")}
    for scope in delivered:
        while True:
            inventory = store.inventory(scope)
            assert inventory is not None
            if not inventory.remaining:
                break
            delivered[scope].append(str(inventory.remaining[0]))
            if len(inventory.remaining) == 1:
                break
            capability = next(
                item
                for item in store.continuation_capabilities({inventory.kind: 1})
                if item.scope == scope
            )
            outcome = store.continue_delivery(capability)
            assert outcome.kind is DeliveryContinuationOutcomeKind.READY
            assert outcome.next_store is not None
            store = outcome.next_store

    assert delivered == {
        "effect": ["e2", "e3"],
        "page_directory": ["r1", "r2"],
        "base": ["a1", "a2", "a3"],
        "query": ["q1", "q2"],
    }

    fresh = store.install_inventories((
        _inventory("effect", "effect_actions", ("fresh",), world="world:2"),
    ))
    assert fresh.continue_delivery(effect_capability).kind is DeliveryContinuationOutcomeKind.STALE
