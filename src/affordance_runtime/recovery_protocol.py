"""Unified SAR-8 recovery failure taxonomy.

This module is intentionally pure: it classifies an existing
``FailureEnvelope`` into the recovery protocol vocabulary, but does not choose
or execute recovery commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.failure_envelope import FailureClass, FailureEnvelope, FailurePhase


class FailureKind(StrEnum):
    MODEL_DEFERRAL_WITH_ACTION_SPACE = "model_deferral_with_action_space"
    NO_FEASIBLE_ACTION = "no_feasible_action"
    GROUNDING_AMBIGUOUS = "grounding_ambiguous"
    MISSING_USER_INPUT = "missing_user_input"
    PLAN_OUTPUT_REJECTED = "plan_output_rejected"
    INTENT_COMPILATION_REJECTED = "intent_compilation_rejected"
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    CURRENT_STEP_ALREADY_SATISFIED = "current_step_already_satisfied"
    OBSERVATION_INSUFFICIENT = "observation_insufficient"
    PROVIDER_OR_SCHEMA_FAILURE = "provider_or_schema_failure"
    AUTHORITY_BLOCKED = "authority_blocked"
    UNKNOWN = "unknown"


class FailureDisposition(StrEnum):
    RECOVERY = "recovery"
    PROGRESS_PRECHECK = "progress_precheck"
    USER_INPUT = "user_input"
    TERMINAL = "terminal"


class PlannerDeferralKind(StrEnum):
    ACTION_SPACE_AVAILABLE = "action_space_available"
    USER_INPUT_REQUIRED = "user_input_required"
    NO_FEASIBLE_ACTION = "no_feasible_action"
    UNKNOWN = "unknown"


class RecoveryKind(StrEnum):
    REOBSERVE = "reobserve"
    ACTIVE_PERCEPTION = "active_perception"
    COMPACT_CONTEXT = "compact_context"
    SWITCH_PROVIDER = "switch_provider"
    REPAIR_MODEL_SCHEMA = "repair_model_schema"
    CLARIFY_INTENT = "clarify_intent"
    REPLAN_TASK = "replan_task"
    REPLAN_STEP = "replan_step"
    REGROUND = "reground"
    REROUTE = "reroute"
    INSPECT_POST_STATE = "inspect_post_state"
    RETRY_IDEMPOTENT = "retry_idempotent"
    COMPENSATE = "compensate"
    REQUEST_APPROVAL = "request_approval"
    ASK_USER = "ask_user"
    ABORT = "abort"


class RecoveryDimension(StrEnum):
    OBSERVATION = "observation"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    TASK_PLAN = "task_plan"
    STEP_PLAN = "step_plan"
    CANDIDATE = "candidate"
    ROUTE = "route"
    VERIFIER = "verifier"
    PROVIDER = "provider"
    CONTEXT = "context"
    SKILL = "skill"
    USER_INFORMATION = "user_information"
    APPROVAL = "approval"
    EFFECT_STATUS = "effect_status"
    TERMINAL = "terminal"


class RuntimePhase(StrEnum):
    INTAKE = "intake"
    OBSERVING = "observing"
    PLANNING = "planning"
    PREFLIGHT = "preflight"
    VERIFYING = "verifying"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_USER = "waiting_user"
    DEFERRED = "deferred"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass(frozen=True)
class RecoveryBudgetCost:
    recoveries: int = 1
    observations: int = 0
    replans: int = 0
    provider_switches: int = 0
    user_escalations: int = 0
    timeout_ms: int = 0
    model_calls: int = 0
    estimated_cost: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "recoveries",
            "observations",
            "replans",
            "provider_switches",
            "user_escalations",
            "timeout_ms",
            "model_calls",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"recovery budget {field_name} must be non-negative")
        if self.estimated_cost < 0:
            raise ValueError("recovery budget estimated_cost must be non-negative")

    def fits(self, remaining: object) -> bool:
        return (
            self.recoveries <= getattr(remaining, "recoveries")
            and self.observations <= getattr(remaining, "observations")
            and self.replans <= getattr(remaining, "replans")
            and self.provider_switches <= getattr(remaining, "provider_switches")
            and self.user_escalations <= getattr(remaining, "user_escalations")
            and self.timeout_ms <= getattr(remaining, "timeout_ms")
            and self.model_calls <= getattr(remaining, "model_calls")
            and self.estimated_cost <= getattr(remaining, "estimated_cost")
        )


@dataclass(frozen=True)
class FailureClassificationFacts:
    available_action_count: int = 0
    user_input_required: bool = False

    def __post_init__(self) -> None:
        if self.available_action_count < 0:
            raise ValueError("available_action_count must be non-negative")


@dataclass(frozen=True)
class FailureClassification:
    kind: FailureKind
    disposition: FailureDisposition
    reason_code: str
    planner_deferral_kind: PlannerDeferralKind | None = None
    available_action_count: int = 0

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("failure classification reason_code is required")
        if self.available_action_count < 0:
            raise ValueError("available_action_count must be non-negative")


@dataclass(frozen=True)
class RecoveryDecision:
    decision_id: str
    failure_id: str
    based_on_state_version: int
    strategy_key: str
    kind: RecoveryKind
    reason_code: str
    reentry_phase: RuntimePhase
    changed_dimensions: tuple[RecoveryDimension, ...]
    preconditions: tuple[str, ...]
    budget_cost: RecoveryBudgetCost
    candidate_id: str = ""
    route_ref: str = ""
    provider_id: str = ""
    question: str = ""
    idempotency_key: str = ""
    compensation_contract_id: str = ""

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("recovery decision_id is required")
        if not self.failure_id.strip():
            raise ValueError("recovery decision failure_id is required")
        if self.based_on_state_version < 0:
            raise ValueError("recovery decision state version must be non-negative")
        if not self.strategy_key.strip():
            raise ValueError("recovery decision strategy_key is required")
        if not self.reason_code.strip():
            raise ValueError("recovery decision reason_code is required")
        if not self.changed_dimensions:
            raise ValueError("recovery decision changed_dimensions are required")
        if len(self.changed_dimensions) != len(set(self.changed_dimensions)):
            raise ValueError("recovery decision changed_dimensions must be unique")
        if not self.preconditions:
            raise ValueError("recovery decision preconditions are required")
        if self.kind in {RecoveryKind.ASK_USER, RecoveryKind.CLARIFY_INTENT} and not self.question:
            raise ValueError("user-information recovery decision requires a question")
        if self.kind == RecoveryKind.REROUTE and not (self.candidate_id or self.route_ref):
            raise ValueError("reroute recovery decision requires a candidate or route ref")
        if self.kind == RecoveryKind.SWITCH_PROVIDER and not self.provider_id:
            raise ValueError("provider switch recovery decision requires provider_id")
        if self.kind == RecoveryKind.RETRY_IDEMPOTENT and not self.idempotency_key:
            raise ValueError("idempotent retry recovery decision requires idempotency_key")
        if self.kind == RecoveryKind.COMPENSATE and not self.compensation_contract_id:
            raise ValueError("compensation recovery decision requires compensation_contract_id")


def classify_failure(
    failure: FailureEnvelope,
    facts: FailureClassificationFacts | None = None,
) -> FailureClassification:
    """Return typed SAR-8 classification for one failure envelope."""

    error_code = failure.error_code
    if error_code == "planner_waiting_clarification":
        resolved_facts = facts or FailureClassificationFacts()
        if resolved_facts.user_input_required:
            return FailureClassification(
                kind=FailureKind.MISSING_USER_INPUT,
                disposition=FailureDisposition.USER_INPUT,
                reason_code="planner_clarification_user_input_required",
                planner_deferral_kind=PlannerDeferralKind.USER_INPUT_REQUIRED,
                available_action_count=resolved_facts.available_action_count,
            )
        if resolved_facts.available_action_count > 0:
            return FailureClassification(
                kind=FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE,
                disposition=FailureDisposition.RECOVERY,
                reason_code="planner_deferral_with_action_space",
                planner_deferral_kind=PlannerDeferralKind.ACTION_SPACE_AVAILABLE,
                available_action_count=resolved_facts.available_action_count,
            )
        return FailureClassification(
            kind=FailureKind.UNKNOWN,
            disposition=FailureDisposition.TERMINAL,
            reason_code="planner_clarification_without_typed_action_space",
            planner_deferral_kind=PlannerDeferralKind.UNKNOWN,
        )
    proposal_reason = ""
    if failure.proposal_rejection is not None:
        proposal_reason = (
            failure.proposal_rejection.reason_code
            or failure.proposal_rejection.code
        )
    if (
        error_code == "planner_proposal_rejected"
        and proposal_reason == "entry_outcome_already_satisfied"
    ):
        return FailureClassification(
            kind=FailureKind.CURRENT_STEP_ALREADY_SATISFIED,
            disposition=FailureDisposition.PROGRESS_PRECHECK,
            reason_code="current_step_already_satisfied",
        )
    if error_code in {"missing_user_input", "clarification_required"}:
        return _classification(FailureKind.MISSING_USER_INPUT, FailureDisposition.USER_INPUT, error_code)
    if error_code in {"no_feasible_action", "no_action_candidate"}:
        return _classification(FailureKind.NO_FEASIBLE_ACTION, FailureDisposition.RECOVERY, error_code)
    if error_code in {"grounding_ambiguous", "ambiguous_target"}:
        return _classification(FailureKind.GROUNDING_AMBIGUOUS, FailureDisposition.RECOVERY, error_code)
    if failure.failure_class == FailureClass.AUTHORITY:
        return _classification(FailureKind.AUTHORITY_BLOCKED, FailureDisposition.USER_INPUT, "authority_blocked")
    if failure.phase == FailurePhase.INTAKE:
        return _classification(FailureKind.INTENT_COMPILATION_REJECTED, FailureDisposition.USER_INPUT, "intake_failure")
    if failure.phase == FailurePhase.PROPOSAL_VALIDATION:
        return _classification(FailureKind.PLAN_OUTPUT_REJECTED, FailureDisposition.RECOVERY, "proposal_validation_failed")
    if failure.phase in {
        FailurePhase.EXECUTION_NOT_DISPATCHED,
        FailurePhase.EXECUTION_UNCERTAIN,
    }:
        return _classification(FailureKind.EXECUTION_FAILED, FailureDisposition.RECOVERY, "execution_failed")
    if failure.phase == FailurePhase.VERIFICATION:
        return _classification(FailureKind.VERIFICATION_FAILED, FailureDisposition.RECOVERY, "verification_failed")
    if failure.phase in {FailurePhase.OBSERVATION, FailurePhase.FUSION}:
        return _classification(FailureKind.OBSERVATION_INSUFFICIENT, FailureDisposition.RECOVERY, "observation_insufficient")
    if failure.phase == FailurePhase.PROVIDER_CONTEXT:
        return _classification(FailureKind.PROVIDER_OR_SCHEMA_FAILURE, FailureDisposition.RECOVERY, "provider_or_schema_failure")
    if failure.phase == FailurePhase.PREFLIGHT:
        return _classification(FailureKind.NO_FEASIBLE_ACTION, FailureDisposition.RECOVERY, "preflight_no_feasible_action")
    if failure.phase in {
        FailurePhase.TASK_PLANNING,
        FailurePhase.STEP_PLANNING,
        FailurePhase.SKILL_ACTIVATION,
    }:
        return _classification(FailureKind.PLAN_OUTPUT_REJECTED, FailureDisposition.RECOVERY, "planning_output_rejected")
    if failure.phase == FailurePhase.GROUNDING_BINDING:
        return _classification(FailureKind.NO_FEASIBLE_ACTION, FailureDisposition.RECOVERY, "grounding_no_feasible_action")
    return _classification(FailureKind.UNKNOWN, FailureDisposition.TERMINAL, "unknown_failure")


def classify_failure_kind(
    failure: FailureEnvelope,
    facts: FailureClassificationFacts | None = None,
) -> FailureKind:
    """Compatibility wrapper for existing call sites that only need the kind."""

    return classify_failure(failure, facts).kind


def _classification(
    kind: FailureKind,
    disposition: FailureDisposition,
    reason_code: str,
) -> FailureClassification:
    return FailureClassification(
        kind=kind,
        disposition=disposition,
        reason_code=reason_code,
    )
