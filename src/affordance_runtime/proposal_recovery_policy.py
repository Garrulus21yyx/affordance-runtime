"""Classify proposal rejections without mutating Runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.planning import ProposalRejectionCode
from affordance_runtime.recovery_commands import RecoveryCommandKind


@dataclass(frozen=True)
class ProposalRejectionRecoveryDecision:
    available_commands: frozenset[RecoveryCommandKind]
    recoverable: bool
    planner_feedback: str


@dataclass(frozen=True)
class ProposalRejectionRecoveryPolicy:
    """Permit only evidence-safe, non-effectful proposal replacement."""

    def decide(
        self,
        code: ProposalRejectionCode,
        detail: str = "",
        reason_code: str = "",
    ) -> ProposalRejectionRecoveryDecision:
        feedback = ":".join(item for item in (code.value, reason_code, detail) if item)
        if code == ProposalRejectionCode.TARGET_OUT_OF_SCOPE:
            return ProposalRejectionRecoveryDecision(
                available_commands=frozenset(
                    {
                        RecoveryCommandKind.REPLAN_STEP,
                        RecoveryCommandKind.ABORT,
                    }
                ),
                recoverable=True,
                planner_feedback=feedback,
            )
        return ProposalRejectionRecoveryDecision(
            available_commands=frozenset({RecoveryCommandKind.ABORT}),
            recoverable=False,
            planner_feedback=feedback,
        )
