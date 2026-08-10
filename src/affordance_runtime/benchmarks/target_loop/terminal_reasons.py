"""Privacy-safe projection of Runtime terminal messages for benchmark evidence."""

from affordance_runtime.agent import AgentFailureCode, AgentLoopStatus
from affordance_runtime.benchmarks.target_loop.contracts import TerminalReasonCode

_EXACT_BLOCKED_REASONS = {
    "policy selected outside the current action page": TerminalReasonCode.ACTION_OUTSIDE_CURRENT_PAGE,
    "policy selected a destination outside the current action page": (
        TerminalReasonCode.DESTINATION_OUTSIDE_CURRENT_PAGE
    ),
    "policy selected outside ActionSpace": TerminalReasonCode.ACTION_OUTSIDE_ACTION_SPACE,
    "completion claim contains an unknown or duplicate criterion": (
        TerminalReasonCode.INVALID_COMPLETION_CLAIM
    ),
    "completion claim retains unresolved items": TerminalReasonCode.INVALID_COMPLETION_CLAIM,
    "completion evidence is not current": TerminalReasonCode.COMPLETION_EVIDENCE_NOT_CURRENT,
    "observation capability was not offered": TerminalReasonCode.OBSERVATION_CAPABILITY_NOT_OFFERED,
    "invalid action page request": TerminalReasonCode.INVALID_ACTION_PAGE_REQUEST,
    "total wait budget exhausted": TerminalReasonCode.WAIT_BUDGET_EXHAUSTED,
    "bound request context is not current": TerminalReasonCode.STALE_BOUND_REQUEST,
    "confirmation decision is stale or already resolved": (
        TerminalReasonCode.INVALID_CONFIRMATION_DECISION
    ),
    "confirmation decision identity mismatch": TerminalReasonCode.INVALID_CONFIRMATION_DECISION,
}
_INVALID_PARAMETER_PREFIXES = (
    "action parameters ",
    "destination IDs ",
    "destination contains ",
    "missing required semantic parameters:",
    "policy parameters ",
    "semantic destination ",
    "unknown semantic parameters:",
)
_INVALID_PARAMETER_EXACT = {
    "action does not accept a semantic destination",
    "semantic destination is required",
    "semantic destination was not offered by the current ActionSpace",
}


def project_terminal_reason_code(
    status: AgentLoopStatus,
    message: str,
    failure_code: AgentFailureCode | None = None,
) -> TerminalReasonCode | None:
    """Return a bounded code without copying message content into evidence."""
    if failure_code == AgentFailureCode.NO_PROGRESS_REPETITION:
        return TerminalReasonCode.NO_PROGRESS_REPETITION
    if status != AgentLoopStatus.BLOCKED:
        return None
    exact = _EXACT_BLOCKED_REASONS.get(message)
    if exact is not None:
        return exact
    if message in _INVALID_PARAMETER_EXACT or message.startswith(_INVALID_PARAMETER_PREFIXES):
        return TerminalReasonCode.INVALID_ACTION_PARAMETERS
    return TerminalReasonCode.BLOCKED_OTHER
