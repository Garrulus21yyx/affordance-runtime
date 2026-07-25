"""Pure construction of evidence-backed successful recovery completion facts."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery_commands import RecoveryCommand, RecoveryDelta, RecoveryReceipt
from affordance_runtime.recovery_coordinator import RecoveryHistoryItem


@dataclass(frozen=True)
class RecoveryCompletion:
    receipt: RecoveryReceipt
    delta: RecoveryDelta
    history: RecoveryHistoryItem


def successful_recovery_completion(
    *,
    failure: FailureEnvelope,
    command: RecoveryCommand,
    state_version: int,
    retired_assumptions: tuple[str, ...],
    fingerprint_ref: str,
    plan_or_route_ref: str,
) -> RecoveryCompletion:
    """Create receipt/delta/history after a Coordinator-observed state change."""

    previous = failure.progress_fingerprint or f"{failure.semantic_family_key}:state:{failure.state_version}"
    next_fingerprint = f"{failure.semantic_family_key}:{command.strategy_id}:{fingerprint_ref}:state:{state_version}"
    delta = RecoveryDelta(
        previous_attempt_fingerprint=previous,
        next_attempt_fingerprint=next_fingerprint,
        changed_dimensions=command.changed_dimensions,
        retired_assumptions=retired_assumptions,
        new_plan_or_route_ref=plan_or_route_ref,
        explanation=command.expected_change,
    )
    receipt = RecoveryReceipt(
        command_id=command.command_id,
        success=True,
        state_before=f"state:{failure.state_version}",
        state_after=f"state:{state_version}",
        changed_dimensions=command.changed_dimensions,
        plan_refs=(plan_or_route_ref,) if plan_or_route_ref else (),
        delta=delta,
    )
    return RecoveryCompletion(
        receipt=receipt,
        delta=delta,
        history=RecoveryHistoryItem(
            failure.semantic_family_key,
            command.strategy_id,
            previous,
            next_fingerprint,
        ),
    )
