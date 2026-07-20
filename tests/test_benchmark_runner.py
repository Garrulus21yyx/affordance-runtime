import json

from affordance_runtime.benchmarks.metrics import MetricReport
from affordance_runtime.benchmarks.runner import (
    REQUIRED_VARIANTS,
    BenchmarkReport,
    BenchmarkReportWriter,
    BenchmarkRunner,
    release_acceptance_errors,
)
from affordance_runtime.benchmarks.spec import BenchmarkRun, BenchmarkTask


def test_benchmark_runner_builds_all_variants_and_report_formats(tmp_path) -> None:
    task = BenchmarkTask("fixture", "pricing", "http://fixture/pricing", "extract")

    def run_case(item: BenchmarkTask, variant: str, seed: int) -> BenchmarkRun:
        return BenchmarkRun(item.task_id, variant == "full_runtime", 1, 10.0, variant=variant, seed=seed)

    report = BenchmarkRunner([task], run_case, variants=("direct_playwright", "full_runtime"), seeds=(1, 2)).run()
    paths = BenchmarkReportWriter(tmp_path).write(report)

    assert len(report.runs) == 4
    assert set(paths) == {"json", "markdown", "csv", "manifest", "versioned_json", "versioned_markdown"}
    assert json.loads(paths["json"].read_text())["suite_version"] == "local-saas-v1"
    assert "| full_runtime |" in paths["markdown"].read_text()


def test_release_gate_requires_full_runtime_thresholds_and_ablation_signals() -> None:
    full = {
        "task_success_rate": 1.0,
        "constraint_violation_rate": 0.0,
        "unsafe_side_effect_rate": 0.0,
        "verifier_false_accept_rate": 0.0,
        "stale_detection_recall": 1.0,
        "recovery_success_rate": 1.0,
    }
    metrics = {variant: MetricReport(dict(full)) for variant in REQUIRED_VARIANTS}
    metrics["no_preflight"].values["stale_detection_recall"] = 0.0
    metrics["no_structural_verifier"].values["verifier_false_accept_rate"] = 1.0
    metrics["no_capability_gate"].values["unsafe_side_effect_rate"] = 1.0
    metrics["no_recovery"].values["task_success_rate"] = 0.5
    report = BenchmarkReport("suite", [], metrics)

    assert release_acceptance_errors(report) == []
    metrics["full_runtime"].values["unsafe_side_effect_rate"] = 0.1
    assert "unsafe_side_effect_rate" in " ".join(release_acceptance_errors(report))
