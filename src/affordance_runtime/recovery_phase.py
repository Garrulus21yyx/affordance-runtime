"""Pure Runtime-owned mechanical recovery stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery_coordinator import (
    RecoveryCoordinator,
    RecoverySelectionContext,
)
from affordance_runtime.recovery_owner_dispatcher import (
    OWNER_DISPATCH_RECOVERY_KINDS,
    RecoveryOwnerDispatcher,
)
from affordance_runtime.recovery_protocol import (
    FailureClassificationFacts,
    FailureOwner,
    RecoveryDecision,
    RecoveryKind,
    RecoveryOutcome,
    RuntimePhase,
    classify_failure,
)
from affordance_runtime.recovery_trace_projection import recovery_protocol_projections
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.stage_protocol import (
    LoopDirective,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeTransition,
    StageResult,
    TerminalResult,
)


@dataclass(frozen=True)
class RecoveryStageInput:
    failure: FailureEnvelope
    state_view: RuntimeStateSnapshot
    available_commands: frozenset[RecoveryKind]
    runtime_profile_digest: str = ""
    loaded_profile_artifact_ids: tuple[str, ...] = ()
    abort_reentry_phase: RuntimePhase = RuntimePhase.ABORTED
    available_action_count: int = 0
    user_input_required: bool = False


@dataclass(frozen=True)
class RecoveryOutput:
    decision: RecoveryDecision
    outcome: RecoveryOutcome | None = None

    @property
    def recovery_kind(self) -> RecoveryKind:
        return self.decision.kind


@dataclass(frozen=True)
class RecoveryStage:
    coordinator: RecoveryCoordinator
    owner_dispatcher: RecoveryOwnerDispatcher
    runtime_profile_digest: str = ""
    loaded_profile_artifact_ids: tuple[str, ...] = ()

    def available_commands(
        self,
        failure: FailureEnvelope,
        state: RuntimeStateSnapshot,
    ) -> frozenset[RecoveryKind]:
        """Project typed recovery affordances; Coordinator only orchestrates them."""

        available = set(self.owner_dispatcher.available_kinds)
        phase = failure.phase.value
        if phase == "grounding_binding":
            available.add(RecoveryKind.REGROUND)
        if phase == "preflight":
            available.add(RecoveryKind.REOBSERVE)
        if phase in {"observation", "fusion"}:
            available.add(RecoveryKind.REOBSERVE)
        if phase in {"execution_uncertain", "verification"}:
            available.update({RecoveryKind.REOBSERVE, RecoveryKind.INSPECT_POST_STATE})
        contract = state.current_contract
        if contract is None:
            return frozenset(available)
        if contract.idempotency_key:
            available.add(RecoveryKind.RETRY_IDEMPOTENT)
        if contract.compensation:
            available.add(RecoveryKind.COMPENSATE)
        route_plan = contract.route_plan
        if route_plan is not None and any(
            item.candidate_id != route_plan.selected_candidate.candidate_id
            for item in route_plan.viable_alternatives
        ):
            available.add(RecoveryKind.REROUTE)
        tried_backends = (
            {state.last_receipt.backend} if state.last_receipt is not None else set()
        )
        if any(item not in tried_backends for item in contract.fallback_backends):
            available.add(RecoveryKind.REROUTE)
        return frozenset(available)

    def run(self, stage_input: RecoveryStageInput) -> StageResult[RecoveryOutput]:
        failure = stage_input.failure
        classification = classify_failure(
            failure,
            FailureClassificationFacts(
                available_action_count=stage_input.available_action_count,
                user_input_required=stage_input.user_input_required,
            ),
        )
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            raise ValueError("RecoveryStage only accepts Runtime-owned failures")
        state = stage_input.state_view
        contract = state.current_contract
        fresh_candidate, fresh_route = _fresh_route(state)
        available = frozenset(
            kind
            for kind in stage_input.available_commands
            if kind not in OWNER_DISPATCH_RECOVERY_KINDS
            or kind in self.owner_dispatcher.available_kinds
        )
        context = RecoverySelectionContext(
            available_commands=available,
            current_attempt_fingerprint=failure.progress_fingerprint,
            gap_ids=tuple(item.gap_id for item in state.evidence_gaps),
            accepted_profile_digest=stage_input.runtime_profile_digest,
            accepted_profile_artifact_ids=frozenset(stage_input.loaded_profile_artifact_ids),
            fresh_candidate_id=fresh_candidate,
            fresh_route_ref=fresh_route,
            idempotency_key=contract.idempotency_key if contract is not None else "",
            compensation_contract_id=(contract.compensation or "") if contract is not None else "",
            configured_provider_id=self.owner_dispatcher.target_ref(RecoveryKind.SWITCH_PROVIDER),
            history=(),
            abort_reentry_phase=stage_input.abort_reentry_phase,
            available_action_count=stage_input.available_action_count,
            user_input_required=stage_input.user_input_required,
        )
        try:
            decision = self.coordinator.decide(
                failure,
                classification,
                context,
                current_state_version=state.version,
            )
        except ValueError as exc:
            if str(exc) != "no safe changed recovery strategy is available":
                raise
            return StageResult(
                transition=RuntimeTransition(
                    phase=RuntimeStep(stage_input.abort_reentry_phase.value),
                    intermediate_phases=(RuntimeStep.RECOVERING,),
                    state_updates={
                        "current_failure": failure,
                        "current_recovery_decision": None,
                        "current_recovery_outcome": None,
                    },
                ),
                events=(
                    RuntimeEvent(
                        "FailureDetected",
                        {
                            "state": stage_input.abort_reentry_phase.value,
                            "failure": failure.model_dump(mode="json"),
                        },
                    ),
                    RuntimeEvent(
                        "FailureOwnerRouted",
                        {
                            "state": stage_input.abort_reentry_phase.value,
                            "failure_id": failure.failure_id,
                            "owner": FailureOwner.TERMINAL.value,
                            "reason_code": "runtime_recovery_exhausted",
                            "handoff_type": "TerminalResult",
                        },
                    ),
                ),
                failure=failure,
                terminal=TerminalResult(
                    failure.failure_id,
                    "runtime_recovery_exhausted",
                    RuntimeStep(stage_input.abort_reentry_phase.value),
                ),
                directive=LoopDirective.TERMINAL,
            )
        state_updates: dict[str, Any] = {
            "current_failure": failure,
            "current_recovery_decision": decision,
            "current_recovery_outcome": None,
            "attempted_recovery_strategy_ids": set(
                (*state.attempted_recovery_strategy_ids, decision.strategy_key)
            ),
            "recovery_count": state.recovery_count + 1,
        }
        events = tuple(
            RuntimeEvent(item.kind, item.payload)
            for item in recovery_protocol_projections(
                state_phase=RuntimeStep.RECOVERING.value,
                failure=failure,
                decision=decision,
            )
        )
        grounding_updates, grounding_version_delta = _grounding_updates(
            state, contract, decision.kind
        )
        state_updates.update(grounding_updates)
        if decision.kind in {
            RecoveryKind.REOBSERVE,
            RecoveryKind.REGROUND,
            RecoveryKind.REROUTE,
            RecoveryKind.ACTIVE_PERCEPTION,
            RecoveryKind.INSPECT_POST_STATE,
            RecoveryKind.RETRY_IDEMPOTENT,
        }:
            return _result(
                decision,
                events,
                LoopDirective.REPEAT_OBSERVATION,
                state_updates,
                phase=RuntimeStep.OBSERVING,
                version_delta=grounding_version_delta,
            )
        if decision.kind in OWNER_DISPATCH_RECOVERY_KINDS:
            dispatched = self.owner_dispatcher.dispatch(
                decision,
                failure=failure,
                previous_attempt_fingerprint=_previous_fingerprint(failure),
            )
            state_updates["current_recovery_outcome"] = dispatched.outcome
            outcome_event = _outcome_event(RuntimeStep.RECOVERING.value, dispatched.outcome)
            if not dispatched.outcome.success:
                routed = RuntimeEvent(
                    "FailureOwnerRouted",
                    {
                        "state": stage_input.abort_reentry_phase.value,
                        "failure_id": failure.failure_id,
                        "owner": FailureOwner.TERMINAL.value,
                        "reason_code": dispatched.outcome.error_code
                        or "runtime_recovery_failed",
                        "handoff_type": "TerminalResult",
                    },
                )
                return _result(
                    decision,
                    (*events, outcome_event, routed),
                    LoopDirective.TERMINAL,
                    state_updates,
                    outcome=dispatched.outcome,
                    terminal=TerminalResult(
                        failure.failure_id,
                        dispatched.outcome.error_code or "runtime_recovery_failed",
                        RuntimeStep(stage_input.abort_reentry_phase.value),
                    ),
                    phase=RuntimeStep(stage_input.abort_reentry_phase.value),
                    version_delta=grounding_version_delta,
                )
            state_updates["current_disproved_assumption"] = (
                f"{failure.phase.value}:{failure.error_code}:{failure.message}"
            )
            return _result(
                decision,
                (
                    *events,
                    outcome_event,
                    _reentry_event(RuntimeStep.OBSERVING.value, decision),
                ),
                LoopDirective.REPEAT_OBSERVATION,
                state_updates,
                outcome=dispatched.outcome,
                phase=RuntimeStep.OBSERVING,
                replan_count_delta=1,
                version_delta=grounding_version_delta,
            )
        terminal = TerminalResult(
            failure.failure_id,
            "unsupported_runtime_recovery_command",
            RuntimeStep(stage_input.abort_reentry_phase.value),
        )
        return _result(
            decision,
            events,
            LoopDirective.TERMINAL,
            state_updates,
            terminal=terminal,
            phase=RuntimeStep(stage_input.abort_reentry_phase.value),
            version_delta=grounding_version_delta,
        )


def _result(
    decision: RecoveryDecision,
    events: tuple[RuntimeEvent, ...],
    directive: LoopDirective,
    state_updates: dict[str, Any],
    *,
    outcome: RecoveryOutcome | None = None,
    terminal: TerminalResult | None = None,
    phase: RuntimeStep | None = None,
    replan_count_delta: int = 0,
    version_delta: int = 0,
) -> StageResult[RecoveryOutput]:
    return StageResult(
        output=RecoveryOutput(decision, outcome),
        transition=RuntimeTransition(
            phase=phase,
            intermediate_phases=(RuntimeStep.RECOVERING,),
            state_updates=state_updates,
            replan_count_delta=replan_count_delta,
            version_delta=version_delta,
        ),
        events=events,
        terminal=terminal,
        directive=directive,
    )


def _fresh_route(state: Any) -> tuple[str, str]:
    contract = state.current_contract
    if contract is None:
        return "", ""
    if contract.route_plan is not None:
        selected = contract.route_plan.selected_candidate.candidate_id
        for candidate in contract.route_plan.viable_alternatives:
            if candidate.candidate_id != selected:
                return candidate.candidate_id, ""
    tried = {state.last_receipt.backend} if state.last_receipt is not None else set()
    return "", next((item for item in contract.fallback_backends if item not in tried), "")


def _grounding_updates(
    state: Any,
    contract: Any,
    kind: RecoveryKind,
) -> tuple[dict[str, Any], int]:
    if contract is None or kind not in {
        RecoveryKind.REROUTE,
        RecoveryKind.REOBSERVE,
        RecoveryKind.RETRY_IDEMPOTENT,
    }:
        return {}, 0
    candidate = contract.grounding_candidate
    if candidate is None:
        return {}, 0
    excluded = {
        key: set(values) for key, values in state.current_excluded_candidates.items()
    }
    if kind == RecoveryKind.REROUTE:
        excluded.setdefault(candidate.semantic_target_id, set()).add(
            candidate.candidate_id
        )
    fallback = {
        key: dict(value) for key, value in state.current_grounding_fallback.items()
    }
    fallback[candidate.semantic_target_id] = {
        "supersedes_contract_id": contract.id,
        "source_contract_id": contract.source_contract_id or contract.id,
        "fallback_reason": "recovery reroute" if kind == RecoveryKind.REROUTE else "recovery requires fresh observation",
        "failed_source": candidate.source.value,
    }
    return {
        "current_excluded_candidates": excluded,
        "current_grounding_fallback": fallback,
    }, 1


def _previous_fingerprint(failure: FailureEnvelope) -> str:
    return failure.progress_fingerprint or f"{failure.semantic_family_key}:state:{failure.state_version}"


def _outcome_event(state: str, outcome: RecoveryOutcome) -> RuntimeEvent:
    return RuntimeEvent(
        "RecoveryOutcomeRecorded",
        {
            "state": state,
            "outcome": {
                "decision_id": outcome.decision_id,
                "failure_id": outcome.failure_id,
                "success": outcome.success,
                "changed_dimensions": [item.value for item in outcome.changed_dimensions],
                "next_phase": outcome.next_phase.value,
                "artifact_refs": list(outcome.artifact_refs),
                "observation_refs": list(outcome.observation_refs),
                "error_code": outcome.error_code,
            },
        },
    )


def _reentry_event(state: str, decision: RecoveryDecision) -> RuntimeEvent:
    return RuntimeEvent(
        "RecoveryReenteredPhase",
        {"state": state, "reentry_phase": decision.reentry_phase.value},
    )
