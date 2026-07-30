import pytest

from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailureEnvelope,
    FailurePhase,
    ProposalRejectionContext,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.recovery_coordinator import (
    RecoveryCoordinator,
    RecoveryHistoryItem,
    RecoverySelectionContext,
)
from affordance_runtime.recovery_protocol import (
    FailureClassificationFacts,
    FailureKind,
    FailureOwner,
    PlannerDeferralKind,
    RecoveryBudgetCost,
    RecoveryDecision,
    RecoveryDimension,
    RecoveryKind,
    RuntimePhase,
    classify_failure,
)

ALL_COMMANDS = frozenset(RecoveryKind)


def _decision(
    failure: FailureEnvelope,
    context: RecoverySelectionContext,
    *,
    current_state_version: int = 3,
) -> RecoveryDecision:
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
        FailurePhase.OBSERVATION: RecoveryKind.ACTIVE_PERCEPTION,
        FailurePhase.FUSION: RecoveryKind.ACTIVE_PERCEPTION,
        FailurePhase.GROUNDING_BINDING: RecoveryKind.ACTIVE_PERCEPTION,
        FailurePhase.PREFLIGHT: RecoveryKind.ACTIVE_PERCEPTION,
        FailurePhase.EXECUTION_NOT_DISPATCHED: RecoveryKind.REROUTE,
        FailurePhase.VERIFICATION: RecoveryKind.ACTIVE_PERCEPTION,
        FailurePhase.PROVIDER_CONTEXT: RecoveryKind.COMPACT_CONTEXT,
    }

    for phase, kind in expected.items():
        decision = _decision(_failure(phase), _context(), current_state_version=3)
        assert decision.kind == kind


def test_recovery_coordinator_rejects_non_runtime_failure_owners() -> None:
    for phase in (
        FailurePhase.INTAKE,
        FailurePhase.TASK_PLANNING,
        FailurePhase.STEP_PLANNING,
        FailurePhase.PROPOSAL_VALIDATION,
        FailurePhase.SKILL_ACTIVATION,
    ):
        failure = _failure(phase)
        classification = classify_failure(failure)

        assert classification.owner != FailureOwner.RUNTIME_RECOVERY
        with pytest.raises(ValueError, match="RecoveryCoordinator only selects Runtime-owned"):
            RecoveryCoordinator().decide(
                failure,
                classification,
                _context(),
                current_state_version=3,
            )


def test_uncertain_effect_is_inspected_before_any_retry_or_reroute() -> None:
    failure = _failure(
        FailurePhase.EXECUTION_UNCERTAIN,
        failure_class=FailureClass.EXECUTION,
        effect_status=EffectStatus.MAY_HAVE_OCCURRED,
    )

    decision = _decision(failure, _context(), current_state_version=3)

    assert decision.kind == RecoveryKind.INSPECT_POST_STATE
    assert decision.changed_dimensions == (RecoveryDimension.EFFECT_STATUS,)


def test_irreducible_runtime_missing_evidence_aborts_when_no_probe_or_reobserve_exists() -> None:
    failure = _failure(FailurePhase.OBSERVATION)
    decision = _decision(
        failure,
        _context(
            available_commands=frozenset({RecoveryKind.ASK_USER, RecoveryKind.ABORT}),
            gap_ids=(),
            user_question="Which visible control is the intended target?",
        ),
        current_state_version=3,
    )

    assert decision.kind == RecoveryKind.ABORT
    assert decision.reentry_phase == RuntimePhase.ABORTED


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
    assert classification.owner == FailureOwner.STEP_PLANNER
    assert classification.planner_deferral_kind == PlannerDeferralKind.ACTION_SPACE_AVAILABLE

    with pytest.raises(ValueError, match="RecoveryCoordinator only selects Runtime-owned"):
        _decision(failure, _context(), current_state_version=3)


def test_failure_classification_routes_model_deferral_to_step_planner_owner() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "planner_waiting_clarification",
            "message": "planner requested clarification with typed choices available",
        }
    )

    classification = classify_failure(
        failure,
        FailureClassificationFacts(available_action_count=2),
    )

    assert classification.owner == FailureOwner.STEP_PLANNER
    assert classification.planner_deferral_kind == PlannerDeferralKind.ACTION_SPACE_AVAILABLE


def test_planner_deferral_does_not_default_to_ask_user_when_action_space_is_unknown() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "planner_waiting_clarification",
            "message": "planner requested clarification with non-ask action space",
        }
    )

    with pytest.raises(ValueError, match="RecoveryCoordinator only selects Runtime-owned"):
        _decision(
            failure,
            _context(
                available_commands=frozenset({RecoveryKind.ASK_USER, RecoveryKind.ABORT}),
                available_action_count=0,
            ),
            current_state_version=3,
        )


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
    ) == (RecoveryKind.ABORT,)


