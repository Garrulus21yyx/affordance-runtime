from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from affordance_runtime.agent.context.action_candidate_projection import (
    ActionDeliveryPlan,
    ActionRouteIssueFragment,
    DeliveryObligation,
    DeliveryObligationKind,
)
from affordance_runtime.agent.context.budgets import ModelRequestBudget
from affordance_runtime.agent.context.observation_delivery import DeliveryInventorySnapshot
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model.policy.request_admission import ModelRequestCapacityError
from affordance_runtime.model.policy.turn_packer import TurnPacker

_BOUND = 8


def _packed_artifacts(counts: dict[str, int], backoff_count: int):
    admitted_counts = tuple(sorted(counts.items()))
    delivery = SimpleNamespace(
        delivery_id="delivery:test",
        admitted_record_counts=admitted_counts,
        packing_backoff_count=backoff_count,
    )
    catalog = SimpleNamespace(delivery_id="delivery:test")
    admitted = SimpleNamespace(
        envelope=SimpleNamespace(delivery_id="delivery:test", catalog=catalog)
    )
    return delivery, catalog, admitted


def _fake_binder():
    return SimpleNamespace(
        request_budget=ModelRequestBudget(),
        context_binder=SimpleNamespace(_include_images=lambda *_args: False),
    )


def _fake_profile():
    return SimpleNamespace(max_output_tokens=1024)


def _records(count: int):
    return tuple(
        ActionRouteIssueFragment(
            "action_route_conflict",
            "activate",
            "E1",
            (),
            (f"field_{index}",),
            rendered_cost_bytes=10 + index,
        )
        for index in range(count)
    )


def _obligation(kind: DeliveryObligationKind, count: int, priority: int) -> DeliveryObligation:
    records = _records(count)
    digest = "sha256:" + hashlib.sha256(repr(records).encode()).hexdigest()
    return DeliveryObligation(
        kind,
        records,
        priority,
        DeliveryInventorySnapshot(
            kind.value,
            kind.value,
            "world:test",
            "actions:test",
            "result:test",
            digest,
            records,
        ),
        kind.value,
    )


@pytest.mark.parametrize("count", (0, 1, _BOUND - 1, _BOUND, _BOUND + 1, 2 * _BOUND, 4 * _BOUND))
def test_inventory_cardinality_never_creates_more_than_one_group_per_protocol_kind(count: int) -> None:
    obligations = tuple(
        _obligation(kind, count, priority)
        for priority, kind in enumerate(DeliveryObligationKind)
        if count
    )
    plan = ActionDeliveryPlan(
        "actions:test",
        "world:test",
        obligations,
        obligations[0].continuation_scope if obligations else None,
    )

    assert len(plan.obligations) == (len(DeliveryObligationKind) if count else 0)
    assert len({item.kind for item in plan.obligations}) == len(plan.obligations)
    assert all(len(item.records) == count for item in plan.obligations)
    assert plan.foreground_scope == (DeliveryObligationKind.PUBLIC_RESULT.value if count else None)


@pytest.mark.parametrize("group_count", range(2, len(DeliveryObligationKind) + 1))
def test_multi_group_cursor_pages_and_suffix_reconstruct_each_authority_inventory(group_count: int) -> None:
    obligations = tuple(
        _obligation(kind, _BOUND + 3, priority)
        for priority, kind in enumerate(tuple(DeliveryObligationKind)[:group_count])
    )
    plan = ActionDeliveryPlan("actions:test", "world:test", obligations, obligations[0].continuation_scope)

    for obligation in plan.obligations:
        pages = tuple(
            obligation.records[offset : offset + 3]
            for offset in range(0, len(obligation.records), 3)
        )
        delivered = tuple(item for page in pages[:-1] for item in page)
        suffix = pages[-1]
        assert (*delivered, *suffix) == obligation.records
        assert obligation.remaining == obligation.records


def test_explicit_private_continuation_scope_becomes_next_foreground() -> None:
    first_kind, selected_kind = tuple(DeliveryObligationKind)[:2]
    obligations = (
        _obligation(first_kind, 3, 0),
        _obligation(selected_kind, 3, 1),
    )

    plan = ActionDeliveryPlan(
        "actions:test",
        "world:test",
        obligations,
        selected_kind.value,
        requested_scope=selected_kind.value,
    )

    assert plan.foreground_scope == selected_kind.value
    assert "requested_scope" not in json.dumps(to_json_compatible(plan))


