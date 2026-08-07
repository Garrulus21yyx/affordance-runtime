"""Classify proposal rejections without mutating Runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import ProposalRejectionContext
from affordance_runtime.planning import ProposalRejectionCode


@dataclass(frozen=True)
class ProposalRejectionDisposition:
    recoverable: bool
    planner_feedback: str
    rejection_context: ProposalRejectionContext


@dataclass(frozen=True)
class ProposalRejectionRecoveryPolicy:
    """Permit only evidence-safe, non-effectful proposal replacement."""

    def decide(
        self,
        code: ProposalRejectionCode,
        detail: str = "",
        reason_code: str = "",
        semantic_target_id: str = "",
    ) -> ProposalRejectionDisposition:
        feedback = ":".join(item for item in (code.value, reason_code, detail) if item)
        rejection_context = ProposalRejectionContext(
            code=code.value,
            reason_code=reason_code,
            semantic_target_id=semantic_target_id,
        )
        if code == ProposalRejectionCode.TARGET_OUT_OF_SCOPE:
            return ProposalRejectionDisposition(
                recoverable=True,
                planner_feedback=feedback,
                rejection_context=rejection_context,
            )
        return ProposalRejectionDisposition(
            recoverable=False,
            planner_feedback=feedback,
            rejection_context=rejection_context,
        )
