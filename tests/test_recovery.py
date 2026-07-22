from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RiskLevel, RuntimeErrorCode
from affordance_runtime.grounding import (
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    RoutePlan,
)
from affordance_runtime.recovery import (
    BoundedRecoveryPolicy,
    FailureSignature,
    RecoveryAction,
    RecoveryAttempt,
    RecoveryAttemptOutcome,
    RecoveryCascadeDetector,
    RecoveryContext,
    RecoveryIncident,
    RecoveryLoopKind,
)


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


def test_recovery_prefers_fresh_grounding_candidate_over_blind_retry() -> None:
    selected = GroundingCandidate(
        "candidate:dom:save",
        "semantic:save",
        GroundingSource.DOM,
        DomGroundingPayload(backend_handle="save-handle"),
        "dom",
        "snapshot-1",
        "rev-1",
        "page-1",
        "fp-dom",
        frozenset({"activate"}),
        frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}),
    )
    alternative = GroundingCandidate(
        "candidate:accessibility:save",
        "semantic:save",
        GroundingSource.ACCESSIBILITY,
        DomGroundingPayload(selector="role=button[name='Save']"),
        "browsergym",
        "snapshot-1",
        "rev-1",
        "page-1",
        "fp-a11y",
        frozenset({"activate"}),
        frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}),
    )
    decision = BoundedRecoveryPolicy().decide(
        _contract(
            grounding_candidate=selected,
            route_plan=RoutePlan("semantic:save", selected, (alternative,)),
            idempotency_key="save:1",
        ),
        _failed_receipt(),
        RecoveryContext(),
    )

    assert decision.action == RecoveryAction.REROUTE
    assert decision.backend == "browsergym"
    assert "fresh route" in decision.reason


def _signature(name: str, revision: str = "rev-1") -> FailureSignature:
    return FailureSignature("acting", name, "execution_failed", "click", "dom", "target", "", revision)


def test_cascade_detector_stops_repeated_no_progress_signature() -> None:
    signature = _signature("timeout")
    incident = RecoveryIncident("incident-1", "contract", "snapshot", signature)
    incident.attempts.append(
        RecoveryAttempt(
            1,
            signature,
            RecoveryAction.RETRY,
            "rev-1",
            "rev-1",
            RecoveryAttemptOutcome.FAILED,
            idempotency_key="save:1",
        )
    )

    assessment = RecoveryCascadeDetector().assess(
        incident,
        signature,
        fallbacks_remaining=False,
        effect_may_have_occurred=False,
        idempotency_key="save:1",
    )

    assert assessment.should_abort
    assert RecoveryLoopKind.REPEATED_SIGNATURE in assessment.findings
    assert RecoveryLoopKind.NO_PROGRESS in assessment.findings


def test_cascade_detector_recognizes_a_b_oscillation() -> None:
    first = _signature("a", "rev-a")
    second = _signature("b", "rev-b")
    incident = RecoveryIncident("incident-2", "contract", "snapshot", first)
    incident.attempts = [
        RecoveryAttempt(1, first, RecoveryAction.REROUTE, "rev-a", "rev-b", RecoveryAttemptOutcome.FAILED),
        RecoveryAttempt(2, second, RecoveryAction.REROUTE, "rev-b", "rev-a", RecoveryAttemptOutcome.FAILED),
    ]

    assessment = RecoveryCascadeDetector().assess(
        incident,
        first,
        fallbacks_remaining=True,
        effect_may_have_occurred=False,
        idempotency_key="",
    )

    assert assessment.should_abort
    assert RecoveryLoopKind.AB_OSCILLATION in assessment.findings