@pytest.mark.parametrize("capacity, expected_total", ((3, 3), (2, 2)))
def test_depth_round_packer_obeys_exact_fit_and_one_unit_under(
    monkeypatch: pytest.MonkeyPatch,
    capacity: int,
    expected_total: int,
) -> None:
    kinds = tuple(DeliveryObligationKind)[:3]
    plan = ActionDeliveryPlan(
        "actions:test",
        "world:test",
        tuple(_obligation(kind, 2, priority) for priority, kind in enumerate(kinds)),
        kinds[0].value,
    )
    calls: list[dict[str, int]] = []

    def attempt(_request, **kwargs):
        counts = dict(kwargs["admitted_records"])
        calls.append(counts)
        if sum(counts.values()) > capacity:
            raise ModelRequestCapacityError(SimpleNamespace())
        return _packed_artifacts(counts, kwargs["backoff_count"])

    monkeypatch.setattr(TurnPacker, "_attempt", staticmethod(attempt))
    packed = TurnPacker().pack(
        SimpleNamespace(agent_context=SimpleNamespace(action_delivery_plan=plan)),
        binder=_fake_binder(),
        identity=None,
        call_profile=_fake_profile(),
        supports_multimodal=False,
        perception_profile=SimpleNamespace(),
    )

    assert sum(dict(packed.admitted_record_counts).values()) == expected_total
    assert dict(packed.admitted_record_counts)[kinds[0].value] == 1
    first_round_heads = [
        next(kind for kind, value in call.items() if value > prior.get(kind, 0))
        for prior, call in zip(calls, calls[1:], strict=False)
        if sum(call.values()) == sum(prior.values()) + 1
    ]
    assert first_round_heads[:3] == [kind.value for kind in kinds]


def test_oversized_optional_head_blocks_only_its_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreground_kind, oversized_kind, small_kind = tuple(DeliveryObligationKind)[:3]
    plan = ActionDeliveryPlan(
        "actions:test",
        "world:test",
        (
            _obligation(foreground_kind, 2, 0),
            _obligation(oversized_kind, 2, 1),
            _obligation(small_kind, 1, 2),
        ),
        foreground_kind.value,
    )

    def attempt(_request, **kwargs):
        counts = dict(kwargs["admitted_records"])
        if counts[oversized_kind.value] or sum(counts.values()) > 2:
            raise ModelRequestCapacityError(SimpleNamespace())
        return _packed_artifacts(counts, kwargs["backoff_count"])

    monkeypatch.setattr(TurnPacker, "_attempt", staticmethod(attempt))
    packed = TurnPacker().pack(
        SimpleNamespace(agent_context=SimpleNamespace(action_delivery_plan=plan)),
        binder=_fake_binder(),
        identity=None,
        call_profile=_fake_profile(),
        supports_multimodal=False,
        perception_profile=SimpleNamespace(),
    )

    admitted = dict(packed.admitted_record_counts)
    assert admitted[foreground_kind.value] == 1
    assert admitted[oversized_kind.value] == 0
    assert admitted[small_kind.value] == 1


@pytest.mark.parametrize("count", (1, 2, 16, 84, 167, 500))
@pytest.mark.parametrize("capacity", (1, 5))
def test_run21_fanout_shape_keeps_one_foreground_minimum_and_bounded_cost(
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    capacity: int,
) -> None:
    kind = DeliveryObligationKind.PUBLIC_EFFECT
    plan = ActionDeliveryPlan(
        "actions:test",
        "world:test",
        (_obligation(kind, count, 0),),
        kind.value,
    )

    def attempt(_request, **kwargs):
        counts = dict(kwargs["admitted_records"])
        if sum(counts.values()) > capacity:
            raise ModelRequestCapacityError(SimpleNamespace())
        return _packed_artifacts(counts, kwargs["backoff_count"])

    monkeypatch.setattr(TurnPacker, "_attempt", staticmethod(attempt))
    packed = TurnPacker().pack(
        SimpleNamespace(agent_context=SimpleNamespace(action_delivery_plan=plan)),
        binder=_fake_binder(),
        identity=None,
        call_profile=_fake_profile(),
        supports_multimodal=False,
        perception_profile=SimpleNamespace(),
    )

    admitted = dict(packed.admitted_record_counts)[kind.value]
    assert admitted == min(count, capacity)
    assert 1 <= admitted <= capacity
    assert (*plan.obligations[0].records[:admitted], *plan.obligations[0].records[admitted:]) == (
        plan.obligations[0].records
    )
