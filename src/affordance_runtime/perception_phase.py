"""Coordinator-facing perception seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from affordance_runtime.artifacts import ArtifactRef
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureClass, FailurePhase
from affordance_runtime.perception_session import PerceptionSession
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_evidence import verification_confirms_effect_absent
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


@dataclass(frozen=True)
class PerceptionTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode


@dataclass(frozen=True)
class PerceptionPhaseResult:
    parent: TraceNode
    snapshot: BrowserSnapshot | None = None
    latest_verification: VerificationReport | None = None
    terminal: PerceptionTerminal | None = None
    continue_observing: bool = False


class PerceptionPhase:
    """Capture and commit the current observation behind a named seam."""

    def run(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        perception_session: PerceptionSession,
        contract_execution_loop: ContractExecutionLoop,
        recovery_phase: RecoveryPhase,
        task_skill_runtime: object | None,
        recovery_enabled: bool,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        task_skill_progress_for: Callable[
            [object | None, StateKernel], TaskSkillRunState | None
        ],
        write_observation: Callable[..., ArtifactRef | None],
        index_artifact: Callable[..., None],
        index_paths: Callable[..., None],
        trace_source_arbitration: Callable[..., TraceNode],
        fulfill_targeted_perception: Callable[
            [TaskEnvelope, StateKernel, TraceDag, TraceNode, BrowserSnapshot],
            tuple[BrowserSnapshot, TraceNode],
        ],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
    ) -> PerceptionPhaseResult:
        if state.phase in {RuntimeStep.CREATED.value, RuntimeStep.RECOVERING.value}:
            state.transition(RuntimeStep.OBSERVING.value)
        try:
            snapshot = perception_session.capture(
                envelope,
                state,
                state.observation_count + 1,
            )
        except Exception as exc:
            return self._handle_observation_failure(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                error=exc,
                recovery_enabled=recovery_enabled,
                recover_phase_failure=recover_phase_failure,
            )
        state.remember_observation(snapshot.observation)
        observation_ref = write_observation(
            envelope.task_id,
            state.observation_count,
            snapshot,
        )
        parent = trace.add(
            "ObservationCaptured",
            {
                "state": state.phase,
                "snapshot_id": snapshot.observation.snapshot_id,
                "page_revision": snapshot.observation.page_revision,
                "environment_revision": snapshot.observation.environment_revision,
                "url": snapshot.observation.url,
                "artifact_refs": ([observation_ref.path] if observation_ref else [])
                + list(snapshot.observation.artifact_refs),
                "perception_requirements": snapshot.observation.metadata.get(
                    "perception_requirements"
                ),
                "source_observations": [
                    {
                        "source": item.source.value,
                        "parser_id": item.parser_id,
                        "observation_epoch_id": item.observation_epoch_id,
                        "artifact_refs": list(item.artifact_refs),
                    }
                    for item in snapshot.source_observations
                ],
            },
            parents=[parent.id],
        )
        index_artifact(trace, observation_ref)
        index_paths(trace, snapshot.observation.artifact_refs)
        parent = trace_source_arbitration(trace, parent, snapshot, state.phase)
        snapshot, parent = fulfill_targeted_perception(
            envelope,
            state,
            trace,
            parent,
            snapshot,
        )
        recovered_verification, recovery_inspection_failed, parent = (
            self._inspect_pending_recovery_state(
                state=state,
                trace=trace,
                parent=parent,
                snapshot=snapshot,
                pending_recovery_kind=pending_recovery_kind,
                contract_execution_loop=contract_execution_loop,
                task_skill_runtime=task_skill_runtime,
                task_skill_progress_for=task_skill_progress_for,
            )
        )
        parent, recovery_must_stop = recovery_phase.complete_pending_observation(
            state,
            trace,
            parent,
            snapshot,
            verification=recovered_verification,
            post_state_inspection_failed=recovery_inspection_failed,
        )
        if recovery_must_stop:
            state.transition(RuntimeStep.ABORTED.value)
            return PerceptionPhaseResult(
                parent=parent,
                snapshot=snapshot,
                latest_verification=recovered_verification,
                terminal=PerceptionTerminal(
                    RuntimeStep.ABORTED,
                    RuntimeErrorCode.PRECONDITION_FAILED,
                ),
            )
        if (
            state.perception_resolution is not None
            and state.perception_resolution.blocks_effectful_action
        ):
            _recovery_kind, parent = recover_phase_failure(
                envelope,
                state,
                trace,
                parent,
                phase=FailurePhase.FUSION,
                failure_class=FailureClass.SOURCE_CONFLICT,
                error_code=RuntimeErrorCode.PRECONDITION_FAILED,
                message=state.perception_resolution.reason,
                available_commands=frozenset({RecoveryKind.ABORT}),
                snapshot=snapshot,
                recoverable=False,
            )
            parent = trace.add(
                (
                    "PerceptionBlockedEffectfulRepeat"
                    if state.receipts
                    else "PerceptionBlockedEffectfulAction"
                ),
                {
                    "state": state.phase,
                    "resolution": state.perception_resolution.model_dump(mode="json"),
                },
                parents=[parent.id],
            )
            return PerceptionPhaseResult(
                parent=parent,
                snapshot=snapshot,
                latest_verification=recovered_verification,
                terminal=PerceptionTerminal(
                    RuntimeStep.ABORTED,
                    RuntimeErrorCode.PRECONDITION_FAILED,
                ),
            )
        return PerceptionPhaseResult(
            parent=parent,
            snapshot=snapshot,
            latest_verification=recovered_verification,
        )

    def _handle_observation_failure(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        error: Exception,
        recovery_enabled: bool,
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
    ) -> PerceptionPhaseResult:
        if not recovery_enabled:
            state.transition(RuntimeStep.FAILED.value)
            parent = trace.add(
                "ObservationFailed",
                {
                    "state": state.phase,
                    "error_code": RuntimeErrorCode.PRECONDITION_FAILED.value,
                    "reason": f"{type(error).__name__}: {error}"[:500],
                },
                parents=[parent.id],
            )
            return PerceptionPhaseResult(
                parent=parent,
                terminal=PerceptionTerminal(
                    RuntimeStep.FAILED,
                    RuntimeErrorCode.PRECONDITION_FAILED,
                ),
            )
        recovery_kind, parent = recover_phase_failure(
            envelope,
            state,
            trace,
            parent,
            phase=FailurePhase.OBSERVATION,
            failure_class=FailureClass.INTERNAL,
            error_code=RuntimeErrorCode.PRECONDITION_FAILED,
            message=f"{type(error).__name__}: {error}"[:500],
            available_commands=frozenset(
                {
                    RecoveryKind.REOBSERVE,
                    RecoveryKind.ABORT,
                }
            ),
        )
        if recovery_kind == RecoveryKind.REOBSERVE:
            return PerceptionPhaseResult(parent=parent, continue_observing=True)
        return PerceptionPhaseResult(
            parent=parent,
            terminal=PerceptionTerminal(
                RuntimeStep(state.phase),
                RuntimeErrorCode.PRECONDITION_FAILED,
            ),
        )

    def _inspect_pending_recovery_state(
        self,
        *,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        contract_execution_loop: ContractExecutionLoop,
        task_skill_runtime: object | None,
        task_skill_progress_for: Callable[
            [object | None, StateKernel], TaskSkillRunState | None
        ],
    ) -> tuple[VerificationReport | None, bool, TraceNode]:
        if pending_recovery_kind(state) != RecoveryKind.INSPECT_POST_STATE:
            return None, False, parent
        contract = state.current_contract
        execution_receipt = state.receipts[-1] if state.receipts else None
        if contract is None or execution_receipt is None:
            raise ValueError(
                "post-state recovery inspection requires contract and receipt lineage"
            )
        recovered_verification = contract_execution_loop.verify(
            contract,
            execution_receipt,
            snapshot.observation,
            structural_verification_enabled=True,
            disabled_reason="",
        )
        state.latest_verification = recovered_verification
        parent = trace.add(
            "RecoveryStateInspected",
            {
                "state": state.phase,
                "verification": recovered_verification.status.value,
                "snapshot_id": snapshot.observation.snapshot_id,
                "artifact_refs": snapshot.observation.artifact_refs,
            },
            parents=[parent.id],
        )
        recovery_skill_progress = (
            task_skill_progress_for(task_skill_runtime, state)
            if task_skill_runtime is not None
            else None
        )
        changed_skill_fallthrough = bool(
            verification_confirms_effect_absent(recovered_verification)
            and recovery_skill_progress is not None
            and not recovery_skill_progress.active
        )
        return (
            recovered_verification,
            not recovered_verification.passed and not changed_skill_fallthrough,
            parent,
        )
