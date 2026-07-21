"""Task-level coordinator for the bounded observe/act/verify loop."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from time import time
from typing import Any, Awaitable, Protocol
from uuid import uuid4

from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSession, BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ApprovalToken, ExecutionReceipt, RuntimeErrorCode
from affordance_runtime.model_port import ModelCallRecord
from affordance_runtime.planning import ContractBuilder, PlannerProposal, ProposalRejected, ProposalRejectionCode
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
                return self._finish(envelope, state, trace, RuntimeStep.FAILED, parent, budget_error, latest_verification)

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
                        envelope, state, trace, RuntimeStep.FAILED, parent,
                        RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED, latest_verification,
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
                        envelope, state, trace, RuntimeStep.FAILED, parent,
                        RuntimeErrorCode.PLANNER_FAILED, latest_verification,
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
                        envelope, state, trace, RuntimeStep.FAILED, parent,
                        RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED, latest_verification,
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
            try:
                decision = _resolve_planner_decision(self.planner.propose(envelope, state, snapshot))
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
                            decision.model_call.model_dump(mode="json")
                            if decision.model_call is not None
                            else None
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
            error = self.task_policy.check(contract, envelope.constraints) or (
                effective_gate.check(contract) if self.features.capability_gate else None
            ) or (
                preflight(contract, snapshot.observation) if self.features.preflight else None
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
                error = preflight(
                    contract,
                    preflight_snapshot.observation,
                    require_snapshot_identity=False,
                    require_environment_revision=False,
                )
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
                error = effective_gate.check(contract) or preflight(
                    contract,
                    approval_snapshot.observation,
                    require_snapshot_identity=False,
                    require_environment_revision=False,
                )
                execution_observation = approval_snapshot.observation
            if error is not None:
                if error in {
                    RuntimeErrorCode.STALE_OBSERVATION,
                    RuntimeErrorCode.STALE_PAGE_REVISION,
                    RuntimeErrorCode.SNAPSHOT_MISMATCH,
                    RuntimeErrorCode.TARGET_FINGERPRINT_MISMATCH,
                    RuntimeErrorCode.LEASE_EXPIRED,
                } and state.recovery_count < self.budget.max_recoveries:
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
                    evidence = self.subgoal_verifier.verify(subgoal, latest_verification) if subgoal is not None else None
                    if evidence is not None and subgoal is not None:
                        state.complete_subgoal(subgoal.subgoal_id, evidence)
                        parent = trace.add(
                            "SubgoalCompleted",
                            {
                                "state": state.phase,
                                "plan_id": state.task_plan.plan_id,
                                "subgoal_id": subgoal.subgoal_id,
                                "evidence": list(evidence),
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
                state.replan_count += 1
                state.transition(RuntimeStep.OBSERVING.value)
                continue

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
            recovery_result = self._recover(state, contract, receipt, RuntimeErrorCode.VERIFICATION_FAILED)
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
        outcome = (
            RecoveryAttemptOutcome.LOOP_ABORTED
            if assessment.should_abort
            else RecoveryAttemptOutcome.PENDING
        )
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
        if decision.action in {RecoveryAction.REOBSERVE, RecoveryAction.RETRY, RecoveryAction.REROUTE, RecoveryAction.VERIFY_STATE}:
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


def _proposal_error_code(code: ProposalRejectionCode) -> RuntimeErrorCode:
    if code == ProposalRejectionCode.STALE_TASK_REVISION:
        return RuntimeErrorCode.STALE_TASK_REVISION
    if code == ProposalRejectionCode.STALE_STATE_VERSION:
        return RuntimeErrorCode.STALE_STATE_VERSION
    if code == ProposalRejectionCode.STALE_SNAPSHOT:
        return RuntimeErrorCode.SNAPSHOT_MISMATCH
    return RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
