import asyncio
from dataclasses import dataclass

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.failure_envelope import FailurePhase
from affordance_runtime.model_port import ProviderFailureKind, ProviderModelError
from affordance_runtime.planning import (
    ContractBuilder,
    PlannerActionKind,
    PlannerProposal,
    PlannerProposalProvenance,
    PlannerProposalSource,
    PlannerProposalValidator,
    ProposalRejected,
    ProposalRejectionCode,
)
from affordance_runtime.recovery_owner_dispatcher import (
    RecoveryOwnerDispatcher,
    RecoveryOwnerResult,
)
from affordance_runtime.recovery_protocol import RecoveryDecision, RecoveryDimension, RecoveryKind
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    CompilationIssue,
    CompilationResult,
    CompilationStatus,
    IntentDraft,
    OperationClass,
    TaskSpec,
    UserRequest,
)
from affordance_runtime.task_pipeline import GeneralistTaskPipeline
from affordance_runtime.task_planning import (
    SubgoalSpec,
    TaskPlan,
    TaskPlanningContext,
    TaskPlanSource,
)
from affordance_runtime.task_skills import TaskSkillRuntimeDecision


def _snapshot(sequence: int) -> BrowserSnapshot:
    revision = f"revision-{sequence}"
    snapshot_id = f"snapshot-{sequence}"
    model = DomAdapter().transduce(
        "<main><button id='continue'>Continue</button></main>",
        environment_revision=revision,
        snapshot_id=snapshot_id,
        page_revision=revision,
    )
    return BrowserSnapshot(
        Observation(
            revision,
            snapshot_id=snapshot_id,
            page_revision=revision,
            target_fingerprints={
                item.id: item.target_fingerprint for item in model.affordances
            },
        ),
        model,
    )


class FlakyObserver:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self) -> BrowserSnapshot:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary observation transport failure")
        return _snapshot(self.calls)


class StableObserver:
    def __init__(self) -> None:
        self.calls = 0

    def capture(self) -> BrowserSnapshot:
        self.calls += 1
        return _snapshot(self.calls)


class DonePlanner:
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope, state, snapshot
        return PlannerDecision(done=True, result={"status": "observed"})


class FailOncePlanner(DonePlanner):
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient structured planning failure")
        return super().propose(envelope, state, snapshot)


class AlwaysFailPlanner:
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope, state, snapshot
        raise RuntimeError("stable structured planning failure")


class TargetScopeThenClarifyPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        self.calls += 1
        if self.calls > 1:
            return PlannerDecision(
                proposal=PlannerProposal(
                    proposal_id="clarify-after-target-rejection",
                    based_on_task_revision=1,
                    based_on_state_version=state.version,
                    snapshot_id=snapshot.observation.snapshot_id,
                    action_kind=PlannerActionKind.ASK_USER,
                    subgoal="Which visible target should be used?",
                    requires_clarification=True,
                    uncertainty=1.0,
                ),
                proposal_provenance=PlannerProposalProvenance(
                    source=PlannerProposalSource.MODEL,
                    producer_id="test-planner",
                ),
            )
        target = snapshot.affordance_model.affordances[0]
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id="wrong-target",
                based_on_task_revision=1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=target.id,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.MODEL,
                producer_id="test-planner",
            ),
        )


class RejectTargetScopeOnceValidator:
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, *args: object, **kwargs: object) -> None:
        self.calls += 1
        if self.calls == 1:
            raise ProposalRejected(
                ProposalRejectionCode.TARGET_OUT_OF_SCOPE,
                "semantic:wrong-target",
                reason_code="relational_evidence_not_proven",
            )
        PlannerProposalValidator().validate(*args, **kwargs)  # type: ignore[arg-type]


class ProviderFailOncePlanner(DonePlanner):
    def __init__(self) -> None:
        self.calls = 0

    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        self.calls += 1
        if self.calls == 1:
            raise ProviderModelError(ProviderFailureKind.QUOTA_EXHAUSTED)
        return super().propose(envelope, state, snapshot)


@dataclass
class ProviderSwitchOwner:
    no_op: bool = False
    owner_id: str = "provider-registry"
    target_ref: str = "provider-b"
    calls: int = 0

    def execute(self, decision: RecoveryDecision) -> RecoveryOwnerResult:
        self.calls += 1
        return RecoveryOwnerResult(
            owner_id=self.owner_id,
            kind=decision.kind,
            success=True,
            state_before_ref="provider:provider-a",
            state_after_ref=(
                "provider:provider-a" if self.no_op else "provider:provider-b"
            ),
            changed_dimensions=(RecoveryDimension.PROVIDER,),
            evidence_refs=("artifact:provider-switch",),
        )


