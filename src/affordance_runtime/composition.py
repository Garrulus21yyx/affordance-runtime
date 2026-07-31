"""Application composition root for the five-stage runtime."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from affordance_runtime.active_perception_flow import ActivePerceptionFlow
from affordance_runtime.approval_contracts import ApprovalProvider
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.coordinator import RunBudget, RunCoordinator, RuntimeFeatures
from affordance_runtime.execution_phase import ActionStage
from affordance_runtime.perception_phase import PerceptionStage
from affordance_runtime.perception_session import ObservationSource, PerceptionSession
from affordance_runtime.planning import ContractBuilder, PlannerProposalValidator
from affordance_runtime.planning_contracts import PlannerPort
from affordance_runtime.planning_phase import PlanningStage
from affordance_runtime.progress_phase import ProgressStage
from affordance_runtime.proposal_recovery_policy import ProposalRejectionRecoveryPolicy
from affordance_runtime.recovery_coordinator import RecoveryCoordinator
from affordance_runtime.recovery_owner_dispatcher import RecoveryOwnerDispatcher
from affordance_runtime.recovery_phase import RecoveryStage
from affordance_runtime.route_calibration import RouteCalibrator
from affordance_runtime.runtime import Executor
from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.runtime_result_phase import RuntimeResultPhase
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.task_plan_flow import TaskPlanFlow
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_planning import (
    PlanningRouter,
    SubgoalVerifierPort,
    TaskPlannerPort,
    TaskPlanValidator,
    VerifierBackedSubgoalVerifier,
)
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.verification import VerifierLadder

_DEFAULT_TASK_PLANNER = object()


def compose_run_coordinator(
    observer: ObservationSource,
    planner: PlannerPort,
    executor: Executor,
    *,
    verifier: VerifierLadder | None = None,
    gate: CapabilityGate | None = None,
    task_policy: TaskConstraintPolicy | None = None,
    approval_provider: ApprovalProvider | None = None,
    artifacts: ArtifactStore | None = None,
    budget: RunBudget | None = None,
    features: RuntimeFeatures | None = None,
    contract_builder: ContractBuilder | None = None,
    proposal_validator: PlannerProposalValidator | None = None,
    proposal_recovery_policy: ProposalRejectionRecoveryPolicy | None = None,
    task_planner: TaskPlannerPort | None | object = _DEFAULT_TASK_PLANNER,
    task_plan_validator: TaskPlanValidator | None = None,
    subgoal_verifier: SubgoalVerifierPort | None = None,
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None,
    runtime_profile_digest: str = "",
    loaded_profile_artifact_ids: tuple[str, ...] = (),
    route_calibrator: RouteCalibrator | None = None,
    recovery_coordinator: RecoveryCoordinator | None = None,
    recovery_owner_dispatcher: RecoveryOwnerDispatcher | None = None,
) -> RunCoordinator:
    """Build the runtime once at the application boundary."""

    resolved_budget = budget or RunBudget()
    resolved_features = features or RuntimeFeatures()
    resolved_verifier = verifier or VerifierLadder()
    resolved_gate = gate or CapabilityGate()
    resolved_task_policy = task_policy or TaskConstraintPolicy()
    resolved_calibrator = route_calibrator or RouteCalibrator()
    session = PerceptionSession(observer, artifacts)
    active_flow = ActivePerceptionFlow(session)
    perception = PerceptionStage(session, active_flow, artifacts, resolved_budget)
    execution_loop = ContractExecutionLoop(
        executor=executor,
        verifier=resolved_verifier,
        gate=resolved_gate,
        task_policy=resolved_task_policy,
        artifacts=artifacts,
    )
    if task_planner is _DEFAULT_TASK_PLANNER:
        task_planner = PlanningRouter()
    resolved_task_planner = (
        None if task_planner is None else cast(TaskPlannerPort, task_planner)
    )
    plan_flow = (
        TaskPlanFlow(
            TaskPlanLifecycle(
                planner=resolved_task_planner,
                validator=task_plan_validator or TaskPlanValidator(),
            )
        )
        if resolved_task_planner is not None
        else None
    )
    planning = PlanningStage(
        planner=planner,
        task_plan_flow=plan_flow,
        task_skill_runtime=task_skill_runtime,
        proposal_validator=proposal_validator or PlannerProposalValidator(),
        proposal_recovery_policy=(
            proposal_recovery_policy or ProposalRejectionRecoveryPolicy()
        ),
        runtime_profile_digest=runtime_profile_digest,
    )
    if isinstance(contract_builder, ContractBuilder):
        contract_builder.unified_resolver.router = replace(
            contract_builder.unified_resolver.router,
            calibrator=resolved_calibrator,
        )
    action = ActionStage(
        contract_builder=contract_builder,
        contract_execution_loop=execution_loop,
        perception_session=session,
        active_perception_flow=active_flow,
        approval_provider=approval_provider,
        artifacts=artifacts,
        task_skill_runtime=task_skill_runtime,
        runtime_gate=resolved_gate,
        preflight_enabled=resolved_features.preflight,
        capability_gate_enabled=resolved_features.capability_gate,
        recovery_enabled=resolved_features.recovery,
        approval_required_risks=frozenset(resolved_gate.approval_required_risks),
        approval_required_capabilities=frozenset(
            resolved_gate.approval_required_capabilities
        ),
    )
    progress = ProgressStage(
        execution_loop=execution_loop,
        perception_session=session,
        subgoal_verifier=subgoal_verifier or VerifierBackedSubgoalVerifier(),
        route_calibrator=resolved_calibrator,
        task_skill_runtime=task_skill_runtime,
        artifacts=artifacts,
        structural_verification_enabled=resolved_features.structural_verification,
        recovery_enabled=resolved_features.recovery,
        task_planner_is_router=isinstance(resolved_task_planner, PlanningRouter),
    )
    recovery = RecoveryStage(
        recovery_coordinator or RecoveryCoordinator(),
        recovery_owner_dispatcher or RecoveryOwnerDispatcher(),
        runtime_profile_digest,
        loaded_profile_artifact_ids,
    )
    return RunCoordinator(
        perception,
        planning,
        action,
        progress,
        recovery,
        RuntimeCommitter(),
        RuntimeResultPhase(artifacts),
    )
