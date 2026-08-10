"""Evaluation results do not carry execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.evaluation.evidence import validate_evidence_refs
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


class CriterionEvaluationStatus(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
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
        if not isinstance(self.status, ActionEvaluationStatus):
            raise TypeError("action evaluation status must be typed")
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
        confirmed = self.status in {
            ActionEvaluationStatus.EFFECT_CONFIRMED,
            ActionEvaluationStatus.NO_EFFECT_CONFIRMED,
        }
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(tuple(self.evidence_refs), allow_empty=not confirmed),
        )
        if _contains_secret_key(self.evidence):
            raise ValueError("action evaluation evidence cannot contain secret fields")
        object.__setattr__(self, "evidence", freeze_json(self.evidence))


@dataclass(frozen=True)
class CriterionEvaluation:
    criterion_id: str
    status: CriterionEvaluationStatus
    evidence_refs: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, CriterionEvaluationStatus):
            raise TypeError("criterion evaluation status must be typed")
        if not self.criterion_id.strip() or not self.reason.strip():
            raise ValueError("criterion evaluation requires identity and reason")
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(
                tuple(self.evidence_refs),
                allow_empty=self.status != CriterionEvaluationStatus.SATISFIED,
            ),
        )


@dataclass(frozen=True)
class EvaluatedOutput:
    output_id: str
    value: object
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.output_id.strip():
            raise ValueError("evaluated output requires identity")
        object.__setattr__(self, "value", freeze_json(self.value))
        object.__setattr__(
            self,
            "evidence_refs",
            validate_evidence_refs(tuple(self.evidence_refs), allow_empty=False),
        )


@dataclass(frozen=True)
class TaskEvaluation:
    task_id: str
    observation_id: str
    status: TaskEvaluationStatus
    reason: str
    criteria: tuple[CriterionEvaluation, ...] = ()
    completion_evidence_refs: tuple[str, ...] = ()
    outputs: tuple[EvaluatedOutput, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaskEvaluationStatus):
            raise TypeError("task evaluation status must be typed")
        if not self.task_id.strip() or not self.observation_id.strip() or not self.reason.strip():
            raise ValueError("task evaluation requires task, observation, and reason")
        criteria = tuple(self.criteria)
        outputs = tuple(self.outputs)
        if any(not isinstance(item, CriterionEvaluation) for item in criteria):
            raise TypeError("task evaluation criteria must be typed")
        if any(not isinstance(item, EvaluatedOutput) for item in outputs):
            raise TypeError("task evaluation outputs must be typed")
        if len({item.criterion_id for item in criteria}) != len(criteria):
            raise ValueError("task evaluation criterion IDs must be unique")
        if len({item.output_id for item in outputs}) != len(outputs):
            raise ValueError("task evaluation output IDs must be unique")
        object.__setattr__(self, "criteria", criteria)
        object.__setattr__(
            self,
            "completion_evidence_refs",
            validate_evidence_refs(
                tuple(self.completion_evidence_refs),
                allow_empty=self.status != TaskEvaluationStatus.COMPLETE,
            ),
        )
        object.__setattr__(self, "outputs", outputs)


def _contains_secret_key(value: object) -> bool:
    markers = ("password", "secret", "token", "credential", "authorization", "api_key", "apikey")
    if isinstance(value, Mapping):
        return any(
            any(marker in str(key).casefold().replace("-", "_") for marker in markers)
            or _contains_secret_key(item)
            for key, item in value.items()
        )
    if isinstance(value, tuple | list):
        return any(_contains_secret_key(item) for item in value)
    return False
