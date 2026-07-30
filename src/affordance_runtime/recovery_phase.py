"""Coordinator-facing SAR-8 recovery phase seam."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.failure_envelope import FailureEnvelope
from affordance_runtime.recovery_command_dispatcher import (
    OWNER_DISPATCH_COMMANDS,
    RecoveryCommandDispatcher,
)
from affordance_runtime.recovery_commands import (
    RecoveryCommandKind,
    RecoveryReentryPhase,
)
from affordance_runtime.recovery_completion import successful_recovery_completion
from affordance_runtime.recovery_coordinator import (
    RecoveryCoordinator,
    RecoveryHistoryItem,
    RecoverySelectionContext,
)
from affordance_runtime.recovery_decision_compatibility import (
    legacy_plan_from_recovery_decision,
)
from affordance_runtime.recovery_protocol import classify_failure
from affordance_runtime.recovery_trace_projection import recovery_protocol_projections
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode


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
    ) -> tuple[RecoveryCommandKind, TraceNode]:
        available = frozenset(
            kind
            for kind in available_commands
            if kind not in OWNER_DISPATCH_COMMANDS
            or kind in self.command_dispatcher.available_commands
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
            abort_reentry_phase=abort_reentry_phase,
        )
        decision = self.coordinator.decide(
            failure,
            classify_failure(failure),
            recovery_context,
            current_state_version=state.version,
        )
        plan = legacy_plan_from_recovery_decision(
            decision,
            failure,
            effect_status=failure.effect_status,
            profile_digest=runtime_profile_digest,
            gap_ids=recovery_context.gap_ids,
        )
        state.current_failure = failure
        state.current_recovery_plan = plan
        command = plan.commands[0]
        state.attempted_recovery_strategy_ids.add(command.strategy_id)
        state.recovery_count += 1
        parent = _trace_recovery_protocol(trace, parent, state)
        if command.kind in {
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.ACTIVE_PERCEPTION,
            RecoveryCommandKind.INSPECT_POST_STATE,
            RecoveryCommandKind.RETRY_IDEMPOTENT,
        }:
            state.transition(RuntimeStep.OBSERVING.value)
            return command.kind, parent
        if command.kind in {
            RecoveryCommandKind.REPLAN_STEP,
            RecoveryCommandKind.REPLAN_TASK,
        }:
            state.replan_count += 1
            state.record_disproved_assumption(
                f"{failure.phase.value}:{failure.error_code}:{failure.message}"
            )
            state.transition(RuntimeStep.OBSERVING.value)
            return command.kind, parent
        if command.kind in OWNER_DISPATCH_COMMANDS:
            return self._dispatch_owner_command(
                failure,
                state,
                trace,
                parent,
                abort_reentry_phase=abort_reentry_phase,
            )
        return _complete_immediate_recovery_command(state, trace, parent)

    def _dispatch_owner_command(
        self,
        failure: FailureEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        abort_reentry_phase: RecoveryReentryPhase,
    ) -> tuple[RecoveryCommandKind, TraceNode]:
        plan = state.current_recovery_plan
        if plan is None:
            raise ValueError("owner recovery dispatch requires a pending plan")
        command = plan.commands[0]
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        dispatched = self.command_dispatcher.dispatch(
            command,
            previous_attempt_fingerprint=previous_fingerprint,
        )
        state.recovery_receipts.append(dispatched.receipt)
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": dispatched.receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        if not dispatched.receipt.success or dispatched.delta is None:
            state.current_recovery_plan = None
            state.transition(abort_reentry_phase.value)
            return RecoveryCommandKind.ABORT, parent
        state.replan_count += 1
        state.record_disproved_assumption(
            f"{failure.phase.value}:{failure.error_code}:{failure.message}"
        )
        state.recovery_deltas.append(dispatched.delta)
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                dispatched.delta.next_attempt_fingerprint,
            )
        )
        state.current_recovery_plan = None
        state.transition(RuntimeStep.OBSERVING.value)
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


def _trace_recovery_protocol(
    trace: TraceDag,
    parent: TraceNode,
    state: StateKernel,
) -> TraceNode:
    failure = state.current_failure
    plan = state.current_recovery_plan
    if failure is None or plan is None:
        return parent
    for projection in recovery_protocol_projections(
        state_phase=state.phase,
        failure=failure,
        plan=plan,
    ):
        parent = trace.add(projection.kind, projection.payload, parents=[parent.id])
    return parent


def _complete_immediate_recovery_command(
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
) -> tuple[RecoveryCommandKind, TraceNode]:
    failure = state.current_failure
    plan = state.current_recovery_plan
    if failure is None or plan is None:
        raise ValueError("immediate recovery completion requires failure and plan")
    command = plan.commands[0]
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
    state.recovery_deltas.append(completion.delta)
    state.recovery_receipts.append(completion.receipt)
    state.recovery_history.append(completion.history)
    state.current_recovery_plan = None
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
