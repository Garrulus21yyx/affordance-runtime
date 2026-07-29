from __future__ import annotations

import pytest

from affordance_runtime.collection_window import (
    OrdinalRouteKind,
    _SnapshotAffordanceView,
    resolve_global_ordinal_constraint,
)
from affordance_runtime.planner_context import AffordanceSummary


def _item(identifier: str, position: int) -> AffordanceSummary:
    return AffordanceSummary(
        id=identifier,
        surface="dom",
        role="link",
        label=identifier,
        action="activate",
        confidence=1.0,
        state={"collection_position": position},
    )


def _page(page: int, *, current: bool = False) -> AffordanceSummary:
    return AffordanceSummary(
        id=f"page-{page}",
        surface="dom",
        role="link",
        label=str(page),
        action="activate",
        confidence=1.0,
        state={
            "pagination_owner": "results-pages",
            "pagination_relation": "page",
            "pagination_page": page,
            "pagination_current": current,
            "pagination_total_pages": 3,
        },
    )


def test_snapshot_affordance_view_state_is_deeply_immutable_from_source_payload() -> None:
    state = {
        "pagination_owner": "results-pages",
        "nested": {"page": 1},
    }

    view = _SnapshotAffordanceView(
        id="page-1",
        role="link",
        label="1",
        action="activate",
        state=state,
    )

    state["pagination_owner"] = "mutated"
    state["nested"]["page"] = 2

    assert view.state["pagination_owner"] == "results-pages"
    assert view.state["nested"] == {"page": 1}
    with pytest.raises(TypeError):
        view.state["pagination_owner"] = "mutated"  # type: ignore[index]


def test_global_ordinal_routes_to_required_page_then_current_item() -> None:
    first_page = (*(_item(f"result-{index}", index) for index in range(1, 4)), *(_page(index, current=index == 1) for index in range(1, 4)))
    transition = resolve_global_ordinal_constraint(
        objective="Click the 4th search result",
        targets=("search result",),
        affordances=first_page,
    )

    assert transition is not None
    assert transition.kind == OrdinalRouteKind.PAGE_TRANSITION
    assert transition.target_id == "page-2"

    second_page = (*(_item(f"result-{index}", index) for index in range(4, 7)), *(_page(index, current=index == 2) for index in range(1, 4)))
    target = resolve_global_ordinal_constraint(
        objective="Click the 4th search result",
        targets=("search result",),
        affordances=second_page,
    )

    assert target is not None
    assert target.kind == OrdinalRouteKind.CURRENT_ITEM
    assert target.target_id == "result-4"


def test_global_ordinal_falls_through_without_one_coherent_window() -> None:
    no_active_page = (*(_item(f"result-{index}", index) for index in range(1, 4)), *(_page(index) for index in range(1, 4)))
    ambiguous_ordinal = (*(_item(f"result-{index}", index) for index in range(1, 4)), *(_page(index, current=index == 1) for index in range(1, 4)))

    assert resolve_global_ordinal_constraint(
        objective="Click the 4th search result",
        targets=("search result",),
        affordances=no_active_page,
    ) is None
    assert resolve_global_ordinal_constraint(
        objective="Compare the 3rd and 4th results",
        targets=("search result",),
        affordances=ambiguous_ordinal,
    ) is None
    assert resolve_global_ordinal_constraint(
        objective="Press Search and verify results are visible",
        targets=("search result",),
        affordances=ambiguous_ordinal,
    ) is None
