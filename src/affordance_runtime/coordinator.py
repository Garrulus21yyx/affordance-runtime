"""Task-level coordinator for the bounded observe/act/verify loop."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from affordance_runtime.active_perception import (
    PerceptionResolutionStatus,
)
from affordance_runtime.active_perception_flow import (
    ActivePerceptionFlow,
    ActivePerceptionFlowContext,
)
from affordance_runtime.approval_contracts import (
    ApprovalProvider,
)
from affordance_runtime.approval_contracts import (
    ConfiguredApprovalProvider as ConfiguredApprovalProvider,
)
from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_binding_phase import ContractBindingPhase
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contract_failure_phase import ContractFailurePhase
from affordance_runtime.contracts import (
    ActionContract,
    ExecutionReceipt,
    RuntimeErrorCode,
)
from affordance_runtime.execution_phase import ExecutionPhase
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    ProposalRejectionContext,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.failure_owner_flow import commit_non_runtime_failure_owner_handoff
from affordance_runtime.model_port import ProviderModelError
from affordance_runtime.perception_phase import PerceptionPhase
from affordance_runtime.perception_session import ObservationSource, PerceptionSession
from affordance_runtime.planner_compatibility import PlannerCompatibilityPort
from affordance_runtime.planning import (
    ContractBuilder,
    PlannerProposalValidator,
)
from affordance_runtime.planning_contracts import PlannerDecision as PlannerDecision  # noqa: F401
from affordance_runtime.planning_failure_phase import PlanningFailurePhase
from affordance_runtime.planning_phase import (
    PlanningDecisionPhase,
)
from affordance_runtime.preflight_phase import PreflightPhase
from affordance_runtime.progress_phase import ProgressPhase
from affordance_runtime.proposal_recovery_policy import ProposalRejectionRecoveryPolicy
from affordance_runtime.recovery_coordinator import RecoveryCoordinator
from affordance_runtime.recovery_owner_dispatcher import RecoveryOwnerDispatcher
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import (
    FailureOwner,
    RecoveryKind,
    RuntimePhase,
    classify_failure,
)
from affordance_runtime.route_calibration import (
    RouteCalibrator,
    RouteOutcome,
    RouteOutcomeStatus,
    RouteScope,
)
from affordance_runtime.runtime import Executor, RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_evidence import (
    semantic_progress_fingerprint,
)
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_flow import TaskPlanFlow
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_plan_phase import commit_task_plan_phase
from affordance_runtime.task_planning import (
    PlanningRouter,
    SubgoalVerifierPort,
    TaskPlannerPort,
    TaskPlanValidator,
    VerifierBackedSubgoalVerifier,
)
from affordance_runtime.task_skill_phase import (
    TaskSkillPhase,
)
from affordance_runtime.task_skill_phase import (
    resolve_planner_decision as _resolve_planner_decision,  # noqa: F401
)
from affordance_runtime.task_skill_progress import TaskSkillRunState
from affordance_runtime.task_skill_progress_phase import TaskSkillProgressPhase
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport, VerifierLadder
from affordance_runtime.verification_failure_phase import VerificationFailurePhase
from affordance_runtime.verification_phase import VerificationPhase
from affordance_runtime.verified_progress_phase import VerifiedProgressPhase

OWNER_DISPATCH_RECOVERY_KINDS = frozenset(
    {
        RecoveryKind.COMPACT_CONTEXT,
        RecoveryKind.REPAIR_MODEL_SCHEMA,
        RecoveryKind.SWITCH_PROVIDER,
    }
)
PROGRESS_PHASE = ProgressPhase()
PERCEPTION_PHASE = PerceptionPhase()
TASK_SKILL_PHASE = TaskSkillPhase()
PLANNING_DECISION_PHASE = PlanningDecisionPhase()
PLANNING_FAILURE_PHASE = PlanningFailurePhase()
CONTRACT_BINDING_PHASE = ContractBindingPhase()
CONTRACT_FAILURE_PHASE = ContractFailurePhase()
PREFLIGHT_PHASE = PreflightPhase()
EXECUTION_PHASE = ExecutionPhase()
VERIFICATION_PHASE = VerificationPhase()
TASK_SKILL_PROGRESS_PHASE = TaskSkillProgressPhase()
VERIFIED_PROGRESS_PHASE = VerifiedProgressPhase()
VERIFICATION_FAILURE_PHASE = VerificationFailurePhase()


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


def _task_skill_progress(
    runtime: object | None,
    state: StateKernel,
) -> TaskSkillRunState | None:
    progress_for = getattr(runtime, "progress_for", None)
    if not callable(progress_for):
        return None
    progress = progress_for(state)
    return progress if isinstance(progress, TaskSkillRunState) else None


@dataclass
class RunCoordinator:
    observer: ObservationSource
    planner: PlannerCompatibilityPort
    executor: Executor
    verifier: VerifierLadder = field(default_factory=VerifierLadder)
    gate: CapabilityGate = field(default_factory=CapabilityGate)
    task_policy: TaskConstraintPolicy = field(default_factory=TaskConstraintPolicy)
    approval_provider: ApprovalProvider | None = None
    artifacts: ArtifactStore | None = None
    budget: RunBudget = field(default_factory=RunBudget)
    features: RuntimeFeatures = field(default_factory=RuntimeFeatures)
    contract_builder: ContractBuilder | None = None
    proposal_validator: PlannerProposalValidator = field(default_factory=PlannerProposalValidator)
    proposal_recovery_policy: ProposalRejectionRecoveryPolicy = field(
        default_factory=ProposalRejectionRecoveryPolicy
    )
    task_planner: TaskPlannerPort | None = field(default_factory=PlanningRouter)
    task_plan_validator: TaskPlanValidator = field(default_factory=TaskPlanValidator)
    subgoal_verifier: SubgoalVerifierPort = field(default_factory=VerifierBackedSubgoalVerifier)
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None
    runtime_profile_digest: str = ""
    loaded_profile_artifact_ids: tuple[str, ...] = ()
    route_calibrator: RouteCalibrator = field(default_factory=RouteCalibrator)
    recovery_coordinator: RecoveryCoordinator = field(default_factory=RecoveryCoordinator)
    recovery_owner_dispatcher: RecoveryOwnerDispatcher = field(
        default_factory=RecoveryOwnerDispatcher
    )
    task_plan_flow: TaskPlanFlow | None = field(init=False, default=None, repr=False)
    perception_session: PerceptionSession = field(init=False, repr=False)
    active_perception_flow: ActivePerceptionFlow = field(init=False, repr=False)
    contract_execution_loop: ContractExecutionLoop = field(init=False, repr=False)
    recovery_phase: RecoveryPhase = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.perception_session = PerceptionSession(self.observer, self.artifacts)
        self.active_perception_flow = ActivePerceptionFlow(self.perception_session)
        self.contract_execution_loop = ContractExecutionLoop(
            executor=self.executor,
            verifier=self.verifier,
            gate=self.gate,
            task_policy=self.task_policy,
            artifacts=self.artifacts,
        )
        self.recovery_phase = RecoveryPhase(
            coordinator=self.recovery_coordinator,
            owner_dispatcher=self.recovery_owner_dispatcher,
        )
        if self.task_planner is not None:
            self.task_plan_flow = TaskPlanFlow(
                TaskPlanLifecycle(
                    planner=self.task_planner,
                    validator=self.task_plan_validator,
                )
            )
        if isinstance(self.contract_builder, ContractBuilder):
            router = self.contract_builder.unified_resolver.router
            self.contract_builder.unified_resolver.router = replace(
                router,
                calibrator=self.route_calibrator,
            )

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
            {
                "state": RuntimeStep.CREATED.value,
                "goal": envelope.goal,
                "constraints": envelope.constraints,
                "task_spec_identity": envelope.task_spec.identity if envelope.task_spec is not None else "",
                "runtime_profile_digest": self.runtime_profile_digest,
                "loaded_profile_artifact_ids": list(self.loaded_profile_artifact_ids),
            },
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
            assert parent is not None
            perception = PERCEPTION_PHASE.run(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                perception_session=self.perception_session,
                contract_execution_loop=self.contract_execution_loop,
                recovery_phase=self.recovery_phase,
                task_skill_runtime=self.task_skill_runtime,
                recovery_enabled=self.features.recovery,
                pending_recovery_kind=_pending_recovery_kind,
                task_skill_progress_for=_task_skill_progress,
                write_observation=self._write_observation,
                index_artifact=self._index,
                index_paths=self._index_paths,
                trace_source_arbitration=self._trace_source_arbitration,
                fulfill_targeted_perception=self._fulfill_targeted_perception,
                recover_phase_failure=self._recover_phase_failure,
            )
            parent = perception.parent
            if perception.latest_verification is not None:
                latest_verification = perception.latest_verification
            if perception.continue_observing:
                continue
            if perception.terminal is not None:
                return self._finish(
                    envelope,
                    state,
                    trace,
                    perception.terminal.status,
                    parent,
                    perception.terminal.error_code,
                    latest_verification,
                )
            assert perception.snapshot is not None
            snapshot = perception.snapshot
            progress_commit = PROGRESS_PHASE.commit_post_observation(
                envelope.task_spec, state, snapshot, self.budget, trace, parent
            )
            parent = progress_commit.parent
            if progress_commit.completion_committed:
                continue
            if self.task_plan_flow is not None and envelope.task_spec is not None:
                task_plan_phase = commit_task_plan_phase(
                    envelope.task_spec, state, snapshot, self.budget, trace, parent,
                    task_plan_flow=self.task_plan_flow,
                    recovery_phase=self.recovery_phase,
                    progress_phase=PROGRESS_PHASE,
                )
                parent = task_plan_phase.parent
                planning_failure = PLANNING_FAILURE_PHASE.handle_task_plan_result(
                    envelope=envelope,
                    state=state,
                    trace=trace,
                    parent=parent,
                    snapshot=snapshot,
                    task_plan_phase=task_plan_phase,
                    recovery_phase=self.recovery_phase,
                    pending_recovery_kind=_pending_recovery_kind,
                    recover_phase_failure=self._recover_phase_failure,
                    owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                        self.recovery_owner_dispatcher
                    ),
                )
                if planning_failure is not None:
                    parent = planning_failure.parent
                    if planning_failure.continue_observing:
                        continue
                    assert planning_failure.terminal is not None
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        planning_failure.terminal.status,
                        parent,
                        planning_failure.terminal.error_code,
                        latest_verification,
                    )
                if task_plan_phase.current_state_completion_committed:
                    continue
            state.transition(RuntimeStep.PLANNING.value)
            if state.task_plan is not None:
                state.activate_next_subgoal()
            skill_step_id = ""
            try:
                task_skill_phase = TASK_SKILL_PHASE.select(
                    task_skill_runtime=self.task_skill_runtime,
                    planner=self.planner,
                    envelope=envelope,
                    state=state,
                    snapshot=snapshot,
                    trace=trace,
                    parent=parent,
                    runtime_profile_digest=self.runtime_profile_digest,
                )
                parent = task_skill_phase.parent
                skill_step_id = task_skill_phase.skill_step_id
                planning_failure = PLANNING_FAILURE_PHASE.handle_task_skill_result(
                    envelope=envelope,
                    state=state,
                    trace=trace,
                    parent=parent,
                    snapshot=snapshot,
                    task_skill_phase=task_skill_phase,
                    recovery_phase=self.recovery_phase,
                    pending_recovery_kind=_pending_recovery_kind,
                    recover_phase_failure=self._recover_phase_failure,
                    owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                        self.recovery_owner_dispatcher
                    ),
                )
                if planning_failure is not None:
                    parent = planning_failure.parent
                    if planning_failure.continue_observing:
                        continue
                    assert planning_failure.terminal is not None
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        planning_failure.terminal.status,
                        parent,
                        planning_failure.terminal.error_code,
                        latest_verification,
                    )
                assert task_skill_phase.decision is not None
                decision = task_skill_phase.decision
            except ProviderModelError as exc:
                planning_failure = PLANNING_FAILURE_PHASE.handle_provider_failure(
                    envelope=envelope,
                    state=state,
                    trace=trace,
                    parent=parent,
                    snapshot=snapshot,
                    error=exc,
                    recovery_phase=self.recovery_phase,
                    pending_recovery_kind=_pending_recovery_kind,
                    recover_phase_failure=self._recover_phase_failure,
                    owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                        self.recovery_owner_dispatcher
                    ),
                )
                parent = planning_failure.parent
                if planning_failure.continue_observing:
                    continue
                assert planning_failure.terminal is not None
                return self._finish(
                    envelope,
                    state,
                    trace,
                    planning_failure.terminal.status,
                    parent,
                    planning_failure.terminal.error_code,
                    latest_verification,
                )
            except Exception as exc:
                planning_failure = (
                    PLANNING_FAILURE_PHASE.handle_unexpected_planner_failure(
                        envelope=envelope,
                        state=state,
                        trace=trace,
                        parent=parent,
                        snapshot=snapshot,
                        error=exc,
                        planner=self.planner,
                        recovery_phase=self.recovery_phase,
                        pending_recovery_kind=_pending_recovery_kind,
                        recover_phase_failure=self._recover_phase_failure,
                        owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                            self.recovery_owner_dispatcher
                        ),
                    )
                )
                parent = planning_failure.parent
                if planning_failure.continue_observing:
                    continue
                assert planning_failure.terminal is not None
                return self._finish(
                    envelope,
                    state,
                    trace,
                    planning_failure.terminal.status,
                    parent,
                    planning_failure.terminal.error_code,
                    latest_verification,
                )
            planning_decision = PLANNING_DECISION_PHASE.handle(
                decision=decision,
                envelope=envelope,
                state=state,
                snapshot=snapshot,
                trace=trace,
                parent=parent,
                latest_verification=latest_verification,
                proposal_validator=self.proposal_validator,
                proposal_recovery_policy=self.proposal_recovery_policy,
                recovery_phase=self.recovery_phase,
                task_skill_runtime=self.task_skill_runtime,
                skill_step_id=skill_step_id,
                owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                    self.recovery_owner_dispatcher
                ),
            )
            parent = planning_decision.parent
            decision = planning_decision.decision
            if planning_decision.terminal is not None:
                return self._finish(
                    envelope,
                    state,
                    trace,
                    planning_decision.terminal.status,
                    parent,
                    planning_decision.terminal.error_code,
                    latest_verification,
                )
            planning_failure = PLANNING_FAILURE_PHASE.handle_planning_decision_result(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                snapshot=snapshot,
                planning_decision=planning_decision,
                recovery_phase=self.recovery_phase,
                task_skill_runtime=self.task_skill_runtime,
                skill_step_id=skill_step_id,
                pending_recovery_kind=_pending_recovery_kind,
                recover_phase_failure=self._recover_phase_failure,
                owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                    self.recovery_owner_dispatcher
                ),
            )
            if planning_failure is not None:
                parent = planning_failure.parent
                if planning_failure.continue_observing:
                    continue
                assert planning_failure.terminal is not None
                return self._finish(
                    envelope,
                    state,
                    trace,
                    planning_failure.terminal.status,
                    parent,
                    planning_failure.terminal.error_code,
                    latest_verification,
                )
            contract_binding = CONTRACT_BINDING_PHASE.bind(
                decision=decision,
                envelope=envelope,
                state=state,
                snapshot=snapshot,
                trace=trace,
                parent=parent,
                contract_builder=self.contract_builder,
                contract_execution_loop=self.contract_execution_loop,
                recovery_phase=self.recovery_phase,
                task_skill_runtime=self.task_skill_runtime,
                skill_step_id=skill_step_id,
                approval_required_risks=frozenset(self.gate.approval_required_risks),
                approval_required_capabilities=frozenset(self.gate.approval_required_capabilities),
            )
            parent = contract_binding.parent
            if contract_binding.continue_observing:
                continue
            if contract_binding.terminal is not None:
                return self._finish(
                    envelope,
                    state,
                    trace,
                    contract_binding.terminal.status,
                    parent,
                    contract_binding.terminal.error_code,
                    latest_verification,
                )
            contract_failure = CONTRACT_FAILURE_PHASE.handle(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                snapshot=snapshot,
                contract_binding=contract_binding,
                recover_phase_failure=self._recover_phase_failure,
            )
            if contract_failure is not None:
                parent = contract_failure.parent
                if contract_failure.continue_observing:
                    continue
                assert contract_failure.terminal is not None
                return self._finish(
                    envelope,
                    state,
                    trace,
                    contract_failure.terminal.status,
                    parent,
                    contract_failure.terminal.error_code,
                    latest_verification,
                )
            assert contract_binding.contract is not None
            contract = contract_binding.contract
            action_signature = contract_binding.action_signature
            preflight_result = PREFLIGHT_PHASE.run(
                decision=decision,
                envelope=envelope,
                state=state,
                snapshot=snapshot,
                trace=trace,
                parent=parent,
                contract=contract,
                contract_execution_loop=self.contract_execution_loop,
                contract_binding_phase=CONTRACT_BINDING_PHASE,
                perception_session=self.perception_session,
                approval_provider=self.approval_provider,
                runtime_gate=self.gate,
                preflight_enabled=self.features.preflight,
                capability_gate_enabled=self.features.capability_gate,
                max_recoveries=self.budget.max_recoveries,
                contract_builder=self.contract_builder,
                recovery_phase=self.recovery_phase,
                write_observation=self._write_observation,
                index_artifact=self._index,
                index_paths=self._index_paths,
                trace_source_arbitration=self._trace_source_arbitration,
                fulfill_targeted_perception=self._fulfill_targeted_perception,
                recover_execution_failure=self._recover_execution_failure,
                recover_phase_failure=self._recover_phase_failure,
                terminal_recovery_status=lambda current_state: _terminal_recovery_status(
                    current_state,
                    fallback=RuntimeStep.ABORTED,
                ),
                trace_recovery_started=_trace_recovery_started,
            )
            parent = preflight_result.parent
            contract = preflight_result.contract
            execution_observation = preflight_result.execution_observation
            if preflight_result.continue_observing:
                continue
            if preflight_result.terminal is not None:
                return self._finish(
                    envelope,
                    state,
                    trace,
                    preflight_result.terminal.status,
                    parent,
                    preflight_result.terminal.error_code,
                    latest_verification,
                )
            execution_result = EXECUTION_PHASE.run(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                contract=contract,
                execution_observation=execution_observation,
                contract_execution_loop=self.contract_execution_loop,
                perception_session=self.perception_session,
                recovery_phase=self.recovery_phase,
                task_skill_runtime=self.task_skill_runtime,
                recovery_enabled=self.features.recovery,
                write_receipt=self._write_receipt,
                write_observation=self._write_observation,
                index_artifact=self._index,
                index_paths=self._index_paths,
                trace_source_arbitration=self._trace_source_arbitration,
                fulfill_targeted_perception=self._fulfill_targeted_perception,
                recover_execution_failure=self._recover_execution_failure,
                terminal_recovery_status=lambda current_state: _terminal_recovery_status(
                    current_state,
                    fallback=RuntimeStep.FAILED,
                ),
                trace_recovery_started=_trace_recovery_started,
            )
            parent = execution_result.parent
            if execution_result.latest_verification is not None:
                latest_verification = execution_result.latest_verification
            if execution_result.continue_observing:
                continue
            if execution_result.terminal is not None:
                return self._finish(
                    envelope,
                    state,
                    trace,
                    execution_result.terminal.status,
                    parent,
                    execution_result.terminal.error_code,
                    latest_verification,
                )
            assert execution_result.receipt is not None
            receipt = execution_result.receipt
            state.transition(RuntimeStep.VERIFYING.value)
            verification_result = VERIFICATION_PHASE.run(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                contract=contract,
                receipt=receipt,
                execution_observation=execution_observation,
                action_signature=action_signature,
                skill_step_id=skill_step_id,
                contract_execution_loop=self.contract_execution_loop,
                perception_session=self.perception_session,
                structural_verification_enabled=self.features.structural_verification,
                write_observation=self._write_observation,
                write_verification=self._write_verification,
                index_artifact=self._index,
                index_paths=self._index_paths,
                trace_source_arbitration=self._trace_source_arbitration,
                fulfill_targeted_perception=self._fulfill_targeted_perception,
                record_route_outcome=self._record_route_outcome,
                decision_has_proposal=decision.proposal is not None,
            )
            parent = verification_result.parent
            post_snapshot = verification_result.post_snapshot
            latest_verification = verification_result.verification
            verification_ref = verification_result.verification_ref
            task_skill_progress_result = TASK_SKILL_PROGRESS_PHASE.run(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                contract=contract,
                skill_step_id=skill_step_id,
                task_skill_runtime=self.task_skill_runtime,
                verification=latest_verification,
                post_snapshot=post_snapshot,
                verification_ref_path=verification_ref.path if verification_ref else "",
            )
            parent = task_skill_progress_result.parent
            if task_skill_progress_result.terminal is not None:
                return self._finish(
                    envelope,
                    state,
                    trace,
                    task_skill_progress_result.terminal.status,
                    parent,
                    None,
                    latest_verification,
                )
            skill_complete = task_skill_progress_result.skill_complete
            if latest_verification.passed:
                verified_progress = VERIFIED_PROGRESS_PHASE.run(
                    envelope=envelope,
                    state=state,
                    trace=trace,
                    parent=parent,
                    contract=contract,
                    subgoal_verifier=self.subgoal_verifier,
                    verification=latest_verification,
                    post_snapshot=post_snapshot,
                    task_planner_is_router=isinstance(self.task_planner, PlanningRouter),
                    skill_complete=skill_complete,
                    skill_progress=task_skill_progress_result.skill_progress,
                )
                parent = verified_progress.parent
                if verified_progress.terminal is not None:
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        verified_progress.terminal.status,
                        parent,
                        None,
                        latest_verification,
                    )
                if verified_progress.continue_observing:
                    continue
            verification_failure = VERIFICATION_FAILURE_PHASE.run(
                envelope=envelope,
                state=state,
                trace=trace,
                parent=parent,
                contract=contract,
                receipt=receipt,
                verification=latest_verification,
                verification_ref=verification_ref,
                post_snapshot=post_snapshot,
                recovery_enabled=self.features.recovery,
                skill_step_id=skill_step_id,
                task_skill_runtime=self.task_skill_runtime,
                task_skill_progress_for=_task_skill_progress,
                recover_execution_failure=self._recover_execution_failure,
                trace_recovery_started=_trace_recovery_started,
                terminal_recovery_status=_terminal_recovery_status,
            )
            parent = verification_failure.parent
            if verification_failure.continue_observing:
                continue
            assert verification_failure.terminal is not None
            return self._finish(
                envelope,
                state,
                trace,
                verification_failure.terminal.status,
                parent,
                verification_failure.terminal.error_code,
                latest_verification,
            )

    def _recover_execution_failure(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        receipt: ExecutionReceipt | None,
        error: RuntimeErrorCode | None,
        *,
        failure_context: dict[str, Any] | None = None,
        verification: VerificationReport | None = None, verification_ref: str = "",
    ) -> tuple[RecoveryKind, TraceNode]:
        task_plan = state.task_plan
        if verification is not None or error == RuntimeErrorCode.VERIFICATION_FAILED:
            phase = FailurePhase.VERIFICATION
            failure_class = FailureClass.VERIFICATION
        elif state.phase == RuntimeStep.PREFLIGHT.value:
            phase = FailurePhase.PREFLIGHT
            failure_class = (
                FailureClass.AUTHORITY
                if error
                in {
                    RuntimeErrorCode.CAPABILITY_DENIED,
                    RuntimeErrorCode.UNSAFE_ACTION,
                    RuntimeErrorCode.APPROVAL_REQUIRED,
                }
                else FailureClass.VALIDATION
            )
        elif (
            receipt is not None
            and receipt.error_code == RuntimeErrorCode.EXECUTION_TIMEOUT
            and receipt.evidence.get("dispatched") is not False
        ):
            phase = FailurePhase.EXECUTION_UNCERTAIN
            failure_class = FailureClass.EXECUTION
        else:
            phase = FailurePhase.EXECUTION_NOT_DISPATCHED
            failure_class = FailureClass.EXECUTION
        failure_message = (
            verification.reason
            if verification is not None and verification.reason
            else error.value
            if isinstance(error, RuntimeErrorCode)
            else str(error or "execution failed")
        )
        failure = make_failure_envelope(
            run_id=envelope.task_id,
            phase=phase,
            failure_class=failure_class,
            error_code=error or RuntimeErrorCode.EXECUTION_FAILED,
            message=failure_message,
            state_version=state.version,
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
            observation_epoch_id=state.current_snapshot_id,
            snapshot_id=state.current_snapshot_id,
            contract=contract,
            receipt=receipt,
            expected_effect=contract.intent,
            evidence_refs=(verification_ref,) if verification_ref else (),
            verification_ref=verification_ref,
            attempted_strategy_ids=tuple(sorted(state.attempted_recovery_strategy_ids)),
            rejected_assumptions=tuple(state.disproved_assumptions),
            remaining_budgets=self._remaining_recovery_budgets(state),
            progress_fingerprint=semantic_progress_fingerprint(state),
            debug_context=failure_context or {},
        )
        available: set[RecoveryKind] = {RecoveryKind.ABORT}
        if phase == FailurePhase.PREFLIGHT:
            available.add(RecoveryKind.REOBSERVE)
        if phase in {
            FailurePhase.EXECUTION_UNCERTAIN,
            FailurePhase.VERIFICATION,
        }:
            available.update(
                {
                    RecoveryKind.REOBSERVE,
                    RecoveryKind.INSPECT_POST_STATE,
                }
            )
        fresh_candidate_id = ""
        fresh_route_ref = ""
        route_plan = contract.route_plan
        if route_plan is not None:
            for candidate in route_plan.viable_alternatives:
                if candidate.candidate_id != route_plan.selected_candidate.candidate_id:
                    fresh_candidate_id = candidate.candidate_id
                    available.add(RecoveryKind.REROUTE)
                    break
        if not fresh_candidate_id:
            tried_backends = {item.backend for item in state.receipts}
            for backend in contract.fallback_backends:
                if backend not in tried_backends:
                    fresh_route_ref = backend
                    available.add(RecoveryKind.REROUTE)
                    break
        if contract.idempotency_key:
            available.add(RecoveryKind.RETRY_IDEMPOTENT)
        if contract.compensation:
            available.add(RecoveryKind.COMPENSATE)
        classification = classify_failure(failure)
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            return commit_non_runtime_failure_owner_handoff(
                state,
                trace,
                parent,
                failure=failure,
                classification=classification,
            )
        recovery_result = self.recovery_phase.handle_phase_failure(
            failure=failure,
            state=state,
            trace=trace,
            parent=parent,
            available_commands=frozenset(available),
            runtime_profile_digest=self.runtime_profile_digest,
            loaded_profile_artifact_ids=self.loaded_profile_artifact_ids,
            fresh_candidate_id=fresh_candidate_id,
            fresh_route_ref=fresh_route_ref,
            idempotency_key=contract.idempotency_key,
            compensation_contract_id=(
                f"compensation:{contract.id}" if contract.compensation else ""
            ),
        )
        parent = recovery_result.parent
        recovery_kind = recovery_result.recovery_kind
        if contract.grounding_candidate is not None:
            if recovery_kind == RecoveryKind.REROUTE:
                state.record_grounding_reroute(
                    contract,
                    "recovery reroute",
                    exclude_candidate=True,
                )
            elif recovery_kind in {
                RecoveryKind.REOBSERVE,
                RecoveryKind.RETRY_IDEMPOTENT,
            }:
                state.record_grounding_reroute(
                    contract,
                    "recovery requires fresh observation",
                    exclude_candidate=False,
                )
        return recovery_kind, parent

    def _recover_phase_failure(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        phase: FailurePhase,
        failure_class: FailureClass,
        error_code: RuntimeErrorCode | str,
        message: str,
        available_commands: frozenset[RecoveryKind],
        snapshot: BrowserSnapshot | None = None,
        proposal_id: str = "",
        proposal_rejection: ProposalRejectionContext | None = None,
        expected_effect: str = "",
        recoverable: bool = True,
        abort_reentry_phase: RuntimePhase = RuntimePhase.ABORTED,
    ) -> tuple[RecoveryKind, TraceNode]:
        task_plan = state.task_plan
        failure = make_failure_envelope(
            run_id=envelope.task_id,
            phase=phase,
            failure_class=failure_class,
            error_code=error_code,
            message=message,
            state_version=state.version,
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
            observation_epoch_id=(
                snapshot.observation.snapshot_id if snapshot is not None else state.current_snapshot_id
            ),
            snapshot_id=(
                snapshot.observation.snapshot_id if snapshot is not None else state.current_snapshot_id
            ),
            proposal_id=proposal_id,
            proposal_rejection=proposal_rejection,
            expected_effect=expected_effect or envelope.goal,
            effect_status=EffectStatus.NOT_DISPATCHED,
            attempted_strategy_ids=tuple(sorted(state.attempted_recovery_strategy_ids)),
            rejected_assumptions=tuple(state.disproved_assumptions),
            remaining_budgets=self._remaining_recovery_budgets(state),
            recoverable=recoverable,
            progress_fingerprint=semantic_progress_fingerprint(state),
        )
        classification = classify_failure(failure)
        if classification.owner != FailureOwner.RUNTIME_RECOVERY:
            return commit_non_runtime_failure_owner_handoff(
                state,
                trace,
                parent,
                failure=failure,
                classification=classification,
            )
        recovery_result = self.recovery_phase.handle_phase_failure(
            failure=failure,
            state=state,
            trace=trace,
            parent=parent,
            available_commands=available_commands,
            runtime_profile_digest=self.runtime_profile_digest,
            loaded_profile_artifact_ids=self.loaded_profile_artifact_ids,
            abort_reentry_phase=abort_reentry_phase,
        )
        return recovery_result.recovery_kind, recovery_result.parent

    def _remaining_recovery_budgets(self, state: StateKernel) -> RemainingRecoveryBudgets:
        return RemainingRecoveryBudgets(
            recoveries=max(0, self.budget.max_recoveries - state.recovery_count),
            observations=max(0, self.budget.max_observations - state.observation_count),
            replans=max(0, self.budget.max_replans - state.replan_count),
            provider_switches=1,
            user_escalations=1,
            timeout_ms=120_000,
            model_calls=max(0, self.budget.max_replans - state.replan_count),
            estimated_cost=10.0,
        )

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

    def _fulfill_targeted_perception(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
    ) -> tuple[BrowserSnapshot, TraceNode]:
        """Commit typed active-perception results from the owning flow."""

        while True:
            run_id = envelope.task_id
            task_plan = state.task_plan
            plan_version = task_plan.plan_version if task_plan is not None else 0
            remaining_observations = min(
                self.budget.max_active_perception_observations - state.active_perception_count,
                self.budget.max_observations - state.observation_count,
            )
            effectful_action = (
                envelope.task_spec is not None
                and envelope.task_spec.operation_class
                not in {OperationClass.READ_ONLY, OperationClass.NAVIGATION}
            )
            preparation = self.active_perception_flow.prepare(
                ActivePerceptionFlowContext(
                    snapshot=snapshot,
                    run_id=run_id,
                    task_revision=(
                        task_plan.task_revision
                        if task_plan is not None
                        else envelope.task_spec.revision
                        if envelope.task_spec is not None
                        else 1
                    ),
                    plan_version=plan_version,
                    active_subgoal_id=(
                        state.plan_progress.active_subgoal_id
                        if state.plan_progress is not None
                        else ""
                    ),
                    state_version=state.version,
                    remaining_observations=remaining_observations,
                    attempted_probe_fingerprints=frozenset(
                        state.attempted_probe_fingerprints
                    ),
                    effectful_action=effectful_action,
                )
            )
            gaps = preparation.gaps
            state.evidence_gaps = gaps
            if not gaps:
                break
            parent = trace.add(
                "EvidenceGapDetected",
                {
                    "state": state.phase,
                    "snapshot_id": snapshot.observation.snapshot_id,
                    "gaps": [item.model_dump(mode="json") for item in gaps],
                },
                parents=[parent.id],
            )
            decision = preparation.decision
            if decision is None:  # guarded by non-empty gaps
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
                            self.budget.max_active_perception_observations
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
            probe_result = self.active_perception_flow.execute(preparation)
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
            targeted_ref = self._write_observation(
                run_id=run_id,
                sequence=state.observation_count,
                snapshot=targeted,
            )
            self._index(trace, targeted_ref)
            self._index_paths(trace, targeted.observation.artifact_refs)
            parent = trace.add(
                "TargetedPerceptionCaptured",
                {
                    "state": state.phase,
                    "snapshot_id": targeted.observation.snapshot_id,
                    "page_revision": targeted.observation.page_revision,
                    "environment_revision": targeted.observation.environment_revision,
                    "artifact_refs": ([targeted_ref.path] if targeted_ref else []) + list(targeted.observation.artifact_refs),
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
            parent = self._trace_source_arbitration(trace, parent, targeted, state.phase)
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

    def _record_route_outcome(
        self,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        receipt: ExecutionReceipt,
        report: VerificationReport,
        snapshot: BrowserSnapshot,
        state_phase: str,
    ) -> TraceNode:
        candidate = contract.grounding_candidate
        route_plan = contract.route_plan
        if candidate is None or route_plan is None or not route_plan.verifier_kinds:
            return parent
        scope = RouteScope(
            environment_family=route_plan.environment_scope,
            action_kind=route_plan.action_kind or contract.action,
            source=candidate.source,
            executor=candidate.compatible_executor,
            verifier_kinds=route_plan.verifier_kinds,
        )
        outcome = RouteOutcome.from_verification(
            outcome_id=f"route-outcome:{contract.id}:{snapshot.observation.snapshot_id}",
            scope=scope,
            semantic_target_id=candidate.semantic_target_id,
            candidate_id=candidate.candidate_id,
            contract_id=contract.id,
            report=report,
            post_snapshot_id=snapshot.observation.snapshot_id,
            latency_ms=receipt.latency_ms,
            expected_cost=candidate.expected_cost,
        )
        self.route_calibrator.record(outcome)
        return trace.add(
            "RouteOutcomeRecorded",
            {
                "state": state_phase,
                "outcome_id": outcome.outcome_id,
                "status": outcome.status.value,
                "verification_status": outcome.verification_status.value,
                "trainable": outcome.status != RouteOutcomeStatus.INCONCLUSIVE,
                "semantic_target_id": outcome.semantic_target_id,
                "candidate_id": outcome.candidate_id,
                "contract_id": outcome.contract_id,
                "post_snapshot_id": outcome.post_snapshot_id,
                "evidence_ids": list(outcome.evidence_ids),
                "scope": {
                    "environment_family": scope.environment_family,
                    "action_kind": scope.action_kind,
                    "source": scope.source.value,
                    "executor": scope.executor,
                    "verifier_kinds": list(scope.verifier_kinds),
                },
                "latency_ms": outcome.latency_ms,
                "expected_cost": outcome.expected_cost,
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


def _pending_recovery_kind(state: StateKernel) -> RecoveryKind | None:
    if state.current_recovery_outcome is not None:
        return None
    decision = state.current_recovery_decision
    return decision.kind if decision is not None else None


def _available_owner_recovery_kinds(
    dispatcher: RecoveryOwnerDispatcher,
) -> frozenset[RecoveryKind]:
    return dispatcher.available_kinds


def _terminal_recovery_status(
    state: StateKernel,
    *,
    fallback: RuntimeStep,
) -> RuntimeStep:
    current = RuntimeStep(state.phase)
    if current in {
        RuntimeStep.ABORTED,
        RuntimeStep.FAILED,
        RuntimeStep.WAITING_CLARIFICATION,
        RuntimeStep.WAITING_APPROVAL,
        RuntimeStep.DEFERRED,
    }:
        return current
    state.transition(fallback.value)
    return fallback


def _trace_recovery_started(
    trace: TraceDag,
    parent: TraceNode,
    state: StateKernel,
    command: RecoveryKind,
    *,
    verification_status: str = "",
) -> TraceNode:
    payload: dict[str, Any] = {"state": state.phase, "action": command.value}
    if verification_status:
        payload["verification"] = verification_status
    return trace.add("RecoveryStarted", payload, parents=[parent.id])
