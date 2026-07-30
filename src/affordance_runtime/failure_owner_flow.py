"""Application seam for non-runtime failure-owner handoff.

RecoveryPhase is intentionally limited to Runtime-owned recovery work. Planner,
user, progress, and terminal failures are classified in the shared SAR-8
taxonomy, but handed back to their owning runtime boundary here instead of being
forced through Runtime recovery policy.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class FailureOwnerHandoff:
    failure_id: str
    owner: FailureOwner
    reason_code: str
    target_phase: RuntimePhase
    changed_dimensions: tuple[RecoveryDimension, ...]
    replan_scope: str = ""
    user_question: str = ""

    def __post_init__(self) -> None:
        if not self.failure_id.strip():
            raise ValueError("failure owner handoff failure_id is required")
        if not self.reason_code.strip():
            raise ValueError("failure owner handoff reason_code is required")
        if self.owner == FailureOwner.RUNTIME_RECOVERY:
            raise ValueError("non-runtime failure owner handoff cannot target runtime recovery")
        if not self.changed_dimensions:
            raise ValueError("failure owner handoff changed_dimensions are required")
        object.__setattr__(
            self,
            "changed_dimensions",
            tuple(RecoveryDimension(str(item)) for item in self.changed_dimensions),
        )
        object.__setattr__(self, "owner", FailureOwner(str(self.owner)))
        object.__setattr__(self, "target_phase", RuntimePhase(str(self.target_phase)))


@dataclass(frozen=True)
class FailureOwnerHandoffDecision:
    decision: RecoveryDecision
    handoff: FailureOwnerHandoff

    def __getattr__(self, name: str) -> object:
        return getattr(self.decision, name)


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

    handoff_decision = non_runtime_failure_owner_decision(
        failure,
        classification,
        current_state_version=state.version,
    )
    decision = handoff_decision.decision
    if decision.strategy_key in failure.attempted_strategy_ids:
        classification = FailureClassification(
            kind=classification.kind,
            owner=FailureOwner.TERMINAL,
            reason_code=f"{classification.reason_code}_owner_strategy_exhausted",
            planner_deferral_kind=classification.planner_deferral_kind,
            available_action_count=classification.available_action_count,
        )
        handoff_decision = non_runtime_failure_owner_decision(
            failure,
            classification,
            current_state_version=state.version,
        )
        decision = handoff_decision.decision

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

    if classification.owner in {FailureOwner.STEP_PLANNER, FailureOwner.TASK_PLANNER}:
        state.replan_count += 1
        state.record_disproved_assumption(
            f"{failure.phase.value}:{failure.error_code}:{failure.message}"
        )
        if state.phase != RuntimeStep.OBSERVING.value:
            state.transition(RuntimeStep.OBSERVING.value)
        return decision.kind, parent

    return decision.kind, parent


def non_runtime_failure_owner_decision(
    failure: FailureEnvelope,
    classification: FailureClassification,
    *,
    current_state_version: int,
) -> FailureOwnerHandoffDecision:
    handoff = build_failure_owner_handoff(failure, classification)
    kind = _recovery_kind_for_handoff(handoff, failure)
    cost = _budget_cost_for_handoff(handoff, kind)
    strategy_key = (
        f"strategy:{kind.value}:"
        f"{failure.semantic_family_key.removeprefix('sha256:')[:16]}"
    )
    decision = RecoveryDecision(
        decision_id=f"failure-owner-decision-{uuid4().hex}",
        failure_id=failure.failure_id,
        based_on_state_version=current_state_version,
        strategy_key=strategy_key,
        kind=kind,
        reason_code=classification.reason_code,
        reentry_phase=handoff.target_phase,
        changed_dimensions=handoff.changed_dimensions,
        preconditions=(f"failure owner is {handoff.owner.value}",),
        budget_cost=cost,
        question=handoff.user_question if kind != RecoveryKind.ABORT else "",
    )
    return FailureOwnerHandoffDecision(decision=decision, handoff=handoff)


def build_failure_owner_handoff(
    failure: FailureEnvelope,
    classification: FailureClassification,
) -> FailureOwnerHandoff:
    if classification.owner == FailureOwner.RUNTIME_RECOVERY:
        raise ValueError("non-runtime failure owner handoff received runtime recovery owner")
    owner = FailureOwner.TERMINAL if not failure.recoverable else classification.owner
    dimension, target_phase, replan_scope, question = {
        FailureOwner.PROGRESS: (
            RecoveryDimension.TERMINAL,
            RuntimePhase.ABORTED,
            "",
            "",
        ),
        FailureOwner.STEP_PLANNER: (
            RecoveryDimension.STEP_PLAN,
            RuntimePhase.PLANNING,
            "step",
            "",
        ),
        FailureOwner.TASK_PLANNER: (
            RecoveryDimension.TASK_PLAN,
            RuntimePhase.PLANNING,
            "task",
            "",
        ),
        FailureOwner.USER: (
            RecoveryDimension.USER_INFORMATION,
            RuntimePhase.WAITING_USER,
            "",
            "What information or authority is required to continue safely?",
        ),
        FailureOwner.TERMINAL: (
            RecoveryDimension.TERMINAL,
            RuntimePhase.ABORTED,
            "",
            "",
        ),
    }[owner]
    return FailureOwnerHandoff(
        failure_id=failure.failure_id,
        owner=owner,
        reason_code=classification.reason_code,
        target_phase=target_phase,
        changed_dimensions=(dimension,),
        replan_scope=replan_scope,
        user_question=question,
    )


def _recovery_kind_for_handoff(
    handoff: FailureOwnerHandoff,
    failure: FailureEnvelope,
) -> RecoveryKind:
    if handoff.owner in {FailureOwner.PROGRESS, FailureOwner.TERMINAL}:
        return RecoveryKind.ABORT
    if handoff.owner == FailureOwner.STEP_PLANNER:
        return RecoveryKind.REPLAN_STEP
    if handoff.owner == FailureOwner.TASK_PLANNER:
        return RecoveryKind.REPLAN_TASK
    if handoff.owner == FailureOwner.USER:
        return (
            RecoveryKind.CLARIFY_INTENT
            if failure.phase == FailurePhase.INTAKE
            else RecoveryKind.ASK_USER
        )
    raise ValueError(f"unsupported failure owner handoff: {handoff.owner}")


def _budget_cost_for_handoff(
    handoff: FailureOwnerHandoff,
    kind: RecoveryKind,
) -> RecoveryBudgetCost:
    if kind == RecoveryKind.ABORT:
        return RecoveryBudgetCost(recoveries=0)
    if handoff.owner in {FailureOwner.STEP_PLANNER, FailureOwner.TASK_PLANNER}:
        return RecoveryBudgetCost(replans=1)
    if handoff.owner == FailureOwner.USER:
        return RecoveryBudgetCost(user_escalations=1)
    return RecoveryBudgetCost(recoveries=0)


def _runtime_step_for_owner_decision(decision: RecoveryDecision) -> str | None:
    return {
        RuntimePhase.WAITING_USER: RuntimeStep.WAITING_CLARIFICATION.value,
        RuntimePhase.WAITING_APPROVAL: RuntimeStep.WAITING_APPROVAL.value,
        RuntimePhase.DEFERRED: RuntimeStep.DEFERRED.value,
        RuntimePhase.FAILED: RuntimeStep.FAILED.value,
        RuntimePhase.ABORTED: RuntimeStep.ABORTED.value,
    }.get(decision.reentry_phase)
