"""Task-level coordinator for the bounded observe/act/verify loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Any

from affordance_runtime.active_perception_flow import ActivePerceptionFlow
from affordance_runtime.approval_contracts import (
    ApprovalProvider,
)
from affordance_runtime.approval_contracts import (
    ConfiguredApprovalProvider as ConfiguredApprovalProvider,
)
from affordance_runtime.artifact_phase import ArtifactPhase
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.contract_binding_phase import ContractBindingPhase
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contract_failure_phase import ContractFailurePhase
from affordance_runtime.execution_phase import ExecutionPhase
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
from affordance_runtime.recovery_failure_phase import RecoveryFailurePhase
from affordance_runtime.recovery_owner_dispatcher import RecoveryOwnerDispatcher
from affordance_runtime.recovery_phase import RecoveryPhase
from affordance_runtime.recovery_protocol import (
    RecoveryKind,
)
from affordance_runtime.recovery_trace_commit import trace_recovery_started
from affordance_runtime.route_calibration import RouteCalibrator
from affordance_runtime.runtime import Executor, RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_loop_phase import RuntimeLoopPhase
from affordance_runtime.runtime_result_phase import CoordinatorResult, RuntimeResultPhase
from affordance_runtime.runtime_transition_commit import (
    apply_runtime_loop_transition,
    commit_runtime_loop_event,
)
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.state_kernel import StateKernel
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
from affordance_runtime.trace import TraceDag
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
RUNTIME_LOOP_PHASE = RuntimeLoopPhase()


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
    recovery_failure_phase: RecoveryFailurePhase = field(init=False, repr=False)
    artifact_phase: ArtifactPhase = field(init=False, repr=False)
    result_phase: RuntimeResultPhase = field(init=False, repr=False)
    targeted_perception_fulfiller: Any = field(init=False, repr=False)
    source_arbitration_tracer: Any = field(init=False, repr=False)

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
        self.recovery_failure_phase = RecoveryFailurePhase(
            recovery_phase=self.recovery_phase,
            budget=self.budget,
            runtime_profile_digest=self.runtime_profile_digest,
            loaded_profile_artifact_ids=self.loaded_profile_artifact_ids,
        )
        self.artifact_phase = ArtifactPhase(self.artifacts)
        self.result_phase = RuntimeResultPhase(self.artifacts)
        self.source_arbitration_tracer = PERCEPTION_PHASE.trace_source_arbitration
        self.targeted_perception_fulfiller = partial(
            PERCEPTION_PHASE.fulfill_targeted_perception,
            active_perception_flow=self.active_perception_flow,
            budget=self.budget,
            write_observation=self.artifact_phase.write_observation,
            index_artifact=self.artifact_phase.index_artifact,
            index_paths=self.artifact_phase.index_paths,
            trace_source_arbitration=self.source_arbitration_tracer,
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
        loop_start = RUNTIME_LOOP_PHASE.start(
            envelope=envelope,
            upstream_trace=upstream_trace,
            runtime_profile_digest=self.runtime_profile_digest,
            loaded_profile_artifact_ids=self.loaded_profile_artifact_ids,
        )
        state = loop_start.state
        trace = loop_start.trace
        parent = commit_runtime_loop_event(trace, loop_start.event)
        latest_verification: VerificationReport | None = None
        while True:
            budget_result = RUNTIME_LOOP_PHASE.check_budget(state=state, budget=self.budget)
            if budget_result is not None:
                apply_runtime_loop_transition(state, budget_result.transition)
                parent = commit_runtime_loop_event(trace, budget_result.event, parent)
                return self.result_phase.finish(
                    envelope,
                    state,
                    trace,
                    budget_result.status,
                    parent,
                    budget_result.error_code,
                    latest_verification,
                )
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
                active_perception_flow=self.active_perception_flow,
                budget=self.budget,
                pending_recovery_kind=_pending_recovery_kind,
                task_skill_progress_for=_task_skill_progress,
                write_observation=self.artifact_phase.write_observation,
                index_artifact=self.artifact_phase.index_artifact,
                index_paths=self.artifact_phase.index_paths,
                trace_source_arbitration=self.source_arbitration_tracer,
                recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
            )
            parent = perception.parent
            if perception.latest_verification is not None:
                latest_verification = perception.latest_verification
            if perception.continue_observing:
                continue
            if perception.terminal is not None:
                return self.result_phase.finish(
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
                    recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
                    owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                        self.recovery_owner_dispatcher
                    ),
                )
                if planning_failure is not None:
                    parent = planning_failure.parent
                    if planning_failure.continue_observing:
                        continue
                    assert planning_failure.terminal is not None
                    return self.result_phase.finish(
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
            apply_runtime_loop_transition(state, RUNTIME_LOOP_PHASE.enter_planning(has_task_plan=state.task_plan is not None))
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
                    recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
                    owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                        self.recovery_owner_dispatcher
                    ),
                )
                if planning_failure is not None:
                    parent = planning_failure.parent
                    if planning_failure.continue_observing:
                        continue
                    assert planning_failure.terminal is not None
                    return self.result_phase.finish(
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
                    recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
                    owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                        self.recovery_owner_dispatcher
                    ),
                )
                parent = planning_failure.parent
                if planning_failure.continue_observing:
                    continue
                assert planning_failure.terminal is not None
                return self.result_phase.finish(
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
                        recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
                        owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                            self.recovery_owner_dispatcher
                        ),
                    )
                )
                parent = planning_failure.parent
                if planning_failure.continue_observing:
                    continue
                assert planning_failure.terminal is not None
                return self.result_phase.finish(
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
                return self.result_phase.finish(
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
                recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
                owner_dispatch_recovery_kinds=_available_owner_recovery_kinds(
                    self.recovery_owner_dispatcher
                ),
            )
            if planning_failure is not None:
                parent = planning_failure.parent
                if planning_failure.continue_observing:
                    continue
                assert planning_failure.terminal is not None
                return self.result_phase.finish(
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
                return self.result_phase.finish(
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
                recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
            )
            if contract_failure is not None:
                parent = contract_failure.parent
                if contract_failure.continue_observing:
                    continue
                assert contract_failure.terminal is not None
                return self.result_phase.finish(
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
                write_observation=self.artifact_phase.write_observation,
                index_artifact=self.artifact_phase.index_artifact,
                index_paths=self.artifact_phase.index_paths,
                trace_source_arbitration=self.source_arbitration_tracer,
                fulfill_targeted_perception=self.targeted_perception_fulfiller,
                recover_execution_failure=self.recovery_failure_phase.recover_execution_failure,
                recover_phase_failure=self.recovery_failure_phase.recover_phase_failure,
                terminal_recovery_status=lambda current_state: _terminal_recovery_status(
                    current_state,
                    fallback=RuntimeStep.ABORTED,
                ),
                trace_recovery_started=trace_recovery_started,
            )
            parent = preflight_result.parent
            contract = preflight_result.contract
            execution_observation = preflight_result.execution_observation
            if preflight_result.continue_observing:
                continue
            if preflight_result.terminal is not None:
                return self.result_phase.finish(
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
                write_receipt=self.artifact_phase.write_receipt,
                write_observation=self.artifact_phase.write_observation,
                index_artifact=self.artifact_phase.index_artifact,
                index_paths=self.artifact_phase.index_paths,
                trace_source_arbitration=self.source_arbitration_tracer,
                fulfill_targeted_perception=self.targeted_perception_fulfiller,
                recover_execution_failure=self.recovery_failure_phase.recover_execution_failure,
                terminal_recovery_status=lambda current_state: _terminal_recovery_status(
                    current_state,
                    fallback=RuntimeStep.FAILED,
                ),
                trace_recovery_started=trace_recovery_started,
            )
            parent = execution_result.parent
            if execution_result.latest_verification is not None:
                latest_verification = execution_result.latest_verification
            if execution_result.continue_observing:
                continue
            if execution_result.terminal is not None:
                return self.result_phase.finish(
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
            apply_runtime_loop_transition(state, RUNTIME_LOOP_PHASE.enter_verifying())
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
                write_observation=self.artifact_phase.write_observation,
                write_verification=self.artifact_phase.write_verification,
                index_artifact=self.artifact_phase.index_artifact,
                index_paths=self.artifact_phase.index_paths,
                trace_source_arbitration=self.source_arbitration_tracer,
                fulfill_targeted_perception=self.targeted_perception_fulfiller,
                route_calibrator=self.route_calibrator,
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
                return self.result_phase.finish(
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
                    return self.result_phase.finish(
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
                recover_execution_failure=self.recovery_failure_phase.recover_execution_failure,
                trace_recovery_started=trace_recovery_started,
                terminal_recovery_status=_terminal_recovery_status,
            )
            parent = verification_failure.parent
            if verification_failure.continue_observing:
                continue
            assert verification_failure.terminal is not None
            return self.result_phase.finish(
                envelope,
                state,
                trace,
                verification_failure.terminal.status,
                parent,
                verification_failure.terminal.error_code,
                latest_verification,
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
