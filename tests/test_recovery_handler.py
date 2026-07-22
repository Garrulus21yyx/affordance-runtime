from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.recovery import (
    BoundedRecoveryPolicy,
    FailureSignature,
    RecoveryAction,
    RecoveryAttempt,
    RecoveryAttemptOutcome,
    RecoveryCascadeDetector,
    RecoveryIncident,
    RecoveryLoopKind,
)
from affordance_runtime.recovery_handler import RecoveryHandler, RecoveryRequest


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
