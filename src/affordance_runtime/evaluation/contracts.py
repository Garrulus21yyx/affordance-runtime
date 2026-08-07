"""Evaluation results do not carry execution authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import freeze_json


class ActionEvaluationStatus(StrEnum):
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class TaskEvaluationStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionEvaluation:
    status: ActionEvaluationStatus
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("action evaluation reason cannot be blank")
        object.__setattr__(self, "evidence", freeze_json(self.evidence))


@dataclass(frozen=True)
class TaskEvaluation:
    status: TaskEvaluationStatus
    reason: str
    outputs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("task evaluation reason cannot be blank")
        object.__setattr__(self, "outputs", freeze_json(self.outputs))