def test_no_feasible_action_choice_reason_classifies_as_no_feasible_action() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "no_feasible_action_choice",
            "message": "runtime action choice builder found no executable choice",
        }
    )

    classification = classify_failure(failure)

    assert classification.kind == FailureKind.NO_FEASIBLE_ACTION
    assert classification.owner == FailureOwner.RUNTIME_RECOVERY
    assert classification.reason_code == "no_feasible_action_choice"


def test_legacy_decision_without_proposal_fails_closed_unknown() -> None:
    failure = _failure(
        FailurePhase.STEP_PLANNING,
        failure_class=FailureClass.PLANNING,
    ).model_copy(
        update={
            "error_code": "legacy_decision_without_proposal",
            "message": "legacy planner returned neither a contract nor a result",
        }
    )

    classification = classify_failure(failure)

    assert classification.kind == FailureKind.UNKNOWN
    assert classification.owner == FailureOwner.TERMINAL
    assert classification.reason_code == "legacy_decision_without_proposal"
    assert RecoveryCoordinator().strategy_order_for_test(
        failure,
        _context(available_action_count=0),
    ) == (RecoveryKind.ABORT,)


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
    assert classification.owner == FailureOwner.USER
    assert classification.planner_deferral_kind == PlannerDeferralKind.USER_INPUT_REQUIRED


def test_user_input_required_clarification_routes_to_user_owner() -> None:
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

    assert classification.owner == FailureOwner.USER


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
    assert classification.owner == FailureOwner.PROGRESS
    order = RecoveryCoordinator().strategy_order_for_test(typed_failure, _context())

    assert RecoveryKind.REPLAN_TASK not in order
    assert RecoveryKind.REPLAN_STEP not in order
    assert RecoveryKind.ASK_USER not in order


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


def test_retry_and_compensation_decisions_reject_unsafe_shortcuts() -> None:
    common = {
        "decision_id": "decision-1",
        "failure_id": "failure-1",
        "based_on_state_version": 3,
        "strategy_key": "strategy:retry",
        "reason_code": "runtime_failure",
        "changed_dimensions": (RecoveryDimension.OBSERVATION,),
        "preconditions": ("effect is absent",),
        "budget_cost": RecoveryBudgetCost(observations=1, timeout_ms=5_000),
        "reentry_phase": RuntimePhase.PREFLIGHT,
    }
    with pytest.raises(ValueError, match="idempotent retry"):
        RecoveryDecision(**common, kind=RecoveryKind.RETRY_IDEMPOTENT)
    with pytest.raises(ValueError, match="compensation"):
        RecoveryDecision(**common, kind=RecoveryKind.COMPENSATE)


def test_coordinator_skips_stale_unavailable_overbudget_and_unaccepted_profile() -> None:
    failure = _failure(FailurePhase.OBSERVATION)

    unavailable = _decision(
        failure,
        _context(available_commands=frozenset({RecoveryKind.ABORT})),
        current_state_version=3,
    )
    assert unavailable.kind == RecoveryKind.ABORT

    no_budget = failure.model_copy(
        update={"remaining_budgets": RemainingRecoveryBudgets()}
    )
    overbudget = _decision(no_budget, _context(), current_state_version=3)
    assert overbudget.kind == RecoveryKind.ABORT

    decision = _decision(failure, _context(), current_state_version=7)
    assert decision.based_on_state_version == 7


def test_repeated_strategy_changes_or_stops_and_a_b_oscillation_is_not_reentered() -> None:
    first_failure = _failure(FailurePhase.OBSERVATION)
    first = _decision(first_failure, _context(), current_state_version=3)
    first_id = first.strategy_key
    repeated_failure = first_failure.model_copy(
        update={"attempted_strategy_ids": (first_id,)}
    )

    second = _decision(repeated_failure, _context(), current_state_version=3)

    assert second.strategy_key != first_id
    history = (
        RecoveryHistoryItem(repeated_failure.semantic_family_key, first_id, "a", "b"),
        RecoveryHistoryItem(repeated_failure.semantic_family_key, second.strategy_key, "b", "a"),
    )
    oscillating = repeated_failure.model_copy(
        update={"attempted_strategy_ids": (second.strategy_key,)}
    )
    third = _decision(
        oscillating,
        _context(history=history),
        current_state_version=3,
    )
    assert third.strategy_key not in {first_id, second.strategy_key}


def test_recovery_outcome_requires_non_empty_changed_dimensions() -> None:
    from affordance_runtime.recovery_protocol import RecoveryOutcome

    with pytest.raises(ValueError, match="changed_dimensions"):
        RecoveryOutcome(
            decision_id="decision-1",
            failure_id="failure-1",
            success=True,
            changed_dimensions=(),
            next_phase=RuntimePhase.OBSERVING,
        )
