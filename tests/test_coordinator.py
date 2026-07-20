import asyncio
from dataclasses import dataclass, replace

from affordance_runtime.adapters.dom import DomAdapter
from affordance_runtime.artifacts import ArtifactStore
from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation, RuntimeErrorCode, VerifierSpec
from affordance_runtime.coordinator import PlannerDecision, RunCoordinator
from affordance_runtime.runtime import RuntimeStep, TaskEnvelope
from affordance_runtime.state_kernel import StateKernel


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
