"""Optional, replaceable high-level planning hypotheses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from affordance_runtime.immutable import freeze_json


@dataclass(frozen=True)
class Milestone:
    milestone_id: str
    desired_state: dict[str, Any]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.milestone_id.strip() or not self.desired_state:
            raise ValueError("milestone requires identity and desired world state")
        object.__setattr__(self, "desired_state", freeze_json(self.desired_state))


@dataclass(frozen=True)
class TaskPlan:
    plan_id: str
    milestones: tuple[Milestone, ...]
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id.strip() or not self.milestones:
            raise ValueError("task plan requires identity and milestones")
        object.__setattr__(self, "milestones", tuple(self.milestones))


@dataclass(frozen=True)
class LocalObjective:
    desired_state: dict[str, Any]
    milestone_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.desired_state:
            raise ValueError("local objective requires desired world state")
        object.__setattr__(self, "desired_state", freeze_json(self.desired_state))
        object.__setattr__(self, "context", freeze_json(self.context))
