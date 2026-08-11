"""Runtime-private deterministic filtering and paging of Internal ActionSpace."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.planning_contracts import LocalObjective
from affordance_runtime.world.admission_issue import (
    AdmissionContractOwner,
    AdmissionIssue,
    AdmissionIssueCode,
)
from affordance_runtime.world.contracts import ActionOption, ActionSpace
from affordance_runtime.world.page_cursor import cursor_fingerprint, decode_cursor, encode_cursor
from affordance_runtime.world.relevance import ActionRelevance, ActionRelevancePolicy, ActionRelevanceRole

_ROLE_ORDER = {
    ActionRelevanceRole.DIRECT: 0,
    ActionRelevanceRole.ENABLING: 1,
    ActionRelevanceRole.INFORMATION: 2,
    ActionRelevanceRole.OTHER: 3,
}


def canonical_action_query(query: str) -> str:
    """Return the sole bounded query semantics used by action paging."""

    if not isinstance(query, str):
        raise TypeError("action page query must be text")
    return query[:120].casefold()


@dataclass(frozen=True)
class InternalActionPage:
    page_id: str
    action_space_id: str
    visible_action_ids: tuple[str, ...]
    visible_destinations: tuple[tuple[str, tuple[str, ...]], ...]
    total_count: int
    has_more: bool
    cursor: str = ""
    next_cursor: str = ""
    offset: int = 0
    query: str = ""
    target_id: str = ""
    relevance_role: ActionRelevanceRole | None = None
    relevance: tuple[tuple[str, ActionRelevance], ...] = ()
    objective_digest: str = "objective:none"

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_action_ids", tuple(self.visible_action_ids))
        destinations = tuple((action_id, tuple(items)) for action_id, items in self.visible_destinations)
        object.__setattr__(self, "visible_destinations", destinations)
        object.__setattr__(self, "relevance", tuple(self.relevance))
        if self.offset < 0 or self.total_count < self.offset + len(self.visible_action_ids):
            raise ValueError("internal action page counts are inconsistent")
        if self.has_more != (self.total_count > self.offset + len(self.visible_action_ids)):
            raise ValueError("internal action page continuation is inconsistent")
        if self.has_more != bool(self.next_cursor):
            raise ValueError("has_more requires a usable next cursor")
        if len(set(self.visible_action_ids)) != len(self.visible_action_ids):
            raise ValueError("internal action page IDs must be unique")
        if tuple(action_id for action_id, _ in destinations) != self.visible_action_ids:
            raise ValueError("internal action page destinations must bind every visible action")
        if any(len(set(items)) != len(items) for _, items in destinations):
            raise ValueError("internal action page destination IDs must be unique")
        if self.page_id != _page_id(
            self.action_space_id,
            self.visible_action_ids,
            destinations,
            self.cursor,
            self.offset,
            self.query,
            self.target_id,
            self.relevance_role,
            self.objective_digest,
        ):
            raise ValueError("internal action page identity does not bind its exact projection")

    def relevance_for(self, action_id: str) -> ActionRelevance | None:
        return next((item for candidate, item in self.relevance if candidate == action_id), None)

    def visible_destination_ids(self, action_id: str) -> tuple[str, ...]:
        return next((items for candidate, items in self.visible_destinations if candidate == action_id), ())

    def selection_issue(self, action_id: str, destination_id: str = "") -> AdmissionIssue | None:
        if action_id not in self.visible_action_ids:
            return AdmissionIssue(
                AdmissionIssueCode.ACTION_OUTSIDE_CURRENT_PAGE,
                ("actions",),
                AdmissionContractOwner.CURRENT_ACTION_PAGE,
                {"offered_action_ids": self.visible_action_ids},
                {"action_id_offered": False},
            )
        if destination_id and destination_id not in self.visible_destination_ids(action_id):
            return AdmissionIssue(
                AdmissionIssueCode.DESTINATION_OUTSIDE_CURRENT_PAGE,
                ("destination_id",),
                AdmissionContractOwner.CURRENT_ACTION_PAGE,
                {"offered_destination_ids": self.visible_destination_ids(action_id)},
                {"destination_id_offered": False},
            )
        return None


@dataclass(frozen=True)
class ActionPager:
    page_size: int = 32
    relevance_policy: ActionRelevancePolicy = ActionRelevancePolicy()
    max_projected_bytes: int = 24 * 1024

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 128:
            raise ValueError("action page size must be within [1, 128]")
        if self.max_projected_bytes <= 0:
            raise ValueError("action page byte budget must be positive")

    def page(
        self,
        action_space: ActionSpace,
        objective: LocalObjective | None = None,
        *,
        query: str = "",
        target_id: str = "",
        relevance_role: ActionRelevanceRole | str | None = None,
        labels: Mapping[str, str] | None = None,
        cursor: str = "",
        page_size: int | None = None,
        max_destinations_per_option: int = 16,
        max_targets: int = 64,
    ) -> InternalActionPage:
        query = canonical_action_query(query)
        role = ActionRelevanceRole(relevance_role) if relevance_role else None
        labels = labels or {}
        limit = min(self.page_size, page_size or self.page_size)
        if limit <= 0 or max_destinations_per_option <= 0 or max_targets <= 0:
            raise ValueError("paging limits must be positive")
        objective_digest = _objective_digest(objective)
        fingerprint = cursor_fingerprint(
            action_space.action_space_id,
            query,
            target_id,
            role,
            objective_digest,
            limit,
            max_destinations_per_option,
            max_targets,
        )
        offset = decode_cursor(cursor, fingerprint) if cursor else 0
        ranked = _ranked_options(action_space, objective, self.relevance_policy, query, target_id, role, labels)
        if offset > len(ranked):
            raise ValueError("action page cursor is outside the filtered result")
        visible = _select_page_slice(
            ranked,
            offset,
            limit,
            max_destinations_per_option,
            max_targets,
            self.max_projected_bytes,
        )
        visible_ids = tuple(item[1].action_id for item in visible)
        visible_destinations = tuple(
            (item[1].action_id, item[1].eligible_destination_ids[:max_destinations_per_option])
            for item in visible
        )
        next_offset = offset + len(visible)
        has_more = next_offset < len(ranked)
        if has_more and not visible:
            raise ValueError("action page budgets cannot represent the next option")
        next_cursor = encode_cursor(next_offset, fingerprint) if has_more else ""
        page_id = _page_id(
            action_space.action_space_id,
            visible_ids,
            visible_destinations,
            cursor,
            offset,
            query,
            target_id,
            role,
            objective_digest,
        )
        return InternalActionPage(
            page_id=page_id,
            action_space_id=action_space.action_space_id,
            visible_action_ids=visible_ids,
            visible_destinations=visible_destinations,
            total_count=len(ranked),
            has_more=has_more,
            cursor=cursor,
            next_cursor=next_cursor,
            offset=offset,
            query=query,
            target_id=target_id,
            relevance_role=role,
            relevance=tuple((item[1].action_id, item[2]) for item in visible),
            objective_digest=objective_digest,
        )

    def single_action_page(
        self,
        action_space: ActionSpace,
        objective: LocalObjective | None,
        action_id: str,
        destination_id: str = "",
        *,
        max_destinations_per_option: int = 16,
    ) -> InternalActionPage:
        option = action_space.find(action_id)
        if option is None:
            raise ValueError("execution page action is absent from the current ActionSpace")
        if destination_id and destination_id not in option.eligible_destination_ids:
            raise ValueError("execution page destination is absent from the current ActionSpace")
        visible_destinations = (
            (destination_id,)
            if destination_id
            else option.eligible_destination_ids[:max_destinations_per_option]
        )
        objective_digest = _objective_digest(objective)
        destinations = ((action_id, visible_destinations),)
        relevance = self.relevance_policy.classify(option, objective)
        page_id = _page_id(
            action_space.action_space_id,
            (action_id,),
            destinations,
            "",
            0,
            "",
            "",
            None,
            objective_digest,
        )
        return InternalActionPage(
            page_id=page_id,
            action_space_id=action_space.action_space_id,
            visible_action_ids=(action_id,),
            visible_destinations=destinations,
            total_count=1,
            has_more=False,
            relevance=((action_id, relevance),),
            objective_digest=objective_digest,
        )


def _page_id(
    action_space_id: str,
    visible_ids: tuple[str, ...],
    visible_destinations: tuple[tuple[str, tuple[str, ...]], ...],
    cursor: str,
    offset: int,
    query: str,
    target_id: str,
    role: ActionRelevanceRole | None,
    objective_digest: str,
) -> str:
    payload = (
        action_space_id,
        cursor,
        offset,
        visible_ids,
        visible_destinations,
        canonical_action_query(query),
        target_id,
        role.value if role else "",
        objective_digest,
    )
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return f"action-page:{digest}"


def _ranked_options(
    action_space: ActionSpace,
    objective: LocalObjective | None,
    relevance_policy: ActionRelevancePolicy,
    query: str,
    target_id: str,
    role: ActionRelevanceRole | None,
    labels: Mapping[str, str],
) -> list[tuple[int, ActionOption, ActionRelevance]]:
    ranked = [
        (index, option, relevance_policy.classify(option, objective))
        for index, option in enumerate(action_space.options)
        if not target_id or option.target_id == target_id
    ]
    if role is not None:
        ranked = [item for item in ranked if item[2].role == role]
    if query:
        needle = canonical_action_query(query)
        ranked = [
            item
            for item in ranked
            if needle in f"{labels.get(item[1].target_id, '')} {item[1].description}".casefold()
        ]
    if objective is not None:
        ranked.sort(key=lambda item: (_ROLE_ORDER[item[2].role], -item[2].score, item[0]))
    return ranked


def _select_page_slice(
    ranked: list[tuple[int, ActionOption, ActionRelevance]],
    offset: int,
    limit: int,
    max_destinations: int,
    max_targets: int,
    max_bytes: int,
) -> list[tuple[int, ActionOption, ActionRelevance]]:
    visible: list[tuple[int, ActionOption, ActionRelevance]] = []
    projected_bytes = 0
    pinned_targets: set[str] = set()
    for item in ranked[offset : offset + limit]:
        option_bytes = _projected_option_weight(item[1], max_destinations)
        if option_bytes > max_bytes:
            raise ValueError("single action option exceeds the page byte budget")
        option_targets = {item[1].target_id, *item[1].eligible_destination_ids[:max_destinations]}
        if len(pinned_targets | option_targets) > max_targets or projected_bytes + option_bytes > max_bytes:
            break
        visible.append(item)
        projected_bytes += option_bytes
        pinned_targets.update(option_targets)
    return visible


def _projected_option_weight(option: ActionOption, max_destinations: int) -> int:
    payload = (
        option.action_id,
        option.semantic_action,
        option.target_id,
        option.effect_category,
        to_json_compatible(option.parameter_schema),
        option.description,
        option.semantic_effects,
        option.risk,
        option.destination_required,
        option.eligible_destination_ids[:max_destinations],
        option.observation_barrier,
    )
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _objective_digest(objective: LocalObjective | None) -> str:
    if objective is None:
        return "objective:none"
    payload = to_json_compatible(objective)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"objective:{digest}"
