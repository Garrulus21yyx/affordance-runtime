"""Evaluation results do not carry execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import freeze_json


class ActionEvaluationStatus(StrEnum):
    EFFECT_CONFIRMED = "effect_confirmed"
    NO_EFFECT_CONFIRMED = "no_effect_confirmed"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class TaskEvaluationStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionEvaluation:
    request_id: str
    before_observation_id: str
    after_observation_id: str
    status: ActionEvaluationStatus
    reason: str
    evidence_refs: tuple[str, ...] = ()
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.request_id,
                self.before_observation_id,
                self.after_observation_id,
                self.reason,
            )
        ):
            raise ValueError("action evaluation requires request, observation lineage, and reason")
        if self.before_observation_id == self.after_observation_id:
            raise ValueError("action evaluation requires distinct before and after observations")
        if (
            self.status
            in {ActionEvaluationStatus.EFFECT_CONFIRMED, ActionEvaluationStatus.NO_EFFECT_CONFIRMED}
            and not self.evidence_refs
        ):
            raise ValueError("confirmed action evaluation requires an authoritative evidence reference")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
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
