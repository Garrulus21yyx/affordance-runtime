import pytest
from pydantic import ValidationError

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailureEnvelope,
    FailurePhase,
    ProposalRejectionContext,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_commands import (
    RecoveryBudgetCost,
    RecoveryChangeDimension,
    RecoveryCommand,
    RecoveryCommandKind,
    RecoveryDelta,
    RecoveryPlanValidator,
    RecoveryReceipt,
    RecoveryReentryPhase,
)
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
    FailureDisposition,
    FailureKind,
    PlannerDeferralKind,
    RecoveryKind,
    classify_failure,
)

ALL_COMMANDS = frozenset(RecoveryCommandKind)


def _decision(
    failure: FailureEnvelope,
    context: RecoverySelectionContext,
    *,
    current_state_version: int = 3,
):
    return RecoveryCoordinator().decide(
        failure,
        classify_failure(
            failure,
            FailureClassificationFacts(
                available_action_count=context.available_action_count,
                user_input_required=context.user_input_required,
            ),
        ),
        context,
        current_state_version=current_state_version,
    )


def _plan(
    failure: FailureEnvelope,
    context: RecoverySelectionContext,
    *,
    current_state_version: int = 3,
):
    return legacy_plan_from_recovery_decision(
        _decision(failure, context, current_state_version=current_state_version),
        failure,
        effect_status=failure.effect_status,
        profile_digest=context.accepted_profile_digest,
        profile_artifact_id=context.preferred_profile_artifact_id,
        gap_ids=context.gap_ids,
    )


def _budgets() -> RemainingRecoveryBudgets:
    return RemainingRecoveryBudgets(
        recoveries=3,
        observations=3,
        replans=3,
        provider_switches=1,
        user_escalations=2,
        timeout_ms=30_000,
        model_calls=3,
        estimated_cost=1.0,
    )


def _failure(
    phase: FailurePhase = FailurePhase.OBSERVATION,
    *,
    failure_class: FailureClass = FailureClass.MISSING_EVIDENCE,
    effect_status: EffectStatus = EffectStatus.NOT_DISPATCHED,
    attempted: tuple[str, ...] = (),
) -> FailureEnvelope:
    return make_failure_envelope(
        run_id="run-1",
        phase=phase,
        failure_class=failure_class,
        error_code="runtime_failure",
        message="generic runtime failure",
        state_version=3,
        active_subgoal_id="subgoal-1",
        expected_effect="complete the current semantic obligation",
        effect_status=effect_status,
        attempted_strategy_ids=attempted,
        remaining_budgets=_budgets(),
    )


def _context(**updates: object) -> RecoverySelectionContext:
    values: dict[str, object] = {
        "available_commands": ALL_COMMANDS,
        "current_attempt_fingerprint": "attempt-1",
        "gap_ids": ("gap-1",),
        "fresh_candidate_id": "candidate-fresh",
        "fresh_route_ref": "route-fresh",
        "configured_provider_id": "provider-configured-b",
        "idempotency_key": "effect:1",
        "compensation_contract_id": "compensation-contract-1",
        "available_action_count": 1,
    }
    values.update(updates)
    return RecoverySelectionContext(**values)


def test_phase_general_coordinator_selects_safe_primary_strategy() -> None:
    expected = {
        FailurePhase.INTAKE: RecoveryCommandKind.CLARIFY_INTENT,
        FailurePhase.OBSERVATION: RecoveryCommandKind.ACTIVE_PERCEPTION,
        FailurePhase.FUSION: RecoveryCommandKind.ACTIVE_PERCEPTION,
        FailurePhase.TASK_PLANNING: RecoveryCommandKind.COMPACT_CONTEXT,
        FailurePhase.STEP_PLANNING: RecoveryCommandKind.ACTIVE_PERCEPTION,
        FailurePhase.PROPOSAL_VALIDATION: RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
        FailurePhase.GROUNDING_BINDING: RecoveryCommandKind.ACTIVE_PERCEPTION,
        FailurePhase.PREFLIGHT: RecoveryCommandKind.ACTIVE_PERCEPTION,
        FailurePhase.EXECUTION_NOT_DISPATCHED: RecoveryCommandKind.REROUTE,
        FailurePhase.VERIFICATION: RecoveryCommandKind.ACTIVE_PERCEPTION,
        FailurePhase.PROVIDER_CONTEXT: RecoveryCommandKind.COMPACT_CONTEXT,
        FailurePhase.SKILL_ACTIVATION: RecoveryCommandKind.REPLAN_STEP,
    }

    for phase, kind in expected.items():
        plan = _plan(_failure(phase), _context(), current_state_version=3)
        assert plan.commands[0].kind == kind


