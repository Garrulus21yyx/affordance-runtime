"""Typed policy decisions admitted only against their originating AgentContext."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeAlias

from affordance_runtime.immutable import freeze_json
from affordance_runtime.task.frontier_contracts import (
    NoObjectiveOperation,
    ObjectiveOperation,
    ProposeObjective,
    ReplaceObjective,
    RetainObjective,
)
from affordance_runtime.task.set_objective import PredicateExpr, PredicateTruth, SetQuantifier
from affordance_runtime.world.relevance import ActionRelevanceRole
from affordance_runtime.world.source_profile import ObservationAssurance, ObservationModality

_MAX_REASON = 500
MAX_RESULT_SUMMARY_CHARS = 1_024
_MAX_COLLECTION = 32


class AbortCategory(StrEnum):
    POLICY = "policy"
    SAFETY = "safety"
    UNSUPPORTED = "unsupported"
    NO_PROGRESS = "no_progress"
    USER_REQUEST = "user_request"
    INTERNAL = "internal"


def _require_context(context_id: str) -> None:
    if not context_id.strip():
        raise ValueError("decision requires context identity")


def _require_bounded(value: str, limit: int, field_name: str) -> None:
    if not value.strip() or len(value) > limit:
        raise ValueError(f"{field_name} must be nonblank and at most {limit} characters")


def _require_collection(values: tuple[str, ...], field_name: str, *, item_limit: int = 512) -> None:
    if len(values) > _MAX_COLLECTION or any(not item.strip() or len(item) > item_limit for item in values):
        raise ValueError(f"{field_name} exceeds structured decision bounds")


@dataclass(frozen=True)
class SelectAction:
    context_id: str
    action_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    destination_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.action_id.strip():
            raise ValueError("selection requires an offered action id")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))


@dataclass(frozen=True)
class EstablishSetObjective:
    """Admit model-proposed set semantics without granting an action."""

    context_id: str
    predicate: PredicateExpr
    quantifier: SetQuantifier
    semantic_action: str
    candidate_target_ids: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.semantic_action.strip():
            raise ValueError("set objective requires a semantic action")
        values = tuple(self.candidate_target_ids)
        if (
            not values
            or len(values) > 256
            or len(values) != len(set(values))
            or any(not item.strip() or len(item) > 240 for item in values)
        ):
            raise ValueError("set objective candidate domain is invalid")
        object.__setattr__(self, "candidate_target_ids", values)
        object.__setattr__(self, "parameters", freeze_json(self.parameters))


@dataclass(frozen=True)
class SetPredicateAssessmentDecision:
    target_id: str
    truth: PredicateTruth
    confidence: float | None

    def __post_init__(self) -> None:
        if not self.target_id.strip() or (
            self.confidence is not None and not 0 <= self.confidence <= 1
        ):
            raise ValueError("set predicate assessment decision is invalid")


@dataclass(frozen=True)
class SubmitSetPredicateAssessments:
    context_id: str
    predicate_digest: str
    assessments: tuple[SetPredicateAssessmentDecision, ...]

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        values = tuple(self.assessments)
        if (
            len(self.predicate_digest) != 64
            or not values
            or len(values) > 256
            or len({item.target_id for item in values}) != len(values)
        ):
            raise ValueError("set predicate assessment batch is invalid")
        object.__setattr__(self, "assessments", values)


@dataclass(frozen=True)
class RequestObservation:
    context_id: str
    subject_id: str
    modality: str
    required_assurance: str
    reason: str
    cursor: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.subject_id, 240, "observation subject")
        _require_bounded(self.reason, _MAX_REASON, "observation reason")
        if len(self.cursor) > 512:
            raise ValueError("observation cursor exceeds its bound")
        try:
            ObservationModality(self.modality)
            ObservationAssurance(self.required_assurance)
        except ValueError as exc:
            raise ValueError("observation request requires a supported modality and assurance") from exc


@dataclass(frozen=True)
class RequestActionPage:
    context_id: str
    query: str = ""
    target_id: str = ""
    relevance_role: str = ""
    cursor: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if len(self.query) > 120 or len(self.target_id) > 240 or len(self.cursor) > 512:
            raise ValueError("action page request exceeds bounded fields")
        if self.relevance_role:
            ActionRelevanceRole(self.relevance_role)


@dataclass(frozen=True)
class AskUser:
    context_id: str
    question: str
    requested_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.question, 1_000, "user question")
        object.__setattr__(self, "requested_fields", tuple(self.requested_fields))
        _require_collection(self.requested_fields, "requested fields", item_limit=120)


@dataclass(frozen=True)
class ProposeDone:
    context_id: str
    claimed_criteria: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    result_summary: str
    unresolved_items: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.result_summary, MAX_RESULT_SUMMARY_CHARS, "completion result summary")
        object.__setattr__(self, "claimed_criteria", tuple(self.claimed_criteria))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "unresolved_items", tuple(self.unresolved_items))
        _require_collection(self.claimed_criteria, "claimed criteria", item_limit=240)
        _require_collection(self.evidence_refs, "evidence refs")
        _require_collection(self.unresolved_items, "unresolved items", item_limit=500)


@dataclass(frozen=True)
class Wait:
    context_id: str
    reason: str
    max_wait_ms: int

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.reason.strip() or len(self.reason) > _MAX_REASON or not 0 < self.max_wait_ms <= 60_000:
            raise ValueError("wait requires a bounded duration and reason")


@dataclass(frozen=True)
class Abort:
    context_id: str
    reason: str
    category: str

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.reason, _MAX_REASON, "abort reason")
        try:
            AbortCategory(self.category)
        except ValueError as exc:
            raise ValueError("abort category is unsupported") from exc


AgentDecision: TypeAlias = (
    SelectAction
    | EstablishSetObjective
    | SubmitSetPredicateAssessments
    | RequestObservation
    | RequestActionPage
    | AskUser
    | ProposeDone
    | Wait
    | Abort
)


@dataclass(frozen=True)
class AgentDecisionPackage:
    """One context-bound objective operation and ordinary decision, admitted atomically."""

    objective_operation: ObjectiveOperation
    decision: AgentDecision

    def __post_init__(self) -> None:
        if not isinstance(
            self.objective_operation,
            (NoObjectiveOperation, ProposeObjective, RetainObjective, ReplaceObjective),
        ):
            raise TypeError("decision package requires a typed objective operation")
        if not isinstance(
            self.decision,
            (
                SelectAction,
                EstablishSetObjective,
                SubmitSetPredicateAssessments,
                RequestObservation,
                RequestActionPage,
                AskUser,
                ProposeDone,
                Wait,
                Abort,
            ),
        ):
            raise TypeError("decision package requires a typed agent decision")

    @property
    def context_id(self) -> str:
        return self.decision.context_id


def package_decision(decision: AgentDecision) -> AgentDecisionPackage:
    """Compatibility projection for deterministic policies without objective support."""

    return AgentDecisionPackage(NoObjectiveOperation(), decision)
