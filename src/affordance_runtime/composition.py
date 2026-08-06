"""Application composition root for the five-stage runtime."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from affordance_runtime.action_contract_builder import (
    ActionContractBuilder,
    ActionContractMaterializer,
    CanonicalRouteMaterializer,
)
from affordance_runtime.active_perception_flow import ActivePerceptionFlow
from affordance_runtime.approval_contracts import ApprovalProvider
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.coordinator import RunBudget, RunCoordinator, RuntimeFeatures
from affordance_runtime.execution_phase import ActionStage
from affordance_runtime.observation_store import InMemoryObservationStore
from affordance_runtime.perception_phase import PerceptionStage
from affordance_runtime.perception_session import ObservationSource, PerceptionSession
from affordance_runtime.planning_phase import PlanningStage
from affordance_runtime.progress_phase import ProgressStage
from affordance_runtime.recovery_coordinator import RecoveryCoordinator
from affordance_runtime.recovery_owner_dispatcher import RecoveryOwnerDispatcher
from affordance_runtime.recovery_phase import RecoveryStage
from affordance_runtime.route_calibration import RouteCalibrator
from affordance_runtime.runtime import Executor
from affordance_runtime.runtime_committer import RuntimeCommitter
from affordance_runtime.runtime_result_phase import RuntimeResultPhase
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.step_choice_flow import StepChoiceFlow
from affordance_runtime.step_choice_planner import StepChoicePlanner
from affordance_runtime.task_plan_flow import TaskPlanFlow
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_planner import PlanningRouter, TaskPlannerPort
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime
from affordance_runtime.verification.mechanical import VerifierLadder

_DEFAULT_TASK_PLANNER = object()


def compose_run_coordinator(
    observer: ObservationSource,
    executor: Executor,
    *,
    verifier: VerifierLadder | None = None,
    gate: CapabilityGate | None = None,
    task_policy: TaskConstraintPolicy | None = None,
    approval_provider: ApprovalProvider | None = None,
    artifacts: ArtifactStore | None = None,
    budget: RunBudget | None = None,
    features: RuntimeFeatures | None = None,
    contract_builder: ActionContractBuilder | ActionContractMaterializer | None = None,
    task_planner: TaskPlannerPort | None | object = _DEFAULT_TASK_PLANNER,
    step_choice_planner: StepChoicePlanner | None = None,
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
    observation_builder = CanonicalObservationBuilder()
    observation_store = InMemoryObservationStore()
    active_flow = ActivePerceptionFlow(session)
    perception = PerceptionStage(
        session,
        active_flow,
        artifacts,
        resolved_budget,
        observation_builder,
        observation_store,
    )
    execution_loop = ContractExecutionLoop(
        executor=executor,
        verifier=resolved_verifier,
        gate=resolved_gate,
        task_policy=resolved_task_policy,
        artifacts=artifacts,
    )
    if task_planner is _DEFAULT_TASK_PLANNER:
        task_planner = PlanningRouter()
    resolved_task_planner = None if task_planner is None else cast(TaskPlannerPort, task_planner)
    plan_flow = (
        TaskPlanFlow(
            TaskPlanLifecycle(
                planner=resolved_task_planner,
            )
        )
        if resolved_task_planner is not None
        else None
    )
    planning = PlanningStage(
        task_plan_flow=plan_flow,
        step_choice_flow=StepChoiceFlow(step_choice_planner),
        task_skill_runtime=task_skill_runtime,
    )
    if contract_builder is None:
        resolved_contract_builder = ActionContractBuilder(CanonicalRouteMaterializer())
    elif isinstance(contract_builder, ActionContractMaterializer):
        resolved_contract_builder = ActionContractBuilder(contract_builder)
    else:
        # Explicit external/benchmark adapters remain edge-only inputs. They
        # are never wrapped as canonical builders or used by the default path.
        resolved_contract_builder = contract_builder
    route_owner = (
        resolved_contract_builder.materializer
        if isinstance(resolved_contract_builder, ActionContractBuilder)
        else resolved_contract_builder
    )
    if hasattr(route_owner, "unified_resolver"):
        route_owner.unified_resolver.router = replace(
            route_owner.unified_resolver.router,
            calibrator=resolved_calibrator,
        )
    action = ActionStage(
        contract_builder=resolved_contract_builder,
        contract_execution_loop=execution_loop,
        perception_session=session,
        observation_builder=observation_builder,
        observation_store=observation_store,
        active_perception_flow=active_flow,
        approval_provider=approval_provider,
        artifacts=artifacts,
        task_skill_runtime=task_skill_runtime,
        runtime_gate=resolved_gate,
        preflight_enabled=resolved_features.preflight,
        capability_gate_enabled=resolved_features.capability_gate,
        recovery_enabled=resolved_features.recovery,
        approval_required_risks=frozenset(resolved_gate.approval_required_risks),
        approval_required_capabilities=frozenset(resolved_gate.approval_required_capabilities),
    )
    progress = ProgressStage(
        execution_loop=execution_loop,
        perception_session=session,
        route_calibrator=resolved_calibrator,
        observation_builder=observation_builder,
        observation_store=observation_store,
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
