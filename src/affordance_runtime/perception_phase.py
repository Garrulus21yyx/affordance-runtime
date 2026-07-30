"""Coordinator-facing perception seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from affordance_runtime.active_perception import PerceptionResolutionStatus
from affordance_runtime.active_perception_flow import (
    ActivePerceptionFlow,
    ActivePerceptionFlowContext,
)
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
from affordance_runtime.task_intake import OperationClass
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


class ActivePerceptionBudgetView(Protocol):
    @property
    def max_active_perception_observations(self) -> int: ...

    @property
    def max_observations(self) -> int: ...


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
        active_perception_flow: ActivePerceptionFlow,
        budget: ActivePerceptionBudgetView,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        task_skill_progress_for: Callable[
            [object | None, StateKernel], TaskSkillRunState | None
        ],
        write_observation: Callable[..., ArtifactRef | None],
        index_artifact: Callable[..., None],
        index_paths: Callable[..., None],
        trace_source_arbitration: Callable[..., TraceNode],
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
        snapshot, parent = self.fulfill_targeted_perception(
            envelope=envelope,
            state=state,
            trace=trace,
            parent=parent,
            snapshot=snapshot,
            active_perception_flow=active_perception_flow,
            budget=budget,
            write_observation=write_observation,
            index_artifact=index_artifact,
            index_paths=index_paths,
            trace_source_arbitration=trace_source_arbitration,
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

    def fulfill_targeted_perception(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        *,
        active_perception_flow: ActivePerceptionFlow,
        budget: ActivePerceptionBudgetView,
        write_observation: Callable[..., ArtifactRef | None],
        index_artifact: Callable[..., None],
        index_paths: Callable[..., None],
        trace_source_arbitration: Callable[..., TraceNode],
    ) -> tuple[BrowserSnapshot, TraceNode]:
        while True:
            task_plan = state.task_plan
            preparation = active_perception_flow.prepare(
                ActivePerceptionFlowContext(
                    snapshot=snapshot,
                    run_id=envelope.task_id,
                    task_revision=(
                        task_plan.task_revision
                        if task_plan is not None
                        else envelope.task_spec.revision
                        if envelope.task_spec is not None
                        else 1
                    ),
                    plan_version=task_plan.plan_version if task_plan is not None else 0,
                    active_subgoal_id=(
                        state.plan_progress.active_subgoal_id
                        if state.plan_progress is not None
                        else ""
                    ),
                    state_version=state.version,
                    remaining_observations=min(
                        budget.max_active_perception_observations
                        - state.active_perception_count,
                        budget.max_observations - state.observation_count,
                    ),
                    attempted_probe_fingerprints=frozenset(
                        state.attempted_probe_fingerprints
                    ),
                    effectful_action=(
                        envelope.task_spec is not None
                        and envelope.task_spec.operation_class
                        not in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
                    ),
                )
            )
            state.evidence_gaps = preparation.gaps
            if not preparation.gaps:
                break
            parent = trace.add(
                "EvidenceGapDetected",
                {
                    "state": state.phase,
                    "snapshot_id": snapshot.observation.snapshot_id,
                    "gaps": [item.model_dump(mode="json") for item in preparation.gaps],
                },
                parents=[parent.id],
            )
            decision = preparation.decision
            if decision is None:
                raise RuntimeError("active perception flow omitted a decision")
            if not preparation.targeted_capture_available:
                state.perception_resolution = decision.resolution
                parent = trace.add(
                    "TargetedPerceptionUnavailable",
                    {
                        "state": state.phase,
                        "reason": "observation source has no capture_targeted port",
                    },
                    parents=[parent.id],
                )
                parent = self._trace_perception_resolution(
                    trace,
                    parent,
                    state,
                    decision.resolution,
                )
                break
            if decision.plan is None:
                state.perception_resolution = decision.resolution
                parent = trace.add(
                    "TargetedPerceptionBudgetExhausted",
                    {
                        "state": state.phase,
                        "active_perception_count": state.active_perception_count,
                        "max_active_perception_observations": (
                            budget.max_active_perception_observations
                        ),
                        "reason": (
                            decision.resolution.reason
                            if decision.resolution is not None
                            else ""
                        ),
                    },
                    parents=[parent.id],
                )
                parent = self._trace_perception_resolution(
                    trace,
                    parent,
                    state,
                    decision.resolution,
                )
                break
            plan = decision.plan
            state.active_probe_plan = plan
            if preparation.selected_probe_fingerprint:
                state.attempted_probe_fingerprints.add(
                    preparation.selected_probe_fingerprint
                )
            command = plan.commands[0]
            parent = trace.add(
                "ActivePerceptionPlanned",
                {
                    "state": state.phase,
                    "plan": plan.model_dump(mode="json"),
                    "remaining_budget": preparation.budget.model_dump(mode="json"),
                },
                parents=[parent.id],
            )
            parent = trace.add(
                "ProbeStarted",
                {
                    "state": state.phase,
                    "command": command.model_dump(mode="json"),
                },
                parents=[parent.id],
            )
            probe_result = active_perception_flow.execute(preparation)
            state.active_perception_count += 1
            state.probe_receipts.append(probe_result.receipt)
            state.perception_resolution = probe_result.resolution
            targeted = probe_result.targeted_snapshot
            if targeted is None:
                parent = trace.add(
                    "ProbeCompleted",
                    {
                        "state": state.phase,
                        "receipt": probe_result.receipt.model_dump(mode="json"),
                    },
                    parents=[parent.id],
                )
                parent = self._trace_perception_resolution(
                    trace,
                    parent,
                    state,
                    probe_result.resolution,
                )
                break
            state.remember_observation(targeted.observation)
            targeted_ref = write_observation(
                run_id=envelope.task_id,
                sequence=state.observation_count,
                snapshot=targeted,
            )
            index_artifact(trace, targeted_ref)
            index_paths(trace, targeted.observation.artifact_refs)
            parent = trace.add(
                "TargetedPerceptionCaptured",
                {
                    "state": state.phase,
                    "snapshot_id": targeted.observation.snapshot_id,
                    "page_revision": targeted.observation.page_revision,
                    "environment_revision": targeted.observation.environment_revision,
                    "artifact_refs": ([targeted_ref.path] if targeted_ref else [])
                    + list(targeted.observation.artifact_refs),
                    "source_observations": [
                        {
                            "source": item.source.value,
                            "parser_id": item.parser_id,
                            "observation_epoch_id": item.observation_epoch_id,
                        }
                        for item in targeted.source_observations
                    ],
                },
                parents=[parent.id],
            )
            parent = trace.add(
                "ProbeCompleted",
                {
                    "state": state.phase,
                    "receipt": probe_result.receipt.model_dump(mode="json"),
                },
                parents=[parent.id],
            )
            parent = trace_source_arbitration(trace, parent, targeted, state.phase)
            parent = self._trace_perception_resolution(
                trace,
                parent,
                state,
                probe_result.resolution,
            )
            snapshot = targeted
        return snapshot, parent

    @staticmethod
    def _trace_perception_resolution(
        trace: TraceDag,
        parent: TraceNode,
        state: StateKernel,
        resolution: Any,
    ) -> TraceNode:
        if resolution is None:
            return parent
        event = (
            "EvidenceGapResolved"
            if resolution.status == PerceptionResolutionStatus.RESOLVED
            else "EvidenceGapUnresolved"
        )
        return trace.add(
            event,
            {
                "state": state.phase,
                "resolution": resolution.model_dump(mode="json"),
            },
            parents=[parent.id],
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
