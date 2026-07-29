"""Runtime-facing ODG attribution carry and shadow projection.

This module is a temporary application seam. It can see ActionContract identity
and ODG attribution contracts, but it does not write StateKernel, trace, finish
authority, or planner context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from affordance_runtime.contracts import ActionContract
from affordance_runtime.obligation_attribution import (
    ObligationAttributionResult,
    PostActionEvidenceFact,
    PostVerificationObligationAttributor,
    ProgressAttributionTicket,
)
from affordance_runtime.obligation_progress import ObligationProgressStateView
from affordance_runtime.task_intake import TaskSpec


@dataclass(frozen=True)
class BoundActionExecution:
    """Accepted action plus optional ODG attribution ticket.

    The ticket is carried beside the contract so executor/verifier-facing
    ActionContract schema remains unchanged.
    """

    contract: ActionContract
    attribution_ticket: ProgressAttributionTicket | None = None

    def __post_init__(self) -> None:
        ticket = self.attribution_ticket
        if ticket is None:
            return
        if (
            ticket.contract_id != self.contract.id
            or ticket.contract_hash != self.contract.contract_hash
            or ticket.pre_snapshot_id != self.contract.snapshot_id
            or ticket.pre_page_revision != self.contract.page_revision
            or ticket.pre_environment_revision != self.contract.environment_revision
        ):
            raise ValueError("ticket contract identity does not match bound contract")


@dataclass(frozen=True)
class ObligationAttributionShadowProjection:
    """Diagnostic-only post-verification attribution projection."""

    schema_version: str
    task_spec_identity: str
    task_revision: int
    evaluated_at_state_version: int
    contract_id: str
    contract_hash: str
    ticket_id: str
    candidate_obligation_ids: tuple[str, ...]
    attribution_status: Literal[
        "satisfied",
        "no_match",
        "ambiguous",
        "weak_evidence",
        "stale",
        "invalid",
        "dependency_blocked",
        "not_ticketed",
    ]
    prepared_obligation_id: str = ""
    evidence_refs: tuple[str, ...] = ()
    commit_authorized: bool = False
    reason: str = ""
    event_kind: str = "ObligationAttributionShadowCompared"

    def to_trace_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "task_spec_identity": self.task_spec_identity,
            "task_revision": self.task_revision,
            "evaluated_at_state_version": self.evaluated_at_state_version,
            "contract": {
                "contract_id": self.contract_id,
                "contract_hash": self.contract_hash,
            },
            "ticket": {
                "ticket_id": self.ticket_id,
                "candidate_obligation_ids": list(self.candidate_obligation_ids),
            },
            "attribution": {
                "status": self.attribution_status,
                "prepared_obligation_id": self.prepared_obligation_id,
                "evidence_refs": list(self.evidence_refs),
                "would_commit": self.commit_authorized,
                "reason": self.reason,
            },
        }


def prepare_post_verification_obligation_shadow(
    *,
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    bound_action: BoundActionExecution,
    facts: tuple[PostActionEvidenceFact, ...],
) -> ObligationAttributionShadowProjection | None:
    """Prepare diagnostic ODG attribution output without committing progress."""

    ticket = bound_action.attribution_ticket
    if ticket is None:
        return ObligationAttributionShadowProjection(
            schema_version="1.0",
            task_spec_identity=task_spec.identity,
            task_revision=task_spec.revision,
            evaluated_at_state_version=progress.evaluated_at_state_version,
            contract_id=bound_action.contract.id,
            contract_hash=bound_action.contract.contract_hash,
            ticket_id="",
            candidate_obligation_ids=(),
            attribution_status="not_ticketed",
            reason="no progress attribution ticket was carried with the action",
        )

    result = PostVerificationObligationAttributor().attribute(
        task_spec=task_spec,
        progress=progress,
        ticket=ticket,
        facts=facts,
    )
    return _projection_from_result(
        task_spec=task_spec,
        progress=progress,
        ticket=ticket,
        result=result,
    )


def _projection_from_result(
    *,
    task_spec: TaskSpec,
    progress: ObligationProgressStateView,
    ticket: ProgressAttributionTicket,
    result: ObligationAttributionResult,
) -> ObligationAttributionShadowProjection:
    preparation = result.preparation
    return ObligationAttributionShadowProjection(
        schema_version="1.0",
        task_spec_identity=task_spec.identity,
        task_revision=task_spec.revision,
        evaluated_at_state_version=progress.evaluated_at_state_version,
        contract_id=ticket.contract_id,
        contract_hash=ticket.contract_hash,
        ticket_id=ticket.ticket_id,
        candidate_obligation_ids=ticket.candidate_obligation_ids,
        attribution_status=result.status,
        prepared_obligation_id=preparation.obligation_id if preparation is not None else "",
        evidence_refs=preparation.evidence_refs if preparation is not None else (),
        commit_authorized=False,
        reason=result.reason,
    )
