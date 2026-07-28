"""Terminal decision helpers for Coordinator-controlled runtime stops."""

from __future__ import annotations

from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.state_kernel import StateKernel


def is_safe_incomplete_terminal(decision: PlannerDecision, state: StateKernel) -> bool:
    """Allow an evidence-explicit non-success stop without claiming completion."""

    status = str(decision.result.get("status") or "").casefold()
    return (
        status in {"blocked", "incomplete", "inconclusive", "unsupported"}
        and not state.receipts
        and state.effectful_action_count == 0
    )
