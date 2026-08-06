import json

import pytest

from affordance_runtime.evolution import EvolutionArtifact, EvolutionArtifactType, EvolutionStatus
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.recovery_evolution import (
    RecoveryEvolutionReport,
    RecoveryFixturePlanner,
    RecoveryReplayEvidence,
    _snapshot,
    run_recovery_cascade_evolution,
)
from affordance_runtime.runtime import legacy_run_request
from affordance_runtime.state_kernel import StateKernel
from affordance_runtime.task_intake import (
    OperationClass,
    TaskSpec,
    canonical_effect_requirement_refs,
    canonical_effect_requirements,
)
from affordance_runtime.verification.contracts import SuccessExpression
from runtime_test_support import canonical_observation, remember_observation


def test_recovery_fixture_planner_consumes_canonical_request() -> None:
    snapshot = _snapshot()
    state = StateKernel("recovery-request", "exercise bounded recovery")
    state.transition("observing")
    remember_observation(state, snapshot.observation)
    state.transition("planning")
    task = TaskSpec(
        task_id="recovery-request",
        revision=1,
        objective="exercise bounded recovery",
        operation_class=OperationClass.REVERSIBLE_WRITE,
        requirements=canonical_effect_requirements(
            ("Save",), OperationClass.REVERSIBLE_WRITE, "recovery-request-source", ()
        ),
        allowed_effect_refs=canonical_effect_requirement_refs(("Save",)),
        success=SuccessExpression(
            expression_id="success:save",
            operator="criterion",
            criterion_id="criterion:save",
            requirement_refs=("requirement:effect:1",),
        ),
        source_request_ref="recovery-request-source",
    )

    request = PlanningRequestBuilder().build(legacy_run_request(task_spec=task), state, canonical_observation(snapshot))
    response = RecoveryFixturePlanner(idempotent=True).propose(request)

    assert response.proposal.target_affordance_id == "dom_button_1"


def test_recovery_evolution_report_payloads_are_immutable_from_source_collections() -> None:
    actions = ["reobserve"]
    evidence = RecoveryReplayEvidence(
        category="original",
        task_id="task",
        runtime_status="done",
        cascade_depth=1,
        recovery_actions=actions,
        loop_aborts=0,
        duplicate_effect_risks=0,
        unsafe_side_effects=0,
        passed=True,
        trace_path="trace.jsonl",
    )
    source_incident = {"attempts": [{"action": "reobserve"}]}
    report = RecoveryEvolutionReport(
        source_incident=source_incident,
        artifact=EvolutionArtifact(
            id="artifact-1",
            artifact_type=EvolutionArtifactType.POLICY_PATCH,
            summary="safe recovery",
            applicability={},
            source_traces=(),
        ),
        replays=[evidence],
        decision=EvolutionStatus.ACCEPTED,
        quarantined_before_replay=True,
        fresh_candidate_id="artifact-1",
        registry_path="registry.json",
        quarantine_registry_path="quarantine.json",
        rollback_proof_path="rollback.json",
        rollback_verified=True,
    )
    actions.append("retry")
    source_incident["attempts"][0]["action"] = "mutated"

    assert evidence.recovery_actions == ("reobserve",)
    assert report.source_incident == {"attempts": [{"action": "reobserve"}]}
    assert report.replays == (evidence,)
    with pytest.raises(TypeError):
        report.source_incident["attempts"][0]["action"] = "mutated"  # type: ignore[index]


def test_repeated_recovery_failure_evolves_persists_and_rolls_back(tmp_path) -> None:
    report = run_recovery_cascade_evolution(tmp_path)

    assert report.quarantined_before_replay
    assert report.decision == EvolutionStatus.QUARANTINED
    assert report.rollback_verified
    assert report.source_incident["error_code"] == "execution_failed"
    assert report.source_incident["phase"] == "execution_not_dispatched"
    evidence = {item.category: item for item in report.replays}
    assert evidence["original"].cascade_depth >= 1
    assert evidence["task_family"].cascade_depth >= 1
    assert evidence["global_smoke"].runtime_status == "done"
    assert "retry" not in evidence["safety_smoke"].recovery_actions
    assert evidence["safety_smoke"].duplicate_effect_risks == 0
    assert all(item.passed for item in report.replays)
    assert report.artifact.regression_results["candidate_cascade_depth"] <= 1.0

    registry = json.loads((tmp_path / "registry.json").read_text())
    assert registry["artifacts"][report.artifact.id]["status"] == "quarantined"
    quarantine = json.loads((tmp_path / "quarantined-registry.json").read_text())
    assert quarantine["artifacts"][report.artifact.id]["status"] == "quarantined"
    assert not (tmp_path / "rollback-proof.json").exists()
