"""Typed, provider-neutral constraints for paginated ordinal collections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Protocol

from affordance_runtime.browser_session import BrowserSnapshot


class CollectionAffordanceView(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def role(self) -> str: ...

    @property
    def label(self) -> str: ...

    @property
    def action(self) -> str: ...

    @property
    def state(self) -> dict[str, Any]: ...


class OrdinalRouteKind(StrEnum):
    CURRENT_ITEM = "current_item"
    PAGE_TRANSITION = "page_transition"


@dataclass(frozen=True)
class OrdinalRouteConstraint:
    kind: OrdinalRouteKind
    target_id: str
    requested_ordinal: int
    current_page: int
    target_page: int
    page_size: int
    total_pages: int
    pagination_owner: str


@dataclass(frozen=True)
class _SnapshotAffordanceView:
    id: str
    role: str
    label: str
    action: str
    state: dict[str, Any]


_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def snapshot_collection_affordances(snapshot: BrowserSnapshot) -> tuple[_SnapshotAffordanceView, ...]:
    """Project current source state onto semantic ids for independent validation."""

    source_by_id = {item.id: item for item in snapshot.affordance_model.affordances}
    views: list[_SnapshotAffordanceView] = []
    for target in snapshot.unified_affordances:
        source = next(
            (
                source_by_id[candidate.source_affordance_id]
                for candidate in target.grounding_candidates
                if candidate.source_affordance_id in source_by_id
            ),
            None,
        )
        if source is None or len(target.supported_actions) != 1:
            continue
        views.append(
            _SnapshotAffordanceView(
                id=target.semantic_target_id,
                role=target.role,
                label=target.label,
                action=next(iter(target.supported_actions)),
                state=dict(source.state),
            )
        )
    if views:
        return tuple(views)
    return tuple(
        _SnapshotAffordanceView(item.id, item.role, item.label, item.action, dict(item.state))
        for item in snapshot.affordance_model.affordances
    )


def resolve_global_ordinal_constraint(
    *,
    objective: str,
    targets: Iterable[str],
    affordances: Iterable[CollectionAffordanceView],
) -> OrdinalRouteConstraint | None:
    """Resolve one ordinal only from a coherent current page window."""

    requested = _requested_ordinals(" ".join((objective, *targets)))
    if len(requested) != 1:
        return None
    requested_ordinal = next(iter(requested))
    items = tuple(affordances)
    pagination = [item for item in items if item.state.get("pagination_owner")]
    owners = {str(item.state["pagination_owner"]) for item in pagination}
    if len(owners) != 1:
        return None
    owner = next(iter(owners))
    current_controls = [
        item
        for item in pagination
        if item.state.get("pagination_relation") == "page"
        and item.state.get("pagination_current") is True
        and isinstance(item.state.get("pagination_page"), int)
    ]
    if len(current_controls) != 1:
        return None
    current_page = int(current_controls[0].state["pagination_page"])
    totals = {
        int(item.state["pagination_total_pages"])
        for item in pagination
        if isinstance(item.state.get("pagination_total_pages"), int)
    }
    if len(totals) != 1:
        return None
    total_pages = next(iter(totals))
    collection_items = [
        item
        for item in items
        if not item.state.get("pagination_owner")
        and isinstance(item.state.get("collection_position"), int)
        and int(item.state["collection_position"]) > 0
    ]
    positions = {int(item.state["collection_position"]) for item in collection_items}
    if not positions:
        return None
    current_matches = [
        item for item in collection_items if item.state["collection_position"] == requested_ordinal
    ]
    if len(current_matches) == 1:
        return OrdinalRouteConstraint(
            OrdinalRouteKind.CURRENT_ITEM,
            current_matches[0].id,
            requested_ordinal,
            current_page,
            current_page,
            len(positions),
            total_pages,
            owner,
        )
    if current_matches:
        return None
    page_size = len(positions)
    target_page = (requested_ordinal - 1) // page_size + 1
    if target_page == current_page or target_page > total_pages:
        return None
    page_targets = [
        item
        for item in pagination
        if item.state.get("pagination_relation") == "page"
        and item.state.get("pagination_page") == target_page
    ]
    if len(page_targets) != 1:
        return None
    return OrdinalRouteConstraint(
        OrdinalRouteKind.PAGE_TRANSITION,
        page_targets[0].id,
        requested_ordinal,
        current_page,
        target_page,
        page_size,
        total_pages,
        owner,
    )


def _requested_ordinals(value: str) -> set[int]:
    ordinals = {
        int(match.group(1))
        for match in re.finditer(r"\b(\d+)(?:st|nd|rd|th)\b", value, flags=re.IGNORECASE)
    }
    lowered = value.casefold()
    ordinals.update(number for word, number in _ORDINAL_WORDS.items() if re.search(rf"\b{word}\b", lowered))
    return ordinals
