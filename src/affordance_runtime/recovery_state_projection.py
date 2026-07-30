"""Recovery state read projections owned outside the main Coordinator loop."""

from __future__ import annotations

from affordance_runtime.recovery_owner_dispatcher import RecoveryOwnerDispatcher
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.state_kernel import StateKernel


def pending_recovery_kind(state: StateKernel) -> RecoveryKind | None:
    if state.current_recovery_outcome is not None:
        return None
    decision = state.current_recovery_decision
    return decision.kind if decision is not None else None


def available_owner_recovery_kinds(
    dispatcher: RecoveryOwnerDispatcher,
) -> frozenset[RecoveryKind]:
    return dispatcher.available_kinds
