"""Coordinator-facing planning decision seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import dataclass, replace

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureClass, FailurePhase, ProposalRejectionContext
from affordance_runtime.planning import (
    PlannerProposalValidator,
    ProposalRejected,
    ProposalRejectionCode,
    proposal_error_code,
    proposal_record,
)
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.proposal_recovery_policy import ProposalRejectionRecoveryPolicy
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_evidence import semantic_target_descriptor
from affordance_runtime.runtime_terminal import TaskCompletionVerifier, commit_planner_terminal_decision
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_skill_phase import task_skill_progress, trace_task_skill_fallthrough
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport


@dataclass(frozen=True)
class PlanningDecisionFailure:
    phase: FailurePhase
    failure_class: FailureClass
    error_code: RuntimeErrorCode | str
    message: str
    available_commands: frozenset[RecoveryKind]
    proposal_id: str = ""
    proposal_rejection: ProposalRejectionContext | None = None
    expected_effect: str = ""
    recoverable: bool = True
    skill_fallthrough_reason: str = ""
    return_error_code: RuntimeErrorCode = RuntimeErrorCode.PLANNER_FAILED


@dataclass(frozen=True)
class PlanningDecisionTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode | None = None


@dataclass(frozen=True)
class PlanningDecisionPhaseResult:
    parent: TraceNode
    decision: PlannerDecision
    contract_missing: bool = False
    failure: PlanningDecisionFailure | None = None
    terminal: PlanningDecisionTerminal | None = None


class PlanningDecisionPhase:
    """Handle PlannerDecision trace, validation, and terminal decision semantics."""

    def handle(
        self,
        *,
        decision: PlannerDecision,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        trace: TraceDag,
        parent: TraceNode,
        latest_verification: VerificationReport | None,
        proposal_validator: PlannerProposalValidator,
        proposal_recovery_policy: ProposalRejectionRecoveryPolicy,
        recovery_phase: RecoveryPhase,
        task_skill_runtime: AcceptedTaskSkillRuntime | None,
        skill_step_id: str,
        owner_dispatch_recovery_kinds: frozenset[RecoveryKind],
    ) -> PlanningDecisionPhaseResult:
        if decision.planner_context:
            parent = trace.add(
                "PlannerContextBuilt",
                {"state": state.phase, **decision.planner_context},
                parents=[parent.id],
            )
        parent = trace.add(
            "PlanProposed",
            {
                "state": state.phase,
                "done": decision.done,
                "reason": decision.reason,
                "boundary": "semantic_proposal"
                if decision.proposal
                else "legacy_contract",
            },
            parents=[parent.id],
        )

        if decision.proposal is not None:
            proposal = decision.proposal
            provenance = decision.proposal_provenance
            try:
                if envelope.task_spec is None:
                    raise ProposalRejected(
                        ProposalRejectionCode.UNSUPPORTED_ACTION,
                        "semantic proposal requires a validated TaskSpec",
                    )
                proposal_validator.validate(
                    proposal,
                    provenance,
                    envelope.task_spec,
                    state,
                    snapshot,
                )
            except ProposalRejected as exc:
                error_code = proposal_error_code(exc.code)
                recovery_decision = proposal_recovery_policy.decide(
                    exc.code,
                    exc.detail,
                    exc.reason_code,
                    proposal.target_affordance_id,
                )
                parent = trace.add(
                    "PlannerProposalRejected",
                    {
                        "state": state.phase,
                        "proposal_id": proposal.proposal_id,
                        "error_code": error_code.value,
                        "rejection_code": exc.code.value,
                        "rejection_reason_code": exc.reason_code,
                        "reason": exc.detail,
                        "validation_boundary": "PlannerProposalValidator",
                        "provenance": (
                            provenance.model_dump(mode="json")
                            if provenance is not None
                            else None
                        ),
                    },
                    parents=[parent.id],
                )
                return PlanningDecisionPhaseResult(
                    parent=parent,
                    decision=decision,
                    failure=PlanningDecisionFailure(
                        phase=FailurePhase.PROPOSAL_VALIDATION,
                        failure_class=FailureClass.VALIDATION,
                        error_code=error_code,
                        message=recovery_decision.planner_feedback,
                        available_commands=recovery_decision.available_commands,
                        proposal_id=proposal.proposal_id,
                        proposal_rejection=recovery_decision.rejection_context,
                        expected_effect="; ".join(proposal.expected_effects),
                        recoverable=recovery_decision.recoverable,
                        skill_fallthrough_reason=(
                            f"TaskSkill proposal validation rejected: {exc.detail or exc.code.value}"
                            if skill_step_id and task_skill_runtime is not None
                            else ""
                        ),
                        return_error_code=error_code,
                    ),
                )
            if provenance is None:
                raise RuntimeError("validated proposal is missing provenance")
            parent = trace.add(
                "PlannerProposalValidated",
                {
                    "state": state.phase,
                    "proposal_id": proposal.proposal_id,
                    "validation_boundary": "PlannerProposalValidator",
                    "source": provenance.source.value,
                    "provenance": provenance.model_dump(mode="json"),
                },
                parents=[parent.id],
            )
            parent = trace.add(
                "PlannerProposalProduced",
                {
                    "state": state.phase,
                    "proposal_id": proposal.proposal_id,
                    "based_on_task_revision": proposal.based_on_task_revision,
                    "based_on_state_version": proposal.based_on_state_version,
                    "snapshot_id": proposal.snapshot_id,
                    "action_kind": proposal.action_kind.value,
                    "target_affordance_id": proposal.target_affordance_id,
                    "semantic_target": semantic_target_descriptor(
                        snapshot,
                        proposal.target_affordance_id,
                    ),
                    "semantic_destination": semantic_target_descriptor(
                        snapshot,
                        proposal.destination_affordance_id,
                    ),
                    "uncertainty": proposal.uncertainty,
                    "requires_clarification": proposal.requires_clarification,
                    "proposal": proposal.model_dump(mode="json"),
                    "provenance": provenance.model_dump(mode="json"),
                    "model_call": (
                        decision.model_call.model_dump(mode="json")
                        if decision.model_call is not None
                        else None
                    ),
                },
                parents=[parent.id],
            )
            parent = recovery_phase.complete_pending_plan_change(
                state,
                trace,
                parent,
                kind=RecoveryKind.REPLAN_STEP,
                plan_or_route_ref=proposal.proposal_id,
            )
            if proposal.done:
                state.record_planner_proposal(proposal_record(proposal, provenance))
                decision = replace(decision, done=True, result=dict(proposal.result))
            elif proposal.requires_clarification:
                state.record_planner_proposal(proposal_record(proposal, provenance))
                state.final_result = {
                    "clarification": proposal.subgoal or proposal.reason,
                    "proposal_id": proposal.proposal_id,
                    "task_revision": proposal.based_on_task_revision,
                }
                state.transition(RuntimeStep.WAITING_CLARIFICATION.value)
                parent = trace.add(
                    "ClarificationRequested",
                    {"state": state.phase, **state.final_result},
                    parents=[parent.id],
                )
                return PlanningDecisionPhaseResult(
                    parent=parent,
                    decision=decision,
                    terminal=PlanningDecisionTerminal(
                        RuntimeStep.WAITING_CLARIFICATION
                    ),
                )
        else:
            parent = recovery_phase.complete_pending_plan_change(
                state,
                trace,
                parent,
                kind=RecoveryKind.REPLAN_STEP,
                plan_or_route_ref=f"planner-decision:state:{state.version}",
            )

        terminal_commit = commit_planner_terminal_decision(
            decision=decision,
            state=state,
            trace=trace,
            parent=parent,
            completion=TaskCompletionVerifier().verify(
                task_spec=envelope.task_spec,
                state=state,
                verification=latest_verification,
                result=decision.result,
            ),
        )
        parent = terminal_commit.parent
        if terminal_commit.rejected:
            return PlanningDecisionPhaseResult(
                parent=parent,
                decision=decision,
                failure=PlanningDecisionFailure(
                    phase=FailurePhase.PROPOSAL_VALIDATION,
                    failure_class=FailureClass.VALIDATION,
                    error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                    message=terminal_commit.message,
                    available_commands=frozenset({RecoveryKind.ABORT}),
                    recoverable=False,
                    return_error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                ),
            )
        if terminal_commit.completed:
            return PlanningDecisionPhaseResult(
                parent=parent,
                decision=decision,
                terminal=PlanningDecisionTerminal(RuntimeStep.DONE),
            )
        if decision.contract is None and (
            decision.proposal is None or decision.proposal.requires_clarification
        ):
            unsupported_reason_code = str(
                decision.planner_context.get("unsupported_reason_code", "")
            )
            failure_error_code: RuntimeErrorCode | str = (
                unsupported_reason_code or "legacy_decision_without_proposal"
            )
            failure_message = (
                decision.reason or "planner returned neither a contract nor a result"
            )
            parent = trace.add(
                "TaskFailed",
                {
                    "state": state.phase,
                    "reason": failure_message,
                    "error_code": (
                        failure_error_code.value
                        if isinstance(failure_error_code, RuntimeErrorCode)
                        else failure_error_code
                    ),
                },
                parents=[parent.id],
            )
            return PlanningDecisionPhaseResult(
                parent=parent,
                decision=decision,
                contract_missing=True,
                failure=PlanningDecisionFailure(
                    phase=FailurePhase.STEP_PLANNING,
                    failure_class=FailureClass.VALIDATION,
                    error_code=failure_error_code,
                    message=failure_message,
                    available_commands=frozenset(
                        {
                            RecoveryKind.REPLAN_STEP,
                            *owner_dispatch_recovery_kinds,
                            RecoveryKind.ABORT,
                        }
                    ),
                    return_error_code=RuntimeErrorCode.PLANNER_FAILED,
                ),
            )
        return PlanningDecisionPhaseResult(parent=parent, decision=decision)


def apply_taskskill_planning_fallthrough(
    *,
    task_skill_runtime: AcceptedTaskSkillRuntime | None,
    state: StateKernel,
    trace: TraceDag,
    parent: TraceNode,
    reason: str,
    step_id: str,
) -> TraceNode:
    if task_skill_runtime is None or not step_id:
        return parent
    task_skill_runtime.fallthrough(state, reason)
    return trace_task_skill_fallthrough(
        trace,
        parent,
        state,
        reason,
        progress=task_skill_progress(task_skill_runtime, state),
        step_id=step_id,
    )
