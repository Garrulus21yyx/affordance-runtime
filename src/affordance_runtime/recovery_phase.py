"""Coordinator-facing SAR-8 recovery phase seam."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery_coordinator import (
    RecoveryCoordinator,
    RecoveryHistoryItem,
    RecoverySelectionContext,
)
from affordance_runtime.recovery_owner_dispatcher import (
    OWNER_DISPATCH_RECOVERY_KINDS,
    RecoveryOwnerDispatcher,
)
from affordance_runtime.recovery_protocol import (
    FailureClassification,
    FailureClassificationFacts,
    RecoveryDecision,
    RecoveryKind,
    RecoveryOutcome,
    RuntimePhase,
    classify_failure,
)
from affordance_runtime.recovery_trace_projection import recovery_protocol_projections
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


@dataclass(frozen=True)
class RecoveryApplicationResult:
    classification: FailureClassification
    decision: RecoveryDecision
    recovery_kind: RecoveryKind
    parent: TraceNode
    outcome: RecoveryOutcome | None = None

    def __iter__(self):
        yield self.recovery_kind
        yield self.parent


@dataclass(frozen=True)
class RecoveryPhase:
    """Apply phase-general recovery selection without exposing policy in Coordinator."""

    coordinator: RecoveryCoordinator
    owner_dispatcher: RecoveryOwnerDispatcher

    def handle_phase_failure(
        self,
        *,
        failure: FailureEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        available_commands: frozenset[RecoveryKind],
        runtime_profile_digest: str,
        loaded_profile_artifact_ids: tuple[str, ...],
        abort_reentry_phase: RuntimePhase = RuntimePhase.ABORTED,
        fresh_candidate_id: str = "",
        fresh_route_ref: str = "",
        idempotency_key: str = "",
        compensation_contract_id: str = "",
        available_action_count: int = 0,
        user_input_required: bool = False,
    ) -> RecoveryApplicationResult:
        available = _available_recovery_kinds(
            available_commands,
            self.owner_dispatcher.available_kinds,
        )
        state.transition(RuntimeStep.RECOVERING.value)
        recovery_context = RecoverySelectionContext(
            available_commands=available,
            current_attempt_fingerprint=failure.progress_fingerprint,
            gap_ids=tuple(item.gap_id for item in state.evidence_gaps),
            accepted_profile_digest=runtime_profile_digest,
            accepted_profile_artifact_ids=frozenset(loaded_profile_artifact_ids),
            fresh_candidate_id=fresh_candidate_id,
            fresh_route_ref=fresh_route_ref,
            idempotency_key=idempotency_key,
            compensation_contract_id=compensation_contract_id,
            configured_provider_id=self.owner_dispatcher.target_ref(RecoveryKind.SWITCH_PROVIDER),
            history=tuple(state.recovery_history),
            abort_reentry_phase=abort_reentry_phase,
            available_action_count=available_action_count,
            user_input_required=user_input_required,
        )
        classification = classify_failure(
            failure,
            FailureClassificationFacts(
                available_action_count=recovery_context.available_action_count,
                user_input_required=recovery_context.user_input_required,
            ),
        )
        decision = self.coordinator.decide(
            failure,
            classification,
            recovery_context,
            current_state_version=state.version,
        )
        state.current_failure = failure
        state.current_recovery_decision = decision
        state.current_recovery_outcome = None
        state.attempted_recovery_strategy_ids.add(decision.strategy_key)
        state.recovery_count += 1
        parent = _trace_recovery_protocol(
            trace,
            parent,
            state_phase=state.phase,
            failure=failure,
            decision=decision,
        )
        if decision.kind in {
            RecoveryKind.REOBSERVE,
            RecoveryKind.REGROUND,
            RecoveryKind.ACTIVE_PERCEPTION,
            RecoveryKind.INSPECT_POST_STATE,
            RecoveryKind.RETRY_IDEMPOTENT,
        }:
            state.transition(RuntimeStep.OBSERVING.value)
            return RecoveryApplicationResult(
                classification,
                decision,
                decision.kind,
                parent,
            )
        if decision.kind in {
            RecoveryKind.REPLAN_STEP,
            RecoveryKind.REPLAN_TASK,
        }:
            state.replan_count += 1
            state.record_disproved_assumption(
                f"{failure.phase.value}:{failure.error_code}:{failure.message}"
            )
            state.transition(RuntimeStep.OBSERVING.value)
            return RecoveryApplicationResult(
                classification,
                decision,
                decision.kind,
                parent,
            )
        if decision.kind in OWNER_DISPATCH_RECOVERY_KINDS:
            recovery_kind, parent = self._dispatch_owner_command(
                failure,
                state,
                trace,
                parent,
                abort_reentry_phase=abort_reentry_phase,
            )
            return RecoveryApplicationResult(
                classification,
                decision,
                recovery_kind,
                parent,
                state.current_recovery_outcome,
            )
        recovery_kind, parent = _complete_immediate_recovery_command(
            state,
            trace,
            parent,
            failure=failure,
            decision=decision,
        )
        return RecoveryApplicationResult(
            classification,
            decision,
            recovery_kind,
            parent,
            state.current_recovery_outcome,
        )

    def _dispatch_owner_command(
        self,
        failure: FailureEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        abort_reentry_phase: RuntimePhase,
    ) -> tuple[RecoveryKind, TraceNode]:
        decision = state.current_recovery_decision
        if decision is None:
            raise ValueError("owner recovery dispatch requires a pending decision")
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        dispatched = self.owner_dispatcher.dispatch(
            decision,
            failure=failure,
            previous_attempt_fingerprint=previous_fingerprint,
        )
        state.current_recovery_outcome = dispatched.outcome
        parent = trace.add(
            "RecoveryOutcomeRecorded",
            {
                "state": state.phase,
                "outcome": {
                    "decision_id": dispatched.outcome.decision_id,
                    "failure_id": dispatched.outcome.failure_id,
                    "success": dispatched.outcome.success,
                    "changed_dimensions": [
                        item.value for item in dispatched.outcome.changed_dimensions
                    ],
                    "next_phase": dispatched.outcome.next_phase.value,
                    "artifact_refs": list(dispatched.outcome.artifact_refs),
                    "observation_refs": list(dispatched.outcome.observation_refs),
                    "error_code": dispatched.outcome.error_code,
                },
                "state_before_ref": dispatched.state_before_ref,
                "state_after_ref": dispatched.state_after_ref,
            },
            parents=[parent.id],
        )
        if not dispatched.outcome.success:
            state.transition(abort_reentry_phase.value)
            return RecoveryKind.ABORT, parent
        state.replan_count += 1
        state.record_disproved_assumption(
            f"{failure.phase.value}:{failure.error_code}:{failure.message}"
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                decision.strategy_key,
                previous_fingerprint,
                dispatched.next_attempt_fingerprint,
            )
        )
        state.transition(RuntimeStep.OBSERVING.value)
        return (
            decision.kind,
            trace.add(
                "RecoveryReenteredPhase",
                {"state": state.phase, "reentry_phase": decision.reentry_phase.value},
                parents=[parent.id],
            ),
        )

    @staticmethod
    def complete_pending_plan_change(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        kind: RecoveryKind,
        plan_or_route_ref: str,
    ) -> TraceNode:
        failure = state.current_failure
        decision = _pending_recovery_decision(state)
        if failure is None or decision is None or decision.kind != kind:
            return parent
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = f"{failure.semantic_family_key}:{decision.strategy_key}:{plan_or_route_ref}"
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                decision.strategy_key,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
            artifact_refs=(plan_or_route_ref,) if plan_or_route_ref else (),
        )
        parent = _trace_recovery_outcome(trace, parent, state=state, outcome=state.current_recovery_outcome)
        return trace.add(
            "RecoveryReenteredPhase",
            {"state": state.phase, "reentry_phase": decision.reentry_phase.value},
            parents=[parent.id],
        )

    @staticmethod
    def complete_pending_binding(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
    ) -> tuple[TraceNode, bool]:
        failure = state.current_failure
        decision = _pending_recovery_decision(state)
        if failure is None or decision is None:
            return parent, False
        if decision.kind not in {
            RecoveryKind.REGROUND,
            RecoveryKind.REROUTE,
        }:
            return parent, False
        candidate_id = (
            contract.grounding_candidate.candidate_id
            if contract.grounding_candidate is not None
            else ""
        )
        fresh_epoch = bool(contract.snapshot_id and contract.snapshot_id != failure.snapshot_id)
        route_matches = bool(
            decision.kind == RecoveryKind.REGROUND
            or (decision.candidate_id and candidate_id == decision.candidate_id)
            or (decision.route_ref and contract.backend == decision.route_ref)
        )
        if not fresh_epoch or not route_matches:
            parent = RecoveryPhase.fail_pending_command(
                state,
                trace,
                parent,
                error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
            )
            return parent, True
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{decision.strategy_key}:"
            f"contract:{contract.contract_hash or contract.id}"
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                decision.strategy_key,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
            artifact_refs=tuple(item for item in (candidate_id, contract.id) if item),
        )
        parent = _trace_recovery_outcome(trace, parent, state=state, outcome=state.current_recovery_outcome)
        return (
            trace.add(
                "RecoveryReenteredPhase",
                {"state": state.phase, "reentry_phase": decision.reentry_phase.value},
                parents=[parent.id],
            ),
            False,
        )

    @staticmethod
    def fail_pending_command(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        error_code: str,
    ) -> TraceNode:
        decision = _pending_recovery_decision(state)
        failure = state.current_failure
        if decision is None or failure is None:
            return parent
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=False,
            changed_dimensions=decision.changed_dimensions,
            next_phase=RuntimePhase.ABORTED,
            error_code=error_code,
        )
        return _trace_recovery_outcome(trace, parent, state=state, outcome=state.current_recovery_outcome)

    @staticmethod
    def complete_pending_execution(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        execution_receipt: ExecutionReceipt,
        observation: Observation,
    ) -> TraceNode:
        failure = state.current_failure
        decision = _pending_recovery_decision(state)
        if (
            failure is None
            or decision is None
            or decision.kind != RecoveryKind.RETRY_IDEMPOTENT
        ):
            return parent
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{decision.strategy_key}:"
            f"contract:{contract.contract_hash or contract.id}:snapshot:{observation.snapshot_id}"
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                decision.strategy_key,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        error_code = (
            ""
            if execution_receipt.success
            else (
                execution_receipt.error_code.value
                if execution_receipt.error_code is not None
                else RuntimeErrorCode.EXECUTION_FAILED.value
            )
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=execution_receipt.success,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
            artifact_refs=tuple(
                item for item in execution_receipt.evidence.values() if isinstance(item, str)
            ),
            observation_refs=(observation.snapshot_id,) if observation.snapshot_id else (),
            error_code=error_code,
        )
        return _trace_recovery_outcome(trace, parent, state=state, outcome=state.current_recovery_outcome)

    @staticmethod
    def complete_pending_observation(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        *,
        verification: VerificationReport | None = None,
        post_state_inspection_failed: bool = False,
    ) -> tuple[TraceNode, bool]:
        failure = state.current_failure
        decision = _pending_recovery_decision(state)
        if failure is None or decision is None:
            return parent, False
        observation_kinds = {
            RecoveryKind.REOBSERVE,
            RecoveryKind.INSPECT_POST_STATE,
        }
        if decision.kind not in observation_kinds:
            return parent, False
        if post_state_inspection_failed:
            state.current_recovery_outcome = RecoveryOutcome(
                decision_id=decision.decision_id,
                failure_id=failure.failure_id,
                success=False,
                changed_dimensions=decision.changed_dimensions,
                next_phase=RuntimePhase.ABORTED,
                error_code=RuntimeErrorCode.VERIFICATION_FAILED.value,
            )
            parent = _trace_recovery_outcome(
                trace,
                parent,
                state=state,
                outcome=state.current_recovery_outcome,
            )
            parent = trace.add(
                "RecoveryAborted",
                {
                    "state": state.phase,
                    "reason": "post-state inspection did not establish a safe changed effect status",
                },
                parents=[parent.id],
            )
            return parent, True
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{decision.strategy_key}:"
            f"{snapshot.observation.snapshot_id}:state:{state.version}"
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                decision.strategy_key,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=decision.decision_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=decision.changed_dimensions,
            next_phase=decision.reentry_phase,
            artifact_refs=tuple(snapshot.observation.artifact_refs),
            observation_refs=(snapshot.observation.snapshot_id,),
        )
        parent = _trace_recovery_outcome(trace, parent, state=state, outcome=state.current_recovery_outcome)
        parent = trace.add(
            "RecoveryReenteredPhase",
            {
                "state": state.phase,
                "reentry_phase": decision.reentry_phase.value,
            },
            parents=[parent.id],
        )
        return parent, False


def _available_recovery_kinds(
    available_commands: frozenset[RecoveryKind],
    owner_available_commands: frozenset[RecoveryKind],
) -> frozenset[RecoveryKind]:
    return frozenset(
        kind
        for kind in available_commands
        if kind not in OWNER_DISPATCH_RECOVERY_KINDS or kind in owner_available_commands
    )


def _pending_recovery_decision(state: StateKernel) -> RecoveryDecision | None:
    if state.current_recovery_outcome is not None:
        return None
    decision = state.current_recovery_decision
    failure = state.current_failure
    if decision is None or failure is None:
        return None
    return decision


def _trace_recovery_protocol(
    trace: TraceDag,
    parent: TraceNode,
    *,
    state_phase: str,
    failure: FailureEnvelope,
    decision: RecoveryDecision,
) -> TraceNode:
    for projection in recovery_protocol_projections(
        state_phase=state_phase,
        failure=failure,
        decision=decision,
    ):
        parent = trace.add(projection.kind, projection.payload, parents=[parent.id])
    return parent


def _trace_recovery_outcome(
    trace: TraceDag,
    parent: TraceNode,
    *,
    state: StateKernel,
    outcome: RecoveryOutcome,
) -> TraceNode:
    return trace.add(
        "RecoveryOutcomeRecorded",
        {
            "state": state.phase,
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
        parents=[parent.id],
    )


def _complete_immediate_recovery_command(
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    *,
    failure: FailureEnvelope,
    decision: RecoveryDecision,
) -> tuple[RecoveryKind, TraceNode]:
    terminal_phase = _runtime_step_for_reentry(decision.reentry_phase)
    if terminal_phase is None:
        raise ValueError(f"unsupported immediate recovery re-entry: {decision.reentry_phase.value}")
    state.transition(terminal_phase)
    previous_fingerprint = (
        failure.progress_fingerprint
        or f"{failure.semantic_family_key}:state:{failure.state_version}"
    )
    next_fingerprint = f"{failure.semantic_family_key}:{decision.strategy_key}:{state.phase}"
    state.recovery_history.append(
        RecoveryHistoryItem(
            failure.semantic_family_key,
            decision.strategy_key,
            previous_fingerprint,
            next_fingerprint,
        )
    )
    state.current_recovery_outcome = RecoveryOutcome(
        decision_id=decision.decision_id,
        failure_id=failure.failure_id,
        success=True,
        changed_dimensions=decision.changed_dimensions,
        next_phase=decision.reentry_phase,
        artifact_refs=(decision.provider_id,) if decision.provider_id else (),
    )
    parent = _trace_recovery_outcome(trace, parent, state=state, outcome=state.current_recovery_outcome)
    return (
        decision.kind,
        trace.add(
            "RecoveryReenteredPhase",
            {"state": state.phase, "reentry_phase": decision.reentry_phase.value},
            parents=[parent.id],
        ),
    )


def _runtime_step_for_reentry(phase: RuntimePhase) -> str | None:
    return {
        RuntimePhase.WAITING_USER: RuntimeStep.WAITING_CLARIFICATION.value,
        RuntimePhase.WAITING_APPROVAL: RuntimeStep.WAITING_APPROVAL.value,
        RuntimePhase.DEFERRED: RuntimeStep.DEFERRED.value,
        RuntimePhase.FAILED: RuntimeStep.FAILED.value,
        RuntimePhase.ABORTED: RuntimeStep.ABORTED.value,
    }.get(phase)
