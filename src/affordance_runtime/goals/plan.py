"""Bounded, non-authoritative semantic GoalPlan contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import TypeAlias

from affordance_runtime.immutable import freeze_json, to_json_compatible

MAX_GOAL_PLAN_ITEMS = 8
MAX_GOAL_PLAN_TEXT_LENGTH = 500
MAX_GOAL_PLAN_ID_LENGTH = 80
_GOAL_PLAN_ID = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


@dataclass(frozen=True)
class GoalPlanItem:
    id: str
    objective: str
    done_when: str
    depends_on: tuple[str, ...] = ()
    final: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "depends_on", tuple(self.depends_on))
        if not isinstance(self.id, str) or _GOAL_PLAN_ID.fullmatch(self.id) is None:
            raise ValueError("goal plan item id must be bounded snake_case")
        for label, value in (("objective", self.objective), ("done_when", self.done_when)):
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_GOAL_PLAN_TEXT_LENGTH:
                raise ValueError(f"goal plan item {label} must be bounded and nonblank")
        if type(self.final) is not bool:
            raise TypeError("goal plan item final must be boolean")
        if len(self.depends_on) > MAX_GOAL_PLAN_ITEMS or len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("goal plan item dependencies must be bounded and unique")
        if any(not isinstance(item, str) or _GOAL_PLAN_ID.fullmatch(item) is None for item in self.depends_on):
            raise ValueError("goal plan item dependencies must use bounded root ids")


@dataclass(frozen=True)
class GoalPlan:
    task_revision: int
    plan_version: int
    items: tuple[GoalPlanItem, ...]
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        if self.task_revision < 1 or self.plan_version < 1:
            raise ValueError("goal plan requires positive task and plan versions")
        if not 1 <= len(self.items) <= MAX_GOAL_PLAN_ITEMS:
            raise ValueError("goal plan requires 1..8 items")
        if any(not isinstance(item, GoalPlanItem) for item in self.items):
            raise TypeError("goal plan items must be typed")
        ids = tuple(item.id for item in self.items)
        if len(ids) != len(set(ids)):
            raise ValueError("goal plan item ids must be unique")
        known = set(ids)
        if any(dependency not in known for item in self.items for dependency in item.depends_on):
            raise ValueError("goal plan dependency is dangling")
        if any(item.id in item.depends_on for item in self.items):
            raise ValueError("goal plan item cannot depend on itself")
        if sum(item.final for item in self.items) > 1:
            raise ValueError("goal plan supports at most one final item")
        outgoing = {item_id: [] for item_id in ids}
        indegree = {item_id: 0 for item_id in ids}
        for item in self.items:
            for prerequisite in item.depends_on:
                outgoing[prerequisite].append(item.id)
                indegree[item.id] += 1
        pending = [item_id for item_id, count in indegree.items() if count == 0]
        visited = 0
        while pending:
            current = pending.pop()
            visited += 1
            for dependent in outgoing[current]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    pending.append(dependent)
        if visited != len(ids):
            raise ValueError("goal plan dependencies must form a DAG")
        encoded = json.dumps(
            to_json_compatible({"task_revision": self.task_revision, "plan_version": self.plan_version, "items": self.items}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        object.__setattr__(self, "digest", hashlib.sha256(encoded.encode()).hexdigest())


@dataclass(frozen=True)
class GoalPlanProposal:
    task_revision: int
    items: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        if self.task_revision < 1 or not 1 <= len(self.items) <= MAX_GOAL_PLAN_ITEMS:
            raise ValueError("goal plan proposal requires task scope and 1..8 items")
        object.__setattr__(self, "items", tuple(freeze_json(item) for item in self.items))


@dataclass(frozen=True)
class Ready:
    task_revision: int
    accepted_plan: GoalPlan

    def __post_init__(self) -> None:
        if self.accepted_plan.task_revision != self.task_revision:
            raise ValueError("ready resolution and accepted plan revisions disagree")


@dataclass(frozen=True)
class NotRequired:
    task_revision: int
    reason: str

    def __post_init__(self) -> None:
        _validate_resolution(self.task_revision, self.reason)


@dataclass(frozen=True)
class NeedsInput:
    task_revision: int
    question: str
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(dict.fromkeys(self.fields)))
        if self.task_revision < 1 or not self.question.strip() or len(self.question) > 1000 or not self.fields:
            raise ValueError("NeedsInput requires task scope, question, and fields")
        if len(self.fields) > 32 or any(not item.strip() or len(item) > 120 for item in self.fields):
            raise ValueError("NeedsInput fields exceed bounds")


@dataclass(frozen=True)
class Unsupported:
    task_revision: int
    reason: str

    def __post_init__(self) -> None:
        _validate_resolution(self.task_revision, self.reason)


@dataclass(frozen=True)
class Failed:
    task_revision: int
    reason: str

    def __post_init__(self) -> None:
        _validate_resolution(self.task_revision, self.reason)


GoalPlanResolution: TypeAlias = Ready | NotRequired | NeedsInput | Unsupported | Failed
GoalCompilerOutcome: TypeAlias = GoalPlanProposal | NotRequired | NeedsInput | Unsupported | Failed


@dataclass(frozen=True)
class AgentGoalPlanView:
    task_revision: int
    resolution: str
    plan_version: int | None = None
    plan_digest: str = ""
    items: tuple[GoalPlanItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        if self.task_revision < 1 or self.resolution not in {"ready", "not_required", "unavailable"}:
            raise ValueError("goal plan view disposition is invalid")
        if self.resolution == "ready":
            if self.plan_version is None or self.plan_version < 1 or re.fullmatch(r"[0-9a-f]{64}", self.plan_digest) is None or not self.items:
                raise ValueError("ready goal plan view requires accepted plan identity and items")
        elif self.plan_version is not None or self.plan_digest or self.items:
            raise ValueError("empty goal plan view cannot invent plan state")


def _validate_resolution(task_revision: int, reason: str) -> None:
    if task_revision < 1 or not reason.strip() or len(reason) > 240:
        raise ValueError("goal resolution requires task scope and bounded reason")
