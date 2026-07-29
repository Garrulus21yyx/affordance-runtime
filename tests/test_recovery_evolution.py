import json
from dataclasses import dataclass

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.evolution import EvolutionStatus
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.recovery_evolution import RecoveryFixturePlanner, _snapshot, run_recovery_cascade_evolution
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import OperationClass, TaskSpec


def test_recovery_fixture_planner_builds_request_when_task_spec_is_available() -> None:
    snapshot = _snapshot()
    state = StateKernel("recovery-request", "exercise bounded recovery")
    state.transition("observing")
    state.remember_observation(snapshot.observation)
    state.transition("planning")
    task = TaskSpec(
        task_id="recovery-request",
        revision=1,
        objective="exercise bounded recovery",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        targets=("Save",),
        success_criteria=("effect verified",),
        evidence_requirements=("receipt evidence",),
        source_request_ref="recovery-request-source",
    )

    @dataclass
    class RecordingRequestBuilder:
        inner: PlanningRequestBuilder = PlanningRequestBuilder()
        built: PlanningRequest | None = None

        def build(
            self,
            envelope: TaskEnvelope,
            state: StateKernel,
            snapshot: BrowserSnapshot,
        ) -> PlanningRequest:
            self.built = self.inner.build(envelope, state, snapshot)
            return self.built

    request_builder = RecordingRequestBuilder()

    decision = RecoveryFixturePlanner(
        idempotent=True,
        planning_request_builder=request_builder,
    ).propose(TaskEnvelope(task_spec=task), state, snapshot)

    assert request_builder.built is not None
    assert decision.contract is not None
    assert decision.contract.idempotency_key == "recovery-fixture:save"


def test_repeated_recovery_failure_evolves_persists_and_rolls_back(tmp_path) -> None:
    report = run_recovery_cascade_evolution(tmp_path)

    assert report.quarantined_before_replay
    assert report.decision == EvolutionStatus.ACCEPTED
    assert report.rollback_verified
    assert len(report.source_incident["attempts"]) == 2
    assert len(report.source_incident["symptom_chain"]) == 1
    evidence = {item.category: item for item in report.replays}
    assert evidence["original"].cascade_depth == 1
    assert evidence["task_family"].cascade_depth == 1
    assert evidence["global_smoke"].runtime_status == "done"
    assert "retry" not in evidence["safety_smoke"].recovery_actions
    assert evidence["safety_smoke"].duplicate_effect_risks == 0
    assert all(item.passed for item in report.replays)

    registry = json.loads((tmp_path / "registry.json").read_text())
    assert registry["artifacts"][report.artifact.id]["status"] == "accepted"
    quarantine = json.loads((tmp_path / "quarantined-registry.json").read_text())
    assert quarantine["artifacts"][report.artifact.id]["status"] == "quarantined"
    rollback = json.loads((tmp_path / "rollback-proof.json").read_text())
    assert rollback["patched_abort"]
    assert rollback["runtime_restored_retry"]
    assert rollback["rolled_back_load_rejected"]
    assert (tmp_path / "rolled-back-registry.json").exists()
