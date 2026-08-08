"""Runtime-private deterministic filtering and paging of Internal ActionSpace."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.task.planning_contracts import LocalObjective
from affordance_runtime.world.contracts import ActionOption, ActionSpace
from affordance_runtime.world.relevance import ActionRelevance, ActionRelevancePolicy, ActionRelevanceRole

_ROLE_ORDER = {
    ActionRelevanceRole.DIRECT: 0,
    ActionRelevanceRole.ENABLING: 1,
    ActionRelevanceRole.INFORMATION: 2,
    ActionRelevanceRole.OTHER: 3,
}


@dataclass(frozen=True)
class InternalActionPage:
    page_id: str
    action_space_id: str
    visible_action_ids: tuple[str, ...]
    total_count: int
    has_more: bool
    query: str = ""
    target_id: str = ""
    relevance_role: ActionRelevanceRole | None = None
    relevance: tuple[tuple[str, ActionRelevance], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_action_ids", tuple(self.visible_action_ids))
        object.__setattr__(self, "relevance", tuple(self.relevance))
        if self.total_count < len(self.visible_action_ids) or self.has_more != (
            self.total_count > len(self.visible_action_ids)
        ):
            raise ValueError("internal action page counts are inconsistent")
        if len(set(self.visible_action_ids)) != len(self.visible_action_ids):
            raise ValueError("internal action page IDs must be unique")
        if self.page_id != _page_id(
            self.action_space_id,
            self.visible_action_ids,
            self.query,
            self.target_id,
            self.relevance_role,
        ):
            raise ValueError("internal action page identity does not bind its exact projection")

    def relevance_for(self, action_id: str) -> ActionRelevance | None:
        return next((item for candidate, item in self.relevance if candidate == action_id), None)


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
    ) -> InternalActionPage:
        query = query[:120]
        role = ActionRelevanceRole(relevance_role) if relevance_role else None
        labels = labels or {}
        ranked = [
            (index, option, self.relevance_policy.classify(option, objective))
            for index, option in enumerate(action_space.options)
            if (not target_id or option.target_id == target_id)
        ]
        if role is not None:
            ranked = [item for item in ranked if item[2].role == role]
        if query:
            needle = query.casefold()
            ranked = [
                item
                for item in ranked
                if needle in f"{labels.get(item[1].target_id, '')} {item[1].description}".casefold()
            ]
        if objective is not None:
            ranked.sort(key=lambda item: (_ROLE_ORDER[item[2].role], -item[2].score, item[0]))
        visible: list[tuple[int, ActionOption, ActionRelevance]] = []
        projected_bytes = 0
        for item in ranked[: self.page_size]:
            option_bytes = _projected_option_weight(item[1])
            if visible and projected_bytes + option_bytes > self.max_projected_bytes:
                break
            visible.append(item)
            projected_bytes += option_bytes
        visible_ids = tuple(item[1].action_id for item in visible)
        page_id = _page_id(action_space.action_space_id, visible_ids, query, target_id, role)
        return InternalActionPage(
            page_id,
            action_space.action_space_id,
            visible_ids,
            len(ranked),
            len(ranked) > len(visible),
            query,
            target_id,
            role,
            tuple((item[1].action_id, item[2]) for item in visible),
        )


def _page_id(
    action_space_id: str,
    visible_ids: tuple[str, ...],
    query: str,
    target_id: str,
    role: ActionRelevanceRole | None,
) -> str:
    payload = (action_space_id, visible_ids, query.casefold(), target_id, role.value if role else "")
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return f"action-page:{digest}"


def _projected_option_weight(option) -> int:
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
        option.eligible_destination_ids,
        option.observation_barrier,
    )
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
