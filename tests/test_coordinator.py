import asyncio
from dataclasses import dataclass, replace
from typing import Sequence, TypeVar

from pydantic import BaseModel

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunBudget, RunCoordinator, _resolve_planner_decision
from affordance_runtime.criteria import criterion_id, evidence_requirement_id
from affordance_runtime.grounding import GroundingSource, SourceAssertion
from affordance_runtime.intent_compiler import LLMIntentCompiler
from affordance_runtime.model_port import (
    ModelCallRecord,
    ModelConfig,
    ModelMessage,
    ProviderFailureKind,
    ProviderModelError,
)
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
)
from affordance_runtime.recovery import BoundedRecoveryPolicy, RecoveryAction, RecoveryDecision
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.source_assertions import SourceAssertionArbiter
from affordance_runtime.state_kernel import ProgressGuardReason, StateKernel
from affordance_runtime.task_intake import IntentDraft, OperationClass, RequestedEffect, TaskSpec, UserRequest
from affordance_runtime.task_pipeline import GeneralistTaskPipeline
from affordance_runtime.task_planning import (
    SubgoalSpec,
    TaskPlan,
    TaskPlanningContext,
    TaskPlanSource,
)
from affordance_runtime.trace import TraceDag


def _snapshot(sequence: int, *, saved: bool = False) -> BrowserSnapshot:
    environment_revision = f"environment-{sequence}"
    snapshot_id = f"snapshot-{sequence}"
    model = DomAdapter().transduce(
        "<main><button id='save'>Save</button></main>",
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
    )
    observation = Observation(
        environment_revision=environment_revision,
        snapshot_id=snapshot_id,
        page_revision=f"page-{sequence}",
        target_fingerprints={item.id: item.target_fingerprint for item in model.affordances},
        metadata={"saved": saved},
    )
    return BrowserSnapshot(observation, model)


class FakeObserver:
    def __init__(self) -> None:
        self.snapshots = [_snapshot(1), _snapshot(1), _snapshot(2, saved=True), _snapshot(3, saved=True)]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class SavePlanner:
    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        if state.receipts:
            return PlannerDecision(done=True, result={"saved": True}, reason="persisted state observed")
        contract = ActionContract.from_affordance(
            snapshot.affordance_model.affordances[0],
            intent="save settings",
            backend="fake",
            verifier_plan=[VerifierSpec("observation_metadata", "saved", True)],
        )
        return PlannerDecision(contract=contract, reason="save button available")


@dataclass
class FakeExecutor:
    backend: str = "fake"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract.id,
            self.backend,
            True,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            evidence={"dispatched": True},
        )


def test_coordinator_runs_pre_observe_act_post_observe_verify_loop(tmp_path) -> None:
    result = asyncio.run(
        RunCoordinator(
            observer=FakeObserver(),
            planner=SavePlanner(),
            executor=FakeExecutor(),
            artifacts=ArtifactStore(tmp_path / "artifacts"),
        ).run(TaskEnvelope("run-1", "save settings"))
    )

    assert result.status == RuntimeStep.DONE
    assert result.result == {"saved": True}
    assert result.verification is not None and result.verification.passed
    assert result.state.observation_count == 4
    event_types = [node.kind for node in result.trace.nodes]
    assert event_types.index("ActionCompleted") < event_types.index("PostActionObservationCaptured")
    assert (tmp_path / "artifacts/run-1/events.jsonl").exists()
    assert (tmp_path / "artifacts/run-1/run.json").exists()


def test_coordinator_continues_an_upstream_compiler_trace() -> None:
    trace = TraceDag("run-upstream")
    compiler_node = trace.add("TaskSpecCreated", {"task_revision": 1})

    result = RunCoordinator(
        observer=FakeObserver(),
        planner=SavePlanner(),
        executor=FakeExecutor(),
    ).run_sync(TaskEnvelope("run-upstream", "save settings"), trace)

    assert result.trace is trace
    task_node = next(node for node in trace.nodes if node.kind == "TaskCreated")
    assert task_node.parents == [compiler_node.id]


