"""Typed recovery decisions, receipts, deltas, and hard validation gates."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureEnvelope,
    RemainingRecoveryBudgets,
)
from affordance_runtime.task_intake import StrictModel


class RecoveryCommandKind(StrEnum):
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


class RecoveryChangeDimension(StrEnum):
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


class RecoveryReentryPhase(StrEnum):
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


class RecoveryBudgetCost(StrictModel):
    recoveries: int = Field(default=1, ge=0, le=8)
    observations: int = Field(default=0, ge=0, le=16)
    replans: int = Field(default=0, ge=0, le=16)
    provider_switches: int = Field(default=0, ge=0, le=4)
    user_escalations: int = Field(default=0, ge=0, le=4)
    timeout_ms: int = Field(default=0, ge=0, le=120_000)
    model_calls: int = Field(default=0, ge=0, le=16)
    estimated_cost: float = Field(default=0.0, ge=0.0)

    def fits(self, remaining: RemainingRecoveryBudgets) -> bool:
        return (
            self.recoveries <= remaining.recoveries
            and self.observations <= remaining.observations
            and self.replans <= remaining.replans
            and self.provider_switches <= remaining.provider_switches
            and self.user_escalations <= remaining.user_escalations
            and self.timeout_ms <= remaining.timeout_ms
            and self.model_calls <= remaining.model_calls
            and self.estimated_cost <= remaining.estimated_cost
        )


class RecoveryCommand(StrictModel):
    command_id: str = Field(min_length=1)
    failure_id: str = Field(min_length=1)
    based_on_state_version: int = Field(ge=0)
    strategy_id: str = Field(min_length=1)
    kind: RecoveryCommandKind
    expected_change: str = Field(min_length=1, max_length=500)
    changed_dimensions: tuple[RecoveryChangeDimension, ...] = Field(min_length=1)
    preconditions: tuple[str, ...] = Field(min_length=1)
    budget_cost: RecoveryBudgetCost = Field(default_factory=RecoveryBudgetCost)
    timeout_ms: int = Field(default=5_000, ge=0, le=120_000)
    risk: RiskLevel = RiskLevel.LOW
    reentry_phase: RecoveryReentryPhase
    effect_status: EffectStatus
    gap_ids: tuple[str, ...] = ()
    candidate_id: str = ""
    route_ref: str = ""
    provider_id: str = ""
    question: str = ""
    idempotency_key: str = ""
    compensation_contract_id: str = ""
    profile_artifact_id: str = ""

    @model_validator(mode="after")
    def validate_strategy_boundary(self) -> "RecoveryCommand":
        if len(self.changed_dimensions) != len(set(self.changed_dimensions)):
            raise ValueError("recovery changed dimensions must be unique")
        if self.timeout_ms > self.budget_cost.timeout_ms and self.budget_cost.timeout_ms:
            raise ValueError("recovery command timeout exceeds its declared budget cost")
        if self.kind == RecoveryCommandKind.ACTIVE_PERCEPTION and not self.gap_ids:
            raise ValueError("active perception recovery requires evidence gap ids")
        if self.kind == RecoveryCommandKind.REROUTE:
            if not self.candidate_id and not self.route_ref:
                raise ValueError("reroute requires a fresh candidate or route reference")
            if self.effect_status not in {
                EffectStatus.NOT_DISPATCHED,
                EffectStatus.CONFIRMED_NOT_OCCURRED,
            }:
                raise ValueError("reroute cannot bypass uncertain effect inspection")
        if self.kind == RecoveryCommandKind.RETRY_IDEMPOTENT:
            if not self.idempotency_key:
                raise ValueError("idempotent retry requires explicit idempotency authority")
            if self.effect_status not in {
                EffectStatus.NOT_DISPATCHED,
                EffectStatus.CONFIRMED_NOT_OCCURRED,
            }:
                raise ValueError("retry requires proof that the effect is absent")
        if self.kind == RecoveryCommandKind.INSPECT_POST_STATE and self.effect_status not in {
            EffectStatus.MAY_HAVE_OCCURRED,
            EffectStatus.IRREVERSIBLE_OR_UNKNOWN,
        }:
            raise ValueError("post-state inspection is reserved for uncertain effects")
        if self.kind == RecoveryCommandKind.COMPENSATE:
            if not self.compensation_contract_id:
                raise ValueError("compensation requires an explicit ActionContract reference")
            if self.effect_status != EffectStatus.CONFIRMED_OCCURRED:
                raise ValueError("compensation requires a confirmed prior effect")
        if self.kind in {RecoveryCommandKind.ASK_USER, RecoveryCommandKind.CLARIFY_INTENT}:
            if not self.question:
                raise ValueError("user-information recovery requires an explicit question")
        if self.kind == RecoveryCommandKind.ABORT:
            if self.reentry_phase not in {
                RecoveryReentryPhase.ABORTED,
                RecoveryReentryPhase.FAILED,
                RecoveryReentryPhase.DEFERRED,
            }:
                raise ValueError("abort must declare a terminal or deferred re-entry")
        elif RecoveryChangeDimension.TERMINAL in self.changed_dimensions:
            raise ValueError("non-terminal recovery cannot claim a terminal change")
        return self


class RecoveryPlan(StrictModel):
    plan_id: str = Field(min_length=1)
    failure_id: str = Field(min_length=1)
    based_on_state_version: int = Field(ge=0)
    semantic_family_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    commands: tuple[RecoveryCommand, ...] = Field(min_length=1, max_length=1)
    stop_conditions: tuple[str, ...] = Field(min_length=1)
    profile_digest: str = ""

    @model_validator(mode="after")
    def validate_bindings(self) -> "RecoveryPlan":
        command = self.commands[0]
        if command.failure_id != self.failure_id:
            raise ValueError("recovery command failure does not match its plan")
        if command.based_on_state_version != self.based_on_state_version:
            raise ValueError("recovery command state version does not match its plan")
        return self


class RecoveryDelta(StrictModel):
    previous_attempt_fingerprint: str = Field(min_length=1)
    next_attempt_fingerprint: str = Field(min_length=1)
    changed_dimensions: tuple[RecoveryChangeDimension, ...] = Field(min_length=1)
    new_evidence_refs: tuple[str, ...] = ()
    retired_assumptions: tuple[str, ...] = ()
    new_plan_or_route_ref: str = ""
    explanation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_non_empty_delta(self) -> "RecoveryDelta":
        if self.previous_attempt_fingerprint == self.next_attempt_fingerprint:
            raise ValueError("recovery delta must change the next-attempt fingerprint")
        if len(self.changed_dimensions) != len(set(self.changed_dimensions)):
            raise ValueError("recovery delta dimensions must be unique")
        return self


class RecoveryReceipt(StrictModel):
    command_id: str = Field(min_length=1)
    success: bool
    state_before: str = Field(min_length=1)
    state_after: str = Field(min_length=1)
    changed_dimensions: tuple[RecoveryChangeDimension, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    observation_refs: tuple[str, ...] = ()
    plan_refs: tuple[str, ...] = ()
    route_refs: tuple[str, ...] = ()
    verification_refs: tuple[str, ...] = ()
    error_code: str = ""
    latency_ms: float = Field(default=0.0, ge=0.0)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    delta: RecoveryDelta | None = None

    @model_validator(mode="after")
    def validate_receipt_delta(self) -> "RecoveryReceipt":
        if self.success and self.delta is None:
            raise ValueError("successful recovery requires a non-empty RecoveryDelta")
        if self.success and not self.changed_dimensions:
            raise ValueError("successful recovery receipt must declare changed dimensions")
        if self.delta is not None and set(self.changed_dimensions) != set(self.delta.changed_dimensions):
            raise ValueError("recovery receipt and delta dimensions must match")
        if self.success and self.error_code:
            raise ValueError("successful recovery cannot carry an error code")
        return self


class RecoveryPlanValidator:
    """Reject stale, unsafe, unavailable, profile-forged, or no-op recovery."""

    def validate(
        self,
        plan: RecoveryPlan,
        failure: FailureEnvelope,
        *,
        current_state_version: int,
        available_commands: frozenset[RecoveryCommandKind],
        accepted_profile_artifact_ids: frozenset[str] = frozenset(),
    ) -> RecoveryPlan:
        command = plan.commands[0]
        if plan.failure_id != failure.failure_id:
            raise ValueError("recovery plan is bound to a different failure")
        if plan.semantic_family_key != failure.semantic_family_key:
            raise ValueError("recovery plan semantic family is stale or mismatched")
        if plan.based_on_state_version != current_state_version:
            raise ValueError("recovery plan is stale for the current state")
        if not failure.recoverable and command.kind != RecoveryCommandKind.ABORT:
            raise ValueError("non-recoverable failure permits only abort")
        if command.kind not in available_commands:
            raise ValueError("recovery command has no owning Runtime capability")
        if not command.budget_cost.fits(failure.remaining_budgets):
            raise ValueError("recovery command exceeds remaining budgets")
        if command.strategy_id in failure.attempted_strategy_ids:
            raise ValueError("recovery strategy was already attempted for this incident")
        if command.profile_artifact_id and command.profile_artifact_id not in accepted_profile_artifact_ids:
            raise ValueError("recovery strategy references an unaccepted profile artifact")
        return plan
