from dataclasses import replace

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.recovery import (
    BoundedRecoveryPolicy,
    FailureSignature,
    RecoveryAction,
    RecoveryAttempt,
    RecoveryAttemptOutcome,
    RecoveryCascadeDetector,
    RecoveryDecision,
    RecoveryIncident,
    RecoveryLoopKind,
)
from affordance_runtime.recovery_commands import RecoveryCommandKind
from affordance_runtime.recovery_handler import RecoveryHandler, RecoveryRequest
from affordance_runtime.verification import VerificationEvidence, VerificationReport, VerificationStatus


def _contract(**overrides: object) -> ActionContract:
    values = {
        "id": "contract-save",
        "intent": "save settings",
        "affordance_id": "save",
        "action": "activate",
        "backend": "portable-web",
        "environment_revision": "environment-1",
        "snapshot_id": "snapshot-1",
        "page_revision": "page-1",
        "locator": {"backend_handle": "opaque-save"},
    }
    values.update(overrides)
    return ActionContract(**values)  # type: ignore[arg-type]


def _receipt(error: RuntimeErrorCode) -> ExecutionReceipt:
    return ExecutionReceipt(
        "contract-save",
        "portable-web",
        False,
        "environment-1",
        "environment-1",
        1.0,
        evidence={"dispatched": True},
        error_code=error,
        message="transport failed",
    )


def _handler() -> RecoveryHandler:
    return RecoveryHandler(BoundedRecoveryPolicy(), RecoveryCascadeDetector())


def _request(
    *,
    receipt: ExecutionReceipt | None = None,
    error: RuntimeErrorCode | None = None,
    incident: RecoveryIncident | None = None,
) -> RecoveryRequest:
    return RecoveryRequest(
        contract=_contract(idempotency_key="save:v1"),
        receipt=receipt,
        error=error,
        failure_phase="acting",
        state_revision="environment-1",
        task_id="recovery-task",
        recovery_count=0,
        tried_backends=("portable-web",),
        incident=incident,
    )


def test_handler_selects_inspection_for_uncertain_effect_without_mutating_state() -> None:
    evaluation = _handler().evaluate(
        _request(receipt=_receipt(RuntimeErrorCode.EXECUTION_TIMEOUT))
    )

    assert evaluation.effect_may_have_occurred
    assert evaluation.decision.action == RecoveryAction.VERIFY_STATE
    assert not evaluation.continues_open_incident
    assert evaluation.signature.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT.value


def test_handler_returns_reobserve_for_stale_contract() -> None:
    evaluation = _handler().evaluate(
        _request(error=RuntimeErrorCode.STALE_OBSERVATION)
    )

    assert evaluation.decision.action == RecoveryAction.REOBSERVE
    assert not evaluation.assessment.should_abort


def test_handler_preserves_verification_reason_and_artifact_in_failure() -> None:
    verification = VerificationReport(
        VerificationStatus.FAILED,
        [
            VerificationEvidence(
                verifier_kind="control_state",
                target="slider",
                expected={"field": "value", "value": "103"},
                observed="104",
                passed=False,
                source="post_action_observation",
            )
        ],
        "verifier failed: control_state:slider",
    )
    evaluation = _handler().evaluate(
        replace(
            _request(
                receipt=_receipt(RuntimeErrorCode.VERIFICATION_FAILED),
                error=RuntimeErrorCode.VERIFICATION_FAILED,
            ),
            failure_phase="verifying",
            verification=verification,
            verification_ref="artifact:verification",
        )
    )

    assert evaluation.failure.message == verification.reason
    assert evaluation.failure.verification_ref == "artifact:verification"
    assert evaluation.failure.evidence_refs == ("artifact:verification",)


def test_handler_adapts_confirmed_nondispatch_to_typed_reroute_plan() -> None:
    contract = _contract(fallback_backends=["visual"])
    receipt = ExecutionReceipt(
        contract.id,
        contract.backend,
        False,
        "environment-1",
        "environment-1",
        1.0,
        evidence={"dispatched": False},
        error_code=RuntimeErrorCode.EXECUTION_FAILED,
        message="route rejected before dispatch",
    )

    evaluation = _handler().evaluate(
        RecoveryRequest(
            contract=contract,
            receipt=receipt,
            error=RuntimeErrorCode.EXECUTION_FAILED,
            failure_phase="acting",
            state_revision="environment-1",
            task_id="recovery-reroute",
            recovery_count=0,
            tried_backends=(contract.backend,),
        )
    )

    assert evaluation.decision.action == RecoveryAction.REROUTE
    assert evaluation.plan.commands[0].kind == RecoveryCommandKind.REROUTE
    assert evaluation.plan.commands[0].route_ref == "visual"