def test_coordinator_traces_source_assertion_decisions_and_targeted_perception() -> None:
    snapshot = _snapshot(1)
    assertions = (
        SourceAssertion(
            "visible-true",
            "semantic:save",
            "visible",
            True,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
            evidence_refs=("artifact:dom",),
        ),
        SourceAssertion(
            "visible-false",
            "semantic:save",
            "visible",
            False,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
            evidence_refs=("artifact:dom-second",),
        ),
    )
    arbitration = SourceAssertionArbiter().arbitrate(
        assertions,
        snapshot.observation,
        available_sources=frozenset({GroundingSource.DOM, GroundingSource.ACCESSIBILITY}),
        observation_budget=1,
    )

    class AssertionObserver:
        def __init__(self) -> None:
            self.targeted_calls = 0

        def capture(self) -> BrowserSnapshot:
            return replace(
                snapshot,
                source_assertions=assertions,
                assertion_decisions=arbitration.decisions,
                active_perception_requests=arbitration.active_perception_requests,
            )

        def capture_targeted(self, requests: object) -> BrowserSnapshot:
            assert requests == arbitration.active_perception_requests
            self.targeted_calls += 1
            return _snapshot(2)

    class FinishPlanner:
        def propose(
            self,
            envelope: TaskEnvelope,
            state: StateKernel,
            observed: BrowserSnapshot,
        ) -> PlannerDecision:
            del envelope, state, observed
            return PlannerDecision(done=True, result={"observed": True})

    observer = AssertionObserver()
    result = RunCoordinator(
        observer=observer,
        planner=FinishPlanner(),
        executor=FakeExecutor(),
    ).run_sync(TaskEnvelope("assertion-trace", "inspect save visibility"))

    events = [node.kind for node in result.trace.nodes]
    assert "SourceAssertionsCollected" in events
    assert "SourceAssertionsArbitrated" in events
    assert "TargetedPerceptionRequested" in events
    assert "TargetedPerceptionCaptured" in events
    assert observer.targeted_calls == 1
    assert result.state.active_perception_count == 1
    collected = next(node for node in result.trace.nodes if node.kind == "SourceAssertionsCollected")
    assert collected.payload["assertions"][0]["evidence_refs"] == ["artifact:dom"]
    assert "value" not in collected.payload["assertions"][0]


def test_coordinator_bounds_repeated_targeted_perception_requests() -> None:
    snapshot = _snapshot(1)
    assertions = (
        SourceAssertion(
            "checked-true",
            "semantic:save",
            "checked",
            True,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
        ),
        SourceAssertion(
            "checked-false",
            "semantic:save",
            "checked",
            False,
            "boolean",
            GroundingSource.DOM,
            snapshot.observation.snapshot_id,
            snapshot.observation.environment_revision,
            snapshot.observation.page_revision,
            "dom-parser-v1",
        ),
    )
    arbitration = SourceAssertionArbiter().arbitrate(assertions, snapshot.observation)
    unresolved = replace(
        snapshot,
        source_assertions=assertions,
        assertion_decisions=arbitration.decisions,
        active_perception_requests=arbitration.active_perception_requests,
    )

    class LoopingObserver:
        targeted_calls = 0

        def capture(self) -> BrowserSnapshot:
            return unresolved

        def capture_targeted(self, requests: object) -> BrowserSnapshot:
            assert requests == arbitration.active_perception_requests
            self.targeted_calls += 1
            return unresolved

    class FinishPlanner:
        def propose(
            self,
            envelope: TaskEnvelope,
            state: StateKernel,
            observed: BrowserSnapshot,
        ) -> PlannerDecision:
            del envelope, state, observed
            return PlannerDecision(done=True, result={"bounded": True})

    observer = LoopingObserver()
    result = RunCoordinator(
        observer=observer,
        planner=FinishPlanner(),
        executor=FakeExecutor(),
        budget=RunBudget(max_active_perception_observations=2),
    ).run_sync(TaskEnvelope("bounded-perception", "inspect checkbox"))

    assert observer.targeted_calls == 2
    assert result.state.active_perception_count == 2
    assert "TargetedPerceptionBudgetExhausted" in [node.kind for node in result.trace.nodes]


class DriftingObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(2),  # injected drift between planning and preflight
            _snapshot(3),
            _snapshot(3),
            _snapshot(4, saved=True),
            _snapshot(5, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


def test_coordinator_reobserves_drift_before_execution() -> None:
    executor = FakeExecutor()
    result = asyncio.run(
        RunCoordinator(observer=DriftingObserver(), planner=SavePlanner(), executor=executor).run(
            TaskEnvelope("run-drift", "save settings")
        )
    )

    assert result.status == RuntimeStep.DONE
    assert result.state.step_count == 1
    assert result.state.recovery_count == 1
    assert "EnvironmentDriftDetected" in [node.kind for node in result.trace.nodes]


class StableObserver:
    def capture(self) -> BrowserSnapshot:
        return _snapshot(1)


class TwoStageObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(3, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class ReplanObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1),
            _snapshot(1),
            _snapshot(2),
            _snapshot(2),
            _snapshot(2),
            _snapshot(3, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class TwoStageTaskPlanner:
    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        task_spec = context.task_spec
        return TaskPlan(
            plan_id="plan-two-stage",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            plan_version=1,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="write",
                    objective="Write settings",
                    success_criteria=("settings are saved",),
                    evidence_requirements=("saved observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                ),
                SubgoalSpec(
                    subgoal_id="confirm",
                    objective="Confirm settings",
                    depends_on=("write",),
                    success_criteria=("settings are saved",),
                    evidence_requirements=("saved observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                ),
            ),
        )


class AsyncTwoStageTaskPlanner(TwoStageTaskPlanner):
    async def plan(self, context: TaskPlanningContext) -> TaskPlan:
        return super().plan(context)


class SubgoalAwarePlanner:
    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        active_objective = state.active_subgoal()
        active_id = state.plan_progress.active_subgoal_id if state.plan_progress else ""
        return PlannerDecision(
            contract=ActionContract.from_affordance(
                snapshot.affordance_model.affordances[0],
                intent=active_objective,
                backend="fake",
                verifier_plan=[
                    VerifierSpec(
                        "observation_metadata",
                        "saved",
                        True,
                        criterion_ids=(criterion_id("subgoal", active_id, 0),),
                        requirement_ids=(evidence_requirement_id("subgoal", active_id, 0),),
                    )
                ],
            )
        )


def test_coordinator_advances_serial_task_plan_only_after_verifier_evidence() -> None:
    result = RunCoordinator(
        observer=TwoStageObserver(),
        planner=SubgoalAwarePlanner(),
        executor=FakeExecutor(),
        task_planner=AsyncTwoStageTaskPlanner(),
    ).run_sync(TaskEnvelope(task_spec=_semantic_task()))

    assert result.status == RuntimeStep.DONE
    assert result.state.plan_progress is not None
    assert result.state.plan_progress.completed_subgoal_ids == ["write", "confirm"]
    assert result.result["task_plan_id"] == "plan-two-stage"
    events = [node.kind for node in result.trace.nodes]
    assert events.count("SubgoalCompleted") == 2
    assert events.index("TaskPlanAccepted") < events.index("SubgoalCompleted")
    completed = [node for node in result.trace.nodes if node.kind == "SubgoalCompleted"]
    assert all(node.payload["criterion_evidence_links"] for node in completed)


class EarlyFinishPlanner:
    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope, state, snapshot
        return PlannerDecision(done=True, result={"unverified": True})


def test_task_plan_rejects_planner_finish_without_verifier_backed_progress() -> None:
    result = RunCoordinator(
        observer=FakeObserver(),
        planner=EarlyFinishPlanner(),
        executor=FakeExecutor(),
        task_planner=TwoStageTaskPlanner(),
    ).run_sync(TaskEnvelope(task_spec=_semantic_task()))

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.PLANNER_PROPOSAL_REJECTED
    assert result.state.plan_progress is not None
    assert result.state.plan_progress.completed_subgoal_ids == []


class ReplanningTaskPlanner:
    def __init__(self) -> None:
        self.calls = 0
        self.contexts: list[TaskPlanningContext] = []

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        self.calls += 1
        self.contexts.append(context)
        task_spec = context.task_spec
        return TaskPlan(
            plan_id=f"plan-replanned-{self.calls}",
            task_id=task_spec.task_id,
            task_revision=task_spec.revision,
            plan_version=self.calls,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(
                SubgoalSpec(
                    subgoal_id="write",
                    objective="Write settings",
                    success_criteria=("settings are saved",),
                    evidence_requirements=("saved observation",),
                    operation_class=OperationClass.REVERSIBLE_WRITE,
                    max_actions=2 if context.failures else 1,
                ),
            ),
        )


def test_coordinator_replans_only_after_active_subgoal_action_budget_is_exhausted() -> None:
    planner = ReplanningTaskPlanner()
    result = RunCoordinator(
        observer=ReplanObserver(),
        planner=SubgoalAwarePlanner(),
        executor=FakeExecutor(),
        task_planner=planner,
        recovery=BoundedRecoveryPolicy(
            decision_override=lambda contract, receipt, context, error: RecoveryDecision(
                RecoveryAction.REOBSERVE, "test local recovery"
            )
        ),
    ).run_sync(TaskEnvelope(task_spec=_semantic_task()))

    assert result.status == RuntimeStep.DONE
    assert planner.calls == 2
    assert result.state.plan_progress is not None
    assert result.state.plan_progress.task_replan_count == 1
    assert "TaskReplanned" in [node.kind for node in result.trace.nodes]
    initial, replacement = planner.contexts
    assert initial.reason == "initial"
    assert initial.environment.affordances[0].label == "Save"
    assert initial.current_plan_version == 0
    assert replacement.reason == "subgoal_action_budget_exhausted"
    assert replacement.current_plan_id == "plan-replanned-1"
    assert replacement.current_plan_version == 1
    assert replacement.failures[0].error_code == "failed"
    assert replacement.recovery_summary
    assert replacement.remaining_budget.steps_remaining < initial.remaining_budget.steps_remaining
    replanned = next(node for node in result.trace.nodes if node.kind == "TaskReplanned")
    assert replanned.payload["supersedes_plan_id"] == "plan-replanned-1"


class EvidencePreservingObserver:
    def __init__(self) -> None:
        self.snapshots = [
            _snapshot(1, saved=True),
            _snapshot(1, saved=True),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(2, saved=True),
            _snapshot(3, saved=True),
            _snapshot(3, saved=True),
            _snapshot(3, saved=True),
            _snapshot(4, saved=True),
        ]

    def capture(self) -> BrowserSnapshot:
        return self.snapshots.pop(0)


class EvidenceAwareTaskPlanner:
    def __init__(self) -> None:
        self.contexts: list[TaskPlanningContext] = []

    def plan(self, context: TaskPlanningContext) -> TaskPlan:
        self.contexts.append(context)
        task = context.task_spec
        discovered = any(
            item.subgoal_id == "discover" and item.evidence_ids for item in context.criteria_evidence_ledger
        )
        discover = SubgoalSpec(
            subgoal_id="discover",
            objective="Discover saved state",
            success_criteria=("saved state is observed",),
            evidence_requirements=("independent saved observation",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
        )
        apply = SubgoalSpec(
            subgoal_id="apply",
            objective=(
                "Apply using verified saved-state evidence" if discovered else "Apply using the initial assumption"
            ),
            depends_on=("discover",),
            success_criteria=("settings are saved",),
            evidence_requirements=("independent saved observation",),
            operation_class=OperationClass.REVERSIBLE_WRITE,
            max_actions=1,
        )
        return TaskPlan(
            plan_id=f"evidence-plan-{context.current_plan_version + 1}",
            task_id=task.task_id,
            task_revision=task.revision,
            plan_version=context.current_plan_version + 1,
            supersedes_plan_id=context.current_plan_id,
            based_on_state_version=context.state_version,
            generated_by=TaskPlanSource.RULE,
            subgoals=(discover, apply),
            assumptions=("the initial apply route is sufficient",),
        )


class EvidenceAwareActionPlanner:
    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope
        state.active_subgoal()
        active_id = state.plan_progress.active_subgoal_id if state.plan_progress else ""
        plan_version = state.task_plan.plan_version if state.task_plan else 0
        bound_id = active_id if active_id == "discover" or plan_version >= 2 else "unrelated"
        return PlannerDecision(
            contract=ActionContract.from_affordance(
                snapshot.affordance_model.affordances[0],
                intent=state.active_subgoal(),
                backend="fake",
                verifier_plan=[
                    VerifierSpec(
                        "observation_metadata",
                        "saved",
                        True,
                        criterion_ids=(criterion_id("subgoal", bound_id, 0),),
                        requirement_ids=(evidence_requirement_id("subgoal", bound_id, 0),),
                    )
                ],
            )
        )


def test_replan_uses_verified_evidence_and_preserves_progress_across_versions() -> None:
    task_planner = EvidenceAwareTaskPlanner()
    result = RunCoordinator(
        observer=EvidencePreservingObserver(),
        planner=EvidenceAwareActionPlanner(),
        executor=FakeExecutor(),
        task_planner=task_planner,
    ).run_sync(TaskEnvelope(task_spec=_semantic_task()))

    assert result.status == RuntimeStep.DONE
    assert result.state.task_plan is not None
    assert result.state.task_plan.plan_version == 2
    assert result.state.task_plan.supersedes_plan_id == "evidence-plan-1"
    assert result.state.task_plan.subgoals[1].objective == "Apply using verified saved-state evidence"
    assert result.state.plan_progress is not None
    assert result.state.plan_progress.completed_subgoal_ids == ["discover", "apply"]
    assert len(task_planner.contexts) == 2
    replacement_context = task_planner.contexts[1]
    assert replacement_context.criteria_evidence_ledger[0].subgoal_id == "discover"
    assert replacement_context.criteria_evidence_ledger[0].evidence_ids
    assert replacement_context.failures[0].error_code == "subgoal_action_budget_exhausted"
    replanned = next(node for node in result.trace.nodes if node.kind == "TaskReplanned")
    assert replanned.payload["planning_context"]["criteria_evidence_ledger"]


class RepeatingPlanner:
    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope, state
        contract = ActionContract.from_affordance(
            snapshot.affordance_model.affordances[0],
            intent="repeat save",
            backend="fake",
        )
        return PlannerDecision(contract=replace(contract, idempotency_key="repeat-save:1", contract_hash=""))


@dataclass
class AlwaysFailExecutor:
    backend: str = "fake"

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        return ExecutionReceipt(
            contract.id,
            self.backend,
            False,
            observation.environment_revision,
            observation.environment_revision,
            1.0,
            error_code=RuntimeErrorCode.EXECUTION_FAILED,
            message="Timeout 1000 while saving record 42",
        )


def test_coordinator_groups_repeated_failure_and_aborts_loop() -> None:
    result = asyncio.run(
        RunCoordinator(observer=StableObserver(), planner=RepeatingPlanner(), executor=AlwaysFailExecutor()).run(
            TaskEnvelope("run-loop", "repeat save")
        )
    )

    assert result.status == RuntimeStep.FAILED
    assert result.state.recovery_incident is not None
    assert result.state.recovery_incident.root_failure.normalized_error == "timeout <n> while saving record <n>"
    assert len(result.state.recovery_incident.symptom_chain) == 1
    assert result.state.recovery_diagnostics["cascade_depth"] == 2
    assert result.state.recovery_diagnostics["loop_aborts"] == 1
    assert "repeated_signature" in result.state.recovery_diagnostics["findings"]


@dataclass
class AsyncSemanticSavePlanner:
    revision: int = 1

    async def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        if state.receipts:
            return PlannerDecision(
                proposal=PlannerProposal(
                    proposal_id="proposal-finish",
                    based_on_task_revision=self.revision,
                    based_on_state_version=state.version,
                    snapshot_id=snapshot.observation.snapshot_id,
                    action_kind=PlannerActionKind.FINISH,
                    done=True,
                    result={"saved": True},
                )
            )
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id="proposal-save",
                based_on_task_revision=self.revision,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal="Save settings",
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=snapshot.affordance_model.affordances[0].id,
                expected_effects=("settings are saved",),
                evidence_requirements=("saved observation",),
            )
        )


def _semantic_task() -> TaskSpec:
    return TaskSpec(
        task_id="semantic-run",
        revision=1,
        objective="Save settings",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("settings",),
        success_criteria=("settings are saved",),
        evidence_requirements=("saved observation",),
        requested_capabilities=("settings.write",),
        source_request_ref="semantic-request",
    )


def test_coordinator_awaits_semantic_planner_and_builds_contract() -> None:
    task = _semantic_task()
    result = asyncio.run(
        RunCoordinator(
            observer=FakeObserver(),
            planner=AsyncSemanticSavePlanner(),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(
                requirements={
                    "dom_button_1": ContractRequirements(
                        verifier_plan=(VerifierSpec("observation_metadata", "saved", True),),
                        required_capabilities=("settings.write",),
                        idempotency_key="semantic-save-v1",
                        compensation="restore settings",
                    )
                }
            ),
        ).run(TaskEnvelope(task_spec=task, capabilities=["settings.write"]))
    )

    assert result.status == RuntimeStep.DONE
    assert result.result == {"saved": True}
    events = [node.kind for node in result.trace.nodes]
    assert events.count("PlannerProposalProduced") == 2
    contract_event = next(node for node in result.trace.nodes if node.kind == "ContractBuilt")
    assert contract_event.payload["proposal_id"] == "proposal-save"


@dataclass
class RepeatingSemanticPlanner:
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        if state.progress_guard_events:
            return PlannerDecision(done=True, result={"guarded": True})
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id=f"proposal-repeat-{len(state.planner_history)}",
                based_on_task_revision=1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                action_kind=PlannerActionKind.ACTIVATE,
                target_affordance_id=snapshot.affordance_model.affordances[0].id,
                expected_effects=("settings are saved",),
                evidence_requirements=("saved observation",),
            )
        )


class StableSavedObserver:
    def __init__(self, *, saved: bool) -> None:
        self.saved = saved

    def capture(self) -> BrowserSnapshot:
        return _snapshot(1, saved=self.saved)


@dataclass
class CountingExecutor(FakeExecutor):
    calls: int = 0

    def execute(self, contract: ActionContract, observation: Observation) -> ExecutionReceipt:
        self.calls += 1
        return super().execute(contract, observation)


def _semantic_guard_builder() -> ContractBuilder:
    return ContractBuilder(
        requirements={
            "dom_button_1": ContractRequirements(
                verifier_plan=(VerifierSpec("observation_metadata", "saved", True),),
                required_capabilities=("settings.write",),
                idempotency_key="semantic-repeat-v1",
            )
        }
    )


def test_progress_guard_blocks_already_verified_semantic_action() -> None:
    executor = CountingExecutor()
    result = RunCoordinator(
        observer=StableSavedObserver(saved=True),
        planner=RepeatingSemanticPlanner(),
        executor=executor,
        contract_builder=_semantic_guard_builder(),
    ).run_sync(TaskEnvelope(task_spec=_semantic_task(), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert executor.calls == 1
    assert result.state.progress_guard_events[-1]["reason"] == "effect_already_satisfied"
    blocked = [node for node in result.trace.nodes if node.kind == "PlannerProgressBlocked"]
    assert blocked[-1].payload["error_code"] == RuntimeErrorCode.EFFECT_ALREADY_SATISFIED.value


def test_progress_guard_blocks_failed_action_when_state_did_not_change() -> None:
    executor = CountingExecutor()
    result = RunCoordinator(
        observer=StableSavedObserver(saved=False),
        planner=RepeatingSemanticPlanner(),
        executor=executor,
        contract_builder=_semantic_guard_builder(),
        recovery=BoundedRecoveryPolicy(
            decision_override=lambda contract, receipt, context, error: RecoveryDecision(
                RecoveryAction.REOBSERVE, "replan after failed verification"
            )
        ),
    ).run_sync(TaskEnvelope(task_spec=_semantic_task(), capabilities=["settings.write"]))

    assert result.status == RuntimeStep.DONE
    assert executor.calls == 1
    assert result.state.progress_guard_events[-1]["reason"] == "no_progress_repeat"
    blocked = [node for node in result.trace.nodes if node.kind == "PlannerProgressBlocked"]
    assert blocked[-1].payload["error_code"] == RuntimeErrorCode.NO_PROGRESS_REPEAT.value


def test_progress_guard_allows_repeated_verified_delta_until_effect_is_satisfied() -> None:
    state = StateKernel("slider", "move slider several steps")
    state.remember_observation(Observation("rev-2"))
    state.record_action_progress(
        "press:slider:ArrowRight",
        "rev-2",
        verification_passed=True,
        effect_satisfied=False,
    )

    assert state.check_progress_guard("press:slider:ArrowRight") is None


def test_progress_guard_blocks_an_alternating_return_to_a_satisfied_effect() -> None:
    state = StateKernel("task-1", "Select controls")
    state.remember_observation(Observation("rev-3", page_revision="page-1"))
    state.record_action_progress(
        "activate:checkbox-a",
        "rev-1",
        verification_passed=True,
        effect_satisfied=True,
        post_page_revision="page-1",
    )
    state.record_action_progress(
        "activate:checkbox-b",
        "rev-2",
        verification_passed=True,
        effect_satisfied=True,
        post_page_revision="page-1",
    )

    assert state.check_progress_guard("activate:checkbox-a") == ProgressGuardReason.EFFECT_ALREADY_SATISFIED


T = TypeVar("T", bound=BaseModel)


@dataclass
class _PipelineIntentModel:
    provider: str = "fixed"
    model: str = "fixed"
    endpoint_class: str = "test"
    last_call: ModelCallRecord | None = None

    async def generate_structured(
        self,
        messages: Sequence[ModelMessage],
        output_schema: type[T],
        config: ModelConfig,
    ) -> T:
        del messages, config
        return output_schema.model_validate(
            IntentDraft(
                objective="Save settings",
                requested_effects=(
                    RequestedEffect(
                        operation_class=OperationClass.REVERSIBLE_WRITE,
                        target="settings",
                        capability="settings.write",
                        source_ref="pipeline-run",
                    ),
                ),
                candidate_success_criteria=("settings are saved",),
                candidate_evidence_requirements=("saved observation",),
            ).model_dump()
        )


def test_raw_request_pipeline_preserves_compiler_to_contract_lineage() -> None:
    pipeline = GeneralistTaskPipeline(
        compiler=LLMIntentCompiler(_PipelineIntentModel()),
        coordinator=RunCoordinator(
            observer=FakeObserver(),
            planner=AsyncSemanticSavePlanner(),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(
                requirements={
                    "dom_button_1": ContractRequirements(
                        verifier_plan=(VerifierSpec("observation_metadata", "saved", True),),
                        required_capabilities=("settings.write",),
                        idempotency_key="semantic-save-v1",
                        compensation="restore settings",
                    )
                }
            ),
        ),
        granted_capabilities=("settings.write", "admin.unrequested"),
    )

    result = asyncio.run(pipeline.run(UserRequest(request_id="pipeline-run", raw_text="Save my settings")))

    assert result.status == "done"
    assert result.coordinator is not None
    assert [node.kind for node in result.trace.nodes][:4] == [
        "UserRequestReceived",
        "IntentDraftProduced",
        "TaskSpecCreated",
        "TaskCreated",
    ]
    assert "PlannerProposalProduced" in [node.kind for node in result.trace.nodes]
    assert "ContractBuilt" in [node.kind for node in result.trace.nodes]


def test_async_planner_resolution_works_inside_an_existing_event_loop() -> None:
    async def decide() -> PlannerDecision:
        return PlannerDecision(done=True, result={"ok": True})

    async def outer() -> PlannerDecision:
        return _resolve_planner_decision(decide())

    assert asyncio.run(outer()).result == {"ok": True}


def test_coordinator_rejects_stale_task_revision_before_execution() -> None:
    task = _semantic_task()
    result = asyncio.run(
        RunCoordinator(
            observer=StableObserver(),
            planner=AsyncSemanticSavePlanner(revision=2),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(),
        ).run(TaskEnvelope(task_spec=task))
    )

    assert result.status == RuntimeStep.ABORTED
    assert result.error_code == RuntimeErrorCode.STALE_TASK_REVISION
    assert "PlannerProposalRejected" in [node.kind for node in result.trace.nodes]
    assert result.state.receipts == []


class ClarifyingPlanner(AsyncSemanticSavePlanner):
    async def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        del envelope
        return PlannerDecision(
            proposal=PlannerProposal(
                proposal_id="proposal-clarify",
                based_on_task_revision=1,
                based_on_state_version=state.version,
                snapshot_id=snapshot.observation.snapshot_id,
                subgoal="Which settings profile should be changed?",
                action_kind=PlannerActionKind.ASK_USER,
                requires_clarification=True,
                uncertainty=1.0,
            )
        )


def test_semantic_planner_can_request_clarification_without_contract_or_effect() -> None:
    result = asyncio.run(
        RunCoordinator(
            observer=StableObserver(),
            planner=ClarifyingPlanner(),
            executor=FakeExecutor(),
            contract_builder=ContractBuilder(),
        ).run(TaskEnvelope(task_spec=_semantic_task()))
    )

    assert result.status == RuntimeStep.WAITING_CLARIFICATION
    assert result.state.receipts == []
    assert result.result["clarification"] == "Which settings profile should be changed?"
    assert "ClarificationRequested" in [node.kind for node in result.trace.nodes]


class QuotaExhaustedPlanner:
    def propose(self, envelope: TaskEnvelope, state: StateKernel, snapshot: BrowserSnapshot) -> PlannerDecision:
        del envelope, state, snapshot
        raise ProviderModelError(ProviderFailureKind.QUOTA_EXHAUSTED, retry_after_s=60)


def test_coordinator_checkpoints_typed_provider_failure_as_resumable_deferral(tmp_path) -> None:
    result = RunCoordinator(
        observer=StableObserver(),
        planner=QuotaExhaustedPlanner(),
        executor=FakeExecutor(),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
    ).run_sync(TaskEnvelope("provider-defer", "wait for provider capacity"))

    assert result.status == RuntimeStep.DEFERRED
    assert result.error_code == RuntimeErrorCode.QUOTA_EXHAUSTED
    assert result.result == {
        "deferred": True,
        "provider_failure": "quota_exhausted",
        "retry_after_s": 60,
        "resumable": True,
    }
    event = next(node for node in result.trace.nodes if node.kind == "PlannerDeferred")
    assert event.payload["resumable"] is True
    assert (tmp_path / "artifacts/provider-defer/run.json").exists()
