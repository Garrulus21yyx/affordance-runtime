"""Typed contracts for post-verification obligation progress attribution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from affordance_runtime.obligation_progress import (
    PROGRESS_ROLES,
    ObligationProgressStateView,
    ReadyObligationProjection,
    validate_obligation_progress_state,
)
from affordance_runtime.task_intake import TaskObligationRelation, TaskSpec


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    INDEPENDENT = "independent"
    AUTHORITATIVE = "authoritative"


@dataclass(frozen=True)
class CurrentObservationSatisfactionSource:
    snapshot_id: str
    page_revision: str
    environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("snapshot_id", self.snapshot_id)
        _require_nonblank("page_revision", self.page_revision)
        _require_nonblank("environment_revision", self.environment_revision)


@dataclass(frozen=True)
class PostVerificationSatisfactionSource:
    contract_id: str
    post_snapshot_id: str
    post_page_revision: str
    post_environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("post_snapshot_id", self.post_snapshot_id)
        _require_nonblank("post_page_revision", self.post_page_revision)
        _require_nonblank("post_environment_revision", self.post_environment_revision)


@dataclass(frozen=True)
class AttributionActionView:
    """Authority-free accepted-action identity for pre-action ticketing."""

    contract_id: str
    contract_hash: str
    task_spec_identity: str
    task_revision: int
    issued_at_state_version: int
    semantic_target_id: str
    action_kind: str
    pre_snapshot_id: str
    pre_page_revision: str
    pre_environment_revision: str

    def __post_init__(self) -> None:
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.issued_at_state_version < 0:
            raise ValueError("issued state version cannot be negative")
        _require_nonblank("semantic_target_id", self.semantic_target_id)
        _require_nonblank("action_kind", self.action_kind)
        _require_nonblank("pre_snapshot_id", self.pre_snapshot_id)
        _require_nonblank("pre_page_revision", self.pre_page_revision)
        _require_nonblank("pre_environment_revision", self.pre_environment_revision)


@dataclass(frozen=True)
class ProgressAttributionTicket:
    """Pre-action candidate scope for later verifier-owned attribution."""

    ticket_id: str
    task_spec_identity: str
    task_revision: int
    issued_at_state_version: int
    contract_id: str
    contract_hash: str
    semantic_target_id: str
    action_kind: str
    candidate_obligation_ids: tuple[str, ...]
    pre_snapshot_id: str
    pre_page_revision: str
    pre_environment_revision: str
    compatibility_plan_id: str = ""
    compatibility_plan_version: int = 0

    def __post_init__(self) -> None:
        _require_nonblank("ticket_id", self.ticket_id)
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.issued_at_state_version < 0:
            raise ValueError("issued state version cannot be negative")
        _require_nonblank("contract_id", self.contract_id)
        _require_nonblank("contract_hash", self.contract_hash)
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
        if self.compatibility_plan_version < 0:
            raise ValueError("compatibility plan version cannot be negative")


@dataclass(frozen=True)
class ProgressAttributionTicketResolution:
    status: Literal[
        "ticket_created",
        "no_candidate",
        "role_pending",
        "stale",
        "invalid",
    ]
    ticket: ProgressAttributionTicket | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status == "ticket_created" and self.ticket is None:
            raise ValueError("ticket_created resolution requires ticket")
        if self.status != "ticket_created" and self.ticket is not None:
            raise ValueError("non-ticket resolution cannot include ticket")


class ProgressAttributionTicketResolver:
    """Resolve candidate obligation scope before an action is executed."""

    def resolve(
        self,
        *,
        task_spec: TaskSpec,
        progress: ObligationProgressStateView,
        ready_projection: ReadyObligationProjection,
        action: AttributionActionView,
    ) -> ProgressAttributionTicketResolution:
        if ready_projection.status == "role_pending":
            return ProgressAttributionTicketResolution(
                status="role_pending",
                reason=ready_projection.reason,
            )
        if ready_projection.status != "ready":
            return ProgressAttributionTicketResolution(
                status="invalid",
                reason=ready_projection.reason,
            )
        if (
            action.task_spec_identity != task_spec.identity
            or action.task_revision != task_spec.revision
            or action.issued_at_state_version != progress.evaluated_at_state_version
        ):
            return ProgressAttributionTicketResolution(status="stale")
        try:
            validate_obligation_progress_state(task_spec, progress)
        except ValueError as exc:
            return ProgressAttributionTicketResolution(
                status="stale",
                reason=str(exc),
            )

        canonical_by_id = {item.obligation_id: item for item in task_spec.obligations}
        satisfied = set(progress.satisfied_obligation_ids)
        failed = set(progress.failed_obligation_ids)
        candidate_ids: list[str] = []
        for view in ready_projection.ready_obligations:
            obligation = canonical_by_id.get(view.obligation_id)
            if obligation is None:
                return ProgressAttributionTicketResolution(
                    status="invalid",
                    reason=f"unknown ready obligation: {view.obligation_id}",
                )
            if view.role not in PROGRESS_ROLES:
                continue
            if view.obligation_id in satisfied or view.obligation_id in failed:
                continue
            if not set(view.dependency_ids).issubset(satisfied):
                continue
            if view.subject != action.semantic_target_id:
                continue
            if not _action_relation_compatible(action.action_kind, view.relation):
                continue
            candidate_ids.append(view.obligation_id)

        if not candidate_ids:
            return ProgressAttributionTicketResolution(status="no_candidate")
        candidates = tuple(candidate_ids)
        return ProgressAttributionTicketResolution(
            status="ticket_created",
            ticket=ProgressAttributionTicket(
                ticket_id=_ticket_id(action=action, candidate_obligation_ids=candidates),
                task_spec_identity=task_spec.identity,
                task_revision=task_spec.revision,
                issued_at_state_version=action.issued_at_state_version,
                contract_id=action.contract_id,
                contract_hash=action.contract_hash,
                semantic_target_id=action.semantic_target_id,
                action_kind=action.action_kind,
                candidate_obligation_ids=candidates,
                pre_snapshot_id=action.pre_snapshot_id,
                pre_page_revision=action.pre_page_revision,
                pre_environment_revision=action.pre_environment_revision,
            ),
        )


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

    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    obligation_id: str
    evidence_refs: tuple[str, ...]
    source: CurrentObservationSatisfactionSource | PostVerificationSatisfactionSource

    def __post_init__(self) -> None:
        _require_nonblank("task spec identity", self.task_spec_identity)
        if self.task_revision < 1:
            raise ValueError("task revision must be positive")
        if self.evaluated_at_state_version < 0:
            raise ValueError("evaluated state version cannot be negative")
        _require_nonblank("obligation_id", self.obligation_id)
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


def _action_relation_compatible(
    action_kind: str,
    relation: TaskObligationRelation,
) -> bool:
    normalized = action_kind.casefold()
    if normalized in {"type_text", "enter_text", "input_text", "fill"}:
        return relation in {
            TaskObligationRelation.CONTAINS,
            TaskObligationRelation.EQUALS,
            TaskObligationRelation.HAS_CHANGED,
            TaskObligationRelation.MATCHES,
        }
    if normalized in {"press_key", "set_value", "drag", "select_option"}:
        return relation in {
            TaskObligationRelation.CONTAINS,
            TaskObligationRelation.EQUALS,
            TaskObligationRelation.HAS_CHANGED,
            TaskObligationRelation.IS_CHECKED,
            TaskObligationRelation.IS_SELECTED,
        }
    if normalized in {"activate", "click", "submit"}:
        return relation in {
            TaskObligationRelation.HAS_CHANGED,
            TaskObligationRelation.IS_CHECKED,
            TaskObligationRelation.IS_COMPLETED,
            TaskObligationRelation.IS_SELECTED,
        }
    return False


def _ticket_id(
    *,
    action: AttributionActionView,
    candidate_obligation_ids: tuple[str, ...],
) -> str:
    payload = "|".join(
        (
            action.task_spec_identity,
            str(action.task_revision),
            str(action.issued_at_state_version),
            action.contract_id,
            action.contract_hash,
            action.semantic_target_id,
            action.action_kind,
            ",".join(candidate_obligation_ids),
            action.pre_snapshot_id,
            action.pre_page_revision,
            action.pre_environment_revision,
        )
    )
    return f"ticket:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
