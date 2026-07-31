import pytest
from pydantic import ValidationError

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailureEnvelope,
    FailurePhase,
    ProposalRejectionContext,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)


def _budgets() -> RemainingRecoveryBudgets:
    return RemainingRecoveryBudgets(
        recoveries=3,
        observations=3,
        replans=3,
        provider_switches=1,
        user_escalations=1,
        timeout_ms=30_000,
        model_calls=3,
        estimated_cost=1.0,
    )


def test_failure_envelope_is_valid_without_proposal_or_contract() -> None:
    failure = make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.TASK_PLANNING,
        failure_class=FailureClass.PLANNING,
        error_code=RuntimeErrorCode.PLANNER_FAILED,
        message="planner did not produce a valid task plan",
        state_version=4,
        task_revision=2,
        plan_version=1,
        active_subgoal_id="subgoal-1",
        remaining_budgets=_budgets(),
    )

    assert FailureEnvelope.model_validate_json(failure.model_dump_json()) == failure
    assert failure.contract_id == ""
    assert failure.proposal_id == ""
    assert failure.effect_status == EffectStatus.NOT_DISPATCHED


def test_semantic_family_excludes_target_backend_and_dynamic_debug_values() -> None:
    first = make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.GROUNDING_BINDING,
        failure_class=FailureClass.GROUNDING,
        error_code="binding_failed",
        message="selector=#save backend=dom target=abc123 failed at 100",
        state_version=1,
        active_subgoal_id="save-settings",
        expected_effect="persist notification preference",
        snapshot_id="snapshot-a",
        debug_context={"backend": "dom", "target": "abc123"},
        remaining_budgets=_budgets(),
    )
    second = make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.GROUNDING_BINDING,
        failure_class=FailureClass.GROUNDING,
        error_code="binding_failed",
        message="selector=#commit backend=visual target=def456 failed at 200",
        state_version=2,
        active_subgoal_id="save-settings",
        expected_effect="persist notification preference",
        snapshot_id="snapshot-b",
        debug_context={"backend": "visual", "target": "def456"},
        remaining_budgets=_budgets(),
    )

    assert first.semantic_family_key == second.semantic_family_key
    assert first.exact_debug_key != second.exact_debug_key


def test_failure_message_is_redacted_and_debug_context_drops_secrets() -> None:
    failure = make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.PROVIDER_CONTEXT,
        failure_class=FailureClass.PROVIDER,
        error_code="provider_failed",
        message="authorization=Bearer-secret api_key=top-secret quota failed",
        state_version=1,
        debug_context={"token": "hidden", "provider": "configured-a"},
        remaining_budgets=_budgets(),
    )

    assert "Bearer-secret" not in failure.message
    assert "top-secret" not in failure.message
    assert "hidden" not in failure.model_dump_json()


def test_effect_status_is_derived_from_dispatch_and_timeout() -> None:
    contract = ActionContract(
        id="contract-1",
        intent="save",
        affordance_id="semantic:save",
        action="activate",
        backend="dom",
        environment_revision="revision-1",
        locator={"backend_handle": "save"},
    )
    receipt = ExecutionReceipt(
        contract.id,
        "dom",
        False,
        "revision-1",
        "revision-1",
        1.0,
        evidence={"dispatched": True},
        error_code=RuntimeErrorCode.EXECUTION_TIMEOUT,
    )
    failure = make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.EXECUTION_UNCERTAIN,
        failure_class=FailureClass.EXECUTION,
        error_code=RuntimeErrorCode.EXECUTION_TIMEOUT,
        message="executor timed out after dispatch",
        state_version=2,
        contract=contract,
        receipt=receipt,
        remaining_budgets=_budgets(),
    )

    assert failure.effect_status == EffectStatus.MAY_HAVE_OCCURRED


def test_pre_execution_failure_cannot_claim_an_external_effect() -> None:
    valid = make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
        error_code="planner_failed",
        message="planner failed",
        state_version=1,
        remaining_budgets=_budgets(),
    )
    with pytest.raises(ValidationError, match="cannot claim"):
        FailureEnvelope.model_validate(
            {
                **valid.model_dump(),
                "effect_status": EffectStatus.MAY_HAVE_OCCURRED,
            }
        )


def test_proposal_rejection_context_is_typed_and_phase_bound() -> None:
    rejection = ProposalRejectionContext(
        code="target_out_of_scope",
        reason_code="relational_evidence_not_proven",
        semantic_target_id="semantic:wrong-target",
    )
    failure = make_failure_envelope(
        run_id="run-1",
        phase=FailurePhase.PROPOSAL_VALIDATION,
        failure_class=FailureClass.VALIDATION,
        error_code="planner_proposal_rejected",
        message="target rejected",
        state_version=2,
        proposal_id="proposal-1",
        proposal_rejection=rejection,
        remaining_budgets=_budgets(),
    )

    assert failure.proposal_rejection == rejection
    with pytest.raises(ValidationError, match="proposal validation or grounding binding phase"):
        FailureEnvelope.model_validate(
            {
                **failure.model_dump(),
                "phase": FailurePhase.STEP_PLANNING,
            }
        )


def test_rejection_family_uses_reason_but_not_dynamic_target() -> None:
    def failure(reason_code: str, target_id: str) -> FailureEnvelope:
        return make_failure_envelope(
            run_id="run-1",
            phase=FailurePhase.PROPOSAL_VALIDATION,
            failure_class=FailureClass.VALIDATION,
            error_code="planner_proposal_rejected",
            message="target rejected",
            state_version=2,
            proposal_rejection=ProposalRejectionContext(
                code="target_out_of_scope",
                reason_code=reason_code,
                semantic_target_id=target_id,
            ),
            remaining_budgets=_budgets(),
        )

    first = failure("relational_evidence_not_proven", "semantic:first")
    second = failure("relational_evidence_not_proven", "semantic:second")
    value = failure("semantic_value_not_authorized", "semantic:first")

    assert first.semantic_family_key == second.semantic_family_key
    assert first.exact_debug_key != second.exact_debug_key
    assert first.semantic_family_key != value.semantic_family_key
