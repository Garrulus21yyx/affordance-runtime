"""Immutable contracts for Runtime-owned semantic action choice."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias

from affordance_runtime.effect_authority_contracts import ActionAuthorityProof
from affordance_runtime.immutable import FrozenDict
from affordance_runtime.planning import PlannerActionKind
from affordance_runtime.recovery_protocol import FailureKind, FailureOwner

FrozenJsonObject: TypeAlias = FrozenDict


class ChoiceSource(StrEnum):
    RUNTIME = "runtime"


class ChoiceRole(StrEnum):
    DIRECT = "direct"
    ENABLING = "enabling"
    INFORMATION = "information"


class ChoiceConflictStatus(StrEnum):
    CLEAR = "clear"
    MATERIAL_CONFLICT = "material_conflict"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ActionChoice:
    choice_id: str
    task_revision: int
    state_version: int
    snapshot_id: str
    active_step_id: str
    action_kind: PlannerActionKind
    target_id: str = ""
    target_label: str = ""
    target_role: str = "semantic_target"
    relevant_current_state: FrozenJsonObject = field(default_factory=lambda: FrozenDict({}))
    destination_id: str = ""
    destination_label: str = ""
    parameters: FrozenJsonObject = field(default_factory=lambda: FrozenDict({}))
    criterion_ids: tuple[str, ...] = ()
    requirement_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    conflict_status: ChoiceConflictStatus = ChoiceConflictStatus.CLEAR
    risk: str = "low"
    action_authority_proof: ActionAuthorityProof | None = None
    effect_summary: str = ""
    authorization_reason_codes: tuple[str, ...] = ()
    generation_reason_codes: tuple[str, ...] = ("runtime_semantic_admission",)
    role: ChoiceRole = ChoiceRole.DIRECT
    source: ChoiceSource = ChoiceSource.RUNTIME

    def __init__(
        self,
        *,
        choice_id: str,
        task_revision: int,
        state_version: int,
        snapshot_id: str,
        active_step_id: str,
        action_kind: PlannerActionKind,
        target_id: str = "",
        target_label: str = "",
        target_role: str = "semantic_target",
        relevant_current_state: dict[str, object] | FrozenJsonObject | None = None,
        destination_id: str = "",
        destination_label: str = "",
        parameters: dict[str, object] | FrozenJsonObject | None = None,
        criterion_ids: tuple[str, ...] = (),
        requirement_refs: tuple[str, ...] = (),
        effect_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        conflict_status: ChoiceConflictStatus = ChoiceConflictStatus.CLEAR,
        risk: str = "low",
        action_authority_proof: ActionAuthorityProof | None = None,
        effect_summary: str = "",
        authorization_reason_codes: tuple[str, ...] = (),
        generation_reason_codes: tuple[str, ...] = ("runtime_semantic_admission",),
        role: ChoiceRole = ChoiceRole.DIRECT,
        source: ChoiceSource = ChoiceSource.RUNTIME,
    ) -> None:
        values = {
            "choice_id": choice_id,
            "task_revision": task_revision,
            "state_version": state_version,
            "snapshot_id": snapshot_id,
            "active_step_id": active_step_id,
            "action_kind": action_kind,
            "target_id": target_id,
            "target_label": target_label,
            "target_role": target_role,
            "relevant_current_state": relevant_current_state
            if isinstance(relevant_current_state, FrozenDict)
            else FrozenDict(relevant_current_state or {}),
            "destination_id": destination_id,
            "destination_label": destination_label,
            "parameters": parameters if isinstance(parameters, FrozenDict) else FrozenDict(parameters or {}),
            "criterion_ids": tuple(criterion_ids),
            "requirement_refs": tuple(requirement_refs),
            "effect_refs": tuple(effect_refs),
            "evidence_refs": tuple(evidence_refs),
            "conflict_status": conflict_status,
            "risk": risk,
            "action_authority_proof": action_authority_proof,
            "effect_summary": effect_summary,
            "authorization_reason_codes": tuple(authorization_reason_codes),
            "generation_reason_codes": tuple(generation_reason_codes),
            "role": role,
            "source": source,
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)
        self.__post_init__()

    @property
    def effectful(self) -> bool:
        return bool(self.action_authority_proof and self.action_authority_proof.effectful)

    @property
    def authorization_scope_digest(self) -> str:
        proof = self.action_authority_proof
        return proof.authorization_scope_digest or "" if proof else ""

    def __post_init__(self) -> None:
        _nonblank("choice_id", self.choice_id)
        _nonblank("snapshot_id", self.snapshot_id)
        _nonblank("active_step_id", self.active_step_id)
        if self.task_revision < 1 or self.state_version < 0:
            raise ValueError("invalid choice revision")
        if not isinstance(self.action_kind, PlannerActionKind):
            raise ValueError("unsupported action kind")
        for values in (
            self.criterion_ids,
            self.requirement_refs,
            self.effect_refs,
            self.evidence_refs,
            self.generation_reason_codes,
        ):
            if not isinstance(values, tuple) or any(not item.strip() for item in values):
                raise ValueError("choice references must be nonblank immutable tuples")


@dataclass(frozen=True)
class CatalogRef:
    catalog_id: str
    catalog_digest: str
    observation_ref: str


@dataclass(frozen=True)
class CatalogSlice:
    choices: tuple[ActionChoice, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class ChoiceRejection:
    target_id: str | None
    action_kind: PlannerActionKind | None
    reason_code: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChoiceBuildReport:
    considered_target_count: int
    admitted_choice_count: int
    rejections: tuple[ChoiceRejection, ...] = ()


@dataclass(frozen=True)
class ActionChoiceFailure:
    kind: FailureKind
    reason_code: str
    owner: FailureOwner = FailureOwner.RUNTIME_RECOVERY
    build_report: ChoiceBuildReport | None = None


@dataclass(frozen=True)
class ChoicePresentation:
    choice_id: str
    action_kind: PlannerActionKind
    target_id: str
    target_label: str
    target_role: str
    destination_id: str = ""
    destination_label: str = ""
    relevant_current_state: FrozenJsonObject = field(default_factory=lambda: FrozenDict({}))
    requirement_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    conflict_status: ChoiceConflictStatus = ChoiceConflictStatus.CLEAR
    risk: str = "low"
    effect_summary: str = ""
    authorization_reason_codes: tuple[str, ...] = ()
    generation_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChoicePage:
    catalog_id: str
    catalog_digest: str
    total_choice_count: int
    included_choice_count: int
    page_index: int
    page_size: int
    choices: tuple[ChoicePresentation, ...]
    truncated: bool
    continuation_token: str | None
    projection_policy_id: str


@dataclass(frozen=True)
class ChoicePlanningRequest:
    task_revision: int
    plan_revision: int
    active_step_id: str
    catalog_ref: CatalogRef
    page: ChoicePage
    recent_outcomes: tuple["ChoiceOutcomeSummary", ...] = ()
    budget: "ChoicePlanningBudget" = field(default_factory=lambda: ChoicePlanningBudget())


@dataclass(frozen=True)
class ChoiceOutcomeSummary:
    action_kind: str
    target_id: str
    verification_passed: bool
    effect_satisfied: bool


@dataclass(frozen=True)
class ChoicePlanningBudget:
    model_calls_remaining: int = 1
    pages_remaining: int = 0

    def __post_init__(self) -> None:
        if self.model_calls_remaining < 0 or self.pages_remaining < 0:
            raise ValueError("choice planning budget cannot be negative")


@dataclass(frozen=True)
class SelectChoice:
    choice_id: str
    reason: str = ""


@dataclass(frozen=True)
class RequestNextChoicePage:
    continuation_token: str


@dataclass(frozen=True)
class RefineChoiceQuery:
    filter_id: str
    arguments: FrozenJsonObject = field(default_factory=lambda: FrozenDict({}))


@dataclass(frozen=True)
class AskUser:
    question: str


@dataclass(frozen=True)
class DeferChoice:
    reason: str


@dataclass(frozen=True)
class ReportPlanIssue:
    kind: str
    evidence_refs: tuple[str, ...] = ()


ChoicePlannerResponse: TypeAlias = (
    SelectChoice | RequestNextChoicePage | RefineChoiceQuery | AskUser | DeferChoice | ReportPlanIssue
)


@dataclass(frozen=True)
class ActionSelection:
    choice_id: str
    catalog_ref: CatalogRef
    task_revision: int
    plan_revision: int
    state_version: int
    observation_ref: str
    active_step_id: str
    reason_summary: str = ""


def _nonblank(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} cannot be blank")
