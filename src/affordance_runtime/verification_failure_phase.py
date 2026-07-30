"""Coordinator-facing verification-failure seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from affordance_runtime.artifacts import ArtifactRef
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


@dataclass(frozen=True)
class VerificationFailureTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode


@dataclass(frozen=True)
class VerificationFailurePhaseResult:
    parent: TraceNode
    terminal: VerificationFailureTerminal | None = None
    continue_observing: bool = False


class VerificationFailurePhase:
    """Handle failed post-action verification behind a named application seam."""

    def run(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        verification: VerificationReport,
        verification_ref: ArtifactRef | None,
        post_snapshot: BrowserSnapshot,
        recovery_enabled: bool,
        skill_step_id: str,
        task_skill_runtime: object | None,
        task_skill_progress_for: Callable[
            [object | None, StateKernel], TaskSkillRunState | None
        ],
        recover_execution_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        trace_recovery_started: Callable[..., TraceNode],
        terminal_recovery_status: Callable[..., RuntimeStep],
    ) -> VerificationFailurePhaseResult:
        del post_snapshot
        if not recovery_enabled:
            state.transition(RuntimeStep.FAILED.value)
            return VerificationFailurePhaseResult(
                parent=parent,
                terminal=VerificationFailureTerminal(
                    status=RuntimeStep.FAILED,
                    error_code=RuntimeErrorCode.VERIFICATION_FAILED,
                ),
            )
        failure_context = self._skill_failure_context(
            state=state,
            contract=contract,
            verification=verification,
            verification_ref=verification_ref,
            skill_step_id=skill_step_id,
            task_skill_runtime=task_skill_runtime,
            task_skill_progress_for=task_skill_progress_for,
        )
        recovery_result, parent = recover_execution_failure(
            envelope,
            state,
            trace,
            parent,
            contract,
            receipt,
            RuntimeErrorCode.VERIFICATION_FAILED,
            failure_context=failure_context,
            verification=verification,
            verification_ref=verification_ref.path if verification_ref else "",
        )
        parent = trace_recovery_started(
            trace,
            parent,
            state,
            recovery_result,
            verification_status=verification.status.value,
        )
        if recovery_result in {
            RecoveryKind.REOBSERVE,
            RecoveryKind.INSPECT_POST_STATE,
        }:
            return VerificationFailurePhaseResult(
                parent=parent,
                continue_observing=True,
            )
        return VerificationFailurePhaseResult(
            parent=parent,
            terminal=VerificationFailureTerminal(
                status=terminal_recovery_status(
                    state,
                    fallback=RuntimeStep.FAILED,
                ),
                error_code=RuntimeErrorCode.VERIFICATION_FAILED,
            ),
        )

    def _skill_failure_context(
        self,
        *,
        state: StateKernel,
        contract: ActionContract,
        verification: VerificationReport,
        verification_ref: ArtifactRef | None,
        skill_step_id: str,
        task_skill_runtime: object | None,
        task_skill_progress_for: Callable[
            [object | None, StateKernel], TaskSkillRunState | None
        ],
    ) -> dict[str, Any] | None:
        skill_progress = (
            task_skill_progress_for(task_skill_runtime, state)
            if skill_step_id and task_skill_runtime is not None
            else None
        )
        if not skill_step_id or skill_progress is None:
            return None
        return {
            "task_skill_id": skill_progress.skill_id,
            "task_skill_version": skill_progress.version,
            "task_skill_step_id": skill_step_id,
            "selected_route": (
                contract.gesture_binding.selected_route
                if contract.gesture_binding is not None
                else contract.backend
            ),
            "source_evidence": (
                ([verification_ref.path] if verification_ref else [])
                + [item.source for item in verification.evidence]
            ),
            "preserved_completed_step_ids": list(skill_progress.completed_step_ids),
        }
