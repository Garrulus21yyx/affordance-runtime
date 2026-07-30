"""Pure phase-general recovery selection; execution stays in RunCoordinator."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailureEnvelope,
    FailurePhase,
)
from affordance_runtime.recovery_commands import (
    RecoveryChangeDimension,
    RecoveryCommandKind,
    RecoveryPlan,
    RecoveryPlanValidator,
    RecoveryReentryPhase,
)
from affordance_runtime.recovery_decision_compatibility import (
    legacy_plan_from_recovery_decision,
)
from affordance_runtime.recovery_protocol import (
    FailureClassification,
    FailureClassificationFacts,
    FailureKind,
    RecoveryBudgetCost,
    RecoveryDecision,
    RecoveryDimension,
    RecoveryKind,
    RuntimePhase,
    classify_failure,
)


@dataclass(frozen=True)
class RecoveryHistoryItem:
    semantic_family_key: str
    strategy_id: str
    previous_attempt_fingerprint: str
    next_attempt_fingerprint: str


@dataclass(frozen=True)
class RecoverySelectionContext:
    available_commands: frozenset[RecoveryCommandKind]
    current_attempt_fingerprint: str
    gap_ids: tuple[str, ...] = ()
    fresh_candidate_id: str = ""
    fresh_route_ref: str = ""
    configured_provider_id: str = ""
    idempotency_key: str = ""
    compensation_contract_id: str = ""
    user_question: str = "What information or authority is required to continue safely?"
    accepted_profile_digest: str = ""
    accepted_profile_artifact_ids: frozenset[str] = frozenset()
    preferred_profile_commands: tuple[RecoveryCommandKind, ...] = ()
    preferred_profile_artifact_id: str = ""
    history: tuple[RecoveryHistoryItem, ...] = ()
    abort_reentry_phase: RecoveryReentryPhase = RecoveryReentryPhase.ABORTED
    available_action_count: int = 0
    user_input_required: bool = False


@dataclass(frozen=True)
class RecoveryCoordinator:
    """Select and validate one changed strategy without mutating Runtime state."""

    validator: RecoveryPlanValidator = RecoveryPlanValidator()

    def plan(
        self,
        failure: FailureEnvelope,
        context: RecoverySelectionContext,
        *,
        current_state_version: int,
    ) -> RecoveryPlan:
        classification = classify_failure(
            failure,
            FailureClassificationFacts(
                available_action_count=context.available_action_count,
                user_input_required=context.user_input_required,
            ),
        )
        attempted = set(failure.attempted_strategy_ids)
        ordered = _strategy_order(failure, classification, context)
        for kind in ordered:
            strategy_id = _strategy_id(kind, failure.semantic_family_key)
            if strategy_id in attempted:
                continue
            if _would_oscillate(context.history, failure.semantic_family_key, strategy_id):
                continue
            decision = _decision_for(
                kind,
                failure,
                classification,
                context,
                current_state_version=current_state_version,
                strategy_id=strategy_id,
            )
            if decision is None or not decision.budget_cost.fits(failure.remaining_budgets):
                continue
            plan = legacy_plan_from_recovery_decision(
                decision,
                failure,
                effect_status=failure.effect_status,
                profile_digest=context.accepted_profile_digest,
                profile_artifact_id=(
                    context.preferred_profile_artifact_id
                    if kind in context.preferred_profile_commands
                    else ""
                ),
                gap_ids=context.gap_ids,
            )
            try:
                return self.validator.validate(
                    plan,
                    failure,
                    current_state_version=current_state_version,
                    available_commands=context.available_commands,
                    accepted_profile_artifact_ids=context.accepted_profile_artifact_ids,
                )
            except ValueError:
                continue
        raise ValueError("no safe changed recovery strategy is available")

    def decide(
        self,
        failure: FailureEnvelope,
        classification: FailureClassification,
        context: RecoverySelectionContext,
        *,
        current_state_version: int,
    ) -> RecoveryDecision:
        attempted = set(failure.attempted_strategy_ids)
        ordered = _strategy_order(failure, classification, context)
        for kind in ordered:
            strategy_id = _strategy_id(kind, failure.semantic_family_key)
            if strategy_id in attempted:
                continue
            if _would_oscillate(context.history, failure.semantic_family_key, strategy_id):
                continue
            decision = _decision_for(
                kind,
                failure,
                classification,
                context,
                current_state_version=current_state_version,
                strategy_id=strategy_id,
            )
            if decision is None:
                continue
            if not decision.budget_cost.fits(failure.remaining_budgets):
                continue
            return decision
        raise ValueError("no safe changed recovery strategy is available")

    def strategy_order_for_test(
        self,
        failure: FailureEnvelope,
        context: RecoverySelectionContext,
    ) -> tuple[RecoveryCommandKind, ...]:
        classification = classify_failure(
            failure,
            FailureClassificationFacts(
                available_action_count=context.available_action_count,
                user_input_required=context.user_input_required,
            ),
        )
        return _strategy_order(failure, classification, context)


def _strategy_order(
    failure: FailureEnvelope,
    classification: FailureClassification,
    context: RecoverySelectionContext,
) -> tuple[RecoveryCommandKind, ...]:
    base: tuple[RecoveryCommandKind, ...]
    if not failure.recoverable:
        base = (RecoveryCommandKind.ABORT,)
    elif failure.effect_status in {
        EffectStatus.MAY_HAVE_OCCURRED,
        EffectStatus.IRREVERSIBLE_OR_UNKNOWN,
    }:
        base = (
            RecoveryCommandKind.INSPECT_POST_STATE,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    elif failure.failure_class == FailureClass.AUTHORITY:
        base = (
            RecoveryCommandKind.REQUEST_APPROVAL,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    else:
        base = _strategy_order_for_kind(classification.kind, failure.phase)
    profile = tuple(
        item
        for item in context.preferred_profile_commands
        if item in base and item not in {RecoveryCommandKind.RETRY_IDEMPOTENT, RecoveryCommandKind.COMPENSATE}
    )
    if classification.disposition.value == "progress_precheck":
        base = (RecoveryCommandKind.ABORT,)
        profile = ()
    return tuple(dict.fromkeys((*profile, *base)))


def _strategy_order_for_kind(
    kind: FailureKind,
    phase: FailurePhase,
) -> tuple[RecoveryCommandKind, ...]:
    if kind == FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE:
        return (
            RecoveryCommandKind.COMPACT_CONTEXT,
            RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
            RecoveryCommandKind.SWITCH_PROVIDER,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.CURRENT_STEP_ALREADY_SATISFIED:
        return (RecoveryCommandKind.ABORT,)
    if kind == FailureKind.MISSING_USER_INPUT:
        return (RecoveryCommandKind.ASK_USER, RecoveryCommandKind.ABORT)
    if kind == FailureKind.GROUNDING_AMBIGUOUS:
        return (
            RecoveryCommandKind.ACTIVE_PERCEPTION,
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.NO_FEASIBLE_ACTION:
        return (
            RecoveryCommandKind.ACTIVE_PERCEPTION,
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.REROUTE,
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.PLAN_OUTPUT_REJECTED:
        return _planning_strategy_order(phase)
    if kind == FailureKind.INTENT_COMPILATION_REJECTED:
        return (
            RecoveryCommandKind.CLARIFY_INTENT,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.EXECUTION_FAILED:
        return (
            RecoveryCommandKind.REROUTE,
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.RETRY_IDEMPOTENT,
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.VERIFICATION_FAILED:
        return (
            RecoveryCommandKind.ACTIVE_PERCEPTION,
            RecoveryCommandKind.REPLAN_STEP,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.OBSERVATION_INSUFFICIENT:
        return (
            RecoveryCommandKind.ACTIVE_PERCEPTION,
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.PROVIDER_OR_SCHEMA_FAILURE:
        return (
            RecoveryCommandKind.COMPACT_CONTEXT,
            RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
            RecoveryCommandKind.SWITCH_PROVIDER,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.AUTHORITY_BLOCKED:
        return (
            RecoveryCommandKind.REQUEST_APPROVAL,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if kind == FailureKind.UNKNOWN:
        return (RecoveryCommandKind.ABORT,)
    return _planning_strategy_order(phase)


def _planning_strategy_order(phase: FailurePhase) -> tuple[RecoveryCommandKind, ...]:
    if phase == FailurePhase.TASK_PLANNING:
        return (
            RecoveryCommandKind.COMPACT_CONTEXT,
            RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
            RecoveryCommandKind.SWITCH_PROVIDER,
            RecoveryCommandKind.REPLAN_TASK,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if phase == FailurePhase.STEP_PLANNING:
        return (
            RecoveryCommandKind.ACTIVE_PERCEPTION,
            RecoveryCommandKind.COMPACT_CONTEXT,
            RecoveryCommandKind.REPLAN_STEP,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if phase == FailurePhase.PROPOSAL_VALIDATION:
        return (
            RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
            RecoveryCommandKind.REPLAN_STEP,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    if phase == FailurePhase.SKILL_ACTIVATION:
        return (
            RecoveryCommandKind.REPLAN_STEP,
            RecoveryCommandKind.REPLAN_TASK,
            RecoveryCommandKind.ASK_USER,
            RecoveryCommandKind.ABORT,
        )
    return (RecoveryCommandKind.ABORT,)


def _decision_for(
    kind: RecoveryCommandKind,
    failure: FailureEnvelope,
    classification: FailureClassification,
    context: RecoverySelectionContext,
    *,
    current_state_version: int,
    strategy_id: str,
) -> RecoveryDecision | None:
    if kind not in context.available_commands:
        return None
    shape = _command_shape(kind)
    reentry_phase = (
        context.abort_reentry_phase
        if kind == RecoveryCommandKind.ABORT
        else shape.reentry_phase
    )
    if kind == RecoveryCommandKind.ACTIVE_PERCEPTION:
        if not context.gap_ids:
            return None
    if kind == RecoveryCommandKind.REROUTE:
        if not context.fresh_candidate_id and not context.fresh_route_ref:
            return None
    if kind == RecoveryCommandKind.SWITCH_PROVIDER:
        if not context.configured_provider_id:
            return None
    if kind == RecoveryCommandKind.RETRY_IDEMPOTENT:
        if not context.idempotency_key:
            return None
    if kind == RecoveryCommandKind.COMPENSATE:
        if not context.compensation_contract_id:
            return None
    return RecoveryDecision(
        decision_id=f"recovery-decision-{uuid4().hex}",
        failure_id=failure.failure_id,
        based_on_state_version=current_state_version,
        strategy_key=strategy_id,
        kind=RecoveryKind(kind.value),
        reason_code=classification.reason_code,
        changed_dimensions=tuple(RecoveryDimension(item.value) for item in shape.changed_dimensions),
        preconditions=shape.preconditions,
        budget_cost=shape.budget_cost,
        reentry_phase=RuntimePhase(reentry_phase.value),
        candidate_id=context.fresh_candidate_id if kind == RecoveryCommandKind.REROUTE else "",
        route_ref=context.fresh_route_ref if kind == RecoveryCommandKind.REROUTE else "",
        provider_id=context.configured_provider_id if kind == RecoveryCommandKind.SWITCH_PROVIDER else "",
        question=(
            context.user_question
            if kind in {RecoveryCommandKind.ASK_USER, RecoveryCommandKind.CLARIFY_INTENT}
            else ""
        ),
        idempotency_key=(
            context.idempotency_key
            if kind == RecoveryCommandKind.RETRY_IDEMPOTENT
            else ""
        ),
        compensation_contract_id=(
            context.compensation_contract_id
            if kind == RecoveryCommandKind.COMPENSATE
            else ""
        ),
    )


@dataclass(frozen=True)
class _CommandShape:
    expected_change: str
    changed_dimensions: tuple[RecoveryChangeDimension, ...]
    preconditions: tuple[str, ...]
    budget_cost: RecoveryBudgetCost
    timeout_ms: int
    risk: RiskLevel
    reentry_phase: RecoveryReentryPhase


def _command_shape(kind: RecoveryCommandKind) -> _CommandShape:
    dimension, reentry, observations, replans, provider_switches, user_escalations = {
        RecoveryCommandKind.REOBSERVE: (RecoveryChangeDimension.OBSERVATION, RecoveryReentryPhase.OBSERVING, 1, 0, 0, 0),
        RecoveryCommandKind.ACTIVE_PERCEPTION: (RecoveryChangeDimension.EVIDENCE, RecoveryReentryPhase.OBSERVING, 1, 0, 0, 0),
        RecoveryCommandKind.COMPACT_CONTEXT: (RecoveryChangeDimension.CONTEXT, RecoveryReentryPhase.PLANNING, 0, 1, 0, 0),
        RecoveryCommandKind.SWITCH_PROVIDER: (RecoveryChangeDimension.PROVIDER, RecoveryReentryPhase.PLANNING, 0, 1, 1, 0),
        RecoveryCommandKind.REPAIR_MODEL_SCHEMA: (RecoveryChangeDimension.CONTEXT, RecoveryReentryPhase.PLANNING, 0, 1, 0, 0),
        RecoveryCommandKind.CLARIFY_INTENT: (RecoveryChangeDimension.USER_INFORMATION, RecoveryReentryPhase.WAITING_USER, 0, 0, 0, 1),
        RecoveryCommandKind.REPLAN_TASK: (RecoveryChangeDimension.TASK_PLAN, RecoveryReentryPhase.PLANNING, 0, 1, 0, 0),
        RecoveryCommandKind.REPLAN_STEP: (RecoveryChangeDimension.STEP_PLAN, RecoveryReentryPhase.PLANNING, 0, 1, 0, 0),
        RecoveryCommandKind.REGROUND: (RecoveryChangeDimension.CANDIDATE, RecoveryReentryPhase.OBSERVING, 1, 0, 0, 0),
        RecoveryCommandKind.REROUTE: (RecoveryChangeDimension.ROUTE, RecoveryReentryPhase.PREFLIGHT, 1, 0, 0, 0),
        RecoveryCommandKind.INSPECT_POST_STATE: (RecoveryChangeDimension.EFFECT_STATUS, RecoveryReentryPhase.VERIFYING, 1, 0, 0, 0),
        RecoveryCommandKind.RETRY_IDEMPOTENT: (RecoveryChangeDimension.OBSERVATION, RecoveryReentryPhase.PREFLIGHT, 1, 0, 0, 0),
        RecoveryCommandKind.COMPENSATE: (RecoveryChangeDimension.EFFECT_STATUS, RecoveryReentryPhase.PREFLIGHT, 1, 0, 0, 0),
        RecoveryCommandKind.REQUEST_APPROVAL: (RecoveryChangeDimension.APPROVAL, RecoveryReentryPhase.WAITING_APPROVAL, 0, 0, 0, 1),
        RecoveryCommandKind.ASK_USER: (RecoveryChangeDimension.USER_INFORMATION, RecoveryReentryPhase.WAITING_USER, 0, 0, 0, 1),
        RecoveryCommandKind.ABORT: (RecoveryChangeDimension.TERMINAL, RecoveryReentryPhase.ABORTED, 0, 0, 0, 0),
    }[kind]
    timeout_ms = 5_000 if observations or replans else 0
    return _CommandShape(
        expected_change=f"apply {kind.value} and change {dimension.value}",
        changed_dimensions=(dimension,),
        preconditions=(f"owning port for {kind.value} is available",),
        budget_cost=RecoveryBudgetCost(
            recoveries=0 if kind == RecoveryCommandKind.ABORT else 1,
            observations=observations,
            replans=replans,
            provider_switches=provider_switches,
            user_escalations=user_escalations,
            timeout_ms=timeout_ms,
        ),
        timeout_ms=timeout_ms,
        risk=RiskLevel.LOW,
        reentry_phase=reentry,
    )


def _strategy_id(kind: RecoveryCommandKind, semantic_family_key: str) -> str:
    return f"strategy:{kind.value}:{semantic_family_key.removeprefix('sha256:')[:16]}"


def _would_oscillate(
    history: tuple[RecoveryHistoryItem, ...],
    semantic_family_key: str,
    strategy_id: str,
) -> bool:
    same_family = [item for item in history if item.semantic_family_key == semantic_family_key]
    return (
        len(same_family) >= 2
        and same_family[-2].strategy_id == strategy_id
        and same_family[-1].strategy_id != strategy_id
    )
