"""Typed contracts for post-verification obligation progress attribution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from affordance_runtime.task_intake import TaskObligationRelation


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    INDEPENDENT = "independent"
    AUTHORITATIVE = "authoritative"


@dataclass(frozen=True)
class ProgressAttributionTicket:
    """Pre-action candidate scope for later verifier-owned attribution."""

    ticket_id: str
    task_revision: int
    issued_at_state_version: int
    contract_id: str
    semantic_target_id: str
    action_kind: str
    candidate_obligation_ids: tuple[str, ...]
    pre_snapshot_id: str
    pre_page_revision: str
    pre_environment_revision: str
    plan_id: str = ""
    plan_version: int = 0

    def __post_init__(self) -> None:
        _require_nonblank("ticket_id", self.ticket_id)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.issued_at_state_version < 0:
            raise ValueError("issued state version cannot be negative")
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("semantic_target_id", self.semantic_target_id)
        _require_nonblank("action_kind", self.action_kind)
        if not self.candidate_obligation_ids:
            raise ValueError("candidate obligation ids cannot be empty")
        _require_unique_nonblank(
            "candidate obligation ids",
            self.candidate_obligation_ids,
        )
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_nonblank("pre_page_revision", self.pre_page_revision)
        _require_nonblank("pre_environment_revision", self.pre_environment_revision)
        if self.plan_version < 0:
            raise ValueError("plan version cannot be negative")


@dataclass(frozen=True)
class PostActionEvidenceFact:
    """Verifier/observation fact that deliberately carries no obligation id."""

    contract_id: str
    pre_snapshot_id: str
    post_snapshot_id: str
    post_page_revision: str
    post_environment_revision: str
    semantic_target_id: str
    relation: TaskObligationRelation
    before_value: str | bool | int | float | None
    after_value: str | bool | int | float | None
    strength: EvidenceStrength
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_nonblank("post_snapshot_id", self.post_snapshot_id)
        _require_nonblank("post_page_revision", self.post_page_revision)
        _require_nonblank("post_environment_revision", self.post_environment_revision)
        _require_nonblank("semantic_target_id", self.semantic_target_id)
        _require_unique_nonblank("evidence refs", self.evidence_refs)


@dataclass(frozen=True)
class ObligationAttributionResult:
    status: Literal[
        "satisfied",
        "no_match",
        "ambiguous",
        "weak_evidence",
        "stale",
        "dependency_blocked",
    ]
    preparation: "ObligationSatisfactionPreparation | None" = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status == "satisfied" and self.preparation is None:
            raise ValueError("satisfied attribution requires preparation")
        if self.status != "satisfied" and self.preparation is not None:
            raise ValueError("non-satisfied attribution cannot include preparation")


@dataclass(frozen=True)
class ObligationSatisfactionPreparation:
    """Coordinator-owned command payload for committing obligation progress."""

    task_revision: int
    evaluated_at_state_version: int
    obligation_id: str
    contract_id: str
    post_snapshot_id: str
    evidence_refs: tuple[str, ...]
    source: Literal["post_verification", "current_observation"]

    def __post_init__(self) -> None:
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("evaluated state version cannot be negative")
        _require_nonblank("obligation_id", self.obligation_id)
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("post_snapshot_id", self.post_snapshot_id)
        if not self.evidence_refs:
            raise ValueError("satisfaction evidence refs cannot be empty")
        _require_unique_nonblank("satisfaction evidence refs", self.evidence_refs)


def _require_nonblank(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")


def _require_unique_nonblank(field_name: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")
    if any(not item.strip() for item in values):
        raise ValueError(f"{field_name} cannot contain blank values")
