import json
from dataclasses import asdict

from affordance_runtime.benchmarks.spec import BenchmarkRun
from affordance_runtime.evolution import EvolutionStatus
from affordance_runtime.evolution_replay import ExecutedReplay, build_evolution_report


def test_real_failure_becomes_regression_gated_evolution_artifact(tmp_path) -> None:
    runs = [
        BenchmarkRun(
            "reversible_settings_update",
            False,
            2,
            10.0,
            verifier_false_accepts=1,
            failed_outcomes=1,
            variant="no_structural_verifier",
            trace_path="failed/events.jsonl",
        ),
        BenchmarkRun(
            "reversible_settings_update",
            True,
            3,
            12.0,
            variant="full_runtime",
            seed=0,
            side_effect_opportunities=1,
            trace_path="candidate/settings.jsonl",
        ),
        BenchmarkRun(
            "read_only_evidence_chain",
            True,
            2,
            8.0,
            variant="full_runtime",
            seed=0,
            trace_path="candidate/pricing.jsonl",
        ),
        BenchmarkRun(
            "export_with_approval",
            True,
            1,
            9.0,
            variant="full_runtime",
            seed=0,
            side_effect_opportunities=1,
            trace_path="candidate/export.jsonl",
        ),
    ]
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(json.dumps({"suite_version": "suite-v1", "runs": [asdict(run) for run in runs]}))

    full_runs = {run.task_id: run for run in runs if run.variant == "full_runtime"}

    def replay(requests, artifact, output_dir):
        del artifact, output_dir
        return [ExecutedReplay(request.category, full_runs[request.task_id]) for request in requests]

    report = build_evolution_report(benchmark, tmp_path / "evolution", replay_runner=replay)

    assert report.decision == EvolutionStatus.ACCEPTED
    assert report.artifact.artifact_type == "verifier_patch"
    assert {item.category for item in report.replay_evidence} >= {
        "original",
        "task_family",
        "global_smoke",
        "safety_smoke",
    }
    assert (tmp_path / "evolution/evolution-report.json").exists()
    assert report.rollback_verified
    assert report.artifact.payload["feature_overrides"] == {"structural_verification": True}
    assert "Decision: `accepted`" in (tmp_path / "evolution/evolution-report.md").read_text()
    assert (tmp_path / "evolution/registry.json").exists()
    assert (tmp_path / "evolution/rollback-proof.json").exists()