class ClarifyPlanner:
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id="clarify-after-task-replan",
                based_on_task_revision=1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal="Which account should be inspected?",
                action_kind=PlannerActionKind.ASK_USER,
                requires_clarification=True,
                uncertainty=1.0,
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="full-phase-recovery-test",
            ),
        )


class ActivateCurrentPlanner:
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id=f"activate-current-{state.replan_count}",
                based_on_task_revision=1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=snapshot.affordance_model.affordances[0].id,
                expected_effects=("continue control is activated",),
                evidence_requirements=("current continue control",),
            ),
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.DETERMINISTIC_RULE,
                producer_id="full-phase-recovery-test",
            ),
        )


class RejectBindingBuilder(ContractBuilder):
    def build(
        self,
        proposal: PlannerProposal,
        task_spec: TaskSpec,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> ActionContract:
        del proposal, task_spec, state, snapshot
        raise ProposalRejected(
            ProposalRejectionCode.NO_BACKEND,
            "no current route can bind the semantic target",
        )


class FailOnceTaskPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient task-plan schema failure")
        return TaskPlan(
            plan_id="recovered-task-plan",
            task_id=context.task_spec.task_id,
            task_revision=context.task_spec.revision,
            plan_version=1,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="inspect",
                    objective="Inspect the selected account",
                    success_criteria=("selected account is identified",),
                    evidence_requirements=("current account evidence",),
                    operation_class=OperationClass.READ_ONLY,
                ),
            ),
        )


def _task_spec() -> TaskSpec:
    return TaskSpec(
        task_id="task-planning-recovery",
        revision=1,
        objective="Inspect an account after clarification",
        operation_class=OperationClass.READ_ONLY,
        targets=("account",),
        success_criteria=("selected account is identified",),
        evidence_requirements=("current account evidence",),
        source_request_ref="full-phase-recovery-test",
    )


def _navigation_task_spec() -> TaskSpec:
    return TaskSpec(
        task_id="grounding-recovery",
        revision=1,
        objective="Activate the Continue control",
        operation_class=OperationClass.NAVIGATION,
        targets=("Continue",),
        success_criteria=("continue control is activated",),
        evidence_requirements=("current continue control",),
        source_request_ref="full-phase-recovery-test",
    )


class StaticClarificationCompiler:
    async def compile(
        self,
        request: UserRequest,
        *,
        task_id: str,
        trace: object,
    ) -> CompilationResult:
        del request, trace
        return CompilationResult(
            status=CompilationStatus.NEEDS_CLARIFICATION,
            request_id=task_id,
            draft=IntentDraft(objective="Inspect an account"),
            issues=(
                CompilationIssue(
                    code="blocking_ambiguity",
                    field="account",
                    detail="which account should be inspected",
                ),
            ),
        )


class FailOnceSkillRuntime:
    def __init__(self) -> None:
        self.failed = False

    def expose(self, task_spec: object, state: object, snapshot: object) -> object:
        del task_spec, state, snapshot
        if not self.failed:
            raise RuntimeError("accepted skill binding failed")
        return TaskSkillRuntimeDecision(attempted=False, reason="skill disabled after failure")

    def fallthrough(self, state: StateKernel, reason: str) -> None:
        del state, reason
        self.failed = True


@dataclass
class NeverExecutor:
    backend: str = "never"

    def execute(
        self,
        contract: ActionContract,
        observation: Observation,
    ) -> ExecutionReceipt:
        del contract, observation
        raise AssertionError("recovery fixture must not execute an effect")


