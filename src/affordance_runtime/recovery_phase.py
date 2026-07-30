"""Coordinator-facing SAR-8 recovery phase seam."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery_command_dispatcher import (
    OWNER_DISPATCH_COMMANDS,
    RecoveryCommandDispatcher,
)
from affordance_runtime.recovery_commands import (
    RecoveryCommand,
    RecoveryCommandKind,
    RecoveryDelta,
    RecoveryReentryPhase,
)
from affordance_runtime.recovery_commands import (
    RecoveryReceipt as RecoveryCommandReceipt,
)
from affordance_runtime.recovery_completion import successful_recovery_completion
from affordance_runtime.recovery_coordinator import (
    RecoveryCoordinator,
    RecoveryHistoryItem,
    RecoverySelectionContext,
)
from affordance_runtime.recovery_decision_compatibility import (
    legacy_command_from_recovery_decision,
)
from affordance_runtime.recovery_protocol import (
    FailureClassification,
    FailureClassificationFacts,
    RecoveryDecision,
    RecoveryDimension,
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
    command_kind: RecoveryCommandKind
    parent: TraceNode
    outcome: RecoveryOutcome | None = None

    def __iter__(self):
        yield self.command_kind
        yield self.parent


@dataclass(frozen=True)
class RecoveryPhase:
    """Apply phase-general recovery selection without exposing policy in Coordinator."""

    coordinator: RecoveryCoordinator
    command_dispatcher: RecoveryCommandDispatcher

    def handle_phase_failure(
        self,
        *,
        failure: FailureEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        available_commands: frozenset[RecoveryCommandKind],
        runtime_profile_digest: str,
        loaded_profile_artifact_ids: tuple[str, ...],
        abort_reentry_phase: RecoveryReentryPhase = RecoveryReentryPhase.ABORTED,
        fresh_candidate_id: str = "",
        fresh_route_ref: str = "",
        idempotency_key: str = "",
        compensation_contract_id: str = "",
        available_action_count: int = 0,
        user_input_required: bool = False,
    ) -> RecoveryApplicationResult:
        available = _available_recovery_kinds(
            available_commands,
            self.command_dispatcher.available_commands,
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
            configured_provider_id=self.command_dispatcher.target_ref(
                RecoveryCommandKind.SWITCH_PROVIDER
            ),
            history=tuple(state.recovery_history),
            abort_reentry_phase=RuntimePhase(abort_reentry_phase.value),
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
        command = legacy_command_from_recovery_decision(
            decision,
            effect_status=failure.effect_status,
            gap_ids=recovery_context.gap_ids,
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
            command=command,
        )
        if command.kind in {
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.ACTIVE_PERCEPTION,
            RecoveryCommandKind.INSPECT_POST_STATE,
            RecoveryCommandKind.RETRY_IDEMPOTENT,
        }:
            state.transition(RuntimeStep.OBSERVING.value)
            return RecoveryApplicationResult(classification, decision, command.kind, parent)
        if command.kind in {
            RecoveryCommandKind.REPLAN_STEP,
            RecoveryCommandKind.REPLAN_TASK,
        }:
            state.replan_count += 1
            state.record_disproved_assumption(
                f"{failure.phase.value}:{failure.error_code}:{failure.message}"
            )
            state.transition(RuntimeStep.OBSERVING.value)
            return RecoveryApplicationResult(classification, decision, command.kind, parent)
        if command.kind in OWNER_DISPATCH_COMMANDS:
            command_kind, parent = self._dispatch_owner_command(
                failure,
                state,
                trace,
                parent,
                abort_reentry_phase=abort_reentry_phase,
            )
            return RecoveryApplicationResult(
                classification,
                decision,
                command_kind,
                parent,
                state.current_recovery_outcome,
            )
        command_kind, parent = _complete_immediate_recovery_command(
            state,
            trace,
            parent,
            failure=failure,
            decision=decision,
            command=command,
        )
        return RecoveryApplicationResult(
            classification,
            decision,
            command_kind,
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
        abort_reentry_phase: RecoveryReentryPhase,
    ) -> tuple[RecoveryCommandKind, TraceNode]:
        command = _pending_legacy_command(state)
        if command is None:
            raise ValueError("owner recovery dispatch requires a pending command")
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        dispatched = self.command_dispatcher.dispatch(
            command,
            previous_attempt_fingerprint=previous_fingerprint,
        )
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": dispatched.receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        if not dispatched.receipt.success or dispatched.delta is None:
            state.transition(abort_reentry_phase.value)
            state.current_recovery_outcome = RecoveryOutcome(
                decision_id=state.current_recovery_decision.decision_id
                if state.current_recovery_decision is not None
                else command.command_id,
                failure_id=failure.failure_id,
                success=False,
                changed_dimensions=tuple(
                    RecoveryDimension(item.value) for item in command.changed_dimensions
                ),
                next_phase=RuntimePhase(abort_reentry_phase.value),
                error_code=dispatched.receipt.error_code,
            )
            return RecoveryCommandKind.ABORT, parent
        state.replan_count += 1
        state.record_disproved_assumption(
            f"{failure.phase.value}:{failure.error_code}:{failure.message}"
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                dispatched.delta.next_attempt_fingerprint,
            )
        )
        state.transition(RuntimeStep.OBSERVING.value)
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=state.current_recovery_decision.decision_id
            if state.current_recovery_decision is not None
            else command.command_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=tuple(
                RecoveryDimension(item.value) for item in command.changed_dimensions
            ),
            next_phase=RuntimePhase.OBSERVING,
            artifact_refs=dispatched.receipt.artifact_refs,
            observation_refs=dispatched.receipt.observation_refs,
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": dispatched.delta.model_dump(mode="json")},
            parents=[parent.id],
        )
        return (
            command.kind,
            trace.add(
                "RecoveryReenteredPhase",
                {"state": state.phase, "reentry_phase": command.reentry_phase.value},
                parents=[parent.id],
            ),
        )

    @staticmethod
    def complete_pending_plan_change(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        kind: RecoveryCommandKind,
        plan_or_route_ref: str,
    ) -> TraceNode:
        failure = state.current_failure
        command = _pending_legacy_command(state)
        if failure is None or command is None or command.kind != kind:
            return parent
        completion = successful_recovery_completion(
            failure=failure,
            command=command,
            state_version=state.version,
            retired_assumptions=tuple(state.disproved_assumptions[-1:]),
            fingerprint_ref=plan_or_route_ref,
            plan_or_route_ref=plan_or_route_ref,
        )
        state.recovery_history.append(completion.history)
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=state.current_recovery_decision.decision_id
            if state.current_recovery_decision is not None
            else command.command_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=tuple(
                RecoveryDimension(item.value) for item in command.changed_dimensions
            ),
            next_phase=RuntimePhase(command.reentry_phase.value),
            artifact_refs=completion.receipt.artifact_refs,
            observation_refs=completion.receipt.observation_refs,
        )
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": completion.receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": completion.delta.model_dump(mode="json")},
            parents=[parent.id],
        )
        return trace.add(
            "RecoveryReenteredPhase",
            {"state": state.phase, "reentry_phase": command.reentry_phase.value},
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
        command = _pending_legacy_command(state)
        if failure is None or command is None:
            return parent, False
        if command.kind not in {
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.REROUTE,
        }:
            return parent, False
        candidate_id = (
            contract.grounding_candidate.candidate_id
            if contract.grounding_candidate is not None
            else ""
        )
        fresh_epoch = bool(contract.snapshot_id and contract.snapshot_id != failure.snapshot_id)
        route_matches = bool(
            command.kind == RecoveryCommandKind.REGROUND
            or (command.candidate_id and candidate_id == command.candidate_id)
            or (command.route_ref and contract.backend == command.route_ref)
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
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"contract:{contract.contract_hash or contract.id}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            new_plan_or_route_ref=candidate_id or contract.id,
            explanation=command.expected_change,
        )
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=True,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            route_refs=tuple(item for item in (candidate_id, contract.id) if item),
            delta=delta,
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=state.current_recovery_decision.decision_id
            if state.current_recovery_decision is not None
            else command.command_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=tuple(
                RecoveryDimension(item.value) for item in command.changed_dimensions
            ),
            next_phase=RuntimePhase(command.reentry_phase.value),
        )
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": delta.model_dump(mode="json")},
            parents=[parent.id],
        )
        return (
            trace.add(
                "RecoveryReenteredPhase",
                {"state": state.phase, "reentry_phase": command.reentry_phase.value},
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
        command = _pending_legacy_command(state)
        if command is None:
            return parent
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=False,
            state_before=f"state:{command.based_on_state_version}",
            state_after=f"state:{state.version}",
            error_code=error_code,
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=state.current_recovery_decision.decision_id
            if state.current_recovery_decision is not None
            else command.command_id,
            failure_id=command.failure_id,
            success=False,
            changed_dimensions=tuple(
                RecoveryDimension(item.value) for item in command.changed_dimensions
            ),
            next_phase=RuntimePhase.ABORTED,
            error_code=error_code,
        )
        return trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )

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
        command = _pending_legacy_command(state)
        if (
            failure is None
            or command is None
            or command.kind != RecoveryCommandKind.RETRY_IDEMPOTENT
        ):
            return parent
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"contract:{contract.contract_hash or contract.id}:snapshot:{observation.snapshot_id}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            new_evidence_refs=tuple(
                item
                for item in execution_receipt.evidence.values()
                if isinstance(item, str)
            ),
            new_plan_or_route_ref=contract.id,
            explanation=command.expected_change,
        )
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=execution_receipt.success,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            observation_refs=(observation.snapshot_id,) if observation.snapshot_id else (),
            plan_refs=(contract.id,),
            error_code=(
                ""
                if execution_receipt.success
                else (
                    execution_receipt.error_code.value
                    if execution_receipt.error_code is not None
                    else RuntimeErrorCode.EXECUTION_FAILED.value
                )
            ),
            delta=delta,
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=state.current_recovery_decision.decision_id
            if state.current_recovery_decision is not None
            else command.command_id,
            failure_id=failure.failure_id,
            success=execution_receipt.success,
            changed_dimensions=tuple(
                RecoveryDimension(item.value) for item in command.changed_dimensions
            ),
            next_phase=RuntimePhase(command.reentry_phase.value),
            artifact_refs=tuple(
                item for item in execution_receipt.evidence.values() if isinstance(item, str)
            ),
            observation_refs=(observation.snapshot_id,) if observation.snapshot_id else (),
            error_code=receipt.error_code,
        )
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        return trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": delta.model_dump(mode="json")},
            parents=[parent.id],
        )

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
        command = _pending_legacy_command(state)
        if failure is None or command is None:
            return parent, False
        observation_commands = {
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.INSPECT_POST_STATE,
        }
        if command.kind not in observation_commands:
            return parent, False
        if post_state_inspection_failed:
            failed_receipt = RecoveryCommandReceipt(
                command_id=command.command_id,
                success=False,
                state_before=f"state:{failure.state_version}",
                state_after=f"state:{state.version}",
                error_code=RuntimeErrorCode.VERIFICATION_FAILED.value,
            )
            state.current_recovery_outcome = RecoveryOutcome(
                decision_id=state.current_recovery_decision.decision_id
                if state.current_recovery_decision is not None
                else command.command_id,
                failure_id=failure.failure_id,
                success=False,
                changed_dimensions=tuple(
                    RecoveryDimension(item.value) for item in command.changed_dimensions
                ),
                next_phase=RuntimePhase.ABORTED,
                error_code=RuntimeErrorCode.VERIFICATION_FAILED.value,
            )
            parent = trace.add(
                "RecoveryCommandCompleted",
                {
                    "state": state.phase,
                    "receipt": failed_receipt.model_dump(mode="json"),
                },
                parents=[parent.id],
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
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"{snapshot.observation.snapshot_id}:state:{state.version}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            new_evidence_refs=tuple(snapshot.observation.artifact_refs),
            new_plan_or_route_ref=command.route_ref or command.candidate_id,
            explanation=command.expected_change,
        )
        recovery_receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=True,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            artifact_refs=tuple(snapshot.observation.artifact_refs),
            observation_refs=(snapshot.observation.snapshot_id,),
            route_refs=tuple(
                item for item in (command.route_ref, command.candidate_id) if item
            ),
            verification_refs=(verification.status.value,) if verification is not None else (),
            delta=delta,
        )
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_outcome = RecoveryOutcome(
            decision_id=state.current_recovery_decision.decision_id
            if state.current_recovery_decision is not None
            else command.command_id,
            failure_id=failure.failure_id,
            success=True,
            changed_dimensions=tuple(
                RecoveryDimension(item.value) for item in command.changed_dimensions
            ),
            next_phase=RuntimePhase(command.reentry_phase.value),
            artifact_refs=tuple(snapshot.observation.artifact_refs),
            observation_refs=(snapshot.observation.snapshot_id,),
        )
        parent = trace.add(
            "RecoveryCommandCompleted",
            {
                "state": state.phase,
                "receipt": recovery_receipt.model_dump(mode="json"),
            },
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {
                "state": state.phase,
                "delta": delta.model_dump(mode="json"),
            },
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryReenteredPhase",
            {
                "state": state.phase,
                "reentry_phase": command.reentry_phase.value,
            },
            parents=[parent.id],
        )
        return parent, False


def _available_recovery_kinds(
    available_commands: frozenset[RecoveryCommandKind],
    owner_available_commands: frozenset[RecoveryCommandKind],
) -> frozenset[RecoveryKind]:
    return frozenset(
        RecoveryKind(kind.value)
        for kind in available_commands
        if kind not in OWNER_DISPATCH_COMMANDS or kind in owner_available_commands
    )


def _pending_legacy_command(state: StateKernel) -> RecoveryCommand | None:
    if state.current_recovery_outcome is not None:
        return None
    decision = state.current_recovery_decision
    failure = state.current_failure
    if decision is None or failure is None:
        return None
    return legacy_command_from_recovery_decision(
        decision,
        effect_status=failure.effect_status,
        gap_ids=tuple(item.gap_id for item in state.evidence_gaps),
    )


def _trace_recovery_protocol(
    trace: TraceDag,
    parent: TraceNode,
    *,
    state_phase: str,
    failure: FailureEnvelope,
    decision: RecoveryDecision,
    command: RecoveryCommand,
) -> TraceNode:
    for projection in recovery_protocol_projections(
        state_phase=state_phase,
        failure=failure,
        decision=decision,
        command=command,
    ):
        parent = trace.add(projection.kind, projection.payload, parents=[parent.id])
    return parent


def _complete_immediate_recovery_command(
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    *,
    failure: FailureEnvelope,
    decision: RecoveryDecision,
    command: RecoveryCommand,
) -> tuple[RecoveryCommandKind, TraceNode]:
    terminal_phase = {
        RecoveryReentryPhase.WAITING_USER: RuntimeStep.WAITING_CLARIFICATION.value,
        RecoveryReentryPhase.WAITING_APPROVAL: RuntimeStep.WAITING_APPROVAL.value,
        RecoveryReentryPhase.DEFERRED: RuntimeStep.DEFERRED.value,
        RecoveryReentryPhase.FAILED: RuntimeStep.FAILED.value,
        RecoveryReentryPhase.ABORTED: RuntimeStep.ABORTED.value,
    }.get(command.reentry_phase)
    if terminal_phase is None:
        raise ValueError(f"unsupported immediate recovery re-entry: {command.reentry_phase.value}")
    state.transition(terminal_phase)
    completion = successful_recovery_completion(
        failure=failure,
        command=command,
        state_version=state.version,
        retired_assumptions=tuple(state.disproved_assumptions[-1:]),
        fingerprint_ref=state.phase,
        plan_or_route_ref=command.provider_id,
    )
    state.recovery_history.append(completion.history)
    state.current_recovery_outcome = RecoveryOutcome(
        decision_id=state.current_recovery_decision.decision_id
        if state.current_recovery_decision is not None
        else command.command_id,
        failure_id=failure.failure_id,
        success=True,
        changed_dimensions=tuple(
            RecoveryDimension(item.value) for item in command.changed_dimensions
        ),
        next_phase=RuntimePhase(command.reentry_phase.value),
        artifact_refs=completion.receipt.artifact_refs,
        observation_refs=completion.receipt.observation_refs,
    )
    parent = trace.add(
        "RecoveryCommandCompleted",
        {"state": state.phase, "receipt": completion.receipt.model_dump(mode="json")},
        parents=[parent.id],
    )
    parent = trace.add(
        "RecoveryDeltaValidated",
        {"state": state.phase, "delta": completion.delta.model_dump(mode="json")},
        parents=[parent.id],
    )
    return (
        command.kind,
        trace.add(
            "RecoveryReenteredPhase",
            {"state": state.phase, "reentry_phase": command.reentry_phase.value},
            parents=[parent.id],
        ),
    )
