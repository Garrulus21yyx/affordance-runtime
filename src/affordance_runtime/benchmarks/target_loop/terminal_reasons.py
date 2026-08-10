"""Privacy-safe projection of typed Runtime terminal reasons."""

from affordance_runtime.agent import AgentFailureCode, AgentLoopStatus
from affordance_runtime.benchmarks.target_loop.contracts import (
    TerminalReasonCode,
    terminal_reason_from_facts,
)


def project_terminal_reason_code(
    status: AgentLoopStatus,
    reason_code: str,
    failure_code: AgentFailureCode | None = None,
) -> TerminalReasonCode | None:
    """Return a bounded code without copying message content into evidence."""
    return terminal_reason_from_facts(
        status.value,
        reason_code,
        failure_code.value if failure_code is not None else "",
    )
