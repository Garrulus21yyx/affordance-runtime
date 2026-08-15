from dataclasses import dataclass, replace

import pytest

from affordance_runtime.actions import (
    ActionOption,
    ActionPager,
    ActionRelevanceRole,
    ActionRisk,
    ActionSpace,
)


@dataclass(frozen=True)
class _Objective:
    direct_target_ids: tuple[str, ...] = ()
    direct_effects: tuple[str, ...] = ()
    enabling_target_ids: tuple[str, ...] = ()
    enabling_action_hints: tuple[str, ...] = ()


def _option(index: int, *, action: str = "activate", effect: str = "changed") -> ActionOption:
    return ActionOption(
        f"action:{index:02}",
        "obs:1",
        action,
        f"target:{index:02}",
        "observation" if action == "read" else "local_reversible",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "schema:1",
        (f"binding:{index:02}",),
        f"{action} public target {index:02}",
        () if action == "read" else (effect,),
        ActionRisk.LOW,
    )


def test_action_page_is_bounded_truthful_and_other_remains_retrievable() -> None:
    space = ActionSpace("obs:1", tuple(_option(index) for index in range(40)))
    pager = ActionPager(page_size=8)
    objective = _Objective(direct_target_ids=("target:00",))

    default = pager.page(space, objective)
    other = pager.page(space, objective, relevance_role=ActionRelevanceRole.OTHER)

    assert default.visible_action_ids[0] == "action:00"
    assert len(default.visible_action_ids) == 8
    assert default.total_count == 40 and default.has_more
    assert "action:39" not in default.visible_action_ids
    assert "action:39" in other.visible_action_ids or other.has_more
    assert other.page_id != default.page_id


def test_cursor_pager_traverses_every_action_without_overlap() -> None:
    space = ActionSpace("obs:1", tuple(_option(index) for index in range(20)))
    pager = ActionPager(page_size=6)
    pages = []
    cursor = ""

    while True:
        page = pager.page(space, cursor=cursor)
        pages.append(page)
        if not page.has_more:
            break
        cursor = page.next_cursor

    flattened = tuple(action_id for page in pages for action_id in page.visible_action_ids)
    assert flattened == tuple(option.action_id for option in space.options)
    assert len(flattened) == len(set(flattened))
    assert pages[-1].next_cursor == ""


def test_filtered_cursor_is_bound_to_its_exact_filter() -> None:
    space = ActionSpace(
        "obs:1",
        tuple(_option(index, action="read", effect="") for index in range(12)),
    )
    pager = ActionPager(page_size=5)

    first = pager.page(space, relevance_role=ActionRelevanceRole.INFORMATION)
    second = pager.page(
        space,
        relevance_role=ActionRelevanceRole.INFORMATION,
        cursor=first.next_cursor,
    )

    assert first.visible_action_ids != second.visible_action_ids
    with pytest.raises(ValueError, match="cursor"):
        pager.page(space, query="different", cursor=first.next_cursor)


def test_single_oversized_option_fails_closed_at_the_page_budget() -> None:
    option = replace(_option(0), description="x" * 1_000)

    with pytest.raises(ValueError, match="byte budget"):
        ActionPager(max_projected_bytes=100).page(ActionSpace("obs:1", (option,)))


def test_page_weight_counts_only_the_visible_destination_slice() -> None:
    destinations = tuple(f"destination:{index:04}" for index in range(500))
    option = replace(
        _option(0),
        semantic_action="drag_to",
        destination_required=True,
        eligible_destination_ids=destinations,
        verification_contract_digest="",
    )

    page = ActionPager(max_projected_bytes=600).page(
        ActionSpace("obs:1", (option,)),
        max_destinations_per_option=1,
    )

    assert page.visible_action_ids == (option.action_id,)
    assert page.visible_destination_ids(option.action_id) == (destinations[0],)


def test_empty_filtered_page_is_complete_empty_not_truncated() -> None:
    page = ActionPager(page_size=1).page(
        ActionSpace("obs:1", (_option(0),)),
        target_id="target:missing",
    )

    assert page.visible_action_ids == ()
    assert page.total_count == 0
    assert not page.has_more and not page.next_cursor


def test_default_page_orders_explicit_relevance_without_changing_membership() -> None:
    options = (
        _option(0),
        _option(1),
        _option(2, action="read", effect=""),
        _option(3),
    )
    objective = _Objective(
        direct_target_ids=("target:00",),
        enabling_target_ids=("target:01",),
    )

    page = ActionPager(page_size=8).page(ActionSpace("obs:1", options), objective)

    assert page.visible_action_ids == ("action:00", "action:01", "action:02", "action:03")
    assert tuple(item.role for _, item in page.relevance) == (
        ActionRelevanceRole.DIRECT,
        ActionRelevanceRole.ENABLING,
        ActionRelevanceRole.INFORMATION,
        ActionRelevanceRole.OTHER,
    )
