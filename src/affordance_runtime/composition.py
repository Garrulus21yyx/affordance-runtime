"""Application composition root for the five-stage runtime."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import cast

from affordance_runtime.active_perception_flow import ActivePerceptionFlow
from affordance_runtime.approval_contracts import ApprovalProvider
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.canonical_observation_builder import CanonicalObservationBuilder
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.coordinator import RunBudget, RunCoordinator, RuntimeFeatures
from affordance_runtime.execution_context import (
    RunProvenanceManifest,
    describe_component,
    describe_executor,
    digest_payload,
)
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
from affordance_runtime.transaction_materialization import ActionTransactionMaterializer
from affordance_runtime.verification.mechanical import VerifierLadder

_DEFAULT_TASK_PLANNER = object()


class UnsafeProductRuntimeConfiguration(ValueError):
    """A product composition attempted to disable a mandatory safety owner."""


def _require_product_safety(features: RuntimeFeatures) -> None:
    disabled = tuple(
        name
        for name in ("preflight", "structural_verification", "capability_gate")
        if not getattr(features, name)
    )
    if disabled:
        raise UnsafeProductRuntimeConfiguration(
            "product runtime cannot disable mandatory safety gates: " + ", ".join(disabled)
        )


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
    contract_builder: ActionTransactionMaterializer | None = None,
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
    _require_product_safety(resolved_features)
    return _compose_run_coordinator(
        observer,
        executor,
        verifier=verifier,
        gate=gate,
        task_policy=task_policy,
        approval_provider=approval_provider,
        artifacts=artifacts,
        budget=resolved_budget,
        features=resolved_features,
        contract_builder=contract_builder,
        task_planner=task_planner,
        step_choice_planner=step_choice_planner,
        task_skill_runtime=task_skill_runtime,
        runtime_profile_digest=runtime_profile_digest,
        loaded_profile_artifact_ids=loaded_profile_artifact_ids,
        route_calibrator=route_calibrator,
        recovery_coordinator=recovery_coordinator,
        recovery_owner_dispatcher=recovery_owner_dispatcher,
    )


def _compose_run_coordinator(
    observer: ObservationSource,
    executor: Executor,
    *,
    verifier: VerifierLadder | None = None,
    gate: CapabilityGate | None = None,
    task_policy: TaskConstraintPolicy | None = None,
    approval_provider: ApprovalProvider | None = None,
    artifacts: ArtifactStore | None = None,
    budget: RunBudget,
    features: RuntimeFeatures,
    contract_builder: ActionTransactionMaterializer | None = None,
    task_planner: TaskPlannerPort | None | object = _DEFAULT_TASK_PLANNER,
    step_choice_planner: StepChoicePlanner | None = None,
    task_skill_runtime: AcceptedTaskSkillRuntime | None = None,
    runtime_profile_digest: str = "",
    loaded_profile_artifact_ids: tuple[str, ...] = (),
    route_calibrator: RouteCalibrator | None = None,
    recovery_coordinator: RecoveryCoordinator | None = None,
    recovery_owner_dispatcher: RecoveryOwnerDispatcher | None = None,
) -> RunCoordinator:
    """Product constructor; mandatory safety remains enforced for private callers."""

    resolved_budget = budget
    resolved_features = features
    _require_product_safety(resolved_features)
    resolved_verifier = verifier or VerifierLadder()
    resolved_gate = gate or CapabilityGate()
    resolved_task_policy = task_policy or TaskConstraintPolicy()
    descriptor = describe_executor(executor)
    observer_descriptor = describe_component(observer)
    resolved_gate.executor_descriptor = descriptor
    if not resolved_gate.product_allowed_actions:
        resolved_gate.product_allowed_actions = descriptor.supported_actions
    resolved_calibrator = route_calibrator or RouteCalibrator()
    provenance_manifest = RunProvenanceManifest(
        code_digest=_runtime_code_digest(),
        product_profile_digest=runtime_profile_digest
        or digest_payload({"features": resolved_features, "artifacts": loaded_profile_artifact_ids}),
        policy_digest=digest_payload(
            {
                "task_policy": type(resolved_task_policy).__name__,
                "approval_risks": sorted(item.value for item in resolved_gate.approval_required_risks),
                "approval_capabilities": sorted(resolved_gate.approval_required_capabilities),
            }
        ),
        provider_digest=digest_payload(descriptor),
        schema_digest=descriptor.tool_schema_digest,
        transform_digest=digest_payload(resolved_calibrator),
        acquisition_digest=digest_payload(
            {"observer": observer_descriptor, "executor": descriptor}
        ),
        verifier_digest=digest_payload(resolved_verifier),
        environment_digest=digest_payload(
            {"executor": descriptor, "observer": observer_descriptor}
        ),
    )
    session = PerceptionSession(observer, artifacts, descriptor)
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
        resolved_contract_builder = ActionTransactionMaterializer(
            provenance_manifest=provenance_manifest,
            artifacts=artifacts,
        )
    elif isinstance(contract_builder, ActionTransactionMaterializer):
        if contract_builder.route_encoder is not None:
            raise UnsafeProductRuntimeConfiguration(
                "product composition does not accept benchmark or external route encoders"
            )
        resolved_contract_builder = contract_builder
        if resolved_contract_builder.provenance_manifest is None:
            resolved_contract_builder.provenance_manifest = provenance_manifest
        if resolved_contract_builder.artifacts is None:
            resolved_contract_builder.artifacts = artifacts
    else:
        raise UnsafeProductRuntimeConfiguration(
            "product composition accepts only canonical transaction or route-materializer configuration"
        )
    route_owner = resolved_contract_builder
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
        provenance_manifest,
    )


def _runtime_code_digest() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()
