"""Canonical semantic vocabulary for criteria, relations, and evidence policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

JsonScalar: TypeAlias = str | bool | int | float | None
FrozenJsonValue: TypeAlias = object


class CriterionRelation(StrEnum):
    EQUALS = "equals"
    CONTAINS = "contains"
    MATCHES = "matches"
    IS_VISIBLE = "is_visible"
    IS_ABSENT = "is_absent"
    IS_AVAILABLE = "is_available"
    IS_SELECTED = "is_selected"
    IS_CHECKED = "is_checked"
    IS_EXPANDED = "is_expanded"
    IS_COMPLETED = "is_completed"
    IS_ORDERED_AS = "is_ordered_as"
    HAS_CHANGED = "has_changed"


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    INDEPENDENT = "independent"
    AUTHORITATIVE = "authoritative"


class EvidenceSourceKind(StrEnum):
    DOM_STATE = "dom_state"
    ACCESSIBILITY_STATE = "accessibility_state"
    VISUAL_STATE = "visual_state"
    API_STATE = "api_state"
    FILE_RECEIPT = "file_receipt"
    DOWNLOAD_RECEIPT = "download_receipt"
    DEVICE_STATE = "device_state"
    HUMAN_CONFIRMATION = "human_confirmation"
    POST_ACTION_OBSERVATION = "post_action_observation"
    INDEPENDENT_API = "independent_api"
    EXECUTION_RECEIPT = "execution_receipt"
    EXTERNAL_EVALUATOR = "external_evaluator"


class CriterionRole(StrEnum):
    COMPLETION = "completion"
    PRECONDITION = "precondition"


@dataclass(frozen=True)
class EvidencePolicy:
    minimum_strength: EvidenceStrength
    allowed_source_kinds: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.minimum_strength, EvidenceStrength):
            raise ValueError("unsupported evidence strength")
        if not isinstance(self.allowed_source_kinds, tuple):
            raise ValueError("allowed source kinds must be a tuple")
        if not self.allowed_source_kinds:
            raise ValueError("allowed source kinds cannot be empty")
        if len(self.allowed_source_kinds) != len(set(self.allowed_source_kinds)):
            raise ValueError("allowed source kinds must be unique")
        if any(not item.strip() for item in self.allowed_source_kinds):
            raise ValueError("allowed source kinds cannot contain blank values")


@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    role: CriterionRole
    subject: str
    relation: CriterionRelation
    expected_value: JsonScalar | FrozenJsonValue
    evidence_policy: EvidencePolicy

    def __post_init__(self) -> None:
        if not self.criterion_id.strip():
            raise ValueError("criterion id cannot be blank")
        if not isinstance(self.role, CriterionRole):
            raise ValueError("unsupported criterion role")
        if not self.subject.strip():
            raise ValueError("criterion subject cannot be blank")
        if not isinstance(self.relation, CriterionRelation):
            raise ValueError("unsupported criterion relation")


@dataclass(frozen=True)
class CompositeCriterion:
    criterion_id: str
    operator: str
    child_criterion_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.criterion_id.strip():
            raise ValueError("criterion id cannot be blank")
        if self.operator not in {"all_of", "any_of"}:
            raise ValueError("unsupported composite criterion operator")
        if not isinstance(self.child_criterion_ids, tuple):
            raise ValueError("child criterion ids must be a tuple")
        if not self.child_criterion_ids:
            raise ValueError("composite criterion children cannot be empty")
        if len(self.child_criterion_ids) != len(set(self.child_criterion_ids)):
            raise ValueError("child criterion ids must be unique")
        if any(not item.strip() for item in self.child_criterion_ids):
            raise ValueError("child criterion ids cannot contain blank values")
        if self.criterion_id in self.child_criterion_ids:
            raise ValueError("composite criterion cycle is not allowed")