def test_observation_failure_reenters_through_one_reobserve_command() -> None:
    result = RunCoordinator(
        observer=FlakyObserver(),
        planner=DonePlanner(),
        executor=NeverExecutor(),
        task_planner=None,
    ).run_sync(TaskEnvelope("observation-recovery", "observe the current interface"))

    assert result.status == RuntimeStep.DONE
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase == FailurePhase.OBSERVATION
    assert result.state.current_recovery_decision is not None
    assert result.state.current_recovery_decision.kind.value == RecoveryKind.REOBSERVE.value
    assert result.state.recovery_history[0].strategy_id.startswith("strategy:reobserve:")
    recovery_outcome = next(
        node.payload["outcome"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    )
    assert recovery_outcome["success"]
    events = [node.kind for node in result.trace.nodes]
    assert events.index("FailureDetected") < events.index("RecoveryDecisionStarted")
    assert events.index("RecoveryDecisionStarted") < events.index("RecoveryOutcomeRecorded")


def test_step_planning_failure_changes_strategy_then_succeeds() -> None:
    planner = FailOncePlanner()
    result = RunCoordinator(
        observer=StableObserver(),
        planner=planner,
        executor=NeverExecutor(),
        task_planner=None,
    ).run_sync(TaskEnvelope("step-planning-recovery", "produce a safe answer"))

    assert result.status == RuntimeStep.DONE
    assert planner.calls == 2
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase == FailurePhase.STEP_PLANNING
    assert result.state.current_recovery_decision is not None
    assert result.state.current_recovery_decision.kind.value == RecoveryKind.REPLAN_STEP.value
    assert result.state.recovery_history[0].strategy_id.startswith("strategy:replan_step:")
    recovery_outcome = next(
        node.payload["outcome"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    )
    assert recovery_outcome["changed_dimensions"][0] == "step_plan"


def test_target_scope_rejection_replans_without_weakening_validation() -> None:
    planner = TargetScopeThenClarifyPlanner()
    result = RunCoordinator(
        observer=StableObserver(),
        planner=planner,
        executor=NeverExecutor(),
        proposal_validator=RejectTargetScopeOnceValidator(),  # type: ignore[arg-type]
        task_planner=None,
    ).run_sync(TaskEnvelope(task_spec=_navigation_task_spec()))

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert planner.calls == 2
    assert result.state.current_failure is not None
    assert result.state.current_failure.recoverable
    assert result.state.current_failure.message == (
        "target_out_of_scope:relational_evidence_not_proven:semantic:wrong-target"
    )
    assert result.state.current_recovery_decision is not None
    assert result.state.current_recovery_decision.kind.value == RecoveryKind.REPLAN_STEP.value
    rejected = next(
        node for node in result.trace.nodes if node.kind == "PlannerProposalRejected"
    )
    assert rejected.payload["rejection_reason_code"] == (
        "relational_evidence_not_proven"
    )


def test_provider_failure_invokes_real_owner_before_reentering_planning() -> None:
    planner = ProviderFailOncePlanner()
    owner = ProviderSwitchOwner()
    result = RunCoordinator(
        observer=StableObserver(),
        planner=planner,
        executor=NeverExecutor(),
        task_planner=None,
        recovery_owner_dispatcher=RecoveryOwnerDispatcher(
            {RecoveryKind.SWITCH_PROVIDER: owner}
        ),
    ).run_sync(TaskEnvelope("provider-owner-recovery", "produce a safe answer"))

    assert result.status == RuntimeStep.DONE
    assert planner.calls == 2
    assert owner.calls == 1
    recovery_outcome = next(
        node.payload["outcome"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    )
    assert recovery_outcome["success"]
    assert recovery_outcome["changed_dimensions"][0] == "provider"
    events = [node.kind for node in result.trace.nodes]
    assert events.index("RecoveryDecisionStarted") < events.index(
        "RecoveryOutcomeRecorded"
    )
    assert events.index("RecoveryOutcomeRecorded") < events.index(
        "RecoveryReenteredPhase"
    )


def test_provider_no_op_owner_defers_without_crediting_recovery_delta() -> None:
    owner = ProviderSwitchOwner(no_op=True)
    result = RunCoordinator(
        observer=StableObserver(),
        planner=ProviderFailOncePlanner(),
        executor=NeverExecutor(),
        task_planner=None,
        recovery_owner_dispatcher=RecoveryOwnerDispatcher(
            {RecoveryKind.SWITCH_PROVIDER: owner}
        ),
    ).run_sync(TaskEnvelope("provider-no-op-recovery", "produce a safe answer"))

    assert result.status == RuntimeStep.DEFERRED
    assert result.state.phase == RuntimeStep.DEFERRED.value
    assert owner.calls == 1
    assert "RecoveryDeltaValidated" not in [node.kind for node in result.trace.nodes]
    recovery_outcome = next(
        node.payload["outcome"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    )
    assert not recovery_outcome["success"]
    assert recovery_outcome["error_code"] == "owning_port_no_op"


def test_equivalent_step_planning_failure_changes_once_then_aborts_before_budget() -> None:
    result = RunCoordinator(
        observer=StableObserver(),
        planner=AlwaysFailPlanner(),
        executor=NeverExecutor(),
        task_planner=None,
    ).run_sync(TaskEnvelope("step-planning-loop", "produce a safe answer"))

    assert result.status == RuntimeStep.ABORTED
    assert result.state.recovery_count == 2
    assert result.state.recovery_count < 3
    assert result.state.current_recovery_outcome is not None
    assert result.state.current_recovery_outcome.next_phase.value == RuntimeStep.ABORTED.value
    assert [
        node.payload["outcome"]["success"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    ] == [False, True]
    selected = [
        node.payload["decision"]["kind"]
        for node in result.trace.nodes
        if node.kind == "RecoveryStrategySelected"
    ]
    assert selected == [
        RecoveryKind.REPLAN_STEP.value,
        RecoveryKind.ABORT.value,
    ]


def test_task_planning_failure_uses_replan_task_before_step_planning() -> None:
    task_planner = FailOnceTaskPlanner()
    result = RunCoordinator(
        observer=StableObserver(),
        planner=ClarifyPlanner(),
        executor=NeverExecutor(),
        task_planner=task_planner,
    ).run_sync(TaskEnvelope(task_spec=_task_spec()))

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert task_planner.calls == 2
    assert result.state.task_plan is not None
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase == FailurePhase.TASK_PLANNING
    assert result.state.current_recovery_decision is not None
    assert result.state.current_recovery_decision.kind.value == RecoveryKind.REPLAN_TASK.value
    events = [node.kind for node in result.trace.nodes]
    assert events.index("RecoveryDecisionStarted") < events.index("TaskPlanAccepted")
    assert events.index("RecoveryDecisionStarted") < events.index("RecoveryOutcomeRecorded")


def test_intake_clarification_uses_same_recovery_coordinator_without_run_state() -> None:
    pipeline = GeneralistTaskPipeline(
        compiler=StaticClarificationCompiler(),  # type: ignore[arg-type]
        coordinator=RunCoordinator(
            observer=StableObserver(),
            planner=DonePlanner(),
            executor=NeverExecutor(),
            task_planner=None,
        ),
    )

    result = asyncio.run(
        pipeline.run(
            UserRequest(
                request_id="intake-recovery",
                raw_text="Inspect the account",
            )
        )
    )

    assert result.status == CompilationStatus.NEEDS_CLARIFICATION.value
    selected = next(
        node for node in result.trace.nodes if node.kind == "RecoveryStrategySelected"
    )
    if "decision" in selected.payload:
        assert selected.payload["decision"]["kind"] == "clarify_intent"
    else:
        assert selected.payload["plan"]["commands"][0]["kind"] == "clarify_intent"
    assert "RecoveryEscalatedToUser" in [node.kind for node in result.trace.nodes]


def test_skill_activation_failure_falls_through_via_replan_step() -> None:
    skill_runtime = FailOnceSkillRuntime()
    result = RunCoordinator(
        observer=StableObserver(),
        planner=ClarifyPlanner(),
        executor=NeverExecutor(),
        task_planner=None,
        task_skill_runtime=skill_runtime,  # type: ignore[arg-type]
    ).run_sync(TaskEnvelope(task_spec=_task_spec()))

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert skill_runtime.failed
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase == FailurePhase.SKILL_ACTIVATION
    assert result.state.current_recovery_decision is not None
    assert result.state.current_recovery_decision.kind.value == RecoveryKind.REPLAN_STEP.value


def test_grounding_binding_reobserves_once_then_aborts_without_execution() -> None:
    result = RunCoordinator(
        observer=StableObserver(),
        planner=ActivateCurrentPlanner(),
        executor=NeverExecutor(),
        contract_builder=RejectBindingBuilder(),
        task_planner=None,
    ).run_sync(TaskEnvelope(task_spec=_navigation_task_spec()))

    assert result.status == RuntimeStep.ABORTED
    assert result.state.receipts == []
    assert result.state.current_failure is not None
    assert result.state.current_failure.phase == FailurePhase.GROUNDING_BINDING
    assert [
        node.payload["outcome"]["success"]
        for node in result.trace.nodes
        if node.kind == "RecoveryOutcomeRecorded"
    ] == [False, True]
    selected = [
        node.payload["decision"]["kind"]
        for node in result.trace.nodes
        if node.kind == "RecoveryStrategySelected"
    ]
    assert selected == [RecoveryKind.REGROUND.value, RecoveryKind.ABORT.value]
