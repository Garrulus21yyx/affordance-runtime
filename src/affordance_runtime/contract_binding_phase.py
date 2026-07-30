"""Coordinator-facing contract binding seam for SAR-9 extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import ActionContract, RiskLevel, RuntimeErrorCode
from affordance_runtime.failure_envelope import FailureClass, FailurePhase
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.planning import (
    ContractBuilder,
    PlannerActionKind,
    ProposalRejected,
    bind_active_subgoal_verifiers,
    proposal_error_code,
    proposal_record,
)
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.planning_phase import apply_taskskill_planning_fallthrough
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_evidence import (
    action_progress_signature,
    semantic_target_descriptor,
)
from affordance_runtime.safety import CapabilityGate
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_skill_phase import task_skill_progress
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.trace import TraceDag, TraceNode


@dataclass(frozen=True)
class ContractBindingFailure:
    phase: FailurePhase
    failure_class: FailureClass
    error_code: RuntimeErrorCode
    message: str
    available_commands: frozenset[RecoveryKind]
    proposal_id: str = ""
    expected_effect: str = ""
    recoverable: bool = True
    continue_recovery_kinds: frozenset[RecoveryKind] = frozenset()


@dataclass(frozen=True)
class ContractBindingTerminal:
    status: RuntimeStep
    error_code: RuntimeErrorCode


@dataclass(frozen=True)
class ContractBindingPhaseResult:
    parent: TraceNode
    contract: ActionContract | None = None
    action_signature: str = ""
    failure: ContractBindingFailure | None = None
    terminal: ContractBindingTerminal | None = None
    continue_observing: bool = False


@dataclass(frozen=True)
class ContractRebindResult:
    parent: TraceNode
    contract: ActionContract
    error: RuntimeErrorCode | None


class ContractBindingPhase:
    """Bind a PlannerDecision to the current ActionContract boundary."""

    def bind(
        self,
        *,
        decision: PlannerDecision,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
        trace: TraceDag,
        parent: TraceNode,
        contract_builder: ContractBuilder | None,
        contract_execution_loop: ContractExecutionLoop,
        recovery_phase: RecoveryPhase,
        task_skill_runtime: AcceptedTaskSkillRuntime | None,
        skill_step_id: str,
        approval_required_risks: frozenset[RiskLevel],
        approval_required_capabilities: frozenset[str],
    ) -> ContractBindingPhaseResult:
        contract = decision.contract
        if decision.proposal is not None and not decision.proposal.requires_clarification:
            if contract_builder is None or envelope.task_spec is None:
                reason = "semantic proposal requires TaskSpec and ContractBuilder"
                parent = trace.add(
                    "PlannerProposalRejected",
                    {
                        "state": state.phase,
                        "proposal_id": decision.proposal.proposal_id,
                        "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                        "reason": reason,
                    },
                    parents=[parent.id],
                )
                if _pending_recovery_kind(state) in {
                    RecoveryKind.REGROUND,
                    RecoveryKind.REROUTE,
                }:
                    parent = recovery_phase.fail_pending_command(
                        state,
                        trace,
                        parent,
                        error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                    )
                if skill_step_id and task_skill_runtime is not None:
                    parent = apply_taskskill_planning_fallthrough(
                        task_skill_runtime=task_skill_runtime,
                        state=state,
                        trace=trace,
                        parent=parent,
                        reason="TaskSkill requires the normal semantic ContractBuilder",
                        step_id=skill_step_id,
                    )
                    state.replan_count += 1
                    state.transition(RuntimeStep.OBSERVING.value)
                    return ContractBindingPhaseResult(
                        parent=parent,
                        continue_observing=True,
                    )
                return ContractBindingPhaseResult(
                    parent=parent,
                    failure=ContractBindingFailure(
                        phase=FailurePhase.GROUNDING_BINDING,
                        failure_class=FailureClass.GROUNDING,
                        error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        message=reason,
                        available_commands=frozenset({RecoveryKind.ABORT}),
                        proposal_id=decision.proposal.proposal_id,
                        expected_effect="; ".join(decision.proposal.expected_effects),
                        recoverable=False,
                    ),
                )
            try:
                contract = contract_builder.build(
                    decision.proposal,
                    envelope.task_spec,
                    state,
                    snapshot,
                )
            except ProposalRejected as exc:
                error_code = proposal_error_code(exc.code)
                parent = trace.add(
                    "PlannerProposalRejected",
                    {
                        "state": state.phase,
                        "proposal_id": decision.proposal.proposal_id,
                        "error_code": error_code.value,
                        "reason": exc.detail,
                    },
                    parents=[parent.id],
                )
                if _pending_recovery_kind(state) in {
                    RecoveryKind.REGROUND,
                    RecoveryKind.REROUTE,
                }:
                    parent = recovery_phase.fail_pending_command(
                        state,
                        trace,
                        parent,
                        error_code=error_code.value,
                    )
                if skill_step_id and task_skill_runtime is not None:
                    parent = apply_taskskill_planning_fallthrough(
                        task_skill_runtime=task_skill_runtime,
                        state=state,
                        trace=trace,
                        parent=parent,
                        reason=f"TaskSkill contract binding rejected: {exc.detail}",
                        step_id=skill_step_id,
                    )
                    state.replan_count += 1
                    state.transition(RuntimeStep.OBSERVING.value)
                    return ContractBindingPhaseResult(
                        parent=parent,
                        continue_observing=True,
                    )
                return ContractBindingPhaseResult(
                    parent=parent,
                    failure=ContractBindingFailure(
                        phase=FailurePhase.GROUNDING_BINDING,
                        failure_class=FailureClass.GROUNDING,
                        error_code=error_code,
                        message=exc.detail or exc.code.value,
                        available_commands=frozenset(
                            {
                                RecoveryKind.REGROUND,
                                RecoveryKind.ABORT,
                            }
                        ),
                        proposal_id=decision.proposal.proposal_id,
                        expected_effect="; ".join(decision.proposal.expected_effects),
                        continue_recovery_kinds=frozenset({RecoveryKind.REGROUND}),
                    ),
                )
            if decision.proposal_provenance is None:
                raise RuntimeError("validated proposal is missing provenance")
            state.record_planner_proposal(
                proposal_record(decision.proposal, decision.proposal_provenance)
            )

        assert contract is not None
        contract = contract_execution_loop.bind_contract(
            contract,
            envelope,
            snapshot.observation,
        )
        contract = replace(
            contract,
            verifier_plan=list(
                bind_active_subgoal_verifiers(tuple(contract.verifier_plan), state)
            ),
            contract_hash="",
        )
        if skill_step_id and task_skill_runtime is not None:
            requirement_error = task_skill_runtime.contract_requirement_error(
                state,
                contract,
                approval_required_risks=approval_required_risks,
                approval_required_capabilities=approval_required_capabilities,
            )
            if requirement_error:
                parent = apply_taskskill_planning_fallthrough(
                    task_skill_runtime=task_skill_runtime,
                    state=state,
                    trace=trace,
                    parent=parent,
                    reason=requirement_error,
                    step_id=skill_step_id,
                )
                state.replan_count += 1
                state.transition(RuntimeStep.OBSERVING.value)
                return ContractBindingPhaseResult(parent=parent, continue_observing=True)

        action_signature = action_progress_signature(decision.proposal, contract)
        progress_block = (
            state.check_progress_guard(action_signature)
            if decision.proposal is not None
            else None
        )
        if progress_block is not None:
            state.record_progress_guard(progress_block, action_signature)
            state.replan_count += 1
            parent = trace.add(
                "PlannerProgressBlocked",
                {
                    "state": state.phase,
                    "error_code": progress_block.value,
                    "action_signature": action_signature,
                    "environment_revision": state.current_revision(),
                },
                parents=[parent.id],
            )
            if skill_step_id and task_skill_runtime is not None:
                parent = apply_taskskill_planning_fallthrough(
                    task_skill_runtime=task_skill_runtime,
                    state=state,
                    trace=trace,
                    parent=parent,
                    reason=f"TaskSkill progress guard blocked step: {progress_block.value}",
                    step_id=skill_step_id,
                )
            state.transition(RuntimeStep.OBSERVING.value)
            return ContractBindingPhaseResult(parent=parent, continue_observing=True)

        state.current_contract = contract
        state.transition(RuntimeStep.PREFLIGHT.value)
        contract_skill_progress = (
            task_skill_progress(task_skill_runtime, state)
            if skill_step_id and task_skill_runtime is not None
            else None
        )
        parent = _trace_contract_built(
            trace,
            parent,
            state,
            snapshot,
            decision,
            contract,
            skill_step_id,
            contract_skill_progress,
        )
        parent = _trace_route_selected(trace, parent, state, contract)
        parent, binding_recovery_failed = recovery_phase.complete_pending_binding(
            state,
            trace,
            parent,
            contract,
        )
        if binding_recovery_failed:
            state.transition(RuntimeStep.ABORTED.value)
            return ContractBindingPhaseResult(
                parent=parent,
                terminal=ContractBindingTerminal(
                    RuntimeStep.ABORTED,
                    RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                ),
            )
        return ContractBindingPhaseResult(
            parent=parent,
            contract=contract,
            action_signature=action_signature,
        )

    def rebind_preflight_target(
        self,
        *,
        decision: PlannerDecision,
        envelope: TaskEnvelope,
        state: StateKernel,
        preflight_snapshot: BrowserSnapshot,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        error: RuntimeErrorCode | None,
        effective_gate: CapabilityGate,
        contract_builder: ContractBuilder | None,
        contract_execution_loop: ContractExecutionLoop,
        capability_gate_enabled: bool,
    ) -> ContractRebindResult:
        if (
            error != RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH
            or decision.proposal is None
            or decision.proposal.action_kind != PlannerActionKind.POINT_ACTIVATE
            or contract.grounding_candidate is None
            or contract.grounding_candidate.source not in {GroundingSource.SVG, GroundingSource.VISUAL}
            or contract_builder is None
            or envelope.task_spec is None
        ):
            return ContractRebindResult(parent=parent, contract=contract, error=error)

        # A moving rendered target can retain semantic identity while its
        # current point/bbox changes between planning and immediate preflight.
        # Re-run the trusted resolver and binder against the preflight epoch;
        # never mutate the old locator or execute coordinates from the old
        # epoch.
        rebound_proposal = decision.proposal.model_copy(
            update={
                "proposal_id": f"{decision.proposal.proposal_id}-preflight-{state.version}",
                "based_on_state_version": state.version,
                "snapshot_id": preflight_snapshot.observation.snapshot_id,
            }
        )
        try:
            rebound_contract = contract_builder.build(
                rebound_proposal,
                envelope.task_spec,
                state,
                preflight_snapshot,
            )
        except ProposalRejected:
            return ContractRebindResult(parent=parent, contract=contract, error=error)

        rebound_contract = contract_execution_loop.bind_contract(
            rebound_contract,
            envelope,
            preflight_snapshot.observation,
        )
        rebound_contract = replace(
            rebound_contract,
            verifier_plan=list(
                bind_active_subgoal_verifiers(
                    tuple(rebound_contract.verifier_plan),
                    state,
                )
            ),
            contract_hash="",
        )
        rebound_error = contract_execution_loop.revalidate(
            rebound_contract,
            envelope,
            preflight_snapshot.observation,
            effective_gate,
            capability_gate_enabled=capability_gate_enabled,
            include_policy=True,
        )
        if rebound_error is not None:
            return ContractRebindResult(parent=parent, contract=contract, error=error)

        parent = trace.add(
            "ContractReboundAtPreflight",
            {
                "state": state.phase,
                "source_contract_id": contract.id,
                "source_contract_hash": contract.contract_hash,
                "contract_id": rebound_contract.id,
                "contract_hash": rebound_contract.contract_hash,
                "proposal_id": rebound_proposal.proposal_id,
                "snapshot_id": rebound_contract.snapshot_id,
                "page_revision": rebound_contract.page_revision,
                "target_fingerprint": rebound_contract.target_fingerprint,
                "candidate_id": rebound_contract.grounding_candidate.candidate_id
                if rebound_contract.grounding_candidate is not None
                else "",
            },
            parents=[parent.id],
        )
        state.current_contract = rebound_contract
        return ContractRebindResult(parent=parent, contract=rebound_contract, error=None)


def _trace_contract_built(
    trace: TraceDag,
    parent: TraceNode,
    state: StateKernel,
    snapshot: BrowserSnapshot,
    decision: PlannerDecision,
    contract: ActionContract,
    skill_step_id: str,
    contract_skill_progress: TaskSkillRunState | None,
) -> TraceNode:
    return trace.add(
        "ContractBuilt",
        {
            "state": state.phase,
            "contract_id": contract.id,
            "contract_hash": contract.contract_hash,
            "schema_version": contract.schema_version,
            "snapshot_id": contract.snapshot_id,
            "page_revision": contract.page_revision,
            "target_fingerprint": contract.target_fingerprint,
            "backend": contract.backend,
            "proposal_id": decision.proposal.proposal_id if decision.proposal else "",
            "supersedes_contract_id": contract.supersedes_contract_id,
            "source_contract_id": contract.source_contract_id,
            "fallback_reason": contract.fallback_reason,
            "semantic_action": (
                {
                    "action_kind": decision.proposal.action_kind.value,
                    "target": semantic_target_descriptor(
                        snapshot,
                        decision.proposal.target_affordance_id,
                    ),
                    "destination": semantic_target_descriptor(
                        snapshot,
                        decision.proposal.destination_affordance_id,
                    ),
                    "parameters": dict(decision.proposal.parameters),
                    "expected_effects": [
                        asdict(item) for item in contract.expected_effects
                    ],
                    "verifier_plan": [asdict(item) for item in contract.verifier_plan],
                    "required_capabilities": list(contract.required_capabilities),
                    "risk": contract.risk.value,
                }
                if decision.proposal is not None
                else None
            ),
            "task_skill": (
                {
                    "skill_id": contract_skill_progress.skill_id,
                    "version": contract_skill_progress.version,
                    "step_id": skill_step_id,
                }
                if contract_skill_progress is not None
                else None
            ),
            "gesture_binding": (
                {
                    "source": {
                        "semantic_target_id": contract.gesture_binding.source.semantic_target_id,
                        "candidate_id": contract.gesture_binding.source.candidate_id,
                        "snapshot_id": contract.gesture_binding.source.snapshot_id,
                        "target_fingerprint": contract.gesture_binding.source.target_fingerprint,
                    },
                    "destination": {
                        "semantic_target_id": contract.gesture_binding.destination.semantic_target_id,
                        "candidate_id": contract.gesture_binding.destination.candidate_id,
                        "snapshot_id": contract.gesture_binding.destination.snapshot_id,
                        "target_fingerprint": contract.gesture_binding.destination.target_fingerprint,
                    },
                    "selected_route": contract.gesture_binding.selected_route,
                }
                if contract.gesture_binding is not None
                else None
            ),
        },
        parents=[parent.id],
    )


def _trace_route_selected(
    trace: TraceDag,
    parent: TraceNode,
    state: StateKernel,
    contract: ActionContract,
) -> TraceNode:
    if contract.grounding_candidate is None:
        return parent
    candidate = contract.grounding_candidate
    route_plan = contract.route_plan
    return trace.add(
        "RouteSelected",
        {
            "state": state.phase,
            "semantic_target_id": candidate.semantic_target_id,
            "candidate_id": candidate.candidate_id,
            "source": candidate.source.value,
            "executor": candidate.compatible_executor,
            "observation_epoch_id": candidate.observation_epoch_id,
            "page_revision": candidate.page_revision,
            "fingerprint_key": candidate.fingerprint_key or candidate.candidate_id,
            "evidence_refs": list(candidate.evidence_refs),
            "decision_reason": route_plan.decision_reason
            if route_plan is not None
            else "",
            "viable_alternative_ids": (
                [item.candidate_id for item in route_plan.viable_alternatives]
                if route_plan is not None
                else []
            ),
            "hard_gates": (
                [
                    {
                        "candidate_id": item.candidate_id,
                        "passed": item.passed,
                        "reasons": list(item.reasons),
                    }
                    for item in route_plan.hard_gate_results
                ]
                if route_plan is not None
                else []
            ),
            "scores": (
                [
                    {
                        "candidate_id": item.candidate_id,
                        "score": item.score,
                        "confidence_component": item.confidence_component,
                        "latency_component": item.latency_component,
                        "cost_component": item.cost_component,
                        "verification_component": item.verification_component,
                    }
                    for item in route_plan.scores
                ]
                if route_plan is not None
                else []
            ),
            "contract_id": contract.id,
            "contract_hash": contract.contract_hash,
        },
        parents=[parent.id],
    )


def _pending_recovery_kind(state: StateKernel) -> RecoveryKind | None:
    if state.current_recovery_outcome is not None:
        return None
    decision = state.current_recovery_decision
    return decision.kind if decision is not None else None
