"""Coordinator-facing ActionOutcome recording seam.

This SAR-6 migration seam builds the canonical execution outcome and appends
the diagnostic trace event. It does not mutate StateKernel, decide progress, or
decide task finish.
"""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation
from affordance_runtime.simplified_runtime_contracts import ActionOutcome, ExecutionAttempt
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification.mechanical import VerificationReport


@dataclass(frozen=True)
class ActionOutcomeTraceCommit:
    parent: TraceNode
    outcome: ActionOutcome


def record_action_outcome_trace(
    *,
    execution_loop: ContractExecutionLoop,
    trace: TraceDag,
    parent: TraceNode,
    attempt: ExecutionAttempt,
    receipt: ExecutionReceipt,
    verification: VerificationReport,
    post_observation: Observation,
    step_id: str,
    state_phase: str,
) -> ActionOutcomeTraceCommit:
    outcome = execution_loop.record_action_outcome(
        attempt=attempt,
        receipt=receipt,
        verification=verification,
        post_observation=post_observation,
        step_id=step_id,
    )
    return ActionOutcomeTraceCommit(
        parent=trace.add(
            "ActionOutcomeRecorded",
            {
                "state": state_phase,
                "outcome_id": outcome.outcome_id,
                "status": outcome.status.value,
                "contract_id": outcome.attempt.contract_id,
                "contract_hash": outcome.attempt.contract_hash,
                "attempt_id": outcome.attempt.attempt_id,
                "step_id": outcome.step_id,
                "receipt_success": outcome.receipt_success,
                "verification_status": outcome.verification.status.value,
                "post_snapshot_id": outcome.verification.post_observation.snapshot_id,
                "evidence_refs": list(outcome.verification.evidence_refs),
            },
            parents=[parent.id],
        ),
        outcome=outcome,
    )


def record_contract_action_outcome_trace(
    execution_loop: ContractExecutionLoop,
    trace: TraceDag,
    parent: TraceNode,
    contract: ActionContract,
    pre_observation: Observation,
    issued_at_state_version: int,
    receipt: ExecutionReceipt,
    verification: VerificationReport,
    post_observation: Observation,
    step_id: str,
    state_phase: str,
) -> ActionOutcomeTraceCommit:
    attempt = execution_loop.build_execution_attempt(
        contract,
        pre_observation,
        issued_at_state_version=issued_at_state_version,
        active_step_id=step_id if step_id != contract.affordance_id else "",
    )
    return record_action_outcome_trace(
        execution_loop=execution_loop,
        trace=trace,
        parent=parent,
        attempt=attempt,
        receipt=receipt,
        verification=verification,
        post_observation=post_observation,
        step_id=step_id,
        state_phase=state_phase,
    )
