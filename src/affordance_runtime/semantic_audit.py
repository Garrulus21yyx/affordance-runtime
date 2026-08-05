"""Optional risk-triggered semantic veto and clarification boundary."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from affordance_runtime.source_envelope import SourceEnvelope, SourceKind
from affordance_runtime.task_intake import OperationClass, StrictModel
from affordance_runtime.task_spec_authority import MinimalIntentProposal


class SemanticAuditStatus(StrEnum):
    PASS = "pass"
    VETO = "veto"
    CLARIFICATION_REQUIRED = "clarification_required"


class SemanticAuditResult(StrictModel):
    status: SemanticAuditStatus
    triggered: bool
    trigger_reasons: tuple[str, ...] = ()
    issue_codes: tuple[str, ...] = ()
    source_envelope_ref: str = Field(min_length=1)


class SemanticAudit:
    """Exercise negative authority only; never repair or extend a proposal."""

    def evaluate(
        self,
        envelope: SourceEnvelope,
        proposal: MinimalIntentProposal,
        *,
        material_conflicts: tuple[str, ...] = (),
        policy_required: bool = False,
    ) -> SemanticAuditResult:
        reasons: list[str] = []
        operations = {item.operation_class for item in proposal.requested_effects}
        if OperationClass.IRREVERSIBLE in operations:
            reasons.append("irreversible_effect")
        elif OperationClass.EXTERNAL_SIDE_EFFECT in operations:
            reasons.append("external_effect")
        source_kinds = {item.kind for item in envelope.sources}
        if len(source_kinds - {SourceKind.REQUEST}) > 0:
            reasons.append("multi_source_authority")
        if SourceKind.ATTACHMENT in source_kinds or SourceKind.PROFILE in source_kinds:
            reasons.append("attachment_or_profile_authority")
        if material_conflicts:
            reasons.append("material_source_conflict")
        if policy_required:
            reasons.append("explicit_policy_requirement")
        reasons = list(dict.fromkeys(reasons))
        if not reasons:
            return SemanticAuditResult(
                status=SemanticAuditStatus.PASS,
                triggered=False,
                source_envelope_ref=envelope.identity,
            )
        if material_conflicts:
            return SemanticAuditResult(
                status=SemanticAuditStatus.VETO,
                triggered=True,
                trigger_reasons=tuple(reasons),
                issue_codes=("material_source_conflict",),
                source_envelope_ref=envelope.identity,
            )
        return SemanticAuditResult(
            status=SemanticAuditStatus.PASS,
            triggered=True,
            trigger_reasons=tuple(reasons),
            source_envelope_ref=envelope.identity,
        )