def test_uncertain_effect_is_inspected_before_any_retry_or_reroute() -> None:
    failure = _failure(
        FailurePhase.EXECUTION_UNCERTAIN,
        failure_class=FailureClass.EXECUTION,
        effect_status=EffectStatus.MAY_HAVE_OCCURRED,
    )

    plan = _plan(failure, _context(), current_state_version=3)

    assert plan.commands[0].kind == RecoveryCommandKind.INSPECT_POST_STATE
    assert plan.commands[0].changed_dimensions == (RecoveryChangeDimension.EFFECT_STATUS,)


def test_irreducible_missing_evidence_asks_user_when_no_probe_or_reobserve_exists() -> None:
    failure = _failure(FailurePhase.OBSERVATION)
    plan = _plan(
        failure,
        _context(
            available_commands=frozenset(
                {RecoveryCommandKind.ASK_USER, RecoveryCommandKind.ABORT}
            ),
            gap_ids=(),
            user_question="Which visible control is the intended target?",
        ),
        current_state_version=3,
    )

    assert plan.commands[0].kind == RecoveryCommandKind.ASK_USER
    assert plan.commands[0].reentry_phase == RecoveryReentryPhase.WAITING_USER


def test_planner_deferral_with_action_space_uses_internal_recovery_not_user_or_replan() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "planner_waiting_clarification",
            "message": "planner requested clarification with non-ask action space",
        }
    )

    classification = classify_failure(
        failure,
        FailureClassificationFacts(available_action_count=2),
    )

    assert classification.kind == FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE
    assert classification.disposition == FailureDisposition.RECOVERY
    assert classification.planner_deferral_kind == PlannerDeferralKind.ACTION_SPACE_AVAILABLE

    plan = _plan(failure, _context(), current_state_version=3)

    assert plan.commands[0].kind == RecoveryCommandKind.COMPACT_CONTEXT
    assert plan.commands[0].kind not in {
        RecoveryCommandKind.ASK_USER,
        RecoveryCommandKind.REPLAN_STEP,
        RecoveryCommandKind.REPLAN_TASK,
    }


def test_planner_deferral_does_not_default_to_ask_user_when_only_user_is_available() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "planner_waiting_clarification",
            "message": "planner requested clarification with non-ask action space",
        }
    )

    plan = _plan(
        failure,
        _context(
            available_commands=frozenset(
                {RecoveryCommandKind.ASK_USER, RecoveryCommandKind.ABORT}
            ),
            available_action_count=0,
        ),
        current_state_version=3,
    )

    assert plan.commands[0].kind == RecoveryCommandKind.ABORT


def test_planner_deferral_without_typed_action_space_fails_closed_unknown() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "planner_waiting_clarification",
            "message": "planner requested clarification but action space was not classified",
        }
    )

    classification = classify_failure(failure)

    assert classification.kind == FailureKind.UNKNOWN
    assert classification.planner_deferral_kind == PlannerDeferralKind.UNKNOWN
    assert RecoveryCoordinator().strategy_order_for_test(
        failure,
        _context(available_action_count=0),
    ) == (RecoveryCommandKind.ABORT,)


def test_user_input_required_clarification_is_not_model_deferral() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "planner_waiting_clarification",
            "message": "planner requested missing user information",
        }
    )

    classification = classify_failure(
        failure,
        FailureClassificationFacts(user_input_required=True),
    )

    assert classification.kind == FailureKind.MISSING_USER_INPUT
    assert classification.disposition == FailureDisposition.USER_INPUT
    assert classification.planner_deferral_kind == PlannerDeferralKind.USER_INPUT_REQUIRED


def test_already_satisfied_entry_requires_typed_rejection_reason_not_message_substring() -> None:
    failure = _failure(
        FailurePhase.PROPOSAL_VALIDATION,
        failure_class=FailureClass.VALIDATION,
    ).model_copy(
        update={
            "error_code": "planner_proposal_rejected",
            "message": "task plan validation: repair [entry_outcome_already_satisfied]",
        }
    )

    assert classify_failure(failure).kind == FailureKind.PLAN_OUTPUT_REJECTED

    typed_failure = failure.model_copy(
        update={
            "proposal_rejection": ProposalRejectionContext(
                code="entry_outcome_already_satisfied",
                reason_code="entry_outcome_already_satisfied",
            )
        }
    )

    classification = classify_failure(typed_failure)

    assert classification.kind == FailureKind.CURRENT_STEP_ALREADY_SATISFIED
    assert classification.disposition == FailureDisposition.PROGRESS_PRECHECK
    order = RecoveryCoordinator().strategy_order_for_test(typed_failure, _context())

    assert RecoveryCommandKind.REPLAN_TASK not in order
    assert RecoveryCommandKind.REPLAN_STEP not in order
    assert RecoveryCommandKind.ASK_USER not in order


