"""Coordinator-facing contract-failure seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_binding_phase import ContractBindingPhaseResult
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class ContractFailureTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode


@dataclass(frozen=True)
class ContractFailurePhaseResult:
    parent: TraceNode
    terminal: ContractFailureTerminal | None = None
    continue_observing: bool = False


class ContractFailurePhase:
    """Apply contract-binding failure recovery behind a named seam."""

    def handle(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        contract_binding: ContractBindingPhaseResult,
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
    ) -> ContractFailurePhaseResult | None:
        if contract_binding.failure is None:
            return None
        failure = contract_binding.failure
        recovery_kind, parent = recover_phase_failure(
            envelope,
            state,
            trace,
            parent,
            phase=failure.phase,
            failure_class=failure.failure_class,
            error_code=failure.error_code,
            message=failure.message,
            available_commands=failure.available_commands,
            snapshot=snapshot,
            proposal_id=failure.proposal_id,
            expected_effect=failure.expected_effect,
            recoverable=failure.recoverable,
        )
        if recovery_kind in failure.continue_recovery_kinds:
            return ContractFailurePhaseResult(parent=parent, continue_observing=True)
        return ContractFailurePhaseResult(
            parent=parent,
            terminal=ContractFailureTerminal(
                RuntimeStep.ABORTED,
                failure.error_code,
            ),
        )
