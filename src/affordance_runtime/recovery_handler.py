"""Read-only recovery assessment for the serial Runtime Coordinator."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.recovery import (
    BoundedRecoveryPolicy,
    FailureSignature,
    RecoveryAction,
    RecoveryAttemptOutcome,
    RecoveryCascadeAssessment,
    RecoveryCascadeDetector,
    RecoveryContext,
    RecoveryDecision,
    RecoveryIncident,
)


@dataclass(frozen=True)
class RecoveryRequest:
    """Immutable values needed to decide one recovery attempt."""

    contract: ActionContract
    receipt: ExecutionReceipt | None
    error: RuntimeErrorCode | None
    failure_phase: str
    state_revision: str
    task_id: str
    recovery_count: int
    tried_backends: tuple[str, ...]
    incident: RecoveryIncident | None = None


@dataclass(frozen=True)
class RecoveryEvaluation:
    """Recovery decision and evidence for Coordinator-owned application."""

    signature: FailureSignature
    assessment: RecoveryCascadeAssessment
    context: RecoveryContext
    decision: RecoveryDecision
    effect_may_have_occurred: bool
    continues_open_incident: bool


@dataclass(frozen=True)
class RecoveryHandler:
    """Assess a recovery request without mutating its incident or run state."""

    policy: BoundedRecoveryPolicy
    cascade_detector: RecoveryCascadeDetector

    def evaluate(self, request: RecoveryRequest) -> RecoveryEvaluation:
        effect_may_have_occurred = bool(
            request.receipt
            and request.receipt.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT
        )
        signature = FailureSignature.from_failure(
            request.contract,
            request.receipt,
            phase=request.failure_phase,
            error_code=request.error,
            state_revision=request.state_revision,
        )
        source_incident = request.incident
        if source_incident is not None and source_incident.terminal_outcome == "open":
            continues_open_incident = True
            incident_view = deepcopy(source_incident)
            incident_view.complete_pending(
                request.state_revision,
                outcome=RecoveryAttemptOutcome.FAILED,
            )
            incident_view.symptom_chain.append(signature)
        else:
            continues_open_incident = False
            incident_view = RecoveryIncident(
                incident_id=f"recovery-{request.task_id}-{request.recovery_count + 1}",
                source_contract_id=request.contract.id,
                source_snapshot_id=request.contract.snapshot_id,
                root_failure=signature,
            )

        tried_backends = list(request.tried_backends)
        fallbacks_remaining = any(
            item not in set(tried_backends)
            for item in request.contract.fallback_backends
        )
        assessment = self.cascade_detector.assess(
            incident_view,
            signature,
            fallbacks_remaining=fallbacks_remaining,
            effect_may_have_occurred=effect_may_have_occurred,
            idempotency_key=request.contract.idempotency_key,
        )
        context = RecoveryContext(
            attempt=request.recovery_count,
            recovery_count=request.recovery_count,
            tried_backends=tried_backends,
            effect_may_have_occurred=effect_may_have_occurred,
            failure_signature=signature,
            task_id=request.task_id,
        )
        decision = (
            RecoveryDecision(
                RecoveryAction.ABORT,
                "recovery cascade detector stopped a repeated or unsafe loop",
            )
            if assessment.should_abort
            else self.policy.decide(
                request.contract,
                request.receipt,
                context,
                error_code=request.error,
            )
        )
        return RecoveryEvaluation(
            signature=signature,
            assessment=assessment,
            context=context,
            decision=decision,
            effect_may_have_occurred=effect_may_have_occurred,
            continues_open_incident=continues_open_incident,
        )
