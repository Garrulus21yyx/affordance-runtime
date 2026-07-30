"""Read-only recovery assessment for the serial Runtime Coordinator."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailureEnvelope,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
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
from affordance_runtime.recovery_commands import RecoveryCommandKind, RecoveryPlan
from affordance_runtime.recovery_coordinator import (
    RecoveryCoordinator,
    RecoveryHistoryItem,
    RecoverySelectionContext,
)
from affordance_runtime.recovery_decision_compatibility import (
    legacy_plan_from_recovery_decision,
)
from affordance_runtime.recovery_protocol import (
    FailureClassificationFacts,
    classify_failure,
)
from affordance_runtime.verification import VerificationReport


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
    state_version: int = 0
    progress_fingerprint: str = ""
    accepted_profile_digest: str = ""
    accepted_profile_artifact_ids: tuple[str, ...] = ()
    attempted_strategy_ids: tuple[str, ...] = ()
    recovery_history: tuple[RecoveryHistoryItem, ...] = ()
    verification: VerificationReport | None = None
    verification_ref: str = ""


@dataclass(frozen=True)
class RecoveryEvaluation:
    """Recovery decision and evidence for Coordinator-owned application."""

    signature: FailureSignature
    assessment: RecoveryCascadeAssessment
    context: RecoveryContext
    decision: RecoveryDecision
    effect_may_have_occurred: bool
    continues_open_incident: bool
    failure: FailureEnvelope
    plan: RecoveryPlan


@dataclass(frozen=True)
class RecoveryHandler:
    """Assess a recovery request without mutating its incident or run state."""

    policy: BoundedRecoveryPolicy
    cascade_detector: RecoveryCascadeDetector

    def evaluate(self, request: RecoveryRequest) -> RecoveryEvaluation:
        effect_may_have_occurred = bool(
            request.receipt
            and request.receipt.evidence.get("dispatched") is not False
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
            tried_backends=tuple(tried_backends),
            effect_may_have_occurred=effect_may_have_occurred,
            failure_signature=signature,
            task_id=request.task_id,
        )
        legacy_decision = (
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
        failure_phase = _failure_phase(
            request.failure_phase,
            effect_may_have_occurred=effect_may_have_occurred,
        )
        effect_status = (
            EffectStatus.MAY_HAVE_OCCURRED
            if effect_may_have_occurred
            else EffectStatus.NOT_DISPATCHED
        )
        failure = make_failure_envelope(
            run_id=request.task_id,
            phase=failure_phase,
            failure_class=_failure_class(request.error, request.receipt),
            error_code=request.error or (request.receipt.error_code if request.receipt else None) or "unknown",
            message=(
                request.verification.reason
                if request.error == RuntimeErrorCode.VERIFICATION_FAILED
                and request.verification is not None
                else request.receipt.message
                if request.receipt is not None and request.receipt.message
                else signature.normalized_error
            ),
            state_version=request.state_version,
            observation_epoch_id=request.contract.snapshot_id,
            snapshot_id=request.contract.snapshot_id,
            contract=request.contract,
            receipt=request.receipt,
            expected_effect=request.contract.expected_effects[0].description
            if request.contract.expected_effects
            else request.contract.intent,
            evidence_refs=(request.verification_ref,) if request.verification_ref else (),
            verification_ref=request.verification_ref,
            effect_status=effect_status,
            attempted_strategy_ids=request.attempted_strategy_ids,
            remaining_budgets=RemainingRecoveryBudgets(
                recoveries=max(0, self.policy.max_recoveries - request.recovery_count),
                observations=8,
                replans=8,
                provider_switches=1,
                user_escalations=1,
                timeout_ms=120_000,
                model_calls=8,
                estimated_cost=10.0,
            ),
            recoverable=not assessment.should_abort,
            progress_fingerprint=request.progress_fingerprint or request.state_revision,
            debug_context=(
                {
                    "verification_status": request.verification.status.value,
                    "failed_verifier_kinds": [
                        item.verifier_kind
                        for item in request.verification.evidence
                        if not item.passed
                    ],
                }
                if request.verification is not None
                else None
            ),
        )
        available = {
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.INSPECT_POST_STATE,
            RecoveryCommandKind.ABORT,
        }
        alternative_id = ""
        route_ref = ""
        if request.contract.route_plan is not None and request.contract.route_plan.viable_alternatives:
            alternative_id = request.contract.route_plan.viable_alternatives[0].candidate_id
            available.add(RecoveryCommandKind.REROUTE)
        elif request.contract.fallback_backends:
            route_ref = next(
                (
                    item
                    for item in request.contract.fallback_backends
                    if item not in request.tried_backends
                ),
                "",
            )
            if route_ref:
                available.add(RecoveryCommandKind.REROUTE)
        if request.contract.idempotency_key:
            available.add(RecoveryCommandKind.RETRY_IDEMPOTENT)
        if request.contract.compensation:
            available.add(RecoveryCommandKind.COMPENSATE)
        if legacy_decision.action == RecoveryAction.REQUEST_APPROVAL:
            available.add(RecoveryCommandKind.REQUEST_APPROVAL)
        legacy_preferred_kind = _command_kind_for_legacy(legacy_decision.action)
        accepted_profile_artifact_ids = frozenset(request.accepted_profile_artifact_ids)
        preferred_profile_artifact_id = (
            legacy_decision.profile_artifact_id
            if legacy_decision.profile_artifact_id in accepted_profile_artifact_ids
            else ""
        )
        preferred = (
            (legacy_preferred_kind,)
            if not legacy_decision.profile_artifact_id or preferred_profile_artifact_id
            else ()
        )
        recovery_context = RecoverySelectionContext(
            available_commands=frozenset(available),
            current_attempt_fingerprint=request.state_revision,
            fresh_candidate_id=alternative_id,
            fresh_route_ref=route_ref,
            idempotency_key=request.contract.idempotency_key,
            compensation_contract_id=(
                f"compensation:{request.contract.id}"
                if request.contract.compensation
                else ""
            ),
            preferred_profile_commands=preferred,
            preferred_profile_artifact_id=preferred_profile_artifact_id,
            accepted_profile_digest=request.accepted_profile_digest,
            accepted_profile_artifact_ids=accepted_profile_artifact_ids,
            history=request.recovery_history,
        )
        classification = classify_failure(
            failure,
            FailureClassificationFacts(
                available_action_count=recovery_context.available_action_count,
                user_input_required=recovery_context.user_input_required,
            ),
        )
        canonical_decision = RecoveryCoordinator().decide(
            failure,
            classification,
            recovery_context,
            current_state_version=request.state_version,
        )
        plan = legacy_plan_from_recovery_decision(
            canonical_decision,
            failure,
            effect_status=failure.effect_status,
            profile_digest=recovery_context.accepted_profile_digest,
            profile_artifact_id=(
                recovery_context.preferred_profile_artifact_id
                if canonical_decision.kind.value == legacy_preferred_kind.value
                else ""
            ),
            gap_ids=recovery_context.gap_ids,
        )
        decision = RecoveryDecision(
            _legacy_action_for_command(plan.commands[0].kind),
            plan.commands[0].expected_change,
            legacy_decision.backend,
            plan.commands[0].profile_artifact_id,
        )
        return RecoveryEvaluation(
            signature=signature,
            assessment=assessment,
            context=context,
            decision=decision,
            effect_may_have_occurred=effect_may_have_occurred,
            continues_open_incident=continues_open_incident,
            failure=failure,
            plan=plan,
        )


def _failure_phase(value: str, *, effect_may_have_occurred: bool) -> FailurePhase:
    normalized = value.casefold()
    if normalized == "preflight":
        return FailurePhase.PREFLIGHT
    if normalized == "verifying":
        return FailurePhase.VERIFICATION
    if normalized == "acting":
        return (
            FailurePhase.EXECUTION_UNCERTAIN
            if effect_may_have_occurred
            else FailurePhase.EXECUTION_NOT_DISPATCHED
        )
    return FailurePhase.EXECUTION_NOT_DISPATCHED


def _failure_class(
    error: RuntimeErrorCode | None,
    receipt: ExecutionReceipt | None,
) -> FailureClass:
    code = error or (receipt.error_code if receipt is not None else None)
    if code in {
        RuntimeErrorCode.STALE_OBSERVATION,
        RuntimeErrorCode.STALE_PAGE_REVISION,
        RuntimeErrorCode.SNAPSHOT_MISMATCH,
        RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
        RuntimeErrorCode.LEASE_EXPIRED,
    }:
        return FailureClass.STALE_STATE
    if code in {
        RuntimeErrorCode.CAPABILITY_DENIED,
        RuntimeErrorCode.APPROVAL_REQUIRED,
        RuntimeErrorCode.UNSAFE_ACTION,
    }:
        return FailureClass.AUTHORITY
    if code == RuntimeErrorCode.VERIFICATION_FAILED:
        return FailureClass.VERIFICATION
    return FailureClass.EXECUTION


def _command_kind_for_legacy(action: RecoveryAction) -> RecoveryCommandKind:
    return {
        RecoveryAction.REOBSERVE: RecoveryCommandKind.REOBSERVE,
        RecoveryAction.VERIFY_STATE: RecoveryCommandKind.INSPECT_POST_STATE,
        RecoveryAction.RETRY: RecoveryCommandKind.RETRY_IDEMPOTENT,
        RecoveryAction.REROUTE: RecoveryCommandKind.REROUTE,
        RecoveryAction.COMPENSATE: RecoveryCommandKind.COMPENSATE,
        RecoveryAction.REQUEST_APPROVAL: RecoveryCommandKind.REQUEST_APPROVAL,
        RecoveryAction.ABORT: RecoveryCommandKind.ABORT,
    }[action]


def _legacy_action_for_command(kind: RecoveryCommandKind) -> RecoveryAction:
    return {
        RecoveryCommandKind.REOBSERVE: RecoveryAction.REOBSERVE,
        RecoveryCommandKind.INSPECT_POST_STATE: RecoveryAction.VERIFY_STATE,
        RecoveryCommandKind.RETRY_IDEMPOTENT: RecoveryAction.RETRY,
        RecoveryCommandKind.REROUTE: RecoveryAction.REROUTE,
        RecoveryCommandKind.COMPENSATE: RecoveryAction.COMPENSATE,
        RecoveryCommandKind.REQUEST_APPROVAL: RecoveryAction.REQUEST_APPROVAL,
        RecoveryCommandKind.ABORT: RecoveryAction.ABORT,
    }[kind]
