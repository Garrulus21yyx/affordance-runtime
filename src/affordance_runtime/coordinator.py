"""Task-level coordinator for the bounded observe/act/verify loop."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from time import time
from typing import Any, Awaitable, Protocol
from uuid import uuid4

from affordance_runtime.active_perception import (
    PerceptionResolutionStatus,
)
from affordance_runtime.active_perception_flow import (
    ActivePerceptionFlow,
    ActivePerceptionFlowContext,
)
from affordance_runtime.artifacts import ArtifactRef, ArtifactStore
from affordance_runtime.async_bridge import resolve_awaitable
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contract_execution_loop import ContractExecutionLoop
from affordance_runtime.contracts import (
    ActionContract,
    ApprovalToken,
    ExecutionReceipt,
    Observation,
    RuntimeErrorCode,
)
from affordance_runtime.failure_envelope import (
    EffectStatus,
    FailureClass,
    FailurePhase,
    RemainingRecoveryBudgets,
    make_failure_envelope,
)
from affordance_runtime.grounding import ActivePerceptionRequest, GroundingSource
from affordance_runtime.model_port import ModelCallRecord, ProviderModelError
from affordance_runtime.perception_session import ObservationSource, PerceptionSession
from affordance_runtime.planning import (
    ContractBuilder,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
    PlannerProposalValidator,
    ProposalRejected,
    ProposalRejectionCode,
    bind_active_subgoal_verifiers,
    proposal_error_code,
    proposal_record,
)
from affordance_runtime.proposal_recovery_policy import ProposalRejectionRecoveryPolicy
from affordance_runtime.recovery import (
    BoundedRecoveryPolicy,
    RecoveryAction,
    RecoveryAttempt,
    RecoveryAttemptOutcome,
    RecoveryCascadeDetector,
    RecoveryIncident,
)
from affordance_runtime.recovery_command_dispatcher import (
    OWNER_DISPATCH_COMMANDS,
    RecoveryCommandDispatcher,
)
from affordance_runtime.recovery_commands import (
    RecoveryCommandKind,
    RecoveryDelta,
    RecoveryReentryPhase,
)
from affordance_runtime.recovery_commands import (
    RecoveryReceipt as RecoveryCommandReceipt,
)
from affordance_runtime.recovery_coordinator import (
    RecoveryCoordinator,
    RecoveryHistoryItem,
    RecoverySelectionContext,
)
from affordance_runtime.recovery_handler import RecoveryHandler, RecoveryRequest
from affordance_runtime.route_calibration import (
    RouteCalibrator,
    RouteOutcome,
    RouteOutcomeStatus,
    RouteScope,
)
from affordance_runtime.runtime import Executor, RuntimeStep, TaskEnvelope
from affordance_runtime.runtime_evidence import (
    action_progress_signature,
    semantic_progress_fingerprint,
    semantic_target_descriptor,
    verification_confirms_effect_absent,
    verification_satisfies_effect,
)
from affordance_runtime.safety import CapabilityGate, TaskConstraintPolicy
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass
from affordance_runtime.task_plan_lifecycle import TaskPlanLifecycle
from affordance_runtime.task_planning import (
    PlanningRouter,
    SubgoalVerifierPort,
    TaskPlannerPort,
    TaskPlanValidationStatus,
    TaskPlanValidator,
    VerifierBackedSubgoalVerifier,
    task_planning_context_summary,
)
from affordance_runtime.task_skills import AcceptedTaskSkillRuntime, TaskSkillRuntimeDecision
from affordance_runtime.trace import TraceDag, TraceNode
from affordance_runtime.verification import VerificationReport, VerificationStatus, VerifierLadder


@dataclass(frozen=True)
class PlannerDecision:
    contract: ActionContract | None = None
    proposal: PlannerProposal | None = None
    proposal_provenance: PlannerProposalProvenance | None = None
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


def _is_safe_incomplete_terminal(decision: PlannerDecision, state: StateKernel) -> bool:
    """Allow an evidence-explicit non-success stop without claiming plan completion."""

    status = str(decision.result.get("status") or "").casefold()
    return (
        status in {"blocked", "incomplete", "inconclusive", "unsupported"}
        and not state.receipts
        and state.effectful_action_count == 0
    )


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
    recovery_command_dispatcher: RecoveryCommandDispatcher = field(
        default_factory=RecoveryCommandDispatcher
    )
    task_plan_lifecycle: TaskPlanLifecycle | None = field(init=False, default=None, repr=False)
    perception_session: PerceptionSession = field(init=False, repr=False)
    active_perception_flow: ActivePerceptionFlow = field(init=False, repr=False)
    contract_execution_loop: ContractExecutionLoop = field(init=False, repr=False)
    recovery_handler: RecoveryHandler = field(init=False, repr=False)

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
        self.recovery_handler = RecoveryHandler(
            policy=self.recovery,
            cascade_detector=self.cascade_detector,
        )
        if self.task_planner is not None:
            self.task_plan_lifecycle = TaskPlanLifecycle(
                planner=self.task_planner,
                validator=self.task_plan_validator,
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

            if state.phase in {RuntimeStep.CREATED.value, RuntimeStep.RECOVERING.value}:
                state.transition(RuntimeStep.OBSERVING.value)

            try:
                snapshot = self.perception_session.capture(
                    envelope,
                    state,
                    state.observation_count + 1,
                )
            except Exception as exc:
                if not self.features.recovery:
                    state.transition(RuntimeStep.FAILED.value)
                    parent = trace.add(
                        "ObservationFailed",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PRECONDITION_FAILED.value,
                            "reason": f"{type(exc).__name__}: {exc}"[:500],
                        },
                        parents=[parent.id] if parent else None,
                    )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.FAILED,
                        parent,
                        RuntimeErrorCode.PRECONDITION_FAILED,
                        latest_verification,
                    )
                if parent is None:
                    raise ValueError("observation recovery requires a trace parent")
                recovery_command, parent = self._recover_phase_failure(
                    envelope,
                    state,
                    trace,
                    parent,
                    phase=FailurePhase.OBSERVATION,
                    failure_class=FailureClass.INTERNAL,
                    error_code=RuntimeErrorCode.PRECONDITION_FAILED,
                    message=f"{type(exc).__name__}: {exc}"[:500],
                    available_commands=frozenset(
                        {
                            RecoveryCommandKind.REOBSERVE,
                            RecoveryCommandKind.ABORT,
                        }
                    ),
                )
                if recovery_command == RecoveryCommandKind.REOBSERVE:
                    continue
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep(state.phase),
                    parent,
                    RuntimeErrorCode.PRECONDITION_FAILED,
                    latest_verification,
                )
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
                    "perception_requirements": snapshot.observation.metadata.get("perception_requirements"),
                    "source_observations": [
                        {
                            "source": item.source.value,
                            "parser_id": item.parser_id,
                            "observation_epoch_id": item.observation_epoch_id,
                            "artifact_refs": list(item.artifact_refs),
                        }
                        for item in snapshot.source_observations
                    ],
                },
                parents=[parent.id] if parent else None,
            )
            self._index(trace, observation_ref)
            self._index_paths(trace, snapshot.observation.artifact_refs)
            parent = self._trace_source_arbitration(trace, parent, snapshot, state.phase)
            snapshot, parent = self._fulfill_targeted_perception(
                envelope,
                state,
                trace,
                parent,
                snapshot,
            )
            parent, recovered_verification, recovery_must_stop = (
                self._complete_pending_recovery_observation(
                    state,
                    trace,
                    parent,
                    snapshot,
                )
            )
            if recovered_verification is not None:
                latest_verification = recovered_verification
            if recovery_must_stop:
                state.transition(RuntimeStep.ABORTED.value)
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.ABORTED,
                    parent,
                    RuntimeErrorCode.PRECONDITION_FAILED,
                    latest_verification,
                )
            if (
                state.perception_resolution is not None
                and state.perception_resolution.blocks_effectful_action
            ):
                _recovery_command, parent = self._recover_phase_failure(
                    envelope,
                    state,
                    trace,
                    parent,
                    phase=FailurePhase.FUSION,
                    failure_class=FailureClass.SOURCE_CONFLICT,
                    error_code=RuntimeErrorCode.PRECONDITION_FAILED,
                    message=state.perception_resolution.reason,
                    available_commands=frozenset({RecoveryCommandKind.ABORT}),
                    snapshot=snapshot,
                    recoverable=False,
                )
                parent = trace.add(
                    (
                        "PerceptionBlockedEffectfulRepeat"
                        if state.receipts
                        else "PerceptionBlockedEffectfulAction"
                    ),
                    {
                        "state": state.phase,
                        "resolution": state.perception_resolution.model_dump(mode="json"),
                    },
                    parents=[parent.id],
                )
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.ABORTED,
                    parent,
                    RuntimeErrorCode.PRECONDITION_FAILED,
                    latest_verification,
                )

            if (
                self.task_plan_lifecycle is not None
                and envelope.task_spec is not None
                and self.task_plan_lifecycle.should_replan(state)
            ):
                try:
                    transition = self.task_plan_lifecycle.propose_replacement(
                        envelope.task_spec,
                        state,
                        snapshot,
                        self.budget,
                        reason="subgoal_action_budget_exhausted",
                    )
                    task_plan = transition.plan
                    report = transition.validation
                    previous_plan = transition.previous_plan
                    if previous_plan is None:
                        raise ValueError("task replan transition is missing its previous plan")
                    if report.status != TaskPlanValidationStatus.ACCEPT:
                        raise ValueError(f"task replan validation: {report.status.value}")
                    state.replace_task_plan(task_plan)
                    if state.plan_progress is None:
                        raise ValueError("task replan did not install progress state")
                    preserved_subgoal_ids = list(state.plan_progress.completed_subgoal_ids)
                except Exception as exc:
                    parent = trace.add(
                        "TaskReplanRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                            "reason": f"{type(exc).__name__}: {exc}"[:500],
                        },
                        parents=[parent.id],
                    )
                    if (
                        state.current_recovery_plan is not None
                        and state.current_recovery_plan.commands[0].kind
                        == RecoveryCommandKind.REPLAN_TASK
                    ):
                        parent = self._fail_pending_recovery_command(
                            state,
                            trace,
                            parent,
                            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                        )
                    recovery_command, parent = self._recover_phase_failure(
                        envelope,
                        state,
                        trace,
                        parent,
                        phase=FailurePhase.TASK_PLANNING,
                        failure_class=FailureClass.PLANNING,
                        error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        message=f"{type(exc).__name__}: {exc}"[:500],
                        available_commands=frozenset(
                            {
                                RecoveryCommandKind.REPLAN_TASK,
                                *self.recovery_command_dispatcher.available_commands,
                                RecoveryCommandKind.ABORT,
                            }
                        ),
                        snapshot=snapshot,
                    )
                    if (
                        recovery_command == RecoveryCommandKind.REPLAN_TASK
                        or recovery_command in OWNER_DISPATCH_COMMANDS
                    ):
                        continue
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep(state.phase),
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
                        "supersedes_plan_id": task_plan.supersedes_plan_id,
                        "plan_id": task_plan.plan_id,
                        "plan_version": task_plan.plan_version,
                        "preserved_subgoal_ids": preserved_subgoal_ids,
                        "active_subgoal": state.active_subgoal(),
                        "planning_context": task_planning_context_summary(transition.context),
                    },
                    parents=[parent.id],
                )
                parent = self._complete_pending_recovery_plan_change(
                    state,
                    trace,
                    parent,
                    kind=RecoveryCommandKind.REPLAN_TASK,
                    plan_or_route_ref=task_plan.plan_id,
                )

            if self.task_plan_lifecycle is not None and state.task_plan is None and envelope.task_spec is not None:
                try:
                    transition = self.task_plan_lifecycle.propose_initial(
                        envelope.task_spec,
                        state,
                        snapshot,
                        self.budget,
                    )
                    task_plan = transition.plan
                except Exception as exc:
                    parent = trace.add(
                        "TaskPlanRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_FAILED.value,
                            "reason": f"{type(exc).__name__}: {exc}"[:500],
                        },
                        parents=[parent.id],
                    )
                    if (
                        state.current_recovery_plan is not None
                        and state.current_recovery_plan.commands[0].kind
                        == RecoveryCommandKind.REPLAN_TASK
                    ):
                        parent = self._fail_pending_recovery_command(
                            state,
                            trace,
                            parent,
                            error_code=RuntimeErrorCode.PLANNER_FAILED.value,
                        )
                    recovery_command, parent = self._recover_phase_failure(
                        envelope,
                        state,
                        trace,
                        parent,
                        phase=FailurePhase.TASK_PLANNING,
                        failure_class=FailureClass.PLANNING,
                        error_code=RuntimeErrorCode.PLANNER_FAILED,
                        message=f"{type(exc).__name__}: {exc}"[:500],
                        available_commands=frozenset(
                            {
                                RecoveryCommandKind.REPLAN_TASK,
                                *self.recovery_command_dispatcher.available_commands,
                                RecoveryCommandKind.ABORT,
                            }
                        ),
                        snapshot=snapshot,
                    )
                    if (
                        recovery_command == RecoveryCommandKind.REPLAN_TASK
                        or recovery_command in OWNER_DISPATCH_COMMANDS
                    ):
                        continue
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep(state.phase),
                        parent,
                        RuntimeErrorCode.PLANNER_FAILED,
                        latest_verification,
                    )
                report = transition.validation
                parent = trace.add(
                    "TaskPlanProposed",
                    {
                        "state": state.phase,
                        "plan_id": task_plan.plan_id,
                        "plan_version": task_plan.plan_version,
                        "generated_by": task_plan.generated_by.value,
                        "subgoal_count": len(task_plan.subgoals),
                        "supersedes_plan_id": task_plan.supersedes_plan_id,
                        "planning_context": task_planning_context_summary(transition.context),
                        "validation": report.status.value,
                        "issues": [item.model_dump(mode="json") for item in report.issues],
                    },
                    parents=[parent.id],
                )
                if report.status != TaskPlanValidationStatus.ACCEPT:
                    parent = trace.add(
                        "TaskPlanRejected",
                        {
                            "state": state.phase,
                            "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                            "validation": report.status.value,
                        },
                        parents=[parent.id],
                    )
                    if (
                        state.current_recovery_plan is not None
                        and state.current_recovery_plan.commands[0].kind
                        == RecoveryCommandKind.REPLAN_TASK
                    ):
                        parent = self._fail_pending_recovery_command(
                            state,
                            trace,
                            parent,
                            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                        )
                    recovery_command, parent = self._recover_phase_failure(
                        envelope,
                        state,
                        trace,
                        parent,
                        phase=FailurePhase.TASK_PLANNING,
                        failure_class=FailureClass.VALIDATION,
                        error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        message=f"task plan validation: {report.status.value}",
                        available_commands=frozenset(
                            {
                                RecoveryCommandKind.REPLAN_TASK,
                                *self.recovery_command_dispatcher.available_commands,
                                RecoveryCommandKind.ABORT,
                            }
                        ),
                        snapshot=snapshot,
                    )
                    if (
                        recovery_command == RecoveryCommandKind.REPLAN_TASK
                        or recovery_command in OWNER_DISPATCH_COMMANDS
                    ):
                        continue
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep(state.phase),
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
                        "plan_version": task_plan.plan_version,
                        "supersedes_plan_id": task_plan.supersedes_plan_id,
                        "active_subgoal": state.active_subgoal(),
                    },
                    parents=[parent.id],
                )
                parent = self._complete_pending_recovery_plan_change(
                    state,
                    trace,
                    parent,
                    kind=RecoveryCommandKind.REPLAN_TASK,
                    plan_or_route_ref=task_plan.plan_id,
                )

            state.transition(RuntimeStep.PLANNING.value)
            if self.task_plan_lifecycle is not None and state.task_plan is not None:
                # Activate the next
                # ready semantic unit before any action planner or TaskSkill
                # reads progress; contract-time action accounting is too late.
                state.active_subgoal()
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
                    parent = trace.add(
                        "TaskSkillSelectionEvaluated",
                        {
                            "state": state.phase,
                            "matched": skill_decision.payload is not None,
                            "newly_activated": skill_decision.newly_activated,
                            "attempted": skill_decision.attempted,
                            "reason": skill_decision.reason,
                            "profile_digest": self.runtime_profile_digest,
                        },
                        parents=[parent.id],
                    )
                    if (
                        skill_decision.attempted
                        and skill_decision.reason.startswith("TaskSkill runtime error:")
                    ):
                        if (
                            state.current_recovery_plan is not None
                            and state.current_recovery_plan.commands[0].kind
                            == RecoveryCommandKind.REPLAN_STEP
                        ):
                            parent = self._fail_pending_recovery_command(
                                state,
                                trace,
                                parent,
                                error_code=RuntimeErrorCode.PLANNER_FAILED.value,
                            )
                        recovery_command, parent = self._recover_phase_failure(
                            envelope,
                            state,
                            trace,
                            parent,
                            phase=FailurePhase.SKILL_ACTIVATION,
                            failure_class=FailureClass.SKILL,
                            error_code=RuntimeErrorCode.PLANNER_FAILED,
                            message=skill_decision.reason,
                            available_commands=frozenset(
                                {
                                    RecoveryCommandKind.REPLAN_STEP,
                                    *self.recovery_command_dispatcher.available_commands,
                                    RecoveryCommandKind.ABORT,
                                }
                            ),
                            snapshot=snapshot,
                        )
                        if (
                            recovery_command == RecoveryCommandKind.REPLAN_STEP
                            or recovery_command in OWNER_DISPATCH_COMMANDS
                        ):
                            continue
                        return self._finish(
                            envelope,
                            state,
                            trace,
                            RuntimeStep(state.phase),
                            parent,
                            RuntimeErrorCode.PLANNER_FAILED,
                            latest_verification,
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
                            proposal_provenance=PlannerProposalProvenance(
                                source=PlannerProposalSource.ACCEPTED_SKILL,
                                producer_id=skill_payload.skill_id,
                                version=skill_payload.version,
                                evidence_refs=tuple(state.task_skill.evidence) if state.task_skill else (),
                            ),
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
                error_code = RuntimeErrorCode(exc.kind.value)
                if (
                    state.current_recovery_plan is not None
                    and state.current_recovery_plan.commands[0].kind
                    == RecoveryCommandKind.REPLAN_STEP
                ):
                    parent = self._fail_pending_recovery_command(
                        state,
                        trace,
                        parent,
                        error_code=error_code.value,
                    )
                state.final_result = {
                    "deferred": True,
                    "provider_failure": exc.kind.value,
                    "retry_after_s": exc.retry_after_s,
                    "resumable": exc.resumable,
                }
                _recovery_command, parent = self._recover_phase_failure(
                    envelope,
                    state,
                    trace,
                    parent,
                    phase=FailurePhase.PROVIDER_CONTEXT,
                    failure_class=FailureClass.PROVIDER,
                    error_code=error_code,
                    message=f"provider failure: {exc.kind.value}",
                    available_commands=frozenset(
                        {
                            *self.recovery_command_dispatcher.available_commands,
                            RecoveryCommandKind.ABORT,
                        }
                    ),
                    snapshot=snapshot,
                    abort_reentry_phase=RecoveryReentryPhase.DEFERRED,
                )
                if _recovery_command in OWNER_DISPATCH_COMMANDS:
                    continue
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
                if (
                    state.current_recovery_plan is not None
                    and state.current_recovery_plan.commands[0].kind
                    == RecoveryCommandKind.REPLAN_STEP
                ):
                    parent = self._fail_pending_recovery_command(
                        state,
                        trace,
                        parent,
                        error_code=RuntimeErrorCode.PLANNER_FAILED.value,
                    )
                recovery_command, parent = self._recover_phase_failure(
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
                            RecoveryCommandKind.REPLAN_STEP,
                            *self.recovery_command_dispatcher.available_commands,
                            RecoveryCommandKind.ABORT,
                        }
                    ),
                    snapshot=snapshot,
                )
                if (
                    recovery_command == RecoveryCommandKind.REPLAN_STEP
                    or recovery_command in OWNER_DISPATCH_COMMANDS
                ):
                    continue
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep(state.phase),
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
                provenance = decision.proposal_provenance
                try:
                    if envelope.task_spec is None:
                        raise ProposalRejected(
                            ProposalRejectionCode.UNSUPPORTED_ACTION,
                            "semantic proposal requires a validated TaskSpec",
                        )
                    self.proposal_validator.validate(
                        proposal,
                        provenance,
                        envelope.task_spec,
                        state,
                        snapshot,
                    )
                except ProposalRejected as exc:
                    error_code = proposal_error_code(exc.code)
                    recovery_decision = self.proposal_recovery_policy.decide(exc.code, exc.detail)
                    parent = trace.add(
                        "PlannerProposalRejected",
                        {
                            "state": state.phase,
                            "proposal_id": proposal.proposal_id,
                            "error_code": error_code.value,
                            "rejection_code": exc.code.value,
                            "reason": exc.detail,
                            "validation_boundary": "PlannerProposalValidator",
                            "provenance": (provenance.model_dump(mode="json") if provenance is not None else None),
                        },
                        parents=[parent.id],
                    )
                    if (
                        state.current_recovery_plan is not None
                        and state.current_recovery_plan.commands[0].kind
                        in {
                            RecoveryCommandKind.REGROUND,
                            RecoveryCommandKind.REROUTE,
                            RecoveryCommandKind.REPLAN_STEP,
                        }
                    ):
                        parent = self._fail_pending_recovery_command(
                            state,
                            trace,
                            parent,
                            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                        )
                    if skill_step_id and self.task_skill_runtime is not None:
                        reason = f"TaskSkill proposal validation rejected: {exc.detail or exc.code.value}"
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
                    _recovery_command, parent = self._recover_phase_failure(
                        envelope,
                        state,
                        trace,
                        parent,
                        phase=FailurePhase.PROPOSAL_VALIDATION,
                        failure_class=FailureClass.VALIDATION,
                        error_code=error_code,
                        message=recovery_decision.planner_feedback,
                        available_commands=recovery_decision.available_commands,
                        snapshot=snapshot,
                        proposal_id=proposal.proposal_id,
                        expected_effect="; ".join(proposal.expected_effects),
                        recoverable=recovery_decision.recoverable,
                    )
                    if _recovery_command != RecoveryCommandKind.ABORT:
                        continue
                    return self._finish(envelope, state, trace, RuntimeStep.ABORTED, parent, error_code, latest_verification)
                if provenance is None:  # narrowed after source-neutral validation
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
                            decision.model_call.model_dump(mode="json") if decision.model_call is not None else None
                        ),
                    },
                    parents=[parent.id],
                )
                parent = self._complete_pending_recovery_plan_change(
                    state,
                    trace,
                    parent,
                    kind=RecoveryCommandKind.REPLAN_STEP,
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
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.WAITING_CLARIFICATION,
                        parent,
                        None,
                        latest_verification,
                    )
            else:
                parent = self._complete_pending_recovery_plan_change(
                    state,
                    trace,
                    parent,
                    kind=RecoveryCommandKind.REPLAN_STEP,
                    plan_or_route_ref=f"planner-decision:state:{state.version}",
                )
            if decision.done:
                if state.task_plan is not None and not TaskPlanLifecycle.completed(state):
                    if _is_safe_incomplete_terminal(decision, state):
                        parent = trace.add(
                            "TaskPlanStoppedIncomplete",
                            {
                                "state": state.phase,
                                "task_plan_id": state.task_plan.plan_id,
                                "result_status": str(decision.result.get("status") or ""),
                                "reason": decision.reason,
                            },
                            parents=[parent.id],
                        )
                    else:
                        parent = trace.add(
                            "PlannerProposalRejected",
                            {
                                "state": state.phase,
                                "error_code": RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
                                "reason": "planner cannot finish before verifier-backed subgoal completion",
                            },
                            parents=[parent.id],
                        )
                        _recovery_command, parent = self._recover_phase_failure(
                            envelope,
                            state,
                            trace,
                            parent,
                            phase=FailurePhase.PROPOSAL_VALIDATION,
                            failure_class=FailureClass.VALIDATION,
                            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                            message="planner cannot finish before verifier-backed subgoal completion",
                            available_commands=frozenset({RecoveryCommandKind.ABORT}),
                            snapshot=snapshot,
                            recoverable=False,
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
                    if (
                        state.current_recovery_plan is not None
                        and state.current_recovery_plan.commands[0].kind
                        in {RecoveryCommandKind.REGROUND, RecoveryCommandKind.REROUTE}
                    ):
                        parent = self._fail_pending_recovery_command(
                            state,
                            trace,
                            parent,
                            error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
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
                    _recovery_command, parent = self._recover_phase_failure(
                        envelope,
                        state,
                        trace,
                        parent,
                        phase=FailurePhase.GROUNDING_BINDING,
                        failure_class=FailureClass.GROUNDING,
                        error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                        message="semantic proposal requires TaskSpec and ContractBuilder",
                        available_commands=frozenset({RecoveryCommandKind.ABORT}),
                        snapshot=snapshot,
                        proposal_id=decision.proposal.proposal_id,
                        expected_effect="; ".join(decision.proposal.expected_effects),
                        recoverable=False,
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
                try:
                    contract = self.contract_builder.build(decision.proposal, envelope.task_spec, state, snapshot)
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
                    if (
                        state.current_recovery_plan is not None
                        and state.current_recovery_plan.commands[0].kind
                        in {RecoveryCommandKind.REGROUND, RecoveryCommandKind.REROUTE}
                    ):
                        parent = self._fail_pending_recovery_command(
                            state,
                            trace,
                            parent,
                            error_code=error_code.value,
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
                    recovery_command, parent = self._recover_phase_failure(
                        envelope,
                        state,
                        trace,
                        parent,
                        phase=FailurePhase.GROUNDING_BINDING,
                        failure_class=FailureClass.GROUNDING,
                        error_code=error_code,
                        message=exc.detail or exc.code.value,
                        available_commands=frozenset(
                            {
                                RecoveryCommandKind.REGROUND,
                                RecoveryCommandKind.ABORT,
                            }
                        ),
                        snapshot=snapshot,
                        proposal_id=decision.proposal.proposal_id,
                        expected_effect="; ".join(decision.proposal.expected_effects),
                    )
                    if recovery_command == RecoveryCommandKind.REGROUND:
                        continue
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.ABORTED,
                        parent,
                        error_code,
                        latest_verification,
                    )
                if decision.proposal_provenance is None:  # validated above
                    raise RuntimeError("validated proposal is missing provenance")
                state.record_planner_proposal(
                    proposal_record(decision.proposal, decision.proposal_provenance)
                )
            if contract is None:
                parent = trace.add(
                    "TaskFailed",
                    {"state": state.phase, "reason": "planner returned neither a contract nor a result"},
                    parents=[parent.id],
                )
                recovery_command, parent = self._recover_phase_failure(
                    envelope,
                    state,
                    trace,
                    parent,
                    phase=FailurePhase.STEP_PLANNING,
                    failure_class=FailureClass.VALIDATION,
                    error_code=RuntimeErrorCode.PLANNER_FAILED,
                    message="planner returned neither a contract nor a result",
                    available_commands=frozenset(
                        {
                            RecoveryCommandKind.REPLAN_STEP,
                            *self.recovery_command_dispatcher.available_commands,
                            RecoveryCommandKind.ABORT,
                        }
                    ),
                    snapshot=snapshot,
                )
                if (
                    recovery_command == RecoveryCommandKind.REPLAN_STEP
                    or recovery_command in OWNER_DISPATCH_COMMANDS
                ):
                    continue
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep(state.phase),
                    parent,
                    RuntimeErrorCode.PLANNER_FAILED,
                    latest_verification,
                )

            contract = self.contract_execution_loop.bind_contract(
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
            action_signature = action_progress_signature(decision.proposal, contract)
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
                            "expected_effects": [asdict(item) for item in contract.expected_effects],
                            "verifier_plan": [asdict(item) for item in contract.verifier_plan],
                            "required_capabilities": list(contract.required_capabilities),
                            "risk": contract.risk.value,
                        }
                        if decision.proposal is not None
                        else None
                    ),
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
            parent, binding_recovery_failed = self._complete_pending_recovery_binding(
                state,
                trace,
                parent,
                contract,
            )
            if binding_recovery_failed:
                state.transition(RuntimeStep.ABORTED.value)
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.ABORTED,
                    parent,
                    RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED,
                    latest_verification,
                )
            contract_check = self.contract_execution_loop.initial_check(
                contract,
                envelope,
                snapshot.observation,
                capability_gate_enabled=self.features.capability_gate,
                preflight_enabled=self.features.preflight,
            )
            effective_gate = contract_check.gate
            error = contract_check.error
            execution_observation = snapshot.observation
            if error is None and self.features.preflight:
                preflight_snapshot = self.perception_session.capture(
                    envelope,
                    state,
                    state.observation_count + 1,
                )
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
                preflight_snapshot, parent = self._fulfill_targeted_perception(
                    envelope,
                    state,
                    trace,
                    parent,
                    preflight_snapshot,
                )
                perception_error = None
                if (
                    state.perception_resolution is not None
                    and state.perception_resolution.blocks_effectful_action
                ):
                    perception_error = RuntimeErrorCode.PRECONDITION_FAILED
                revalidation_error = self.contract_execution_loop.revalidate(
                    contract,
                    envelope,
                    preflight_snapshot.observation,
                    effective_gate,
                    capability_gate_enabled=False,
                    include_policy=False,
                    require_snapshot_identity=False,
                    require_environment_revision=False,
                )
                error = perception_error or revalidation_error
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
                        rebound_contract = self.contract_execution_loop.bind_contract(
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
                        rebound_error = self.contract_execution_loop.revalidate(
                            rebound_contract,
                            envelope,
                            preflight_snapshot.observation,
                            effective_gate,
                            capability_gate_enabled=self.features.capability_gate,
                            include_policy=True,
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
                approval_snapshot = self.perception_session.capture(
                    envelope,
                    state,
                    state.observation_count + 1,
                )
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
                error = self.contract_execution_loop.revalidate(
                    contract,
                    envelope,
                    approval_snapshot.observation,
                    effective_gate,
                    capability_gate_enabled=True,
                    include_policy=False,
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
                    parent = self._trace_recovery_protocol(trace, parent, state)
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
                    if (
                        state.current_recovery_plan is not None
                        and state.current_recovery_plan.commands[0].kind
                        == RecoveryCommandKind.ABORT
                    ):
                        parent = self._complete_immediate_recovery_command(
                            state,
                            trace,
                            parent,
                        )
                    return self._finish(
                        envelope,
                        state,
                        trace,
                        RuntimeStep.ABORTED,
                        parent,
                        error,
                        latest_verification,
                    )
                _recovery_command, parent = self._recover_phase_failure(
                    envelope,
                    state,
                    trace,
                    parent,
                    phase=FailurePhase.PREFLIGHT,
                    failure_class=(
                        FailureClass.SOURCE_CONFLICT
                        if perception_error is not None
                        else FailureClass.AUTHORITY
                        if error
                        in {
                            RuntimeErrorCode.CAPABILITY_DENIED,
                            RuntimeErrorCode.UNSAFE_ACTION,
                        }
                        else FailureClass.VALIDATION
                    ),
                    error_code=error,
                    message=(
                        state.perception_resolution.reason
                        if perception_error is not None
                        and state.perception_resolution is not None
                        else f"preflight rejected contract: {error.value}"
                    ),
                    available_commands=frozenset({RecoveryCommandKind.ABORT}),
                    snapshot=preflight_snapshot if self.features.preflight else snapshot,
                    expected_effect=contract.intent,
                    recoverable=False,
                )
                parent = trace.add(
                    "PreflightBlocked",
                    {"state": state.phase, "error_code": error.value},
                    parents=[parent.id],
                )
                return self._finish(envelope, state, trace, RuntimeStep.ABORTED, parent, error, latest_verification)

            authorization_error = effective_gate.authorize(contract) if self.features.capability_gate else None
            if authorization_error is not None:
                _recovery_command, parent = self._recover_phase_failure(
                    envelope,
                    state,
                    trace,
                    parent,
                    phase=FailurePhase.PREFLIGHT,
                    failure_class=FailureClass.AUTHORITY,
                    error_code=authorization_error,
                    message=f"contract authorization rejected: {authorization_error.value}",
                    available_commands=frozenset({RecoveryCommandKind.ABORT}),
                    snapshot=snapshot,
                    expected_effect=contract.intent,
                    recoverable=False,
                )
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

            retry_error = self._pending_retry_contract_error(state, contract)
            if retry_error is not None:
                parent = self._fail_pending_recovery_command(
                    state,
                    trace,
                    parent,
                    error_code=retry_error.value,
                )
                state.transition(RuntimeStep.ABORTED.value)
                parent = trace.add(
                    "RecoveryAborted",
                    {
                        "state": state.phase,
                        "reason": "retry contract did not retain validated idempotency and effect scope",
                    },
                    parents=[parent.id],
                )
                return self._finish(
                    envelope,
                    state,
                    trace,
                    RuntimeStep.ABORTED,
                    parent,
                    retry_error,
                    latest_verification,
                )

            state.transition(RuntimeStep.ACTING.value)
            parent = trace.add("ActionStarted", {"state": state.phase, "contract_id": contract.id}, parents=[parent.id])
            receipt = self.contract_execution_loop.execute(contract, execution_observation)
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
            parent = self._complete_pending_recovery_execution(
                state,
                trace,
                parent,
                contract,
                receipt,
                execution_observation,
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
                parent = self._trace_recovery_protocol(trace, parent, state)
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
                    inspection = self.perception_session.capture(
                        envelope,
                        state,
                        state.observation_count + 1,
                    )
                    state.remember_observation(inspection.observation)
                    inspection_ref = self._write_observation(envelope.task_id, state.observation_count, inspection)
                    self._index(trace, inspection_ref)
                    self._index_paths(trace, inspection.observation.artifact_refs)
                    parent = self._trace_source_arbitration(trace, parent, inspection, state.phase)
                    if inspection.active_perception_requests:
                        parent = trace.add(
                            "RecoveryActivePerceptionRequested",
                            {
                                "state": state.phase,
                                "reason": "post-action effect status requires additional current evidence",
                            },
                            parents=[parent.id],
                        )
                        inspection, parent = self._fulfill_targeted_perception(
                            envelope,
                            state,
                            trace,
                            parent,
                            inspection,
                        )
                    latest_verification = self.contract_execution_loop.verify(
                        contract,
                        receipt,
                        inspection.observation,
                        structural_verification_enabled=True,
                        disabled_reason="",
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
                    parent, _completed_verification, _recovery_must_stop = (
                        self._complete_pending_recovery_observation(
                            state,
                            trace,
                            parent,
                            inspection,
                            verification=latest_verification,
                        )
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
                if (
                    state.current_recovery_plan is not None
                    and state.current_recovery_plan.commands[0].kind
                    == RecoveryCommandKind.ABORT
                ):
                    parent = self._complete_immediate_recovery_command(
                        state,
                        trace,
                        parent,
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

            state.transition(RuntimeStep.VERIFYING.value)
            post_snapshot = self.perception_session.capture(
                envelope,
                state,
                state.observation_count + 1,
            )
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
            latest_verification = self.contract_execution_loop.verify(
                contract,
                receipt,
                post_snapshot.observation,
                structural_verification_enabled=self.features.structural_verification,
                disabled_reason="structural verification disabled by benchmark ablation",
            )
            if (
                latest_verification.status == VerificationStatus.INCONCLUSIVE
                and self.features.structural_verification
            ):
                requested_sources = tuple(
                    dict.fromkeys(
                        item.source
                        for item in post_snapshot.source_observations
                        if item.source in {GroundingSource.DOM, GroundingSource.ACCESSIBILITY, GroundingSource.API}
                    )
                ) or (GroundingSource.DOM, GroundingSource.ACCESSIBILITY)
                repair_request = ActivePerceptionRequest(
                    entity_key=contract.affordance_id,
                    property_key="verification",
                    requested_sources=requested_sources,
                    reason="verifier is inconclusive and requires fresh independent structural evidence",
                    max_observations=1,
                )
                repair_snapshot = replace(
                    post_snapshot,
                    active_perception_requests=(repair_request,),
                )
                parent = trace.add(
                    "VerificationEvidenceRepairRequested",
                    {
                        "state": state.phase,
                        "contract_id": contract.id,
                        "verification_status": latest_verification.status.value,
                    },
                    parents=[parent.id],
                )
                repair_snapshot, parent = self._fulfill_targeted_perception(
                    envelope,
                    state,
                    trace,
                    parent,
                    repair_snapshot,
                )
                if repair_snapshot.observation.snapshot_id != post_snapshot.observation.snapshot_id:
                    post_snapshot = repair_snapshot
                    latest_verification = self.contract_execution_loop.verify(
                        contract,
                        receipt,
                        post_snapshot.observation,
                        structural_verification_enabled=True,
                        disabled_reason="",
                    )
                    parent = trace.add(
                        "VerificationEvidenceReevaluated",
                        {
                            "state": state.phase,
                            "contract_id": contract.id,
                            "verification_status": latest_verification.status.value,
                            "snapshot_id": post_snapshot.observation.snapshot_id,
                        },
                        parents=[parent.id],
                    )
            state.latest_verification = latest_verification
            if decision.proposal is not None:
                state.record_action_progress(
                    action_signature,
                    post_snapshot.observation.environment_revision,
                    verification_passed=latest_verification.passed,
                    effect_satisfied=verification_satisfies_effect(latest_verification),
                    post_page_revision=post_snapshot.observation.page_revision,
                )
            verification_ref = self._write_verification(envelope.task_id, state.step_count, latest_verification)
            self._index(trace, verification_ref)
            parent = trace.add(
                "PostconditionPassed" if latest_verification.passed else "PostconditionFailed",
                {
                    "state": state.phase,
                    "contract_id": contract.id,
                    "status": latest_verification.status.value,
                    "reason": latest_verification.reason,
                    "artifact_refs": [verification_ref.path] if verification_ref else [],
                    "evidence": [asdict(item) for item in latest_verification.evidence],
                },
                parents=[parent.id],
            )
            parent = self._record_route_outcome(
                trace,
                parent,
                contract,
                receipt,
                latest_verification,
                post_snapshot,
                state.phase,
            )
            skill_complete = False
            if latest_verification.passed:
                if skill_step_id and self.task_skill_runtime is not None:
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
                    subgoal = TaskPlanLifecycle.active_subgoal_spec(state)
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
                        if TaskPlanLifecycle.completed(state):
                            parent = trace.add(
                                "TaskPlanCompleted",
                                {
                                    "state": state.phase,
                                    "task_plan_id": state.task_plan.plan_id,
                                    "completed_subgoal_ids": list(state.plan_progress.completed_subgoal_ids),
                                },
                                parents=[parent.id],
                            )
                            if (
                                len(state.task_plan.subgoals) > 1
                                or not isinstance(self.task_planner, PlanningRouter)
                                or skill_complete
                            ):
                                if skill_complete and state.task_skill is not None:
                                    state.final_result = {
                                        "task_skill_id": state.task_skill.skill_id,
                                        "task_skill_version": state.task_skill.version,
                                        "completed_step_ids": list(state.task_skill.completed_step_ids),
                                    }
                                    parent = trace.add(
                                        "TaskSkillCompleted",
                                        {"state": state.phase, **state.final_result},
                                        parents=[parent.id],
                                    )
                                else:
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
            parent = self._trace_recovery_protocol(trace, parent, state)
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
            if (
                state.current_recovery_plan is not None
                and state.current_recovery_plan.commands[0].kind
                == RecoveryCommandKind.ABORT
            ):
                parent = self._complete_immediate_recovery_command(
                    state,
                    trace,
                    parent,
                )
            return self._finish(
                envelope,
                state,
                trace,
                RuntimeStep.FAILED,
                parent,
                RuntimeErrorCode.VERIFICATION_FAILED,
                latest_verification,
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
        evaluation = self.recovery_handler.evaluate(
            RecoveryRequest(
                contract=contract,
                receipt=receipt,
                error=error,
                failure_phase=failure_phase,
                state_revision=state.current_revision(),
                task_id=state.task_id,
                recovery_count=state.recovery_count,
                tried_backends=tuple(item.backend for item in state.receipts),
                incident=state.recovery_incident,
                state_version=state.version,
                progress_fingerprint=semantic_progress_fingerprint(state),
                accepted_profile_digest=self.runtime_profile_digest,
                accepted_profile_artifact_ids=self.loaded_profile_artifact_ids,
                attempted_strategy_ids=tuple(
                    sorted(state.attempted_recovery_strategy_ids)
                ),
                recovery_history=tuple(state.recovery_history),
            )
        )
        signature = evaluation.signature
        assessment = evaluation.assessment
        decision = evaluation.decision
        effect_may_have_occurred = evaluation.effect_may_have_occurred
        state.current_failure = evaluation.failure
        state.current_recovery_plan = evaluation.plan
        state.attempted_recovery_strategy_ids.add(
            evaluation.plan.commands[0].strategy_id
        )
        incident = state.recovery_incident
        if not evaluation.continues_open_incident:
            incident = RecoveryIncident(
                incident_id=f"recovery-{state.task_id}-{state.recovery_count + 1}",
                source_contract_id=contract.id,
                source_snapshot_id=contract.snapshot_id,
                root_failure=signature,
            )
            state.recovery_incident = incident
        else:
            if incident is None:
                raise ValueError("open recovery evaluation requires an active incident")
            incident.complete_pending(state.current_revision(), RecoveryAttemptOutcome.FAILED)
            incident.symptom_chain.append(signature)
        if incident is None:
            raise ValueError("recovery incident was not initialized")
        if failure_context:
            incident.context.update(failure_context)
        incident.findings.extend(item for item in assessment.findings if item not in incident.findings)
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

    @staticmethod
    def _trace_recovery_protocol(
        trace: TraceDag,
        parent: TraceNode,
        state: StateKernel,
    ) -> TraceNode:
        failure = state.current_failure
        plan = state.current_recovery_plan
        if failure is None or plan is None:
            return parent
        command = plan.commands[0]
        parent = trace.add(
            "FailureDetected",
            {
                "state": state.phase,
                "failure": failure.model_dump(mode="json"),
            },
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryStrategySelected",
            {
                "state": state.phase,
                "plan": plan.model_dump(mode="json"),
                "strategy_id": command.strategy_id,
                "changed_dimensions": [item.value for item in command.changed_dimensions],
            },
            parents=[parent.id],
        )
        return trace.add(
            "RecoveryCommandStarted",
            {
                "state": state.phase,
                "command": command.model_dump(mode="json"),
            },
            parents=[parent.id],
        )

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
        available_commands: frozenset[RecoveryCommandKind],
        snapshot: BrowserSnapshot | None = None,
        proposal_id: str = "",
        expected_effect: str = "",
        recoverable: bool = True,
        abort_reentry_phase: RecoveryReentryPhase = RecoveryReentryPhase.ABORTED,
    ) -> tuple[RecoveryCommandKind, TraceNode]:
        available_commands = frozenset(
            kind
            for kind in available_commands
            if kind not in OWNER_DISPATCH_COMMANDS
            or kind in self.recovery_command_dispatcher.available_commands
        )
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
            expected_effect=expected_effect or envelope.goal,
            effect_status=EffectStatus.NOT_DISPATCHED,
            attempted_strategy_ids=tuple(sorted(state.attempted_recovery_strategy_ids)),
            rejected_assumptions=tuple(state.disproved_assumptions),
            remaining_budgets=self._remaining_recovery_budgets(state),
            recoverable=recoverable,
            progress_fingerprint=semantic_progress_fingerprint(state),
        )
        state.transition(RuntimeStep.RECOVERING.value)
        plan = self.recovery_coordinator.plan(
            failure,
            RecoverySelectionContext(
                available_commands=available_commands,
                current_attempt_fingerprint=failure.progress_fingerprint,
                gap_ids=tuple(item.gap_id for item in state.evidence_gaps),
                accepted_profile_digest=self.runtime_profile_digest,
                accepted_profile_artifact_ids=frozenset(self.loaded_profile_artifact_ids),
                configured_provider_id=self.recovery_command_dispatcher.target_ref(
                    RecoveryCommandKind.SWITCH_PROVIDER
                ),
                history=tuple(state.recovery_history),
                abort_reentry_phase=abort_reentry_phase,
            ),
            current_state_version=state.version,
        )
        state.current_failure = failure
        state.current_recovery_plan = plan
        command = plan.commands[0]
        state.attempted_recovery_strategy_ids.add(command.strategy_id)
        state.recovery_count += 1
        parent = self._trace_recovery_protocol(trace, parent, state)
        if command.kind in {
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.ACTIVE_PERCEPTION,
        }:
            state.transition(RuntimeStep.OBSERVING.value)
            return command.kind, parent
        if command.kind in {
            RecoveryCommandKind.REPLAN_STEP,
            RecoveryCommandKind.REPLAN_TASK,
        }:
            state.replan_count += 1
            state.record_disproved_assumption(f"{phase.value}:{failure.error_code}:{failure.message}")
            state.transition(RuntimeStep.OBSERVING.value)
            return command.kind, parent
        if command.kind in {
            RecoveryCommandKind.COMPACT_CONTEXT,
            RecoveryCommandKind.REPAIR_MODEL_SCHEMA,
            RecoveryCommandKind.SWITCH_PROVIDER,
        }:
            previous_fingerprint = (
                failure.progress_fingerprint
                or f"{failure.semantic_family_key}:state:{failure.state_version}"
            )
            dispatched = self.recovery_command_dispatcher.dispatch(
                command,
                previous_attempt_fingerprint=previous_fingerprint,
            )
            state.recovery_receipts.append(dispatched.receipt)
            parent = trace.add(
                "RecoveryCommandCompleted",
                {
                    "state": state.phase,
                    "receipt": dispatched.receipt.model_dump(mode="json"),
                },
                parents=[parent.id],
            )
            if not dispatched.receipt.success or dispatched.delta is None:
                state.current_recovery_plan = None
                state.transition(abort_reentry_phase.value)
                return RecoveryCommandKind.ABORT, parent
            state.replan_count += 1
            state.record_disproved_assumption(
                f"{phase.value}:{failure.error_code}:{failure.message}"
            )
            state.recovery_deltas.append(dispatched.delta)
            state.recovery_history.append(
                RecoveryHistoryItem(
                    failure.semantic_family_key,
                    command.strategy_id,
                    previous_fingerprint,
                    dispatched.delta.next_attempt_fingerprint,
                )
            )
            state.current_recovery_plan = None
            state.transition(RuntimeStep.OBSERVING.value)
            parent = trace.add(
                "RecoveryDeltaValidated",
                {
                    "state": state.phase,
                    "delta": dispatched.delta.model_dump(mode="json"),
                },
                parents=[parent.id],
            )
            parent = trace.add(
                "RecoveryReenteredPhase",
                {
                    "state": state.phase,
                    "reentry_phase": command.reentry_phase.value,
                },
                parents=[parent.id],
            )
            return command.kind, parent
        terminal_phase = {
            RecoveryReentryPhase.WAITING_USER: RuntimeStep.WAITING_CLARIFICATION.value,
            RecoveryReentryPhase.WAITING_APPROVAL: RuntimeStep.WAITING_APPROVAL.value,
            RecoveryReentryPhase.DEFERRED: RuntimeStep.DEFERRED.value,
            RecoveryReentryPhase.FAILED: RuntimeStep.FAILED.value,
            RecoveryReentryPhase.ABORTED: RuntimeStep.ABORTED.value,
        }.get(command.reentry_phase)
        if terminal_phase is None:
            raise ValueError(f"unsupported immediate recovery re-entry: {command.reentry_phase.value}")
        state.transition(terminal_phase)
        parent = self._complete_immediate_recovery_command(state, trace, parent)
        return command.kind, parent

    @staticmethod
    def _complete_immediate_recovery_command(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
    ) -> TraceNode:
        failure = state.current_failure
        plan = state.current_recovery_plan
        if failure is None or plan is None:
            raise ValueError("immediate recovery completion requires failure and plan")
        command = plan.commands[0]
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"{state.phase}:state:{state.version}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            retired_assumptions=tuple(state.disproved_assumptions[-1:]),
            new_plan_or_route_ref=command.provider_id,
            explanation=command.expected_change,
        )
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=True,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            plan_refs=(command.provider_id,) if command.provider_id else (),
            delta=delta,
        )
        state.recovery_deltas.append(delta)
        state.recovery_receipts.append(receipt)
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_plan = None
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": delta.model_dump(mode="json")},
            parents=[parent.id],
        )
        return trace.add(
            "RecoveryReenteredPhase",
            {"state": state.phase, "reentry_phase": command.reentry_phase.value},
            parents=[parent.id],
        )

    @staticmethod
    def _complete_pending_recovery_plan_change(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        kind: RecoveryCommandKind,
        plan_or_route_ref: str,
    ) -> TraceNode:
        failure = state.current_failure
        plan = state.current_recovery_plan
        if failure is None or plan is None or plan.commands[0].kind != kind:
            return parent
        command = plan.commands[0]
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"{plan_or_route_ref}:state:{state.version}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            retired_assumptions=tuple(state.disproved_assumptions[-1:]),
            new_plan_or_route_ref=plan_or_route_ref,
            explanation=command.expected_change,
        )
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=True,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            plan_refs=(plan_or_route_ref,),
            delta=delta,
        )
        state.recovery_deltas.append(delta)
        state.recovery_receipts.append(receipt)
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_plan = None
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": delta.model_dump(mode="json")},
            parents=[parent.id],
        )
        return trace.add(
            "RecoveryReenteredPhase",
            {"state": state.phase, "reentry_phase": command.reentry_phase.value},
            parents=[parent.id],
        )

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

    def _complete_pending_recovery_observation(
        self,
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        snapshot: BrowserSnapshot,
        *,
        verification: VerificationReport | None = None,
    ) -> tuple[TraceNode, VerificationReport | None, bool]:
        failure = state.current_failure
        plan = state.current_recovery_plan
        if failure is None or plan is None:
            return parent, verification, False
        command = plan.commands[0]
        observation_commands = {
            RecoveryCommandKind.REOBSERVE,
            RecoveryCommandKind.INSPECT_POST_STATE,
        }
        if command.kind not in observation_commands:
            return parent, verification, False
        if command.kind == RecoveryCommandKind.INSPECT_POST_STATE:
            contract = state.current_contract
            execution_receipt = state.receipts[-1] if state.receipts else None
            if contract is None or execution_receipt is None:
                raise ValueError("post-state recovery inspection requires contract and receipt lineage")
            if verification is None:
                verification = self.contract_execution_loop.verify(
                    contract,
                    execution_receipt,
                    snapshot.observation,
                    structural_verification_enabled=True,
                    disabled_reason="",
                )
                state.latest_verification = verification
                parent = trace.add(
                    "RecoveryStateInspected",
                    {
                        "state": state.phase,
                        "verification": verification.status.value,
                        "snapshot_id": snapshot.observation.snapshot_id,
                        "artifact_refs": snapshot.observation.artifact_refs,
                    },
                    parents=[parent.id],
                )
            changed_skill_fallthrough = bool(
                verification_confirms_effect_absent(verification)
                and state.task_skill is not None
                and not state.task_skill.active
            )
            if not verification.passed and not changed_skill_fallthrough:
                failed_receipt = RecoveryCommandReceipt(
                    command_id=command.command_id,
                    success=False,
                    state_before=f"state:{failure.state_version}",
                    state_after=f"state:{state.version}",
                    error_code=RuntimeErrorCode.VERIFICATION_FAILED.value,
                )
                state.recovery_receipts.append(failed_receipt)
                state.current_recovery_plan = None
                parent = trace.add(
                    "RecoveryCommandCompleted",
                    {
                        "state": state.phase,
                        "receipt": failed_receipt.model_dump(mode="json"),
                    },
                    parents=[parent.id],
                )
                parent = trace.add(
                    "RecoveryAborted",
                    {
                        "state": state.phase,
                        "reason": "post-state inspection did not establish a safe changed effect status",
                    },
                    parents=[parent.id],
                )
                return parent, verification, True
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"{snapshot.observation.snapshot_id}:state:{state.version}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            new_evidence_refs=tuple(snapshot.observation.artifact_refs),
            new_plan_or_route_ref=command.route_ref or command.candidate_id,
            explanation=command.expected_change,
        )
        recovery_receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=True,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            artifact_refs=tuple(snapshot.observation.artifact_refs),
            observation_refs=(snapshot.observation.snapshot_id,),
            route_refs=tuple(
                item for item in (command.route_ref, command.candidate_id) if item
            ),
            verification_refs=(verification.status.value,) if verification is not None else (),
            delta=delta,
        )
        state.recovery_deltas.append(delta)
        state.recovery_receipts.append(recovery_receipt)
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_plan = None
        parent = trace.add(
            "RecoveryCommandCompleted",
            {
                "state": state.phase,
                "receipt": recovery_receipt.model_dump(mode="json"),
            },
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {
                "state": state.phase,
                "delta": delta.model_dump(mode="json"),
            },
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryReenteredPhase",
            {
                "state": state.phase,
                "reentry_phase": command.reentry_phase.value,
            },
            parents=[parent.id],
        )
        return parent, verification, False

    @staticmethod
    def _complete_pending_recovery_binding(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
    ) -> tuple[TraceNode, bool]:
        failure = state.current_failure
        plan = state.current_recovery_plan
        if failure is None or plan is None:
            return parent, False
        command = plan.commands[0]
        if command.kind not in {
            RecoveryCommandKind.REGROUND,
            RecoveryCommandKind.REROUTE,
        }:
            return parent, False
        candidate_id = (
            contract.grounding_candidate.candidate_id
            if contract.grounding_candidate is not None
            else ""
        )
        fresh_epoch = bool(contract.snapshot_id and contract.snapshot_id != failure.snapshot_id)
        route_matches = bool(
            command.kind == RecoveryCommandKind.REGROUND
            or (command.candidate_id and candidate_id == command.candidate_id)
            or (command.route_ref and contract.backend == command.route_ref)
        )
        if not fresh_epoch or not route_matches:
            parent = RunCoordinator._fail_pending_recovery_command(
                state,
                trace,
                parent,
                error_code=RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED.value,
            )
            return parent, True
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"contract:{contract.contract_hash or contract.id}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            new_plan_or_route_ref=candidate_id or contract.id,
            explanation=command.expected_change,
        )
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=True,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            route_refs=tuple(item for item in (candidate_id, contract.id) if item),
            delta=delta,
        )
        state.recovery_deltas.append(delta)
        state.recovery_receipts.append(receipt)
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_plan = None
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        parent = trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": delta.model_dump(mode="json")},
            parents=[parent.id],
        )
        return (
            trace.add(
                "RecoveryReenteredPhase",
                {"state": state.phase, "reentry_phase": command.reentry_phase.value},
                parents=[parent.id],
            ),
            False,
        )

    @staticmethod
    def _fail_pending_recovery_command(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        *,
        error_code: str,
    ) -> TraceNode:
        plan = state.current_recovery_plan
        if plan is None:
            return parent
        command = plan.commands[0]
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=False,
            state_before=f"state:{command.based_on_state_version}",
            state_after=f"state:{state.version}",
            error_code=error_code,
        )
        state.recovery_receipts.append(receipt)
        state.current_recovery_plan = None
        return trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )

    @staticmethod
    def _pending_retry_contract_error(
        state: StateKernel,
        contract: ActionContract,
    ) -> RuntimeErrorCode | None:
        plan = state.current_recovery_plan
        if plan is None or plan.commands[0].kind != RecoveryCommandKind.RETRY_IDEMPOTENT:
            return None
        command = plan.commands[0]
        if (
            not contract.idempotency_key
            or contract.idempotency_key != command.idempotency_key
            or command.effect_status
            not in {EffectStatus.NOT_DISPATCHED, EffectStatus.CONFIRMED_NOT_OCCURRED}
        ):
            return RuntimeErrorCode.UNSAFE_ACTION
        return None

    @staticmethod
    def _complete_pending_recovery_execution(
        state: StateKernel,
        trace: TraceDag,
        parent: TraceNode,
        contract: ActionContract,
        execution_receipt: ExecutionReceipt,
        observation: Observation,
    ) -> TraceNode:
        failure = state.current_failure
        plan = state.current_recovery_plan
        if (
            failure is None
            or plan is None
            or plan.commands[0].kind != RecoveryCommandKind.RETRY_IDEMPOTENT
        ):
            return parent
        command = plan.commands[0]
        previous_fingerprint = (
            failure.progress_fingerprint
            or f"{failure.semantic_family_key}:state:{failure.state_version}"
        )
        next_fingerprint = (
            f"{failure.semantic_family_key}:{command.strategy_id}:"
            f"contract:{contract.contract_hash or contract.id}:snapshot:{observation.snapshot_id}"
        )
        delta = RecoveryDelta(
            previous_attempt_fingerprint=previous_fingerprint,
            next_attempt_fingerprint=next_fingerprint,
            changed_dimensions=command.changed_dimensions,
            new_evidence_refs=tuple(
                item
                for item in execution_receipt.evidence.values()
                if isinstance(item, str)
            ),
            new_plan_or_route_ref=contract.id,
            explanation=command.expected_change,
        )
        receipt = RecoveryCommandReceipt(
            command_id=command.command_id,
            success=execution_receipt.success,
            state_before=f"state:{failure.state_version}",
            state_after=f"state:{state.version}",
            changed_dimensions=command.changed_dimensions,
            observation_refs=(observation.snapshot_id,) if observation.snapshot_id else (),
            plan_refs=(contract.id,),
            error_code=(
                ""
                if execution_receipt.success
                else (
                    execution_receipt.error_code.value
                    if execution_receipt.error_code is not None
                    else RuntimeErrorCode.EXECUTION_FAILED.value
                )
            ),
            delta=delta,
        )
        state.recovery_deltas.append(delta)
        state.recovery_receipts.append(receipt)
        state.recovery_history.append(
            RecoveryHistoryItem(
                failure.semantic_family_key,
                command.strategy_id,
                previous_fingerprint,
                next_fingerprint,
            )
        )
        state.current_recovery_plan = None
        parent = trace.add(
            "RecoveryCommandCompleted",
            {"state": state.phase, "receipt": receipt.model_dump(mode="json")},
            parents=[parent.id],
        )
        return trace.add(
            "RecoveryDeltaValidated",
            {"state": state.phase, "delta": delta.model_dump(mode="json")},
            parents=[parent.id],
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
                    "artifact_refs": ([targeted_ref.path] if targeted_ref else []) + targeted.observation.artifact_refs,
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