def test_recovery_coordinator_decide_returns_canonical_decision() -> None:
    failure = _failure(FailurePhase.OBSERVATION)

    decision = RecoveryCoordinator().decide(
        failure,
        classify_failure(failure),
        _context(),
        current_state_version=3,
    )

    assert decision.kind == RecoveryKind.ACTIVE_PERCEPTION
    assert decision.failure_id == failure.failure_id
    assert decision.based_on_state_version == 3
    assert decision.strategy_key.startswith("strategy:active_perception:")


def test_retry_and_compensation_contracts_reject_unsafe_shortcuts() -> None:
    common = {
        "command_id": "command-1",
        "failure_id": "failure-1",
        "based_on_state_version": 3,
        "strategy_id": "strategy:retry",
        "expected_change": "retry one confirmed absent idempotent effect",
        "changed_dimensions": (RecoveryChangeDimension.OBSERVATION,),
        "preconditions": ("effect is absent",),
        "budget_cost": RecoveryBudgetCost(observations=1, timeout_ms=5_000),
        "timeout_ms": 5_000,
        "risk": RiskLevel.LOW,
        "reentry_phase": RecoveryReentryPhase.PREFLIGHT,
    }
    with pytest.raises(ValidationError, match="idempotency"):
        RecoveryCommand(
            **common,
            kind=RecoveryCommandKind.RETRY_IDEMPOTENT,
            effect_status=EffectStatus.CONFIRMED_NOT_OCCURRED,
        )
    with pytest.raises(ValidationError, match="effect is absent"):
        RecoveryCommand(
            **common,
            kind=RecoveryCommandKind.RETRY_IDEMPOTENT,
            effect_status=EffectStatus.MAY_HAVE_OCCURRED,
            idempotency_key="effect:1",
        )
    with pytest.raises(ValidationError, match="ActionContract"):
        RecoveryCommand(
            **common,
            kind=RecoveryCommandKind.COMPENSATE,
            effect_status=EffectStatus.CONFIRMED_OCCURRED,
        )


def test_validator_rejects_stale_unavailable_overbudget_and_unaccepted_profile() -> None:
    failure = _failure(FailurePhase.TASK_PLANNING)
    plan = _plan(failure, _context(), current_state_version=3)
    validator = RecoveryPlanValidator()

    with pytest.raises(ValueError, match="stale"):
        validator.validate(
            plan,
            failure,
            current_state_version=4,
            available_commands=ALL_COMMANDS,
        )
    with pytest.raises(ValueError, match="no owning"):
        validator.validate(
            plan,
            failure,
            current_state_version=3,
            available_commands=frozenset({RecoveryCommandKind.ABORT}),
        )
    no_budget = failure.model_copy(
        update={"remaining_budgets": RemainingRecoveryBudgets()}
    )
    with pytest.raises(ValueError, match="budgets"):
        validator.validate(
            plan,
            no_budget,
            current_state_version=3,
            available_commands=ALL_COMMANDS,
        )
    forged_command = plan.commands[0].model_copy(update={"profile_artifact_id": "artifact-forged"})
    forged_plan = plan.model_copy(update={"commands": (forged_command,)})
    with pytest.raises(ValueError, match="unaccepted"):
        validator.validate(
            forged_plan,
            failure,
            current_state_version=3,
            available_commands=ALL_COMMANDS,
        )


def test_repeated_strategy_changes_or_stops_and_a_b_oscillation_is_not_reentered() -> None:
    first_failure = _failure(FailurePhase.TASK_PLANNING)
    first = _plan(first_failure, _context(), current_state_version=3)
    first_id = first.commands[0].strategy_id
    repeated_failure = first_failure.model_copy(
        update={"attempted_strategy_ids": (first_id,)}
    )

    second = _plan(repeated_failure, _context(), current_state_version=3)

    assert second.commands[0].strategy_id != first_id
    history = (
        RecoveryHistoryItem(repeated_failure.semantic_family_key, first_id, "a", "b"),
        RecoveryHistoryItem(repeated_failure.semantic_family_key, second.commands[0].strategy_id, "b", "a"),
    )
    oscillating = repeated_failure.model_copy(
        update={"attempted_strategy_ids": (second.commands[0].strategy_id,)}
    )
    third = _plan(
        oscillating,
        _context(history=history),
        current_state_version=3,
    )
    assert third.commands[0].strategy_id not in {first_id, second.commands[0].strategy_id}


def test_successful_recovery_requires_non_empty_changed_delta() -> None:
    with pytest.raises(ValidationError, match="non-empty RecoveryDelta"):
        RecoveryReceipt(
            command_id="command-1",
            success=True,
            state_before="state-a",
            state_after="state-b",
            changed_dimensions=(RecoveryChangeDimension.OBSERVATION,),
        )
    with pytest.raises(ValidationError, match="next-attempt fingerprint"):
        RecoveryDelta(
            previous_attempt_fingerprint="same",
            next_attempt_fingerprint="same",
            changed_dimensions=(RecoveryChangeDimension.OBSERVATION,),
            explanation="claimed observation change",
        )
