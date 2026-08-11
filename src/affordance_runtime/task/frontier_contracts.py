"""Closed rolling-horizon task-frontier contracts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias

from affordance_runtime.evaluation.contracts import CriterionEvaluationStatus
from affordance_runtime.immutable import freeze_json

_ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,239}")
_FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
_OBJECTIVE_ID = re.compile(r"objective:[1-9][0-9]{0,9}")
_MAX_REQUIREMENTS = 32
_MAX_CHECKPOINTS = 32
_MAX_VALUES = 64


def _require_id(value: str, name: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")


def _requirements(values: tuple[str, ...]) -> tuple[str, ...]:
    values = tuple(values)
    if (
        not values
        or len(values) > _MAX_REQUIREMENTS
        or len(set(values)) != len(values)
    ):
        raise ValueError("objective requirements must be nonempty, unique, and bounded")
    for value in values:
        _require_id(value, "objective requirement id")
    return values


class ObjectivePredicateKind(StrEnum):
    FACT_AVAILABLE = "fact_available"
    TARGET_FIELD_EQUALS = "target_field_equals"
    TARGET_PRESENT = "target_present"
    TARGET_ABSENT = "target_absent"
    TASK_OUTCOME_IS = "task_outcome_is"


@dataclass(frozen=True)
class FactAvailable:
    fact_ref: str
    kind: ObjectivePredicateKind = field(
        default=ObjectivePredicateKind.FACT_AVAILABLE, init=False,
    )

    def __post_init__(self) -> None:
        if not self.fact_ref.startswith("fact:"):
            raise ValueError("fact-available predicate requires a canonical fact reference")
        _require_id(self.fact_ref, "fact reference")


@dataclass(frozen=True)
class FactReferenceExpected:
    fact_ref: str

    def __post_init__(self) -> None:
        if not self.fact_ref.startswith("fact:"):
            raise ValueError("expected fact reference must be canonical")
        _require_id(self.fact_ref, "expected fact reference")


@dataclass(frozen=True)
class LiteralExpected:
    value: object

    def __post_init__(self) -> None:
        if not (
            self.value is None
            or type(self.value) in {str, int, float, bool}
        ):
            raise TypeError("objective literal must be a public JSON scalar")
        if isinstance(self.value, str) and len(self.value) > 1_024:
            raise ValueError("objective literal exceeds its public bound")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("objective literal must be finite")
        object.__setattr__(self, "value", freeze_json(self.value))


ObjectiveExpected: TypeAlias = FactReferenceExpected | LiteralExpected


@dataclass(frozen=True)
class TargetFieldEquals:
    target_id: str
    field_name: str
    expected: ObjectiveExpected
    kind: ObjectivePredicateKind = field(
        default=ObjectivePredicateKind.TARGET_FIELD_EQUALS, init=False,
    )

    def __post_init__(self) -> None:
        _require_id(self.target_id, "objective target id")
        if _FIELD.fullmatch(self.field_name) is None:
            raise ValueError("objective target field is invalid")
        if not isinstance(self.expected, FactReferenceExpected | LiteralExpected):
            raise TypeError("target-field predicate requires a typed expected value")


@dataclass(frozen=True)
class TargetPresent:
    target_id: str
    kind: ObjectivePredicateKind = field(
        default=ObjectivePredicateKind.TARGET_PRESENT, init=False,
    )

    def __post_init__(self) -> None:
        _require_id(self.target_id, "objective target id")


@dataclass(frozen=True)
class TargetAbsent:
    target_id: str
    kind: ObjectivePredicateKind = field(
        default=ObjectivePredicateKind.TARGET_ABSENT, init=False,
    )

    def __post_init__(self) -> None:
        _require_id(self.target_id, "objective target id")


class TaskOutcomeStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class TaskOutcomeIs:
    status: TaskOutcomeStatus
    kind: ObjectivePredicateKind = field(
        default=ObjectivePredicateKind.TASK_OUTCOME_IS, init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaskOutcomeStatus):
            raise TypeError("task-outcome predicate status must be typed")


ObjectivePredicate: TypeAlias = (
    FactAvailable | TargetFieldEquals | TargetPresent | TargetAbsent | TaskOutcomeIs
)


class ObjectiveOperationKind(StrEnum):
    NONE = "none"
    PROPOSE = "propose"
    RETAIN = "retain"
    REPLACE = "replace"


@dataclass(frozen=True)
class NoObjectiveOperation:
    kind: ObjectiveOperationKind = field(
        default=ObjectiveOperationKind.NONE, init=False,
    )


@dataclass(frozen=True)
class ProposeObjective:
    intended_requirement_ids: tuple[str, ...]
    predicate: ObjectivePredicate
    kind: ObjectiveOperationKind = field(
        default=ObjectiveOperationKind.PROPOSE, init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "intended_requirement_ids", _requirements(self.intended_requirement_ids),
        )
        if not isinstance(self.predicate, _PREDICATE_TYPES):
            raise TypeError("objective proposal predicate must be typed")


@dataclass(frozen=True)
class RetainObjective:
    active_objective_id: str
    kind: ObjectiveOperationKind = field(
        default=ObjectiveOperationKind.RETAIN, init=False,
    )

    def __post_init__(self) -> None:
        if _OBJECTIVE_ID.fullmatch(self.active_objective_id) is None:
            raise ValueError("retained objective id is invalid")


@dataclass(frozen=True)
class ReplaceObjective:
    replaces_objective_id: str
    intended_requirement_ids: tuple[str, ...]
    predicate: ObjectivePredicate
    kind: ObjectiveOperationKind = field(
        default=ObjectiveOperationKind.REPLACE, init=False,
    )

    def __post_init__(self) -> None:
        if _OBJECTIVE_ID.fullmatch(self.replaces_objective_id) is None:
            raise ValueError("replaced objective id is invalid")
        object.__setattr__(
            self, "intended_requirement_ids", _requirements(self.intended_requirement_ids),
        )
        if not isinstance(self.predicate, _PREDICATE_TYPES):
            raise TypeError("objective replacement predicate must be typed")


ObjectiveOperation: TypeAlias = (
    NoObjectiveOperation | ProposeObjective | RetainObjective | ReplaceObjective
)


class ObjectiveCheckpointStatus(StrEnum):
    VERIFIED = "verified"
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class ActiveObjective:
    objective_id: str
    intended_requirement_ids: tuple[str, ...]
    predicate: ObjectivePredicate
    admitted_context_id: str

    def __post_init__(self) -> None:
        if _OBJECTIVE_ID.fullmatch(self.objective_id) is None:
            raise ValueError("active objective id is invalid")
        object.__setattr__(
            self, "intended_requirement_ids", _requirements(self.intended_requirement_ids),
        )
        if not isinstance(self.predicate, _PREDICATE_TYPES):
            raise TypeError("active objective predicate must be typed")
        if not self.admitted_context_id.startswith("context:"):
            raise ValueError("active objective requires its admitted context")

    @property
    def desired_state(self) -> dict[str, object]:
        return {"kind": self.predicate.kind.value}

    @property
    def direct_target_ids(self) -> tuple[str, ...]:
        target = getattr(self.predicate, "target_id", "")
        return (target,) if target else ()

    @property
    def direct_effects(self) -> tuple[str, ...]:
        return ()

    @property
    def enabling_target_ids(self) -> tuple[str, ...]:
        return ()

    @property
    def enabling_action_hints(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class VerifiedRequirement:
    requirement_id: str
    status: CriterionEvaluationStatus
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.requirement_id, "verified requirement id")
        if not isinstance(self.status, CriterionEvaluationStatus):
            raise TypeError("verified requirement status must be typed")
        refs = tuple(self.evidence_refs)
        if len(refs) > 32 or len(set(refs)) != len(refs):
            raise ValueError("verified requirement evidence is invalid")
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True)
class ObjectiveCheckpoint:
    objective_id: str
    intended_requirement_ids: tuple[str, ...]
    predicate: ObjectivePredicate
    status: ObjectiveCheckpointStatus
    observation_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if _OBJECTIVE_ID.fullmatch(self.objective_id) is None:
            raise ValueError("objective checkpoint id is invalid")
        object.__setattr__(
            self, "intended_requirement_ids", _requirements(self.intended_requirement_ids),
        )
        if not isinstance(self.predicate, _PREDICATE_TYPES):
            raise TypeError("objective checkpoint predicate must be typed")
        if not isinstance(self.status, ObjectiveCheckpointStatus):
            raise TypeError("objective checkpoint status must be typed")
        if not self.observation_id.strip():
            raise ValueError("objective checkpoint requires observation identity")
        refs = tuple(self.evidence_refs)
        if len(refs) > 32 or len(set(refs)) != len(refs):
            raise ValueError("objective checkpoint evidence is invalid")
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True)
class VerifiedValue:
    fact_ref: str
    subject_id: str
    predicate: str
    value: object
    observation_id: str

    def __post_init__(self) -> None:
        if not self.fact_ref.startswith("fact:"):
            raise ValueError("verified value requires a canonical fact reference")
        _require_id(self.fact_ref, "verified value fact reference")
        _require_id(self.subject_id, "verified value subject")
        if not self.predicate.strip() or len(self.predicate) > 240:
            raise ValueError("verified value predicate is invalid")
        if not self.observation_id.strip():
            raise ValueError("verified value requires observation identity")
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class VerifiedTaskState:
    requirements: tuple[VerifiedRequirement, ...]
    current_frontier: tuple[str, ...]
    values: tuple[VerifiedValue, ...] = ()
    objective_checkpoints: tuple[ObjectiveCheckpoint, ...] = ()

    def __post_init__(self) -> None:
        requirements = tuple(self.requirements)
        if (
            len(requirements) > _MAX_REQUIREMENTS
            or len({item.requirement_id for item in requirements}) != len(requirements)
        ):
            raise ValueError("verified task requirements are invalid")
        known = {item.requirement_id for item in requirements}
        frontier = tuple(self.current_frontier)
        if len(frontier) > _MAX_REQUIREMENTS or len(set(frontier)) != len(frontier):
            raise ValueError("verified task frontier is invalid")
        if any(item not in known for item in frontier):
            raise ValueError("task frontier references an unknown requirement")
        values = tuple(self.values[-_MAX_VALUES:])
        if len({item.fact_ref for item in values}) != len(values):
            raise ValueError("verified task values must have unique fact references")
        checkpoints = tuple(self.objective_checkpoints[-_MAX_CHECKPOINTS:])
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "current_frontier", frontier)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "objective_checkpoints", checkpoints)


_PREDICATE_TYPES = (
    FactAvailable,
    TargetFieldEquals,
    TargetPresent,
    TargetAbsent,
    TaskOutcomeIs,
)


def objective_id(sequence: int) -> str:
    if type(sequence) is not int or sequence <= 0:
        raise ValueError("objective sequence must be positive")
    return f"objective:{sequence}"


def predicate_public_value(predicate: ObjectivePredicate) -> dict[str, object]:
    if isinstance(predicate, FactAvailable):
        return {"kind": predicate.kind.value, "fact_ref": predicate.fact_ref}
    if isinstance(predicate, TargetFieldEquals):
        expected = (
            {"kind": "fact_ref", "fact_ref": predicate.expected.fact_ref}
            if isinstance(predicate.expected, FactReferenceExpected)
            else {"kind": "literal", "value": predicate.expected.value}
        )
        return {
            "kind": predicate.kind.value,
            "target_id": predicate.target_id,
            "field_name": predicate.field_name,
            "expected": expected,
        }
    if isinstance(predicate, TargetPresent | TargetAbsent):
        return {"kind": predicate.kind.value, "target_id": predicate.target_id}
    return {"kind": predicate.kind.value, "status": predicate.status.value}
