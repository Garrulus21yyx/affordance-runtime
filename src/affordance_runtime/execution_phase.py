"""Coordinator-facing action execution seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from affordance_runtime.artifacts import ArtifactRef
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode
from affordance_runtime.perception_session import PerceptionSession
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_evidence import verification_confirms_effect_absent
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_skill_phase import task_skill_progress
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport

WriteReceipt = Callable[[str, int, ExecutionReceipt], ArtifactRef | None]
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
TerminalRecoveryStatus = Callable[[StateKernel], RuntimeStep]
TraceRecoveryStarted = Callable[[TraceDag, TraceNode, StateKernel, RecoveryKind], TraceNode]


@dataclass(frozen=True)
class ExecutionPhaseTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode | None


@dataclass(frozen=True)
class ExecutionPhaseResult:
    parent: TraceNode
    receipt: ExecutionReceipt | None = None
    latest_verification: VerificationReport | None = None
    terminal: ExecutionPhaseTerminal | None = None
    continue_observing: bool = False


class ExecutionPhase:
    """Execute the current contract and handle receipt-level failures."""

    def run(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        execution_observation: Observation,
        contract_execution_loop: ContractExecutionLoop,
        perception_session: PerceptionSession,
        recovery_phase: RecoveryPhase,
        task_skill_runtime: AcceptedTaskSkillRuntime | None,
        recovery_enabled: bool,
        write_receipt: WriteReceipt,
        write_observation: WriteObservation,
        index_artifact: IndexArtifact,
        index_paths: IndexPaths,
        trace_source_arbitration: TraceSourceArbitration,
        fulfill_targeted_perception: FulfillTargetedPerception,
        recover_execution_failure: RecoverExecutionFailure,
        terminal_recovery_status: TerminalRecoveryStatus,
        trace_recovery_started: TraceRecoveryStarted,
    ) -> ExecutionPhaseResult:
        state.transition(RuntimeStep.ACTING.value)
        parent = trace.add(
            "ActionStarted",
            {"state": state.phase, "contract_id": contract.id},
            parents=[parent.id],
        )
        receipt = contract_execution_loop.execute(contract, execution_observation)
        state.record_receipt(receipt)
        state.step_count += 1
        state.record_subgoal_action()
        if contract.required_capabilities:
            state.effectful_action_count += 1
        receipt_ref = write_receipt(envelope.task_id, state.step_count, receipt)
        index_artifact(trace, receipt_ref)
        parent = recovery_phase.complete_pending_execution(
            state,
            trace,
            parent,
            contract,
            receipt,
            execution_observation,
        )
        if receipt.success:
            return ExecutionPhaseResult(parent=parent, receipt=receipt)

        if not recovery_enabled:
            state.transition(RuntimeStep.FAILED.value)
            parent = trace.add(
                "TaskFailed",
                {"state": state.phase, "reason": "recovery layer disabled"},
                parents=[parent.id],
            )
            return ExecutionPhaseResult(
                parent=parent,
                receipt=receipt,
                terminal=ExecutionPhaseTerminal(
                    RuntimeStep.FAILED,
                    receipt.error_code or RuntimeErrorCode.EXECUTION_FAILED,
                ),
            )

        recovery_result, parent = recover_execution_failure(
            envelope,
            state,
            trace,
            parent,
            contract,
            receipt,
            receipt.error_code,
        )
        parent = trace_recovery_started(trace, parent, state, recovery_result)
        if recovery_result in {
            RecoveryKind.REOBSERVE,
            RecoveryKind.RETRY_IDEMPOTENT,
            RecoveryKind.REROUTE,
        }:
            return ExecutionPhaseResult(
                parent=parent,
                receipt=receipt,
                continue_observing=True,
            )
        latest_verification = None
        if recovery_result == RecoveryKind.INSPECT_POST_STATE:
            inspection = perception_session.capture(
                envelope,
                state,
                state.observation_count + 1,
            )
            state.remember_observation(inspection.observation)
            inspection_ref = write_observation(
                envelope.task_id,
                state.observation_count,
                inspection,
            )
            index_artifact(trace, inspection_ref)
            index_paths(trace, inspection.observation.artifact_refs)
            parent = trace_source_arbitration(trace, parent, inspection, state.phase)
            if inspection.active_perception_requests:
                parent = trace.add(
                    "RecoveryActivePerceptionRequested",
                    {
                        "state": state.phase,
                        "reason": "post-action effect status requires additional current evidence",
                    },
                    parents=[parent.id],
                )
                inspection, parent = fulfill_targeted_perception(
                    envelope,
                    state,
                    trace,
                    parent,
                    inspection,
                )
            latest_verification = contract_execution_loop.verify(
                contract,
                receipt,
                inspection.observation,
                structural_verification_enabled=True,
                disabled_reason="",
            )
            state.latest_verification = latest_verification
            parent = trace.add(
                "RecoveryStateInspected",
                {
                    "state": state.phase,
                    "verification": latest_verification.status.value,
                    "snapshot_id": inspection.observation.snapshot_id,
                    "artifact_refs": ([inspection_ref.path] if inspection_ref else [])
                    + list(inspection.observation.artifact_refs),
                },
                parents=[parent.id],
            )
            recovery_skill_progress = (
                task_skill_progress(task_skill_runtime, state)
                if task_skill_runtime is not None
                else None
            )
            changed_skill_fallthrough = bool(
                verification_confirms_effect_absent(latest_verification)
                and recovery_skill_progress is not None
                and not recovery_skill_progress.active
            )
            parent, _recovery_must_stop = recovery_phase.complete_pending_observation(
                state,
                trace,
                parent,
                inspection,
                verification=latest_verification,
                post_state_inspection_failed=(
                    not latest_verification.passed
                    and not changed_skill_fallthrough
                ),
            )
            if latest_verification.passed:
                return ExecutionPhaseResult(
                    parent=parent,
                    receipt=receipt,
                    latest_verification=latest_verification,
                    continue_observing=True,
                )
        final_recovery_status = terminal_recovery_status(state)
        return ExecutionPhaseResult(
            parent=parent,
            receipt=receipt,
            latest_verification=latest_verification,
            terminal=ExecutionPhaseTerminal(
                final_recovery_status,
                receipt.error_code or RuntimeErrorCode.EXECUTION_FAILED,
            ),
        )
