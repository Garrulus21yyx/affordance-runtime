"""Recovery trace commit helpers owned outside the main Coordinator loop."""

from __future__ import annotations

from typing import Any

from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode


def trace_recovery_started(
    trace: TraceDag,
    parent: TraceNode,
    state: StateKernel,
    command: RecoveryKind,
    *,
    verification_status: str = "",
) -> TraceNode:
    payload: dict[str, Any] = {"state": state.phase, "action": command.value}
    if verification_status:
        payload["verification"] = verification_status
    return trace.add("RecoveryStarted", payload, parents=[parent.id])
