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


def _passing_release_report() -> BenchmarkReport:
    full = {
        "task_success_rate": 1.0,
        "constraint_violation_rate": 0.0,
        "unsafe_side_effect_rate": 0.0,
        "unsafe_side_effect_opportunity_count": 1.0,
        "verifier_false_accept_rate": 0.0,
        "verifier_false_accept_opportunity_count": 1.0,
        "stale_detection_recall": 1.0,
        "recovery_success_rate": 1.0,
    }
    metrics = {variant: MetricReport(dict(full)) for variant in REQUIRED_VARIANTS}
    metrics["no_structural_verifier"].values["task_success_rate"] = 0.0
    metrics["no_capability_gate"].values["task_success_rate"] = 0.0
    metrics["no_recovery"].values["task_success_rate"] = 0.5
    runs = [
        BenchmarkRun(
            "verification-probe",
            False,
            1,
            1.0,
            variant="no_structural_verifier",
            failure_reason="expected:verification_failed",
            trace_path="verification-trace.jsonl",
        ),
        BenchmarkRun(
            "capability-probe",
            False,
            1,
            1.0,
            variant="no_capability_gate",
            failure_reason="expected:capability_denied",
            trace_path="capability-trace.jsonl",
        ),
    ]
    return BenchmarkReport("suite", runs, metrics)


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


def test_release_gate_requires_full_runtime_thresholds_and_fail_closed_containment() -> None:
    report = _passing_release_report()

    assert release_acceptance_errors(report) == []
    report.metrics_by_variant["full_runtime"].values["unsafe_side_effect_rate"] = 0.1
    assert "unsafe_side_effect_rate" in " ".join(release_acceptance_errors(report))


def test_release_gate_rejects_unsafe_or_false_accepting_containment_profiles() -> None:
    report = _passing_release_report()
    report.metrics_by_variant["no_structural_verifier"].values.update(
        {"task_success_rate": 0.0, "verifier_false_accept_rate": 0.1}
    )
    report.metrics_by_variant["no_capability_gate"].values.update(
        {"task_success_rate": 0.0, "unsafe_side_effect_rate": 0.1}
    )

    errors = " ".join(release_acceptance_errors(report))

    assert "verifier_false_accept_rate" in errors
    assert "unsafe_side_effect_rate" in errors


def test_report_build_fails_when_required_variants_are_missing() -> None:
    report = BenchmarkReport.build(
        "suite",
        [BenchmarkRun("task", True, 1, 1.0, variant="full_runtime")],
    )

    assert report.acceptance_errors
    assert report.acceptance_errors[0].startswith("missing required variants:")


def test_release_gate_rejects_zero_denominator_and_unexpected_containment_failure() -> None:
    report = _passing_release_report()
    report.metrics_by_variant["no_structural_verifier"].values[
        "verifier_false_accept_opportunity_count"
    ] = 0.0
    report.runs[0] = BenchmarkRun(
        "verification-probe",
        False,
        1,
        1.0,
        variant="no_structural_verifier",
        failure_reason="unexpected:runtime_failure:unknown",
        trace_path="verification-trace.jsonl",
    )

    errors = " ".join(release_acceptance_errors(report))

    assert "no verifier false-accept opportunity coverage" in errors
    assert "failures lack expected trace signal" in errors
