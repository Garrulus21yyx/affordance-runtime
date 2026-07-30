"""Pure phase-general recovery selection; execution stays in RunCoordinator."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailureEnvelope,
    FailurePhase,
)
from affordance_runtime.recovery_protocol import (
    FailureClassification,
    FailureClassificationFacts,
    FailureKind,
    FailureOwner,
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
    available_commands: frozenset[RecoveryKind]
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
    preferred_profile_commands: tuple[RecoveryKind, ...] = ()
    preferred_profile_artifact_id: str = ""
    history: tuple[RecoveryHistoryItem, ...] = ()
    abort_reentry_phase: RuntimePhase = RuntimePhase.ABORTED
    available_action_count: int = 0
    user_input_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "available_commands",
            frozenset(RecoveryKind(str(item)) for item in self.available_commands),
        )
        object.__setattr__(
            self,
            "preferred_profile_commands",
            tuple(RecoveryKind(str(item)) for item in self.preferred_profile_commands),
        )
        object.__setattr__(self, "abort_reentry_phase", RuntimePhase(str(self.abort_reentry_phase)))


@dataclass(frozen=True)
class RecoveryCoordinator:
    """Select and validate one changed strategy without mutating Runtime state."""

    def decide(
        self,
        failure: FailureEnvelope,
        classification: FailureClassification,
        context: RecoverySelectionContext,
        *,
        current_state_version: int,
    ) -> RecoveryDecision:
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            raise ValueError("RecoveryCoordinator only selects Runtime-owned recovery decisions")
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
    ) -> tuple[RecoveryKind, ...]:
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
) -> tuple[RecoveryKind, ...]:
    base: tuple[RecoveryKind, ...]
    if not failure.recoverable:
        base = (RecoveryKind.ABORT,)
    elif failure.effect_status in {
        EffectStatus.MAY_HAVE_OCCURRED,
        EffectStatus.IRREVERSIBLE_OR_UNKNOWN,
    }:
        base = (
            RecoveryKind.INSPECT_POST_STATE,
            RecoveryKind.ABORT,
        )
    elif failure.failure_class == FailureClass.AUTHORITY:
        base = (RecoveryKind.ABORT,)
    else:
        base = _strategy_order_for_kind(classification.kind, failure.phase)
    profile = tuple(
        item
        for item in context.preferred_profile_commands
        if item in base and item not in {RecoveryKind.RETRY_IDEMPOTENT, RecoveryKind.COMPENSATE}
    )
    if classification.owner == FailureOwner.PROGRESS:
        base = (RecoveryKind.ABORT,)
        profile = ()
    return tuple(dict.fromkeys((*profile, *base)))


def _strategy_order_for_kind(
    kind: FailureKind,
    phase: FailurePhase,
) -> tuple[RecoveryKind, ...]:
    if kind == FailureKind.MODEL_DEFERRAL_WITH_ACTION_SPACE:
        return (
            RecoveryKind.COMPACT_CONTEXT,
            RecoveryKind.REPAIR_MODEL_SCHEMA,
            RecoveryKind.SWITCH_PROVIDER,
            RecoveryKind.ABORT,
        )
    if kind == FailureKind.CURRENT_STEP_ALREADY_SATISFIED:
        return (RecoveryKind.ABORT,)
    if kind == FailureKind.MISSING_USER_INPUT:
        return (RecoveryKind.ABORT,)
    if kind == FailureKind.GROUNDING_AMBIGUOUS:
        return (
            RecoveryKind.ACTIVE_PERCEPTION,
            RecoveryKind.REGROUND,
            RecoveryKind.REOBSERVE,
            RecoveryKind.ABORT,
        )
    if kind == FailureKind.NO_FEASIBLE_ACTION:
        return (
            RecoveryKind.ACTIVE_PERCEPTION,
            RecoveryKind.REGROUND,
            RecoveryKind.REROUTE,
            RecoveryKind.REOBSERVE,
            RecoveryKind.ABORT,
        )
    if kind == FailureKind.PLAN_OUTPUT_REJECTED:
        return _planning_strategy_order(phase)
    if kind == FailureKind.INTENT_COMPILATION_REJECTED:
        return (RecoveryKind.ABORT,)
    if kind == FailureKind.EXECUTION_FAILED:
        return (
            RecoveryKind.REROUTE,
            RecoveryKind.REGROUND,
            RecoveryKind.RETRY_IDEMPOTENT,
            RecoveryKind.REOBSERVE,
            RecoveryKind.ABORT,
        )
    if kind == FailureKind.VERIFICATION_FAILED:
        return (
            RecoveryKind.ACTIVE_PERCEPTION,
            RecoveryKind.ABORT,
        )
    if kind == FailureKind.OBSERVATION_INSUFFICIENT:
        return (
            RecoveryKind.ACTIVE_PERCEPTION,
            RecoveryKind.REOBSERVE,
            RecoveryKind.ABORT,
        )
    if kind == FailureKind.PROVIDER_OR_SCHEMA_FAILURE:
        return (
            RecoveryKind.COMPACT_CONTEXT,
            RecoveryKind.REPAIR_MODEL_SCHEMA,
            RecoveryKind.SWITCH_PROVIDER,
            RecoveryKind.ABORT,
        )
    if kind == FailureKind.AUTHORITY_BLOCKED:
        return (RecoveryKind.ABORT,)
    if kind == FailureKind.UNKNOWN:
        return (RecoveryKind.ABORT,)
    return _planning_strategy_order(phase)


def _planning_strategy_order(phase: FailurePhase) -> tuple[RecoveryKind, ...]:
    if phase == FailurePhase.TASK_PLANNING:
        return (
            RecoveryKind.COMPACT_CONTEXT,
            RecoveryKind.REPAIR_MODEL_SCHEMA,
            RecoveryKind.SWITCH_PROVIDER,
            RecoveryKind.ABORT,
        )
    if phase == FailurePhase.STEP_PLANNING:
        return (
            RecoveryKind.ACTIVE_PERCEPTION,
            RecoveryKind.COMPACT_CONTEXT,
            RecoveryKind.ABORT,
        )
    if phase == FailurePhase.PROPOSAL_VALIDATION:
        return (
            RecoveryKind.REPAIR_MODEL_SCHEMA,
            RecoveryKind.ABORT,
        )
    if phase == FailurePhase.SKILL_ACTIVATION:
        return (RecoveryKind.ABORT,)
    return (RecoveryKind.ABORT,)


def _decision_for(
    kind: RecoveryKind,
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
        if kind == RecoveryKind.ABORT
        else shape.reentry_phase
    )
    if kind == RecoveryKind.ACTIVE_PERCEPTION:
        if not context.gap_ids:
            return None
    if kind == RecoveryKind.REROUTE:
        if not context.fresh_candidate_id and not context.fresh_route_ref:
            return None
    if kind == RecoveryKind.SWITCH_PROVIDER:
        if not context.configured_provider_id:
            return None
    if kind == RecoveryKind.RETRY_IDEMPOTENT:
        if not context.idempotency_key:
            return None
    if kind == RecoveryKind.COMPENSATE:
        if not context.compensation_contract_id:
            return None
    return RecoveryDecision(
        decision_id=f"recovery-decision-{uuid4().hex}",
        failure_id=failure.failure_id,
        based_on_state_version=current_state_version,
        strategy_key=strategy_id,
        kind=kind,
        reason_code=classification.reason_code,
        changed_dimensions=shape.changed_dimensions,
        preconditions=shape.preconditions,
        budget_cost=shape.budget_cost,
        reentry_phase=reentry_phase,
        candidate_id=context.fresh_candidate_id if kind == RecoveryKind.REROUTE else "",
        route_ref=context.fresh_route_ref if kind == RecoveryKind.REROUTE else "",
        provider_id=context.configured_provider_id if kind == RecoveryKind.SWITCH_PROVIDER else "",
        question=(
            context.user_question
            if kind in {RecoveryKind.ASK_USER, RecoveryKind.CLARIFY_INTENT}
            else ""
        ),
        idempotency_key=(
            context.idempotency_key
            if kind == RecoveryKind.RETRY_IDEMPOTENT
            else ""
        ),
        compensation_contract_id=(
            context.compensation_contract_id
            if kind == RecoveryKind.COMPENSATE
            else ""
        ),
    )


@dataclass(frozen=True)
class _CommandShape:
    expected_change: str
    changed_dimensions: tuple[RecoveryDimension, ...]
    preconditions: tuple[str, ...]
    budget_cost: RecoveryBudgetCost
    timeout_ms: int
    reentry_phase: RuntimePhase


def _command_shape(kind: RecoveryKind) -> _CommandShape:
    dimension, reentry, observations, replans, provider_switches, user_escalations = {
        RecoveryKind.REOBSERVE: (RecoveryDimension.OBSERVATION, RuntimePhase.OBSERVING, 1, 0, 0, 0),
        RecoveryKind.ACTIVE_PERCEPTION: (RecoveryDimension.EVIDENCE, RuntimePhase.OBSERVING, 1, 0, 0, 0),
        RecoveryKind.COMPACT_CONTEXT: (RecoveryDimension.CONTEXT, RuntimePhase.PLANNING, 0, 1, 0, 0),
        RecoveryKind.SWITCH_PROVIDER: (RecoveryDimension.PROVIDER, RuntimePhase.PLANNING, 0, 1, 1, 0),
        RecoveryKind.REPAIR_MODEL_SCHEMA: (RecoveryDimension.CONTEXT, RuntimePhase.PLANNING, 0, 1, 0, 0),
        RecoveryKind.CLARIFY_INTENT: (RecoveryDimension.USER_INFORMATION, RuntimePhase.WAITING_USER, 0, 0, 0, 1),
        RecoveryKind.REPLAN_TASK: (RecoveryDimension.TASK_PLAN, RuntimePhase.PLANNING, 0, 1, 0, 0),
        RecoveryKind.REPLAN_STEP: (RecoveryDimension.STEP_PLAN, RuntimePhase.PLANNING, 0, 1, 0, 0),
        RecoveryKind.REGROUND: (RecoveryDimension.CANDIDATE, RuntimePhase.OBSERVING, 1, 0, 0, 0),
        RecoveryKind.REROUTE: (RecoveryDimension.ROUTE, RuntimePhase.PREFLIGHT, 1, 0, 0, 0),
        RecoveryKind.INSPECT_POST_STATE: (RecoveryDimension.EFFECT_STATUS, RuntimePhase.VERIFYING, 1, 0, 0, 0),
        RecoveryKind.RETRY_IDEMPOTENT: (RecoveryDimension.OBSERVATION, RuntimePhase.PREFLIGHT, 1, 0, 0, 0),
        RecoveryKind.COMPENSATE: (RecoveryDimension.EFFECT_STATUS, RuntimePhase.PREFLIGHT, 1, 0, 0, 0),
        RecoveryKind.REQUEST_APPROVAL: (RecoveryDimension.APPROVAL, RuntimePhase.WAITING_APPROVAL, 0, 0, 0, 1),
        RecoveryKind.ASK_USER: (RecoveryDimension.USER_INFORMATION, RuntimePhase.WAITING_USER, 0, 0, 0, 1),
        RecoveryKind.ABORT: (RecoveryDimension.TERMINAL, RuntimePhase.ABORTED, 0, 0, 0, 0),
    }[kind]
    timeout_ms = 5_000 if observations or replans else 0
    return _CommandShape(
        expected_change=f"apply {kind.value} and change {dimension.value}",
        changed_dimensions=(dimension,),
        preconditions=(f"owning port for {kind.value} is available",),
        budget_cost=RecoveryBudgetCost(
            recoveries=0 if kind == RecoveryKind.ABORT else 1,
            observations=observations,
            replans=replans,
            provider_switches=provider_switches,
            user_escalations=user_escalations,
            timeout_ms=timeout_ms,
        ),
        timeout_ms=timeout_ms,
        reentry_phase=reentry,
    )


def _strategy_id(kind: RecoveryKind, semantic_family_key: str) -> str:
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
