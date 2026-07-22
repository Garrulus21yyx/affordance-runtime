"""Task-level coordinator for the bounded observe/act/verify loop."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from time import time
from typing import Any, Awaitable, Protocol
from uuid import uuid4

from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ApprovalToken, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.grounding import GroundingSource
from affordance_runtime.model_port import ModelCallRecord, ProviderFailureKind, ProviderModelError
from affordance_runtime.planning import (
    ContractBuilder,
    PlannerActionKind,
    PlannerProposal,
    ProposalRejected,
    ProposalRejectionCode,
)
from affordance_runtime.recovery import (
    BoundedRecoveryPolicy,
    FailureSignature,
    RecoveryAction,
    RecoveryAttempt,
    RecoveryAttemptOutcome,
    RecoveryCascadeDetector,
    RecoveryContext,
    RecoveryDecision,
    RecoveryIncident,
)
from affordance_runtime.runtime import Executor, RuntimeStep, TaskEnvelope
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_planning import (
    SubgoalVerifierPort,
    TaskPlannerPort,
    TaskPlanValidationStatus,
    TaskPlanValidator,
    VerifierBackedSubgoalVerifier,
)
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime, TaskSkillRuntimeDecision
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport, VerificationStatus, VerifierLadder, preflight


class ObservationSource(Protocol):
    def capture(self) -> BrowserSnapshot: ...


@dataclass(frozen=True)
class PlannerDecision:
    contract: ActionContract | None = None
    proposal: PlannerProposal | None = None
    done: bool = False
    result: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    planner_context: dict[str, Any] = field(default_factory=dict)
    model_call: ModelCallRecord | None = None


class PlannerPort(Protocol):
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision | Awaitable[PlannerDecision]: ...


class ApprovalProvider(Protocol):
    def approve(self, contract: ActionContract) -> ApprovalToken | None: ...


@dataclass(frozen=True)
class ConfiguredApprovalProvider:
    """Explicit benchmark/CLI approval source; never derives authority from page content."""

    approver: str
    allowed_capabilities: set[str]
    ttl_s: float = 60.0

    def approve(self, contract: ActionContract) -> ApprovalToken | None:
        capabilities = [item for item in contract.required_capabilities if item in self.allowed_capabilities]
        if not capabilities:
            return None
        issued_at = time()
        return ApprovalToken(
            token_id=f"approval-{uuid4().hex}",
            run_id=contract.run_id,
            contract_hash=contract.contract_hash,
            page_revision=contract.page_revision,
            capability=capabilities[0],
            approver=self.approver,
            issued_at_s=issued_at,
            expires_at_s=issued_at + self.ttl_s,
        )


@dataclass(frozen=True)
class RunBudget:
    max_steps: int = 20
    max_observations: int = 30
    max_replans: int = 10
    max_recoveries: int = 3
    max_effectful_actions: int = 5
    max_active_perception_observations: int = 3


@dataclass(frozen=True)
class RuntimeFeatures:
    preflight: bool = True
    structural_verification: bool = True
    capability_gate: bool = True
    recovery: bool = True


@dataclass
class CoordinatorResult:
    run_id: str
    status: RuntimeStep
    state: StateKernel
    trace: TraceDag
    result: dict[str, Any] = field(default_factory=dict)
    error_code: RuntimeErrorCode | None = None
    verification: VerificationReport | None = None
    artifacts: list[ArtifactRef] = field(default_factory=list)


@dataclass
class RunCoordinator:
    observer: ObservationSource
    planner: PlannerPort
    executor: Executor
    verifier: VerifierLadder = field(default_factory=VerifierLadder)
    gate: CapabilityGate = field(default_factory=CapabilityGate)
    task_policy: TaskConstraintPolicy = field(default_factory=TaskConstraintPolicy)
    recovery: BoundedRecoveryPolicy = field(default_factory=BoundedRecoveryPolicy)
    cascade_detector: RecoveryCascadeDetector = field(default_factory=RecoveryCascadeDetector)
    approval_provider: ApprovalProvider | None = None
    artifacts: ArtifactStore | None = None
    budget: RunBudget = field(default_factory=RunBudget)
    features: RuntimeFeatures = field(default_factory=RuntimeFeatures)
    contract_builder: ContractBuilder | None = None
    task_planner: TaskPlannerPort | None = None
    task_plan_validator: TaskPlanValidator = field(default_factory=TaskPlanValidator)
    subgoal_verifier: SubgoalVerifierPort = field(default_factory=VerifierBackedSubgoalVerifier)
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None

    async def run(self, envelope: TaskEnvelope, upstream_trace: TraceDag | None = None) -> CoordinatorResult:
        """Async-compatible entry point for framework and service adapters."""

        return await asyncio.to_thread(self.run_sync, envelope, upstream_trace)

    def run_sync(self, envelope: TaskEnvelope, upstream_trace: TraceDag | None = None) -> CoordinatorResult:
        """Execute one task with serial state mutation and action semantics."""

        state = StateKernel(task_id=envelope.task_id, goal=envelope.goal, constraints=dict(envelope.constraints))
        if upstream_trace is not None and upstream_trace.run_id != envelope.task_id:
            raise ValueError("upstream trace run_id does not match task")
        trace = upstream_trace or TraceDag(run_id=envelope.task_id)
        upstream_parent = trace.nodes[-1] if trace.nodes else None
        parent: TraceNode | None = trace.add(
            "TaskCreated",
            {"state": RuntimeStep.CREATED.value, "goal": envelope.goal, "constraints": envelope.constraints},
            parents=[upstream_parent.id] if upstream_parent else None,
        )
        latest_verification: VerificationReport | None = None

        while True:
            budget_error = self._budget_error(state)
            if budget_error is not None:
                state.transition(RuntimeStep.FAILED.value)
                parent = trace.add(
                    "TaskFailed",
                    {"state": state.phase, "error_code": budget_error.value, "reason": "runtime budget exhausted"},
                    parents=[parent.id] if parent else None,
                )
                return self._finish(
                    envelope, state, trace, RuntimeStep.FAILED, parent, budget_error, latest_verification
                )

            if state.phase in {RuntimeStep.CREATED.value, RuntimeStep.RECOVERING.value}:
                state.transition(RuntimeStep.OBSERVING.value)

            snapshot = self._capture(envelope.task_id, state.observation_count + 1)
            state.remember_observation(snapshot.observation)
            observation_ref = self._write_observation(envelope.task_id, state.observation_count, snapshot)
            parent = trace.add(
                "ObservationCaptured",
                {
                    "state": state.phase,
                    "snapshot_id": snapshot.observation.snapshot_id,
                    "page_revision": snapshot.observation.page_revision,
                    "environment_revision": snapshot.observation.environment_revision,
                    "url": snapshot.observation.url,
                    "artifact_refs": ([observation_ref.path] if observation_ref else [])
                    + snapshot.observation.artifact_refs,
                },
                parents=[parent.id] if parent else None,
            )
            self._index(trace, observation_ref)
            self._index_paths(trace, snapshot.observation.artifact_refs)
            parent = self._trace_source_arbitration(trace, parent, snapshot, state.phase)
            snapshot, parent = self._fulfill_targeted_perception(
                envelope.task_id,
                state,
                trace,
                parent,
                snapshot,
            )

            if (
                self.task_planner is not None
                and envelope.task_spec is not None
                and state.task_plan is not None
                and state.plan_progress is not None
                and state.plan_progress.action_budget_exhausted(state.task_plan)
            ):
                previous_plan = state.task_plan
                try:
                    task_plan = _resolve_task_plan(
                        self.task_planner.plan(envelope.task_spec, state_version=state.version)
                    )
                    report = self.task_plan_validator.validate(
                        task_plan, envelope.task_spec, state_version=state.version
                    )
                    if report.status != TaskPlanValidationStatus.ACCEPT:
                        raise ValueError(f"task replan validation: {report.status.value}")
                    state.replace_task_plan(task_plan)
                except Exception as exc:
                    state.transition(RuntimeStep.FAILED.value)
                    parent = trace.add(
                        "TaskReplanRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                            "reason": f"{type(exc).__name__}: {exc}"[:500],
                        },
                        parents=[parent.id],
                    )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.FAILED,
                        parent,
                        RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        latest_verification,
                    )
                parent = trace.add(
                    "TaskReplanned",
                    {
                        "state": state.phase,
                        "reason": "subgoal_action_budget_exhausted",
                        "previous_plan_id": previous_plan.plan_id,
                        "plan_id": task_plan.plan_id,
                        "plan_version": task_plan.plan_version,
                        "preserved_subgoal_ids": list(state.plan_progress.completed_subgoal_ids),
                        "active_subgoal": state.active_subgoal(),
                    },
                    parents=[parent.id],
                )

            if self.task_planner is not None and state.task_plan is None:
                if envelope.task_spec is None:
                    state.transition(RuntimeStep.FAILED.value)
                    parent = trace.add(
                        "TaskPlanRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                            "reason": "task planning requires a validated TaskSpec",
                        },
                        parents=[parent.id],
                    )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.FAILED,
                        parent,
                        RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        latest_verification,
                    )
                try:
                    task_plan = _resolve_task_plan(
                        self.task_planner.plan(envelope.task_spec, state_version=state.version)
                    )
                except Exception as exc:
                    state.transition(RuntimeStep.FAILED.value)
                    parent = trace.add(
                        "TaskPlanRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_FAILED.value,
                            "reason": f"{type(exc).__name__}: {exc}"[:500],
                        },
                        parents=[parent.id],
                    )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.FAILED,
                        parent,
                        RuntimeErrorCode.PLANNER_FAILED,
                        latest_verification,
                    )
                report = self.task_plan_validator.validate(task_plan, envelope.task_spec, state_version=state.version)
                parent = trace.add(
                    "TaskPlanProposed",
                    {
                        "state": state.phase,
                        "plan_id": task_plan.plan_id,
                        "plan_version": task_plan.plan_version,
                        "generated_by": task_plan.generated_by.value,
                        "subgoal_count": len(task_plan.subgoals),
                        "validation": report.status.value,
                        "issues": [item.model_dump(mode="json") for item in report.issues],
                    },
                    parents=[parent.id],
                )
                if report.status != TaskPlanValidationStatus.ACCEPT:
                    state.transition(RuntimeStep.FAILED.value)
                    parent = trace.add(
                        "TaskPlanRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                            "validation": report.status.value,
                        },
                        parents=[parent.id],
                    )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.FAILED,
                        parent,
                        RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        latest_verification,
                    )
                state.install_task_plan(task_plan)
                parent = trace.add(
                    "TaskPlanAccepted",
                    {
                        "state": state.phase,
                        "plan_id": task_plan.plan_id,
                        "active_subgoal": state.active_subgoal(),
                    },
                    parents=[parent.id],
                )

            state.transition(RuntimeStep.PLANNING.value)
            skill_decision: TaskSkillRuntimeDecision | None = None
            skill_step_id = ""
            try:
                if self.task_skill_runtime is not None and envelope.task_spec is not None:
                    try:
                        skill_decision = self.task_skill_runtime.expose(
                            envelope.task_spec,
                            state,
                            snapshot,
                        )
                    except Exception as exc:
                        reason = f"TaskSkill runtime error: {type(exc).__name__}: {exc}"[:500]
                        self.task_skill_runtime.fallthrough(state, reason)
                        skill_decision = TaskSkillRuntimeDecision(
                            attempted=True,
                            reason=reason,
                        )
                    if skill_decision.newly_activated and skill_decision.payload is not None:
                        parent = trace.add(
                            "TaskSkillActivated",
                            {
                                "state": state.phase,
                                "skill_id": skill_decision.payload.skill_id,
                                "version": skill_decision.payload.version,
                                "trigger": skill_decision.payload.trigger.task_family,
                            },
                            parents=[parent.id],
                        )
                    exposure = skill_decision.exposure
                    if exposure is not None and exposure.proposal is not None:
                        skill_payload = skill_decision.payload
                        if skill_payload is None:
                            raise ValueError("TaskSkill exposure is missing its payload")
                        skill_step_id = exposure.step_id
                        decision = PlannerDecision(
                            proposal=exposure.proposal,
                            reason="accepted TaskSkill exposed one semantic step",
                        )
                        parent = trace.add(
                            "TaskSkillStepExposed",
                            {
                                "state": state.phase,
                                "skill_id": skill_payload.skill_id,
                                "version": skill_payload.version,
                                "step_id": skill_step_id,
                                "action_kind": exposure.proposal.action_kind.value,
                                "semantic_target_id": exposure.proposal.target_affordance_id,
                                "semantic_destination_id": (exposure.proposal.destination_affordance_id),
                            },
                            parents=[parent.id],
                        )
                    else:
                        if skill_decision.attempted and skill_decision.reason:
                            parent = self._trace_task_skill_fallthrough(
                                trace,
                                parent,
                                state,
                                skill_decision.reason,
                            )
                        decision = _resolve_planner_decision(self.planner.propose(envelope, state, snapshot))
                else:
                    decision = _resolve_planner_decision(self.planner.propose(envelope, state, snapshot))
            except ProviderModelError as exc:
                error_code = _provider_runtime_error(exc.kind)
                state.final_result = {
                    "deferred": True,
                    "provider_failure": exc.kind.value,
                    "retry_after_s": exc.retry_after_s,
                    "resumable": exc.resumable,
                }
                state.transition(RuntimeStep.DEFERRED.value)
                parent = trace.add(
                    "PlannerDeferred",
                    {
                        "state": state.phase,
                        "error_code": error_code.value,
                        "provider_failure": exc.kind.value,
                        "retry_after_s": exc.retry_after_s,
                        "circuit_open": exc.circuit_open,
                        "resumable": exc.resumable,
                    },
                    parents=[parent.id],
                )
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.DEFERRED,
                    parent,
                    error_code,
                    latest_verification,
                )
            except Exception as exc:
                planner_error = f"{type(exc).__name__}: {exc}"
                model = getattr(self.planner, "model", None)
                state.transition(RuntimeStep.FAILED.value)
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
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.FAILED,
                    parent,
                    RuntimeErrorCode.PLANNER_FAILED,
                    latest_verification,
                )
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
                    "boundary": "semantic_proposal" if decision.proposal else "legacy_contract",
                },
                parents=[parent.id],
            )
            if decision.proposal is not None:
                proposal = decision.proposal
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
                        "uncertainty": proposal.uncertainty,
                        "requires_clarification": proposal.requires_clarification,
                        "proposal": proposal.model_dump(mode="json"),
                        "model_call": (
                            decision.model_call.model_dump(mode="json") if decision.model_call is not None else None
                        ),
                    },
                    parents=[parent.id],
                )
                if proposal.done:
                    state.record_planner_proposal(proposal.model_dump(mode="json"))
                    decision = replace(decision, done=True, result=dict(proposal.result))
                elif proposal.requires_clarification:
                    state.record_planner_proposal(proposal.model_dump(mode="json"))
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
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.WAITING_CLARIFICATION,
                        parent,
                        None,
                        latest_verification,
                    )
            if decision.done:
                if state.task_plan is not None and not _task_plan_completed(state):
                    state.transition(RuntimeStep.ABORTED.value)
                    parent = trace.add(
                        "PlannerProposalRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                            "reason": "planner cannot finish before verifier-backed subgoal completion",
                        },
                        parents=[parent.id],
                    )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.ABORTED,
                        parent,
                        RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        latest_verification,
                    )
                state.final_result = dict(decision.result)
                state.transition(RuntimeStep.DONE.value)
                parent = trace.add(
                    "TaskCompleted",
                    {"state": state.phase, "result": decision.result},
                    parents=[parent.id],
                )
                return self._finish(envelope, state, trace, RuntimeStep.DONE, parent, None, latest_verification)
            contract = decision.contract
            if decision.proposal is not None and not decision.proposal.requires_clarification:
                if self.contract_builder is None or envelope.task_spec is None:
                    parent = trace.add(
                        "PlannerProposalRejected",
                        {
                            "state": state.phase,
                            "proposal_id": decision.proposal.proposal_id,
                            "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                            "reason": "semantic proposal requires TaskSpec and ContractBuilder",
                        },
                        parents=[parent.id],
                    )
                    if skill_step_id and self.task_skill_runtime is not None:
                        reason = "TaskSkill requires the normal semantic ContractBuilder"
                        self.task_skill_runtime.fallthrough(state, reason)
                        parent = self._trace_task_skill_fallthrough(
                            trace,
                            parent,
                            state,
                            reason,
                            step_id=skill_step_id,
                        )
                        state.replan_count += 1
                        state.transition(RuntimeStep.OBSERVING.value)
                        continue
                    state.transition(RuntimeStep.FAILED.value)
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.FAILED,
                        parent,
                        RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        latest_verification,
                    )
                try:
                    contract = self.contract_builder.build(decision.proposal, envelope.task_spec, state, snapshot)
                except ProposalRejected as exc:
                    error_code = _proposal_error_code(exc.code)
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
                    if skill_step_id and self.task_skill_runtime is not None:
                        reason = f"TaskSkill contract binding rejected: {exc.detail}"
                        self.task_skill_runtime.fallthrough(state, reason)
                        parent = self._trace_task_skill_fallthrough(
                            trace,
                            parent,
                            state,
                            reason,
                            step_id=skill_step_id,
                        )
                        state.replan_count += 1
                        state.transition(RuntimeStep.OBSERVING.value)
                        continue
                    state.transition(RuntimeStep.ABORTED.value)
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.ABORTED,
                        parent,
                        error_code,
                        latest_verification,
                    )
                state.record_planner_proposal(decision.proposal.model_dump(mode="json"))
            if contract is None:
                state.transition(RuntimeStep.FAILED.value)
                parent = trace.add(
                    "TaskFailed",
                    {"state": state.phase, "reason": "planner returned neither a contract nor a result"},
                    parents=[parent.id],
                )
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.FAILED,
                    parent,
                    RuntimeErrorCode.EXECUTION_FAILED,
                    latest_verification,
                )

            contract = self._bind_contract(contract, envelope, snapshot)
            if skill_step_id and self.task_skill_runtime is not None:
                requirement_error = self.task_skill_runtime.contract_requirement_error(
                    state,
                    contract,
                    approval_required_risks=frozenset(self.gate.approval_required_risks),
                    approval_required_capabilities=frozenset(self.gate.approval_required_capabilities),
                )
                if requirement_error:
                    self.task_skill_runtime.fallthrough(state, requirement_error)
                    parent = self._trace_task_skill_fallthrough(
                        trace,
                        parent,
                        state,
                        requirement_error,
                        step_id=skill_step_id,
                    )
                    state.replan_count += 1
                    state.transition(RuntimeStep.OBSERVING.value)
                    continue
            action_signature = _action_progress_signature(decision.proposal, contract)
            progress_block = state.check_progress_guard(action_signature) if decision.proposal is not None else None
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
                if skill_step_id and self.task_skill_runtime is not None:
                    reason = f"TaskSkill progress guard blocked step: {progress_block.value}"
                    self.task_skill_runtime.fallthrough(state, reason)
                    parent = self._trace_task_skill_fallthrough(
                        trace,
                        parent,
                        state,
                        reason,
                        step_id=skill_step_id,
                    )
                state.transition(RuntimeStep.OBSERVING.value)
                continue
            state.current_contract = contract
            state.transition(RuntimeStep.PREFLIGHT.value)
            parent = trace.add(
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
                    "task_skill": (
                        {
                            "skill_id": state.task_skill.skill_id,
                            "version": state.task_skill.version,
                            "step_id": skill_step_id,
                        }
                        if skill_step_id and state.task_skill is not None
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
            if contract.grounding_candidate is not None:
                candidate = contract.grounding_candidate
                route_plan = contract.route_plan
                parent = trace.add(
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
                        "decision_reason": route_plan.decision_reason if route_plan is not None else "",
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
            effective_gate = CapabilityGate(
                granted_capabilities=self.gate.granted_capabilities | set(envelope.capabilities),
                approval_required_risks=set(self.gate.approval_required_risks),
                approval_required_capabilities=self.gate.approval_required_capabilities
                | set(str(item) for item in envelope.constraints.get("require_approval_for", [])),
                approval_tokens=self.gate.approval_tokens,
                approved_contract_ids=set(self.gate.approved_contract_ids),
            )
            error = (
                self.task_policy.check(contract, envelope.constraints)
                or (effective_gate.check(contract) if self.features.capability_gate else None)
                or (preflight(contract, snapshot.observation) if self.features.preflight else None)
            )
            execution_observation = snapshot.observation
            if error is None and self.features.preflight:
                preflight_snapshot = self._capture(envelope.task_id, state.observation_count + 1)
                state.remember_observation(preflight_snapshot.observation)
                preflight_ref = self._write_observation(envelope.task_id, state.observation_count, preflight_snapshot)
                self._index(trace, preflight_ref)
                self._index_paths(trace, preflight_snapshot.observation.artifact_refs)
                parent = trace.add(
                    "PreflightObservationCaptured",
                    {
                        "state": state.phase,
                        "snapshot_id": preflight_snapshot.observation.snapshot_id,
                        "page_revision": preflight_snapshot.observation.page_revision,
                        "artifact_refs": ([preflight_ref.path] if preflight_ref else [])
                        + preflight_snapshot.observation.artifact_refs,
                    },
                    parents=[parent.id],
                )
                parent = self._trace_source_arbitration(trace, parent, preflight_snapshot, state.phase)
                error = preflight(
                    contract,
                    preflight_snapshot.observation,
                    require_snapshot_identity=False,
                    require_environment_revision=False,
                )
                if (
                    error == RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH
                    and decision.proposal is not None
                    and decision.proposal.action_kind == PlannerActionKind.POINT_ACTIVATE
                    and contract.grounding_candidate is not None
                    and contract.grounding_candidate.source in {GroundingSource.SVG, GroundingSource.VISUAL}
                    and self.contract_builder is not None
                    and envelope.task_spec is not None
                ):
                    # A moving rendered target can retain semantic identity
                    # while its current point/bbox changes between planning
                    # and immediate preflight.  Re-run the trusted resolver
                    # and binder against the preflight epoch; never mutate the
                    # old locator or execute coordinates from the old epoch.
                    rebound_proposal = decision.proposal.model_copy(
                        update={
                            "proposal_id": f"{decision.proposal.proposal_id}-preflight-{state.version}",
                            "based_on_state_version": state.version,
                            "snapshot_id": preflight_snapshot.observation.snapshot_id,
                        }
                    )
                    try:
                        rebound_contract = self.contract_builder.build(
                            rebound_proposal,
                            envelope.task_spec,
                            state,
                            preflight_snapshot,
                        )
                    except ProposalRejected:
                        pass
                    else:
                        rebound_contract = self._bind_contract(rebound_contract, envelope, preflight_snapshot)
                        rebound_error = (
                            self.task_policy.check(rebound_contract, envelope.constraints)
                            or (effective_gate.check(rebound_contract) if self.features.capability_gate else None)
                            or preflight(rebound_contract, preflight_snapshot.observation)
                        )
                        if rebound_error is None:
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
                            contract = rebound_contract
                            state.current_contract = rebound_contract
                            error = None
                execution_observation = preflight_snapshot.observation
            elif not self.features.preflight:
                parent = trace.add(
                    "AblationApplied",
                    {"state": state.phase, "disabled_layer": "preflight"},
                    parents=[parent.id],
                )
            if error == RuntimeErrorCode.APPROVAL_REQUIRED:
                parent = trace.add(
                    "HumanApprovalRequested",
                    {"state": RuntimeStep.WAITING_APPROVAL.value, "contract_hash": contract.contract_hash},
                    parents=[parent.id],
                )
                token = self.approval_provider.approve(contract) if self.approval_provider else None
                if token is None:
                    state.transition(RuntimeStep.WAITING_APPROVAL.value)
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.WAITING_APPROVAL,
                        parent,
                        error,
                        latest_verification,
                    )
                effective_gate.approval_tokens[token.token_id] = token
                self.gate.approval_tokens[token.token_id] = token
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
                approval_snapshot = self._capture(envelope.task_id, state.observation_count + 1)
                state.remember_observation(approval_snapshot.observation)
                approval_ref = self._write_observation(envelope.task_id, state.observation_count, approval_snapshot)
                self._index(trace, approval_ref)
                self._index_paths(trace, approval_snapshot.observation.artifact_refs)
                parent = trace.add(
                    "ApprovalStateRevalidated",
                    {
                        "state": state.phase,
                        "snapshot_id": approval_snapshot.observation.snapshot_id,
                        "page_revision": approval_snapshot.observation.page_revision,
                        "artifact_refs": ([approval_ref.path] if approval_ref else [])
                        + approval_snapshot.observation.artifact_refs,
                    },
                    parents=[parent.id],
                )
                parent = self._trace_source_arbitration(trace, parent, approval_snapshot, state.phase)
                error = effective_gate.check(contract) or preflight(
                    contract,
                    approval_snapshot.observation,
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
                    and state.recovery_count < self.budget.max_recoveries
                ):
                    parent = trace.add(
                        "EnvironmentDriftDetected",
                        {"state": state.phase, "error_code": error.value},
                        parents=[parent.id],
                    )
                    recovery_result = self._recover(state, contract, None, error)
                    parent = trace.add(
                        "RecoveryStarted",
                        {
                            "state": state.phase,
                            "action": recovery_result.value,
                            "incident": state.recovery_diagnostics,
                        },
                        parents=[parent.id],
                    )
                    if recovery_result == RecoveryAction.REOBSERVE:
                        continue
                    state.transition(RuntimeStep.ABORTED.value)
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.ABORTED,
                        parent,
                        error,
                        latest_verification,
                    )
                state.transition(RuntimeStep.ABORTED.value)
                parent = trace.add(
                    "PreflightBlocked",
                    {"state": state.phase, "error_code": error.value},
                    parents=[parent.id],
                )
                return self._finish(envelope, state, trace, RuntimeStep.ABORTED, parent, error, latest_verification)

            authorization_error = effective_gate.authorize(contract) if self.features.capability_gate else None
            if authorization_error is not None:
                state.transition(RuntimeStep.ABORTED.value)
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.ABORTED,
                    parent,
                    authorization_error,
                    latest_verification,
                )
            parent = trace.add("PreflightPassed", {"state": state.phase}, parents=[parent.id])

            state.transition(RuntimeStep.ACTING.value)
            parent = trace.add("ActionStarted", {"state": state.phase, "contract_id": contract.id}, parents=[parent.id])
            receipt = self.executor.execute(contract, execution_observation)
            state.record_receipt(receipt)
            state.step_count += 1
            state.record_subgoal_action()
            if contract.required_capabilities:
                state.effectful_action_count += 1
            receipt_ref = self._write_receipt(envelope.task_id, state.step_count, receipt)
            self._index(trace, receipt_ref)
            parent = trace.add(
                "ActionCompleted",
                {
                    "state": state.phase,
                    "success": receipt.success,
                    "error_code": receipt.error_code.value if receipt.error_code else "",
                    "artifact_refs": [receipt_ref.path] if receipt_ref else [],
                },
                parents=[parent.id],
            )
            if not receipt.success:
                if not self.features.recovery:
                    state.transition(RuntimeStep.FAILED.value)
                    parent = trace.add(
                        "TaskFailed",
                        {"state": state.phase, "reason": "recovery layer disabled"},
                        parents=[parent.id],
                    )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.FAILED,
                        parent,
                        receipt.error_code or RuntimeErrorCode.EXECUTION_FAILED,
                        latest_verification,
                    )
                recovery_result = self._recover(state, contract, receipt, receipt.error_code)
                parent = trace.add(
                    "RecoveryStarted",
                    {
                        "state": state.phase,
                        "action": recovery_result.value,
                        "incident": state.recovery_diagnostics,
                    },
                    parents=[parent.id],
                )
                if recovery_result in {RecoveryAction.REOBSERVE, RecoveryAction.RETRY, RecoveryAction.REROUTE}:
                    continue
                if recovery_result == RecoveryAction.VERIFY_STATE:
                    inspection = self._capture(envelope.task_id, state.observation_count + 1)
                    state.remember_observation(inspection.observation)
                    inspection_ref = self._write_observation(envelope.task_id, state.observation_count, inspection)
                    self._index(trace, inspection_ref)
                    self._index_paths(trace, inspection.observation.artifact_refs)
                    latest_verification = self.verifier.verify_report(
                        contract.verifier_plan,
                        receipt,
                        inspection.observation,
                    )
                    state.latest_verification = latest_verification
                    parent = trace.add(
                        "RecoveryStateInspected",
                        {
                            "state": state.phase,
                            "verification": latest_verification.status.value,
                            "snapshot_id": inspection.observation.snapshot_id,
                            "artifact_refs": ([inspection_ref.path] if inspection_ref else [])
                            + inspection.observation.artifact_refs,
                        },
                        parents=[parent.id],
                    )
                    parent = self._trace_source_arbitration(trace, parent, inspection, state.phase)
                    if latest_verification.passed:
                        incident = state.recovery_incident
                        if incident is not None:
                            incident.complete_pending(
                                inspection.observation.environment_revision,
                                RecoveryAttemptOutcome.SUCCEEDED,
                            )
                            incident.terminal_outcome = "effect_confirmed"
                            state.recovery_diagnostics = incident.diagnostics()
                        continue
                    incident = state.recovery_incident
                    if incident is not None:
                        incident.complete_pending(
                            inspection.observation.environment_revision,
                            RecoveryAttemptOutcome.FAILED,
                        )
                        incident.terminal_outcome = "effect_unconfirmed"
                        state.recovery_diagnostics = incident.diagnostics()
                state.transition(RuntimeStep.FAILED.value)
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.FAILED,
                    parent,
                    receipt.error_code or RuntimeErrorCode.EXECUTION_FAILED,
                    latest_verification,
                )

            state.transition(RuntimeStep.VERIFYING.value)
            post_snapshot = self._capture(envelope.task_id, state.observation_count + 1)
            state.remember_observation(post_snapshot.observation)
            post_ref = self._write_observation(envelope.task_id, state.observation_count, post_snapshot)
            self._index(trace, post_ref)
            self._index_paths(trace, post_snapshot.observation.artifact_refs)
            parent = trace.add(
                "PostActionObservationCaptured",
                {
                    "state": state.phase,
                    "snapshot_id": post_snapshot.observation.snapshot_id,
                    "page_revision": post_snapshot.observation.page_revision,
                    "artifact_refs": ([post_ref.path] if post_ref else []) + post_snapshot.observation.artifact_refs,
                },
                parents=[parent.id],
            )
            parent = self._trace_source_arbitration(trace, parent, post_snapshot, state.phase)
            if self.features.structural_verification:
                latest_verification = self.verifier.verify_report(
                    contract.verifier_plan,
                    receipt,
                    post_snapshot.observation,
                )
            else:
                latest_verification = VerificationReport(
                    VerificationStatus.PASSED,
                    reason="structural verification disabled by benchmark ablation",
                )
            state.latest_verification = latest_verification
            if decision.proposal is not None:
                state.record_action_progress(
                    action_signature,
                    post_snapshot.observation.environment_revision,
                    verification_passed=latest_verification.passed,
                    effect_satisfied=_verification_satisfies_effect(latest_verification),
                    post_page_revision=post_snapshot.observation.page_revision,
                )
            verification_ref = self._write_verification(envelope.task_id, state.step_count, latest_verification)
            self._index(trace, verification_ref)
            parent = trace.add(
                "PostconditionPassed" if latest_verification.passed else "PostconditionFailed",
                {
                    "state": state.phase,
                    "status": latest_verification.status.value,
                    "reason": latest_verification.reason,
                    "artifact_refs": [verification_ref.path] if verification_ref else [],
                },
                parents=[parent.id],
            )
            if latest_verification.passed:
                if skill_step_id and self.task_skill_runtime is not None:
                    skill_complete = False
                    skill_report = self.task_skill_runtime.verify_active_step(
                        state,
                        step_id=skill_step_id,
                        verification=latest_verification,
                        observation=post_snapshot.observation,
                    )
                    if not skill_report.passed:
                        reason = skill_report.match.reason
                        self.task_skill_runtime.fallthrough(state, reason)
                        parent = trace.add(
                            "TaskSkillStepEvidenceRejected",
                            {
                                "state": state.phase,
                                "skill_id": skill_report.skill_id,
                                "version": skill_report.skill_version,
                                "step_id": skill_report.step_id,
                                "criteria_match": asdict(skill_report.match),
                            },
                            parents=[parent.id],
                        )
                        parent = self._trace_task_skill_fallthrough(
                            trace,
                            parent,
                            state,
                            reason,
                            step_id=skill_step_id,
                        )
                    else:
                        skill_complete = self.task_skill_runtime.checkpoint_verified(
                            state,
                            report=skill_report,
                            artifact_refs=([verification_ref.path] if verification_ref else []),
                        )
                        parent = trace.add(
                            "TaskSkillStepCompleted",
                            {
                                "state": state.phase,
                                "skill_id": state.task_skill.skill_id if state.task_skill else "",
                                "version": state.task_skill.version if state.task_skill else "",
                                "step_id": skill_step_id,
                                "completed_step_ids": (
                                    list(state.task_skill.completed_step_ids) if state.task_skill is not None else []
                                ),
                                "evidence": (list(state.task_skill.evidence) if state.task_skill is not None else []),
                                "criterion_evidence_links": [asdict(item) for item in skill_report.match.links],
                            },
                            parents=[parent.id],
                        )
                    if skill_report.passed and skill_complete and state.task_plan is None:
                        skill_progress = state.task_skill
                        if skill_progress is None:
                            raise ValueError("verified TaskSkill progress is missing")
                        if contract.grounding_candidate is not None:
                            state.complete_grounding_recovery(contract.grounding_candidate.semantic_target_id)
                        if state.recovery_incident is not None and state.recovery_incident.terminal_outcome == "open":
                            state.recovery_incident.complete_pending(
                                post_snapshot.observation.environment_revision,
                                RecoveryAttemptOutcome.SUCCEEDED,
                            )
                            state.recovery_incident.terminal_outcome = "recovered"
                            state.recovery_diagnostics = state.recovery_incident.diagnostics()
                            parent = trace.add(
                                "RecoveryIncidentResolved",
                                {
                                    "state": state.phase,
                                    "incident": state.recovery_diagnostics,
                                },
                                parents=[parent.id],
                            )
                        state.final_result = {
                            "task_skill_id": skill_progress.skill_id,
                            "task_skill_version": skill_progress.version,
                            "completed_step_ids": list(skill_progress.completed_step_ids),
                        }
                        parent = trace.add(
                            "TaskSkillCompleted",
                            {"state": state.phase, **state.final_result},
                            parents=[parent.id],
                        )
                        state.transition(RuntimeStep.DONE.value)
                        parent = trace.add(
                            "TaskCompleted",
                            {"state": state.phase, "result": state.final_result},
                            parents=[parent.id],
                        )
                        return self._finish(
                            envelope,
                            state,
                            trace,
                            RuntimeStep.DONE,
                            parent,
                            None,
                            latest_verification,
                        )
                if contract.grounding_candidate is not None:
                    state.complete_grounding_recovery(contract.grounding_candidate.semantic_target_id)
                if state.recovery_incident is not None and state.recovery_incident.terminal_outcome == "open":
                    state.recovery_incident.complete_pending(
                        post_snapshot.observation.environment_revision,
                        RecoveryAttemptOutcome.SUCCEEDED,
                    )
                    state.recovery_incident.terminal_outcome = "recovered"
                    state.recovery_diagnostics = state.recovery_incident.diagnostics()
                    parent = trace.add(
                        "RecoveryIncidentResolved",
                        {"state": state.phase, "incident": state.recovery_diagnostics},
                        parents=[parent.id],
                    )
                if state.task_plan is not None and state.plan_progress is not None:
                    active_id = state.plan_progress.active_subgoal_id
                    subgoal = next((item for item in state.task_plan.subgoals if item.subgoal_id == active_id), None)
                    progress_report = (
                        self.subgoal_verifier.verify(
                            subgoal,
                            latest_verification,
                            post_snapshot.observation,
                        )
                        if subgoal is not None
                        else None
                    )
                    if progress_report is not None and progress_report.passed and subgoal is not None:
                        state.complete_subgoal(
                            subgoal.subgoal_id,
                            progress_report.match.evidence_ids,
                        )
                        parent = trace.add(
                            "SubgoalCompleted",
                            {
                                "state": state.phase,
                                "plan_id": state.task_plan.plan_id,
                                "subgoal_id": subgoal.subgoal_id,
                                "evidence": list(progress_report.match.evidence_ids),
                                "criterion_evidence_links": [asdict(item) for item in progress_report.match.links],
                            },
                            parents=[parent.id],
                        )
                        if _task_plan_completed(state):
                            state.final_result = {
                                "task_plan_id": state.task_plan.plan_id,
                                "completed_subgoal_ids": list(state.plan_progress.completed_subgoal_ids),
                            }
                            state.transition(RuntimeStep.DONE.value)
                            parent = trace.add(
                                "TaskCompleted",
                                {"state": state.phase, "result": state.final_result},
                                parents=[parent.id],
                            )
                            return self._finish(
                                envelope,
                                state,
                                trace,
                                RuntimeStep.DONE,
                                parent,
                                None,
                                latest_verification,
                            )
                    elif progress_report is not None and subgoal is not None:
                        parent = trace.add(
                            "SubgoalEvidenceRejected",
                            {
                                "state": state.phase,
                                "plan_id": state.task_plan.plan_id,
                                "subgoal_id": subgoal.subgoal_id,
                                "criteria_match": asdict(progress_report.match),
                            },
                            parents=[parent.id],
                        )
                state.replan_count += 1
                state.transition(RuntimeStep.OBSERVING.value)
                continue

            if skill_step_id and self.task_skill_runtime is not None:
                reason = f"TaskSkill step verification {latest_verification.status.value}"
                self.task_skill_runtime.fallthrough(state, reason)
                parent = trace.add(
                    "TaskSkillStepFailed",
                    {
                        "state": state.phase,
                        "skill_id": state.task_skill.skill_id if state.task_skill else "",
                        "version": state.task_skill.version if state.task_skill else "",
                        "step_id": skill_step_id,
                        "verification": latest_verification.status.value,
                        "preserved_completed_step_ids": (
                            list(state.task_skill.completed_step_ids) if state.task_skill is not None else []
                        ),
                    },
                    parents=[parent.id],
                )
                parent = self._trace_task_skill_fallthrough(
                    trace,
                    parent,
                    state,
                    reason,
                    step_id=skill_step_id,
                )
            if not self.features.recovery:
                state.transition(RuntimeStep.FAILED.value)
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.FAILED,
                    parent,
                    RuntimeErrorCode.VERIFICATION_FAILED,
                    latest_verification,
                )
            skill_failure_context: dict[str, Any] | None = None
            if skill_step_id and state.task_skill is not None:
                skill_failure_context = {
                    "task_skill_id": state.task_skill.skill_id,
                    "task_skill_version": state.task_skill.version,
                    "task_skill_step_id": skill_step_id,
                    "selected_route": (
                        contract.gesture_binding.selected_route
                        if contract.gesture_binding is not None
                        else contract.backend
                    ),
                    "source_evidence": (
                        ([verification_ref.path] if verification_ref else [])
                        + [item.source for item in latest_verification.evidence]
                    ),
                    "preserved_completed_step_ids": list(state.task_skill.completed_step_ids),
                }
            recovery_result = self._recover(
                state,
                contract,
                receipt,
                RuntimeErrorCode.VERIFICATION_FAILED,
                failure_context=skill_failure_context,
            )
            parent = trace.add(
                "RecoveryStarted",
                {
                    "state": state.phase,
                    "action": recovery_result.value,
                    "verification": latest_verification.status.value,
                    "incident": state.recovery_diagnostics,
                },
                parents=[parent.id],
            )
            if recovery_result in {RecoveryAction.REOBSERVE, RecoveryAction.VERIFY_STATE}:
                continue
            state.transition(RuntimeStep.FAILED.value)
            return self._finish(
                envelope,
                state,
                trace,
                RuntimeStep.FAILED,
                parent,
                RuntimeErrorCode.VERIFICATION_FAILED,
                latest_verification,
            )

    def _bind_contract(
        self,
        contract: ActionContract,
        envelope: TaskEnvelope,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        parameters = dict(contract.parameters)
        if contract.action == "download" and self.artifacts is not None:
            parameters.setdefault("destination_dir", str(self.artifacts.run_dir(envelope.task_id) / "downloads"))
        return replace(
            contract,
            run_id=envelope.task_id,
            snapshot_id=contract.snapshot_id or snapshot.observation.snapshot_id,
            page_revision=contract.page_revision or snapshot.observation.page_revision,
            observed_at_s=contract.observed_at_s or snapshot.observation.observed_at_s,
            parameters=parameters,
            contract_hash="",
        )

    def _recover(
        self,
        state: StateKernel,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        error: RuntimeErrorCode | None,
        *,
        failure_context: dict[str, Any] | None = None,
    ) -> RecoveryAction:
        failure_phase = state.phase
        state.transition(RuntimeStep.RECOVERING.value)
        effect_may_have_occurred = bool(receipt and receipt.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT)
        signature = FailureSignature.from_failure(
            contract,
            receipt,
            phase=failure_phase,
            error_code=error,
            state_revision=state.current_revision(),
        )
        incident = state.recovery_incident
        if incident is None or incident.terminal_outcome != "open":
            incident = RecoveryIncident(
                incident_id=f"recovery-{state.task_id}-{state.recovery_count + 1}",
                source_contract_id=contract.id,
                source_snapshot_id=contract.snapshot_id,
                root_failure=signature,
            )
            state.recovery_incident = incident
        else:
            incident.complete_pending(state.current_revision(), RecoveryAttemptOutcome.FAILED)
            incident.symptom_chain.append(signature)
        if failure_context:
            incident.context.update(failure_context)

        tried_backends = [item.backend for item in state.receipts]
        fallbacks_remaining = any(item not in set(tried_backends) for item in contract.fallback_backends)
        assessment = self.cascade_detector.assess(
            incident,
            signature,
            fallbacks_remaining=fallbacks_remaining,
            effect_may_have_occurred=effect_may_have_occurred,
            idempotency_key=contract.idempotency_key,
        )
        incident.findings.extend(item for item in assessment.findings if item not in incident.findings)
        context = RecoveryContext(
            attempt=state.recovery_count,
            recovery_count=state.recovery_count,
            tried_backends=tried_backends,
            effect_may_have_occurred=effect_may_have_occurred,
            failure_signature=signature,
            task_id=state.task_id,
        )
        decision = (
            RecoveryDecision(RecoveryAction.ABORT, "recovery cascade detector stopped a repeated or unsafe loop")
            if assessment.should_abort
            else self.recovery.decide(contract, receipt, context, error_code=error)
        )
        if contract.grounding_candidate is not None:
            if decision.action == RecoveryAction.REROUTE:
                state.record_grounding_reroute(
                    contract,
                    decision.reason,
                    exclude_candidate=True,
                )
            elif decision.action in {RecoveryAction.REOBSERVE, RecoveryAction.RETRY}:
                # Stale state and safe idempotent retry both require a newly
                # observed, newly hashed contract, but do not prove that the
                # semantic grounding route itself is invalid.
                state.record_grounding_reroute(
                    contract,
                    decision.reason,
                    exclude_candidate=False,
                )
        outcome = RecoveryAttemptOutcome.LOOP_ABORTED if assessment.should_abort else RecoveryAttemptOutcome.PENDING
        incident.attempts.append(
            RecoveryAttempt(
                index=len(incident.attempts) + 1,
                signature=signature,
                recovery_action=decision.action,
                state_before=state.current_revision(),
                outcome=outcome,
                effect_may_have_occurred=effect_may_have_occurred,
                idempotency_key=contract.idempotency_key,
            )
        )
        if assessment.should_abort:
            incident.terminal_outcome = RecoveryAttemptOutcome.LOOP_ABORTED.value
        elif decision.action == RecoveryAction.ABORT:
            incident.terminal_outcome = "aborted"
        state.recovery_diagnostics = incident.diagnostics()
        state.recovery_count += 1
        if decision.action in {
            RecoveryAction.REOBSERVE,
            RecoveryAction.RETRY,
            RecoveryAction.REROUTE,
            RecoveryAction.VERIFY_STATE,
        }:
            state.transition(RuntimeStep.OBSERVING.value)
        return decision.action

    def _budget_error(self, state: StateKernel) -> RuntimeErrorCode | None:
        if state.step_count >= self.budget.max_steps:
            return RuntimeErrorCode.EXECUTION_FAILED
        if state.observation_count >= self.budget.max_observations:
            return RuntimeErrorCode.EXECUTION_FAILED
        if state.replan_count >= self.budget.max_replans:
            return RuntimeErrorCode.EXECUTION_FAILED
        if state.recovery_count >= self.budget.max_recoveries:
            return RuntimeErrorCode.EXECUTION_FAILED
        if state.effectful_action_count >= self.budget.max_effectful_actions:
            return RuntimeErrorCode.UNSAFE_ACTION
        return None

    def _write_observation(self, run_id: str, sequence: int, snapshot: BrowserSnapshot) -> ArtifactRef | None:
        return self.artifacts.write_observation(run_id, sequence, snapshot.observation) if self.artifacts else None

    def _capture(self, run_id: str, sequence: int) -> BrowserSnapshot:
        if self.artifacts is not None and isinstance(self.observer, BrowserSession):
            screenshot_path = self.artifacts.run_dir(run_id) / "screenshots" / f"screenshot_{sequence:04d}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = self.observer.capture(screenshot_path=str(screenshot_path))
            if not screenshot_path.exists():
                screenshot_path.write_bytes(self.observer.screenshot())
            self.artifacts.register_file(run_id, screenshot_path, "image/png")
            return snapshot
        return self.observer.capture()

    def _fulfill_targeted_perception(
        self,
        run_id: str,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
    ) -> tuple[BrowserSnapshot, TraceNode]:
        """Acquire bounded coherent snapshots when arbitration requests them."""

        capture_targeted = getattr(self.observer, "capture_targeted", None)
        while snapshot.active_perception_requests:
            if not callable(capture_targeted):
                parent = trace.add(
                    "TargetedPerceptionUnavailable",
                    {
                        "state": state.phase,
                        "reason": "observation source has no capture_targeted port",
                    },
                    parents=[parent.id],
                )
                break
            if (
                state.active_perception_count >= self.budget.max_active_perception_observations
                or state.observation_count >= self.budget.max_observations
            ):
                parent = trace.add(
                    "TargetedPerceptionBudgetExhausted",
                    {
                        "state": state.phase,
                        "active_perception_count": state.active_perception_count,
                        "max_active_perception_observations": (self.budget.max_active_perception_observations),
                    },
                    parents=[parent.id],
                )
                break
            targeted = capture_targeted(snapshot.active_perception_requests)
            if inspect.isawaitable(targeted):
                targeted = resolve_awaitable(targeted)
            if not isinstance(targeted, BrowserSnapshot):
                raise TypeError("capture_targeted must return one coherent BrowserSnapshot")
            state.active_perception_count += 1
            state.remember_observation(targeted.observation)
            targeted_ref = self._write_observation(run_id, state.observation_count, targeted)
            self._index(trace, targeted_ref)
            self._index_paths(trace, targeted.observation.artifact_refs)
            parent = trace.add(
                "TargetedPerceptionCaptured",
                {
                    "state": state.phase,
                    "snapshot_id": targeted.observation.snapshot_id,
                    "page_revision": targeted.observation.page_revision,
                    "environment_revision": targeted.observation.environment_revision,
                    "artifact_refs": ([targeted_ref.path] if targeted_ref else []) + targeted.observation.artifact_refs,
                },
                parents=[parent.id],
            )
            parent = self._trace_source_arbitration(trace, parent, targeted, state.phase)
            snapshot = targeted
        return snapshot, parent

    @staticmethod
    def _trace_task_skill_fallthrough(
        trace: TraceDag,
        parent: TraceNode,
        state: StateKernel,
        reason: str,
        *,
        step_id: str = "",
    ) -> TraceNode:
        progress = state.task_skill
        return trace.add(
            "TaskSkillFellThrough",
            {
                "state": state.phase,
                "skill_id": progress.skill_id if progress else "",
                "version": progress.version if progress else "",
                "step_id": step_id,
                "reason": reason,
                "preserved_completed_step_ids": (list(progress.completed_step_ids) if progress else []),
                "preserved_evidence": list(progress.evidence) if progress else [],
                "fallback": "system_2",
            },
            parents=[parent.id],
        )

    @staticmethod
    def _trace_source_arbitration(
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        state: str,
    ) -> TraceNode:
        if snapshot.source_assertions:
            parent = trace.add(
                "SourceAssertionsCollected",
                {
                    "state": state,
                    "assertions": [
                        {
                            "assertion_id": item.assertion_id,
                            "entity_key": item.entity_key,
                            "property_key": item.property_key,
                            "source": item.source.value,
                            "observation_epoch_id": item.observation_epoch_id,
                            "parser_id": item.parser_id,
                            "schema_version": item.schema_version,
                            "evidence_refs": list(item.evidence_refs),
                        }
                        for item in snapshot.source_assertions
                    ],
                },
                parents=[parent.id],
            )
        if snapshot.assertion_decisions:
            parent = trace.add(
                "SourceAssertionsArbitrated",
                {
                    "state": state,
                    "decisions": [
                        {
                            "entity_key": item.entity_key,
                            "property_key": item.property_key,
                            "status": item.status.value,
                            "accepted_assertion_id": item.accepted_assertion_id,
                            "assertion_ids": [claim.assertion_id for claim in item.assertions],
                            "reason": item.reason,
                            "material": item.material,
                        }
                        for item in snapshot.assertion_decisions
                    ],
                },
                parents=[parent.id],
            )
        if snapshot.active_perception_requests:
            parent = trace.add(
                "TargetedPerceptionRequested",
                {
                    "state": state,
                    "requests": [
                        {
                            "entity_key": item.entity_key,
                            "property_key": item.property_key,
                            "requested_sources": [source.value for source in item.requested_sources],
                            "reason": item.reason,
                            "max_observations": item.max_observations,
                        }
                        for item in snapshot.active_perception_requests
                    ],
                },
                parents=[parent.id],
            )
        return parent

    def _write_receipt(self, run_id: str, sequence: int, receipt: ExecutionReceipt) -> ArtifactRef | None:
        if self.artifacts is None:
            return None
        download_path = receipt.evidence.get("path")
        if isinstance(download_path, str) and download_path:
            path = self.artifacts.run_dir(run_id) / "downloads" / Path(download_path).name
            if path.exists():
                self.artifacts.register_file(run_id, path, "application/octet-stream")
        return self.artifacts.write_receipt(run_id, sequence, receipt)

    def _write_verification(self, run_id: str, sequence: int, report: VerificationReport) -> ArtifactRef | None:
        return self.artifacts.write_verification(run_id, sequence, report) if self.artifacts else None

    @staticmethod
    def _index(trace: TraceDag, artifact: ArtifactRef | None) -> None:
        if artifact is not None:
            trace.artifact_index.append(artifact.path)

    @staticmethod
    def _index_paths(trace: TraceDag, paths: list[str]) -> None:
        trace.artifact_index.extend(path for path in paths if path)

    def _finish(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        status: RuntimeStep,
        parent: TraceNode | None,
        error_code: RuntimeErrorCode | None,
        verification: VerificationReport | None,
    ) -> CoordinatorResult:
        del parent
        artifact_refs: list[ArtifactRef] = []
        if self.artifacts is not None:
            self.artifacts.finalize(
                envelope.task_id,
                trace,
                {
                    "run_id": envelope.task_id,
                    "goal": envelope.goal,
                    "status": status.value,
                    "error_code": error_code.value if error_code else None,
                    "result": state.final_result,
                    "state": asdict(state),
                },
            )
            artifact_refs = self.artifacts.references(envelope.task_id)
        return CoordinatorResult(
            run_id=envelope.task_id,
            status=status,
            state=state,
            trace=trace,
            result=state.final_result,
            error_code=error_code,
            verification=verification,
            artifacts=artifact_refs,
        )


def _resolve_planner_decision(
    value: PlannerDecision | Awaitable[PlannerDecision],
) -> PlannerDecision:
    if not inspect.isawaitable(value):
        return value
    return resolve_awaitable(_await_planner_decision(value))


async def _await_planner_decision(value: Awaitable[PlannerDecision]) -> PlannerDecision:
    return await value


def _resolve_task_plan(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    return resolve_awaitable(value)


def _task_plan_completed(state: StateKernel) -> bool:
    if state.task_plan is None or state.plan_progress is None:
        return False
    completed = set(state.plan_progress.completed_subgoal_ids)
    return all(subgoal.subgoal_id in completed for subgoal in state.task_plan.subgoals)


def _action_progress_signature(
    proposal: PlannerProposal | None,
    contract: ActionContract,
) -> str:
    """Canonical semantic action identity for deterministic progress checks."""

    if proposal is not None:
        payload: dict[str, Any] = {
            "action_kind": proposal.action_kind.value,
            "target": proposal.target_affordance_id,
            "parameters": proposal.parameters,
        }
        if proposal.destination_affordance_id:
            payload["destination"] = proposal.destination_affordance_id
    else:
        payload = {
            "action_kind": contract.action,
            "target": contract.locator.get("bid") or contract.affordance_id,
            "parameters": contract.parameters,
        }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _proposal_error_code(code: ProposalRejectionCode) -> RuntimeErrorCode:
    if code == ProposalRejectionCode.STALE_TASK_REVISION:
        return RuntimeErrorCode.STALE_TASK_REVISION
    if code == ProposalRejectionCode.STALE_STATE_VERSION:
        return RuntimeErrorCode.STALE_STATE_VERSION
    if code == ProposalRejectionCode.STALE_SNAPSHOT:
        return RuntimeErrorCode.SNAPSHOT_MISMATCH
    return RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED


def _provider_runtime_error(kind: ProviderFailureKind) -> RuntimeErrorCode:
    return {
        ProviderFailureKind.RATE_LIMIT_TRANSIENT: RuntimeErrorCode.RATE_LIMIT_TRANSIENT,
        ProviderFailureKind.QUOTA_EXHAUSTED: RuntimeErrorCode.QUOTA_EXHAUSTED,
        ProviderFailureKind.PROVIDER_CAPACITY: RuntimeErrorCode.PROVIDER_CAPACITY,
    }[kind]


def _verification_satisfies_effect(report: VerificationReport) -> bool:
    if not report.passed:
        return False
    return not any(
        item.verifier_kind == "control_state" and isinstance(item.expected, dict) and "changed_from" in item.expected
        for item in report.evidence
    )