def test_handler_binds_explicit_accepted_profile_digest_without_forging_strategy_source() -> None:
    request = _request(error=RuntimeErrorCode.STALE_OBSERVATION)
    request = replace(
        request,
        accepted_profile_digest="sha256:accepted-profile",
        accepted_profile_artifact_ids=("artifact-accepted",),
    )

    evaluation = _handler().evaluate(request)

    assert evaluation.plan.profile_digest == "sha256:accepted-profile"
    assert evaluation.plan.commands[0].profile_artifact_id == ""


def test_handler_accepts_only_explicitly_loaded_profile_strategy_provenance() -> None:
    policy = BoundedRecoveryPolicy(
        decision_override=lambda contract, receipt, context, error: RecoveryDecision(
            RecoveryAction.REOBSERVE,
            "accepted generic stale-state policy",
            profile_artifact_id="artifact-accepted",
        )
    )
    request = replace(
        _request(error=RuntimeErrorCode.STALE_OBSERVATION),
        accepted_profile_digest="sha256:accepted-profile",
        accepted_profile_artifact_ids=("artifact-accepted",),
    )

    evaluation = RecoveryHandler(policy, RecoveryCascadeDetector()).evaluate(request)

    assert evaluation.plan.commands[0].profile_artifact_id == "artifact-accepted"
    assert evaluation.decision.profile_artifact_id == "artifact-accepted"


def test_handler_rejects_profile_strategy_provenance_not_in_loaded_profile() -> None:
    policy = BoundedRecoveryPolicy(
        decision_override=lambda contract, receipt, context, error: RecoveryDecision(
            RecoveryAction.REOBSERVE,
            "forged profile strategy",
            profile_artifact_id="artifact-forged",
        )
    )
    request = replace(
        _request(error=RuntimeErrorCode.STALE_OBSERVATION),
        accepted_profile_digest="sha256:accepted-profile",
        accepted_profile_artifact_ids=("artifact-accepted",),
    )

    evaluation = RecoveryHandler(policy, RecoveryCascadeDetector()).evaluate(request)

    assert evaluation.plan.commands[0].kind != RecoveryCommandKind.REOBSERVE
    assert evaluation.plan.commands[0].profile_artifact_id == ""


def test_handler_assesses_copy_and_leaves_authoritative_incident_unchanged() -> None:
    contract = _contract(idempotency_key="save:v1")
    receipt = _receipt(RuntimeErrorCode.EXECUTION_FAILED)
    signature = FailureSignature.from_failure(
        contract,
        receipt,
        phase="acting",
        error_code=RuntimeErrorCode.EXECUTION_FAILED,
        state_revision="environment-1",
    )
    incident = RecoveryIncident(
        "incident-1",
        contract.id,
        contract.snapshot_id,
        signature,
        attempts=[
            RecoveryAttempt(
                index=1,
                signature=signature,
                recovery_action=RecoveryAction.RETRY,
                state_before="environment-1",
            )
        ],
    )
    request = RecoveryRequest(
        contract=contract,
        receipt=receipt,
        error=RuntimeErrorCode.EXECUTION_FAILED,
        failure_phase="acting",
        state_revision="environment-1",
        task_id="recovery-task",
        recovery_count=1,
        tried_backends=("portable-web",),
        incident=incident,
    )

    evaluation = _handler().evaluate(request)

    assert evaluation.continues_open_incident
    assert evaluation.assessment.should_abort
    assert evaluation.decision.action == RecoveryAction.ABORT
    assert RecoveryLoopKind.REPEATED_SIGNATURE in evaluation.assessment.findings
    assert incident.attempts[0].outcome == RecoveryAttemptOutcome.PENDING
    assert incident.attempts[0].state_after == ""
    assert incident.symptom_chain == []
    assert incident.findings == []
