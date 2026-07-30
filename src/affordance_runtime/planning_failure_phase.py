"""Coordinator-facing planning-failure handoff seam for SAR-9 extraction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureClass, FailurePhase
from affordance_runtime.model_port import ProviderModelError
from affordance_runtime.planning_phase import (
    PlanningDecisionPhaseResult,
    apply_taskskill_planning_fallthrough,
)
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import RecoveryKind, RuntimePhase
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_plan_flow import TaskPlanFlowFailure
from affordance_runtime.task_plan_phase import TaskPlanPhaseResult
from affordance_runtime.task_skill_phase import TaskSkillPhaseResult
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class PlanningFailureTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode


@dataclass(frozen=True)
class PlanningFailurePhaseResult:
    parent: TraceNode
    terminal: PlanningFailureTerminal | None = None
    continue_observing: bool = False


class PlanningFailurePhase:
    """Apply planning-side failure recovery behind a named seam."""

    def handle_task_plan_result(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        task_plan_phase: TaskPlanPhaseResult,
        recovery_phase: RecoveryPhase,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult | None:
        if task_plan_phase.failure is None:
            return None
        return self.handle_task_plan_failure(
            envelope=envelope,
            state=state,
            trace=trace,
            parent=parent,
            snapshot=snapshot,
            failure=task_plan_phase.failure,
            recovery_phase=recovery_phase,
            pending_recovery_kind=pending_recovery_kind,
            recover_phase_failure=recover_phase_failure,
            owner_dispatch_recovery_kinds=owner_dispatch_recovery_kinds,
        )

    def handle_task_skill_result(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        task_skill_phase: TaskSkillPhaseResult,
        recovery_phase: RecoveryPhase,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult | None:
        if task_skill_phase.failure is None:
            return None
        return self.handle_task_skill_failure(
            envelope=envelope,
            state=state,
            trace=trace,
            parent=parent,
            snapshot=snapshot,
            task_skill_phase=task_skill_phase,
            recovery_phase=recovery_phase,
            pending_recovery_kind=pending_recovery_kind,
            recover_phase_failure=recover_phase_failure,
            owner_dispatch_recovery_kinds=owner_dispatch_recovery_kinds,
        )

    def handle_planning_decision_result(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        planning_decision: PlanningDecisionPhaseResult,
        recovery_phase: RecoveryPhase,
        task_skill_runtime: AcceptedTaskSkillRuntime | None,
        skill_step_id: str,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult | None:
        if planning_decision.failure is None:
            return None
        return self.handle_planning_decision_failure(
            envelope=envelope,
            state=state,
            trace=trace,
            parent=parent,
            snapshot=snapshot,
            planning_decision=planning_decision,
            recovery_phase=recovery_phase,
            task_skill_runtime=task_skill_runtime,
            skill_step_id=skill_step_id,
            pending_recovery_kind=pending_recovery_kind,
            recover_phase_failure=recover_phase_failure,
            owner_dispatch_recovery_kinds=owner_dispatch_recovery_kinds,
        )

    def handle_task_plan_failure(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        failure: TaskPlanFlowFailure,
        recovery_phase: RecoveryPhase,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult:
        if pending_recovery_kind(state) == RecoveryKind.REPLAN_TASK:
            parent = recovery_phase.fail_pending_command(
                state,
                trace,
                parent,
                error_code=failure.error_code.value,
            )
        recovery_kind, parent = recover_phase_failure(
            envelope,
            state,
            trace,
            parent,
            phase=FailurePhase.TASK_PLANNING,
            failure_class=failure.failure_class,
            error_code=failure.error_code,
            message=failure.message,
            available_commands=frozenset(
                {
                    RecoveryKind.REPLAN_TASK,
                    *owner_dispatch_recovery_kinds,
                    RecoveryKind.ABORT,
                }
            ),
            snapshot=snapshot,
        )
        if (
            recovery_kind == RecoveryKind.REPLAN_TASK
            or recovery_kind in owner_dispatch_recovery_kinds
        ):
            return PlanningFailurePhaseResult(parent=parent, continue_observing=True)
        return PlanningFailurePhaseResult(
            parent=parent,
            terminal=PlanningFailureTerminal(
                RuntimeStep(state.phase),
                failure.error_code,
            ),
        )

    def handle_task_skill_failure(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        task_skill_phase: TaskSkillPhaseResult,
        recovery_phase: RecoveryPhase,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult:
        assert task_skill_phase.failure is not None
        if pending_recovery_kind(state) == RecoveryKind.REPLAN_STEP:
            parent = recovery_phase.fail_pending_command(
                state,
                trace,
                parent,
                error_code=RuntimeErrorCode.PLANNER_FAILED.value,
            )
        recovery_kind, parent = recover_phase_failure(
            envelope,
            state,
            trace,
            parent,
            phase=FailurePhase.SKILL_ACTIVATION,
            failure_class=FailureClass.SKILL,
            error_code=RuntimeErrorCode.PLANNER_FAILED,
            message=task_skill_phase.failure.reason,
            available_commands=frozenset(
                {
                    RecoveryKind.REPLAN_STEP,
                    *owner_dispatch_recovery_kinds,
                    RecoveryKind.ABORT,
                }
            ),
            snapshot=snapshot,
        )
        if (
            recovery_kind == RecoveryKind.REPLAN_STEP
            or recovery_kind in owner_dispatch_recovery_kinds
        ):
            return PlanningFailurePhaseResult(parent=parent, continue_observing=True)
        return PlanningFailurePhaseResult(
            parent=parent,
            terminal=PlanningFailureTerminal(
                RuntimeStep(state.phase),
                RuntimeErrorCode.PLANNER_FAILED,
            ),
        )

    def handle_provider_failure(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        error: ProviderModelError,
        recovery_phase: RecoveryPhase,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult:
        error_code = RuntimeErrorCode(error.kind.value)
        if pending_recovery_kind(state) == RecoveryKind.REPLAN_STEP:
            parent = recovery_phase.fail_pending_command(
                state,
                trace,
                parent,
                error_code=error_code.value,
            )
        state.final_result = {
            "deferred": True,
            "provider_failure": error.kind.value,
            "retry_after_s": error.retry_after_s,
            "resumable": error.resumable,
        }
        recovery_kind, parent = recover_phase_failure(
            envelope,
            state,
            trace,
            parent,
            phase=FailurePhase.PROVIDER_CONTEXT,
            failure_class=FailureClass.PROVIDER,
            error_code=error_code,
            message=f"provider failure: {error.kind.value}",
            available_commands=frozenset(
                {
                    *owner_dispatch_recovery_kinds,
                    RecoveryKind.ABORT,
                }
            ),
            snapshot=snapshot,
            abort_reentry_phase=RuntimePhase.DEFERRED,
        )
        if recovery_kind in owner_dispatch_recovery_kinds:
            return PlanningFailurePhaseResult(parent=parent, continue_observing=True)
        parent = trace.add(
            "PlannerDeferred",
            {
                "state": state.phase,
                "error_code": error_code.value,
                "provider_failure": error.kind.value,
                "retry_after_s": error.retry_after_s,
                "circuit_open": error.circuit_open,
                "resumable": error.resumable,
            },
            parents=[parent.id],
        )
        return PlanningFailurePhaseResult(
            parent=parent,
            terminal=PlanningFailureTerminal(RuntimeStep.DEFERRED, error_code),
        )

    def handle_unexpected_planner_failure(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        error: Exception,
        planner: object,
        recovery_phase: RecoveryPhase,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult:
        planner_error = f"{type(error).__name__}: {error}"
        model = getattr(planner, "model", None)
        parent = trace.add(
            "PlannerProposalRejected",
            {
                "state": state.phase,
                "error_code": RuntimeErrorCode.PLANNER_FAILED.value,
                "reason": planner_error[:500],
                "fallback_failures": list(getattr(model, "failure_details", ())),
            },
            parents=[parent.id],
        )
        if pending_recovery_kind(state) == RecoveryKind.REPLAN_STEP:
            parent = recovery_phase.fail_pending_command(
                state,
                trace,
                parent,
                error_code=RuntimeErrorCode.PLANNER_FAILED.value,
            )
        recovery_kind, parent = recover_phase_failure(
            envelope,
            state,
            trace,
            parent,
            phase=FailurePhase.STEP_PLANNING,
            failure_class=FailureClass.PLANNING,
            error_code=RuntimeErrorCode.PLANNER_FAILED,
            message=planner_error[:500],
            available_commands=frozenset(
                {
                    RecoveryKind.REPLAN_STEP,
                    *owner_dispatch_recovery_kinds,
                    RecoveryKind.ABORT,
                }
            ),
            snapshot=snapshot,
        )
        if (
            recovery_kind == RecoveryKind.REPLAN_STEP
            or recovery_kind in owner_dispatch_recovery_kinds
        ):
            return PlanningFailurePhaseResult(parent=parent, continue_observing=True)
        return PlanningFailurePhaseResult(
            parent=parent,
            terminal=PlanningFailureTerminal(
                RuntimeStep(state.phase),
                RuntimeErrorCode.PLANNER_FAILED,
            ),
        )

    def handle_planning_decision_failure(
        self,
        *,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        planning_decision: PlanningDecisionPhaseResult,
        recovery_phase: RecoveryPhase,
        task_skill_runtime: AcceptedTaskSkillRuntime | None,
        skill_step_id: str,
        pending_recovery_kind: Callable[[StateKernel], RecoveryKind | None],
        recover_phase_failure: Callable[..., tuple[RecoveryKind, TraceNode]],
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningFailurePhaseResult:
        assert planning_decision.failure is not None
        failure = planning_decision.failure
        if pending_recovery_kind(state) in {
            RecoveryKind.REGROUND,
            RecoveryKind.REROUTE,
            RecoveryKind.REPLAN_STEP,
        }:
            parent = recovery_phase.fail_pending_command(
                state,
                trace,
                parent,
                error_code=(
                    failure.error_code.value
                    if isinstance(failure.error_code, RuntimeErrorCode)
                    else str(failure.error_code)
                ),
            )
        if failure.skill_fallthrough_reason:
            parent = apply_taskskill_planning_fallthrough(
                task_skill_runtime=task_skill_runtime,
                state=state,
                trace=trace,
                parent=parent,
                reason=failure.skill_fallthrough_reason,
                step_id=skill_step_id,
            )
            state.replan_count += 1
            state.transition(RuntimeStep.OBSERVING.value)
            return PlanningFailurePhaseResult(parent=parent, continue_observing=True)
        recovery_kind, parent = recover_phase_failure(
            envelope,
            state,
            trace,
            parent,
            phase=failure.phase,
            failure_class=failure.failure_class,
            error_code=failure.error_code,
            message=failure.message,
            available_commands=failure.available_commands,
            snapshot=snapshot,
            proposal_id=failure.proposal_id,
            proposal_rejection=failure.proposal_rejection,
            expected_effect=failure.expected_effect,
            recoverable=failure.recoverable,
        )
        if planning_decision.contract_missing:
            if (
                recovery_kind == RecoveryKind.REPLAN_STEP
                or recovery_kind in owner_dispatch_recovery_kinds
            ):
                return PlanningFailurePhaseResult(
                    parent=parent,
                    continue_observing=True,
                )
            return PlanningFailurePhaseResult(
                parent=parent,
                terminal=PlanningFailureTerminal(
                    RuntimeStep(state.phase),
                    failure.return_error_code,
                ),
            )
        if recovery_kind != RecoveryKind.ABORT:
            return PlanningFailurePhaseResult(parent=parent, continue_observing=True)
        return PlanningFailurePhaseResult(
            parent=parent,
            terminal=PlanningFailureTerminal(
                RuntimeStep.ABORTED,
                failure.return_error_code,
            ),
        )
