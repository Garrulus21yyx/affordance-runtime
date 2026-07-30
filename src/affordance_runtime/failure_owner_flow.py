"""Application seam for non-runtime failure-owner handoff.

RecoveryPhase is intentionally limited to Runtime-owned recovery work. Planner,
user, progress, and terminal failures are classified in the shared SAR-8
taxonomy, but handed back to their owning runtime boundary here instead of being
forced through Runtime recovery policy.
"""

from __future__ import annotations

from uuid import uuid4

from affordance_runtime.failure_envelope import FailureEnvelope, FailurePhase
from affordance_runtime.recovery_protocol import (
    FailureClassification,
    FailureOwner,
    RecoveryBudgetCost,
    RecoveryDecision,
    RecoveryDimension,
    RecoveryKind,
    RecoveryOutcome,
    RuntimePhase,
)
from affordance_runtime.recovery_trace_projection import recovery_protocol_projections
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode


def commit_non_runtime_failure_owner_handoff(
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    *,
    failure: FailureEnvelope,
    classification: FailureClassification,
) -> tuple[RecoveryKind, TraceNode]:
    """Commit a typed non-runtime failure-owner handoff.

    This is a temporary application seam while SAR-8C removes the legacy
    recovery protocol. It deliberately does not call RecoveryPhase or choose a
    Runtime recovery strategy for failures owned by Planner, User, Progress, or
    Terminal boundaries.
    """

    decision = _non_runtime_owner_decision(
        failure,
        classification,
        current_state_version=state.version,
    )
    if decision.strategy_key in failure.attempted_strategy_ids:
        classification = FailureClassification(
            kind=classification.kind,
            owner=FailureOwner.TERMINAL,
            reason_code=f"{classification.reason_code}_owner_strategy_exhausted",
            planner_deferral_kind=classification.planner_deferral_kind,
            available_action_count=classification.available_action_count,
        )
        decision = _non_runtime_owner_decision(
            failure,
            classification,
            current_state_version=state.version,
        )

    state.current_failure = failure
    state.current_recovery_decision = decision
    state.current_recovery_outcome = None
    state.attempted_recovery_strategy_ids.add(decision.strategy_key)
    state.recovery_count += 1

    for projection in recovery_protocol_projections(
        state_phase=state.phase,
        failure=failure,
        decision=decision,
    ):
        parent = trace.add(projection.kind, projection.payload, parents=[parent.id])

    if classification.owner in {FailureOwner.STEP_PLANNER, FailureOwner.TASK_PLANNER}:
        state.replan_count += 1
        state.record_disproved_assumption(
            f"{failure.phase.value}:{failure.error_code}:{failure.message}"
        )
        if state.phase != RuntimeStep.OBSERVING.value:
            state.transition(RuntimeStep.OBSERVING.value)
        return decision.kind, parent

    terminal_step = _runtime_step_for_owner_decision(decision)
    if terminal_step is not None:
        state.transition(terminal_step)
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
        )
        parent = trace.add(
            "RecoveryOutcomeRecorded",
            {
                "state": state.phase,
                "outcome": {
                    "decision_id": state.current_recovery_outcome.decision_id,
                    "failure_id": state.current_recovery_outcome.failure_id,
                    "success": state.current_recovery_outcome.success,
                    "changed_dimensions": [
                        item.value
                        for item in state.current_recovery_outcome.changed_dimensions
                    ],
                    "next_phase": state.current_recovery_outcome.next_phase.value,
                    "artifact_refs": [],
                    "observation_refs": [],
                    "error_code": "",
                },
            },
            parents=[parent.id],
        )

    return decision.kind, parent


def _non_runtime_owner_decision(
    failure: FailureEnvelope,
    classification: FailureClassification,
    *,
    current_state_version: int,
) -> RecoveryDecision:
    kind, dimension, reentry, cost = {
        FailureOwner.PROGRESS: (
            RecoveryKind.ABORT,
            RecoveryDimension.TERMINAL,
            RuntimePhase.ABORTED,
            RecoveryBudgetCost(recoveries=0),
        ),
        FailureOwner.STEP_PLANNER: (
            RecoveryKind.REPLAN_STEP,
            RecoveryDimension.STEP_PLAN,
            RuntimePhase.PLANNING,
            RecoveryBudgetCost(replans=1),
        ),
        FailureOwner.TASK_PLANNER: (
            RecoveryKind.REPLAN_TASK,
            RecoveryDimension.TASK_PLAN,
            RuntimePhase.PLANNING,
            RecoveryBudgetCost(replans=1),
        ),
        FailureOwner.USER: (
            RecoveryKind.CLARIFY_INTENT
            if failure.phase == FailurePhase.INTAKE
            else RecoveryKind.ASK_USER,
            RecoveryDimension.USER_INFORMATION,
            RuntimePhase.WAITING_USER,
            RecoveryBudgetCost(user_escalations=1),
        ),
        FailureOwner.TERMINAL: (
            RecoveryKind.ABORT,
            RecoveryDimension.TERMINAL,
            RuntimePhase.ABORTED,
            RecoveryBudgetCost(recoveries=0),
        ),
    }[classification.owner]
    strategy_key = (
        f"strategy:{kind.value}:"
        f"{failure.semantic_family_key.removeprefix('sha256:')[:16]}"
    )
    return RecoveryDecision(
        decision_id=f"failure-owner-decision-{uuid4().hex}",
        failure_id=failure.failure_id,
        based_on_state_version=current_state_version,
        strategy_key=strategy_key,
        kind=kind,
        reason_code=classification.reason_code,
        reentry_phase=reentry,
        changed_dimensions=(dimension,),
        preconditions=(f"failure owner is {classification.owner.value}",),
        budget_cost=cost,
        question=(
            "What information or authority is required to continue safely?"
            if classification.owner == FailureOwner.USER
            else ""
        ),
    )


def _runtime_step_for_owner_decision(decision: RecoveryDecision) -> str | None:
    return {
        RuntimePhase.WAITING_USER: RuntimeStep.WAITING_CLARIFICATION.value,
        RuntimePhase.WAITING_APPROVAL: RuntimeStep.WAITING_APPROVAL.value,
        RuntimePhase.DEFERRED: RuntimeStep.DEFERRED.value,
        RuntimePhase.FAILED: RuntimeStep.FAILED.value,
        RuntimePhase.ABORTED: RuntimeStep.ABORTED.value,
    }.get(decision.reentry_phase)
