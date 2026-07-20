"""Held-out local layouts and master M8 generalization report."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from affordance_runtime.benchmarks.local import LocalSaasRunCase
from affordance_runtime.benchmarks.miniwob import run_official_miniwob_suite
from affordance_runtime.benchmarks.runner import BenchmarkReport, BenchmarkReportWriter
from affordance_runtime.benchmarks.suites import mvp_benchmark_tasks
from affordance_runtime.benchmarks.visual import run_visual_grounding_suite
from affordance_runtime.coordinator import RuntimeFeatures
from affordance_runtime.environment import environment_manifest
from affordance_runtime.fixtures import LOCAL_SAAS_FIXTURE_VERSION, create_fixture_server


def run_heldout_local_suite(
    output_dir: Path,
    *,
    seeds: tuple[int, ...] = (101, 102),
) -> BenchmarkReport:
    server = create_fixture_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{server.server_name}:{server.server_port}"
        run_case = LocalSaasRunCase(base_url, output_dir / "artifacts", profile="heldout")
        runs = [
            run_case.run_runtime_case(task, "heldout_full_runtime", seed, RuntimeFeatures())
            for task in mvp_benchmark_tasks()
            for seed in seeds
        ]
        report = BenchmarkReport.build("local-saas-heldout-v2", runs)
        report.environment = environment_manifest(
            browser_version=run_case.observed_browser_version,
            fixture_version=LOCAL_SAAS_FIXTURE_VERSION,
            suite_version=report.suite_version,
            seed_semantics="heldout_layout_and_distractor_v2",
        ).to_dict()
        if not all(run.success for run in runs):
            report.acceptance_errors.append("one or more held-out Full Runtime cases failed")
        seed_variants = {seed: {run.fixture_variant for run in runs if run.seed == seed} for seed in seeds}
        if any(len(values) != 1 for values in seed_variants.values()) or len(
            {next(iter(values)) for values in seed_variants.values()}
        ) != len(seeds):
            report.acceptance_errors.append("held-out seeds did not produce distinct fixture variants")
        BenchmarkReportWriter(output_dir).write(report)
        return report
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def write_generalization_summary(
    output_dir: Path,
    *,
    training_report_path: Path,
    miniwob_report: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    training = json.loads(training_report_path.read_text(encoding="utf-8"))
    heldout = run_heldout_local_suite(output_dir / "heldout")
    visual = run_visual_grounding_suite(output_dir / "visual")
    training_full = training["metrics_by_variant"]["full_runtime"]
    training_variants = {
        run["seed"]: run.get("fixture_variant", "")
        for run in training["runs"]
        if run["variant"] == "full_runtime"
    }
    errors: list[str] = []
    if len(training_variants) < 3 or len(set(training_variants.values())) < 3:
        errors.append("training benchmark does not contain three distinct seed variants")
    if training_full["task_success_rate"] != 1.0:
        errors.append("training Full Runtime task success is below 1.0")
    if heldout.acceptance_errors:
        errors.extend(heldout.acceptance_errors)
    if visual["acceptance_errors"]:
        errors.extend(visual["acceptance_errors"])
    if miniwob_report.get("acceptance_errors"):
        errors.extend(str(item) for item in miniwob_report["acceptance_errors"])
    summary = {
        "suite_version": "generalization-v1",
        "training_seed_count": len(training_variants),
        "training_distinct_variants": len(set(training_variants.values())),
        "training_full_runtime": training_full,
        "heldout_runs": len(heldout.runs),
        "heldout_success_rate": sum(run.success for run in heldout.runs) / len(heldout.runs),
        "visual": visual,
        "miniwob": miniwob_report,
        "acceptance_errors": errors,
        "acceptance": "passed" if not errors else "failed",
    }
    (output_dir / "generalization-report.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    markdown = [
        "# M8 Generalization Report",
        "",
        f"- Training distinct variants: `{summary['training_distinct_variants']}`",
        f"- Training Full Runtime success: `{training_full['task_success_rate']:.4f}`",
        f"- Held-out runs / success: `{summary['heldout_runs']}` / `{summary['heldout_success_rate']:.4f}`",
        f"- Visual runs / success: `{len(visual['runs'])}` / `{visual['success_rate']:.4f}`",
        f"- MiniWoB++ runs / raw-reward success: `{len(miniwob_report['episodes'])}` / `{miniwob_report['success_rate']:.4f}`",
        f"- Acceptance: `{summary['acceptance'].upper()}`",
        "",
    ]
    (output_dir / "generalization-report.md").write_text("\n".join(markdown), encoding="utf-8")
    return summary


def run_generalization_suite(output_dir: Path, *, training_report_path: Path) -> dict[str, Any]:
    miniwob = run_official_miniwob_suite(output_dir / "miniwob")
    return write_generalization_summary(
        output_dir,
        training_report_path=training_report_path,
        miniwob_report=miniwob,
    )
