import asyncio
from dataclasses import dataclass, replace

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.planning import (
    ContractBuilder,
    ContractRequirements,
    PlannerActionKind,
    PlannerProposal,
)
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec
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
