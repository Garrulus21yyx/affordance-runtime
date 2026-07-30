"""Coordinator-facing preflight / approval seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from affordance_runtime.approval_contracts import ApprovalProvider
from affordance_runtime.artifacts import ArtifactRef
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_binding_phase import ContractBindingPhase
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.failure_envelope import EffectStatus, FailureClass, FailurePhase
from affordance_runtime.perception_session import PerceptionSession
from affordance_runtime.planning import ContractBuilder
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.safety import CapabilityGate
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.trace import TraceDag, TraceNode

WriteObservation = Callable[[str, int, BrowserSnapshot], ArtifactRef | None]
IndexArtifact = Callable[[TraceDag, ArtifactRef | None], None]
IndexPaths = Callable[[TraceDag, list[str]], None]
TraceSourceArbitration = Callable[[TraceDag, TraceNode, BrowserSnapshot, str], TraceNode]
FulfillTargetedPerception = Callable[
    [TaskEnvelope, StateKernel, TraceDag, TraceNode, BrowserSnapshot],
    tuple[BrowserSnapshot, TraceNode],
]
RecoverExecutionFailure = Callable[
    [TaskEnvelope, StateKernel, TraceDag, TraceNode, ActionContract, ExecutionReceipt | None, RuntimeErrorCode | None],
    tuple[RecoveryKind, TraceNode],
]
RecoverPhaseFailure = Callable[..., tuple[RecoveryKind, TraceNode]]
TerminalRecoveryStatus = Callable[[StateKernel], RuntimeStep]
TraceRecoveryStarted = Callable[[TraceDag, TraceNode, StateKernel, RecoveryKind], TraceNode]


@dataclass(frozen=True)
class PreflightPhaseTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode | None


@dataclass(frozen=True)
class PreflightPhaseResult:
    parent: TraceNode
    contract: ActionContract
    execution_observation: Observation
    effective_gate: object
    terminal: PreflightPhaseTerminal | None = None
    continue_observing: bool = False


class PreflightPhase:
    """Run preflight, approval, and retry-contract gates before execution."""

    def run(
        self,
        *,
        decision: PlannerDecision,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        contract_execution_loop: ContractExecutionLoop,
        contract_binding_phase: ContractBindingPhase,
        perception_session: PerceptionSession,
        approval_provider: ApprovalProvider | None,
        runtime_gate: CapabilityGate,
        preflight_enabled: bool,
        capability_gate_enabled: bool,
        max_recoveries: int,
        contract_builder: ContractBuilder | None,
        recovery_phase: RecoveryPhase,
        write_observation: WriteObservation,
        index_artifact: IndexArtifact,
        index_paths: IndexPaths,
        trace_source_arbitration: TraceSourceArbitration,
        fulfill_targeted_perception: FulfillTargetedPerception,
        recover_execution_failure: RecoverExecutionFailure,
        recover_phase_failure: RecoverPhaseFailure,
        terminal_recovery_status: TerminalRecoveryStatus,
        trace_recovery_started: TraceRecoveryStarted,
    ) -> PreflightPhaseResult:
        contract_check = contract_execution_loop.initial_check(
            contract,
            envelope,
            snapshot.observation,
            capability_gate_enabled=capability_gate_enabled,
            preflight_enabled=preflight_enabled,
        )
        effective_gate = contract_check.gate
        error = contract_check.error
        execution_observation = snapshot.observation
        preflight_snapshot = snapshot
        perception_error = None
        if error is None and preflight_enabled:
            preflight_snapshot = perception_session.capture(
                envelope,
                state,
                state.observation_count + 1,
            )
            state.remember_observation(preflight_snapshot.observation)
            preflight_ref = write_observation(
                envelope.task_id,
                state.observation_count,
                preflight_snapshot,
            )
            index_artifact(trace, preflight_ref)
            index_paths(trace, preflight_snapshot.observation.artifact_refs)
            parent = trace.add(
                "PreflightObservationCaptured",
                {
                    "state": state.phase,
                    "snapshot_id": preflight_snapshot.observation.snapshot_id,
                    "page_revision": preflight_snapshot.observation.page_revision,
                    "artifact_refs": ([preflight_ref.path] if preflight_ref else [])
                    + list(preflight_snapshot.observation.artifact_refs),
                },
                parents=[parent.id],
            )
            parent = trace_source_arbitration(trace, parent, preflight_snapshot, state.phase)
            preflight_snapshot, parent = fulfill_targeted_perception(
                envelope,
                state,
                trace,
                parent,
                preflight_snapshot,
            )
            if (
                state.perception_resolution is not None
                and state.perception_resolution.blocks_effectful_action
            ):
                perception_error = RuntimeErrorCode.PRECONDITION_FAILED
            revalidation_error = contract_execution_loop.revalidate(
                contract,
                envelope,
                preflight_snapshot.observation,
                effective_gate,
                capability_gate_enabled=False,
                include_policy=False,
                require_snapshot_identity=False,
                require_environment_revision=False,
            )
            error = perception_error or revalidation_error
            rebound = contract_binding_phase.rebind_preflight_target(
                decision=decision,
                envelope=envelope,
                state=state,
                preflight_snapshot=preflight_snapshot,
                trace=trace,
                parent=parent,
                contract=contract,
                error=error,
                effective_gate=effective_gate,
                contract_builder=contract_builder,
                contract_execution_loop=contract_execution_loop,
                capability_gate_enabled=capability_gate_enabled,
            )
            parent = rebound.parent
            contract = rebound.contract
            error = rebound.error
            execution_observation = preflight_snapshot.observation
        elif not preflight_enabled:
            parent = trace.add(
                "AblationApplied",
                {"state": state.phase, "disabled_layer": "preflight"},
                parents=[parent.id],
            )
        if error == RuntimeErrorCode.APPROVAL_REQUIRED:
            parent = trace.add(
                "HumanApprovalRequested",
                {
                    "state": RuntimeStep.WAITING_APPROVAL.value,
                    "contract_hash": contract.contract_hash,
                },
                parents=[parent.id],
            )
            token = approval_provider.approve(contract) if approval_provider else None
            if token is None:
                state.transition(RuntimeStep.WAITING_APPROVAL.value)
                return PreflightPhaseResult(
                    parent=parent,
                    contract=contract,
                    execution_observation=execution_observation,
                    effective_gate=effective_gate,
                    terminal=PreflightPhaseTerminal(RuntimeStep.WAITING_APPROVAL, error),
            )
            effective_gate.approval_tokens[token.token_id] = token
            runtime_gate.approval_tokens[token.token_id] = token
            parent = trace.add(
                "HumanApprovalGranted",
                {
                    "state": state.phase,
                    "token_id": token.token_id,
                    "approver": token.approver,
                    "capability": token.capability,
                    "expires_at_s": token.expires_at_s,
                },
                parents=[parent.id],
            )
            approval_snapshot = perception_session.capture(
                envelope,
                state,
                state.observation_count + 1,
            )
            state.remember_observation(approval_snapshot.observation)
            approval_ref = write_observation(
                envelope.task_id,
                state.observation_count,
                approval_snapshot,
            )
            index_artifact(trace, approval_ref)
            index_paths(trace, approval_snapshot.observation.artifact_refs)
            parent = trace.add(
                "ApprovalStateRevalidated",
                {
                    "state": state.phase,
                    "snapshot_id": approval_snapshot.observation.snapshot_id,
                    "page_revision": approval_snapshot.observation.page_revision,
                    "artifact_refs": ([approval_ref.path] if approval_ref else [])
                    + list(approval_snapshot.observation.artifact_refs),
                },
                parents=[parent.id],
            )
            parent = trace_source_arbitration(trace, parent, approval_snapshot, state.phase)
            error = contract_execution_loop.revalidate(
                contract,
                envelope,
                approval_snapshot.observation,
                effective_gate,
                capability_gate_enabled=True,
                include_policy=False,
                require_snapshot_identity=False,
                require_environment_revision=False,
            )
            execution_observation = approval_snapshot.observation
        if error is not None:
            if (
                error
                in {
                    RuntimeErrorCode.STALE_OBSERVATION,
                    RuntimeErrorCode.STALE_PAGE_REVISION,
                    RuntimeErrorCode.SNAPSHOT_MISMATCH,
                    RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
                    RuntimeErrorCode.LEASE_EXPIRED,
                }
                and state.recovery_count < max_recoveries
            ):
                parent = trace.add(
                    "EnvironmentDriftDetected",
                    {"state": state.phase, "error_code": error.value},
                    parents=[parent.id],
                )
                recovery_result, parent = recover_execution_failure(
                    envelope,
                    state,
                    trace,
                    parent,
                    contract,
                    None,
                    error,
                )
                parent = trace_recovery_started(trace, parent, state, recovery_result)
                if recovery_result == RecoveryKind.REOBSERVE:
                    return PreflightPhaseResult(
                        parent=parent,
                        contract=contract,
                        execution_observation=execution_observation,
                        effective_gate=effective_gate,
                        continue_observing=True,
                    )
                final_recovery_status = terminal_recovery_status(state)
                return PreflightPhaseResult(
                    parent=parent,
                    contract=contract,
                    execution_observation=execution_observation,
                    effective_gate=effective_gate,
                    terminal=PreflightPhaseTerminal(final_recovery_status, error),
                )
            _recovery_kind, parent = recover_phase_failure(
                envelope,
                state,
                trace,
                parent,
                phase=FailurePhase.PREFLIGHT,
                failure_class=(
                    FailureClass.SOURCE_CONFLICT
                    if perception_error is not None
                    else FailureClass.AUTHORITY
                    if error
                    in {
                        RuntimeErrorCode.CAPABILITY_DENIED,
                        RuntimeErrorCode.UNSAFE_ACTION,
                    }
                    else FailureClass.VALIDATION
                ),
                error_code=error,
                message=(
                    state.perception_resolution.reason
                    if perception_error is not None
                    and state.perception_resolution is not None
                    else f"preflight rejected contract: {error.value}"
                ),
                available_commands=frozenset({RecoveryKind.ABORT}),
                snapshot=preflight_snapshot if preflight_enabled else snapshot,
                expected_effect=contract.intent,
                recoverable=False,
            )
            parent = trace.add(
                "PreflightBlocked",
                {"state": state.phase, "error_code": error.value},
                parents=[parent.id],
            )
            return PreflightPhaseResult(
                parent=parent,
                contract=contract,
                execution_observation=execution_observation,
                effective_gate=effective_gate,
                terminal=PreflightPhaseTerminal(RuntimeStep.ABORTED, error),
            )
        authorization_error = effective_gate.authorize(contract) if capability_gate_enabled else None
        if authorization_error is not None:
            _recovery_kind, parent = recover_phase_failure(
                envelope,
                state,
                trace,
                parent,
                phase=FailurePhase.PREFLIGHT,
                failure_class=FailureClass.AUTHORITY,
                error_code=authorization_error,
                message=f"contract authorization rejected: {authorization_error.value}",
                available_commands=frozenset({RecoveryKind.ABORT}),
                snapshot=snapshot,
                expected_effect=contract.intent,
                recoverable=False,
            )
            return PreflightPhaseResult(
                parent=parent,
                contract=contract,
                execution_observation=execution_observation,
                effective_gate=effective_gate,
                terminal=PreflightPhaseTerminal(RuntimeStep.ABORTED, authorization_error),
            )
        parent = trace.add("PreflightPassed", {"state": state.phase}, parents=[parent.id])

        retry_error = pending_retry_contract_error(state, contract)
        if retry_error is not None:
            parent = recovery_phase.fail_pending_command(
                state,
                trace,
                parent,
                error_code=retry_error.value,
            )
            state.transition(RuntimeStep.ABORTED.value)
            parent = trace.add(
                "RecoveryAborted",
                {
                    "state": state.phase,
                    "reason": "retry contract did not retain validated idempotency and effect scope",
                },
                parents=[parent.id],
            )
            return PreflightPhaseResult(
                parent=parent,
                contract=contract,
                execution_observation=execution_observation,
                effective_gate=effective_gate,
                terminal=PreflightPhaseTerminal(RuntimeStep.ABORTED, retry_error),
            )
        return PreflightPhaseResult(
            parent=parent,
            contract=contract,
            execution_observation=execution_observation,
            effective_gate=effective_gate,
        )


def pending_retry_contract_error(
    state: StateKernel,
    contract: ActionContract,
) -> RuntimeErrorCode | None:
    decision = state.current_recovery_decision
    if decision is None or decision.kind != RecoveryKind.RETRY_IDEMPOTENT:
        return None
    effect_status = (
        state.current_failure.effect_status
        if state.current_failure is not None
        else EffectStatus.NOT_DISPATCHED
    )
    if (
        not contract.idempotency_key
        or contract.idempotency_key != decision.idempotency_key
        or effect_status
        not in {EffectStatus.NOT_DISPATCHED, EffectStatus.CONFIRMED_NOT_OCCURRED}
    ):
        return RuntimeErrorCode.UNSAFE_ACTION
    return None
