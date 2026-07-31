import pytest

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RiskLevel, RuntimeErrorCode
from affordance_runtime.evolution import (
    EvolutionFailureSignature,
    EvolutionRecoveryAction,
    EvolutionRecoveryContext,
    EvolutionRecoveryPolicy,
)
from affordance_runtime.grounding import (
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    RoutePlan,
)
from affordance_runtime.recovery_protocol import RecoveryKind


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
    decision = EvolutionRecoveryPolicy().decide(
        _contract(),
        None,
        EvolutionRecoveryContext(),
        error_code=RuntimeErrorCode.STALE_OBSERVATION,
    )
    assert decision.kind == RecoveryKind.REOBSERVE


def test_recovery_inspects_uncertain_side_effect_before_retry() -> None:
    decision = EvolutionRecoveryPolicy().decide(
        _contract(idempotency_key="save:1"),
        _failed_receipt(),
        EvolutionRecoveryContext(effect_may_have_occurred=True),
    )
    assert decision.kind == RecoveryKind.INSPECT_POST_STATE


def test_recovery_retries_only_idempotent_contract() -> None:
    policy = EvolutionRecoveryPolicy()
    assert (
        policy.decide(
            _contract(idempotency_key="save:1"),
            _failed_receipt(),
            EvolutionRecoveryContext(),
        ).kind
        == RecoveryKind.RETRY_IDEMPOTENT
    )
    assert (
        policy.decide(
            _contract(risk=RiskLevel.IRREVERSIBLE, idempotency_key="save:1"),
            _failed_receipt(),
            EvolutionRecoveryContext(),
        ).kind
        == EvolutionRecoveryAction.ABORT
    )


def test_recovery_uses_declared_fallback_after_retry_budget() -> None:
    decision = EvolutionRecoveryPolicy().decide(
        _contract(fallback_backends=["visual"]),
        _failed_receipt(),
        EvolutionRecoveryContext(attempt=1, tried_backends=["dom"]),
    )
    assert decision.kind == RecoveryKind.REROUTE
    assert decision.route_ref == "visual"


def test_recovery_context_tried_backends_is_immutable_from_source_list() -> None:
    tried_backends = ["dom"]

    context = EvolutionRecoveryContext(tried_backends=tried_backends)
    tried_backends.append("visual")

    assert context.tried_backends == ("dom",)
    with pytest.raises(TypeError):
        context.tried_backends[0] = "visual"  # type: ignore[index]


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
    decision = EvolutionRecoveryPolicy().decide(
        _contract(
            grounding_candidate=selected,
            route_plan=RoutePlan("semantic:save", selected, (alternative,)),
            idempotency_key="save:1",
        ),
        _failed_receipt(),
        EvolutionRecoveryContext(),
    )

    assert decision.kind == RecoveryKind.REROUTE
    assert decision.route_ref == "browsergym"


def test_failure_signature_is_stable_without_debug_revision_by_default() -> None:
    signature = EvolutionFailureSignature(
        "acting",
        "timeout <n>",
        "execution_failed",
        "click",
        "dom",
        "target",
        "",
        "rev",
    )
    changed_revision = EvolutionFailureSignature(
        "acting",
        "timeout <n>",
        "execution_failed",
        "click",
        "dom",
        "target",
        "",
        "rev-2",
    )

    assert signature.key() == changed_revision.key()
    assert signature.key(include_revision=True) != changed_revision.key(include_revision=True)
