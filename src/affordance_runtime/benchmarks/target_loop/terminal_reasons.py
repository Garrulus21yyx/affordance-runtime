"""Privacy-safe projection of typed Runtime terminal reasons."""

from affordance_runtime.agent import AgentFailureCode, AgentLoopStatus
from affordance_runtime.benchmarks.target_loop.contracts import TerminalReasonCode

_BLOCKED_REASON_CODES = {
    "action_outside_current_page": TerminalReasonCode.ACTION_OUTSIDE_CURRENT_PAGE,
    "destination_outside_current_page": (
        TerminalReasonCode.DESTINATION_OUTSIDE_CURRENT_PAGE
    ),
    "action_outside_action_space": TerminalReasonCode.ACTION_OUTSIDE_ACTION_SPACE,
    "invalid_action_parameters": TerminalReasonCode.INVALID_ACTION_PARAMETERS,
    "invalid_completion_claim": TerminalReasonCode.INVALID_COMPLETION_CLAIM,
    "completion_evidence_not_current": TerminalReasonCode.COMPLETION_EVIDENCE_NOT_CURRENT,
    "observation_capability_not_offered": TerminalReasonCode.OBSERVATION_CAPABILITY_NOT_OFFERED,
    "invalid_action_page_request": TerminalReasonCode.INVALID_ACTION_PAGE_REQUEST,
    "wait_budget_exhausted": TerminalReasonCode.WAIT_BUDGET_EXHAUSTED,
    "stale_bound_request": TerminalReasonCode.STALE_BOUND_REQUEST,
    "invalid_confirmation_decision": TerminalReasonCode.INVALID_CONFIRMATION_DECISION,
}


def project_terminal_reason_code(
    status: AgentLoopStatus,
    reason_code: str,
    failure_code: AgentFailureCode | None = None,
) -> TerminalReasonCode | None:
    """Return a bounded code without copying message content into evidence."""
    if failure_code == AgentFailureCode.NO_PROGRESS_REPETITION:
        return TerminalReasonCode.NO_PROGRESS_REPETITION
    if status != AgentLoopStatus.BLOCKED:
        return None
    exact = _BLOCKED_REASON_CODES.get(reason_code)
    if exact is not None:
        return exact
    return TerminalReasonCode.BLOCKED_OTHER
