from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RiskLevel, RuntimeErrorCode
from affordance_runtime.recovery import BoundedRecoveryPolicy, RecoveryAction, RecoveryContext


def _contract(**overrides: object) -> ActionContract:
    values = {
        "id": "contract_1",
        "intent": "save",
        "affordance_id": "save",
        "action": "click",
        "backend": "dom",
        "environment_revision": "rev-1",
        "locator": {"selector": "#save"},
    }
    values.update(overrides)
    return ActionContract(**values)  # type: ignore[arg-type]


def _failed_receipt(error: RuntimeErrorCode = RuntimeErrorCode.EXECUTION_FAILED) -> ExecutionReceipt:
    return ExecutionReceipt("contract_1", "dom", False, "rev-1", "rev-1", 1.0, error_code=error)


def test_recovery_reobserves_stale_contract() -> None:
    decision = BoundedRecoveryPolicy().decide(
        _contract(),
        None,
        RecoveryContext(),
        error_code=RuntimeErrorCode.STALE_OBSERVATION,
    )
    assert decision.action == RecoveryAction.REOBSERVE


def test_recovery_inspects_uncertain_side_effect_before_retry() -> None:
    decision = BoundedRecoveryPolicy().decide(
        _contract(idempotency_key="save:1"),
        _failed_receipt(),
        RecoveryContext(effect_may_have_occurred=True),
    )
    assert decision.action == RecoveryAction.VERIFY_STATE


def test_recovery_retries_only_idempotent_contract() -> None:
    policy = BoundedRecoveryPolicy()
    assert policy.decide(
        _contract(idempotency_key="save:1"),
        _failed_receipt(),
        RecoveryContext(),
    ).action == RecoveryAction.RETRY
    assert policy.decide(
        _contract(risk=RiskLevel.IRREVERSIBLE, idempotency_key="save:1"),
        _failed_receipt(),
        RecoveryContext(),
    ).action == RecoveryAction.ABORT


def test_recovery_uses_declared_fallback_after_retry_budget() -> None:
    decision = BoundedRecoveryPolicy().decide(
        _contract(fallback_backends=["visual"]),
        _failed_receipt(),
        RecoveryContext(attempt=1, tried_backends=["dom"]),
    )
    assert decision.action == RecoveryAction.REROUTE
    assert decision.backend == "visual"
