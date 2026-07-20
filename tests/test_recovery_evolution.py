import json

from affordance_runtime.evolution import EvolutionStatus
from affordance_runtime.recovery_evolution import run_recovery_cascade_evolution


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
