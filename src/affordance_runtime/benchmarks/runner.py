"""Deterministic benchmark protocol and JSON/Markdown/CSV report writers."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from affordance_runtime.benchmarks.metrics import MetricReport, aggregate
from affordance_runtime.benchmarks.spec import BenchmarkRun, BenchmarkTask

REQUIRED_VARIANTS = (
    "direct_playwright",
    "primitive_browser_agent",
    "full_runtime",
    "no_preflight",
    "no_structural_verifier",
    "no_capability_gate",
    "no_recovery",
)


RunCase = Callable[[BenchmarkTask, str, int], BenchmarkRun]


@dataclass
class BenchmarkReport:
    suite_version: str
    runs: list[BenchmarkRun]
    metrics_by_variant: dict[str, MetricReport] = field(default_factory=dict)
    acceptance_errors: list[str] = field(default_factory=list)
    environment: dict[str, object] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def build(cls, suite_version: str, runs: list[BenchmarkRun]) -> "BenchmarkReport":
        variants = sorted({run.variant for run in runs})
        report = cls(
            suite_version,
            runs,
            {variant: aggregate([run for run in runs if run.variant == variant]) for variant in variants},
        )
        report.acceptance_errors = release_acceptance_errors(report) if set(REQUIRED_VARIANTS) <= set(variants) else []
        return report


def release_acceptance_errors(report: BenchmarkReport) -> list[str]:
    errors: list[str] = []
    missing = sorted(set(REQUIRED_VARIANTS) - set(report.metrics_by_variant))
    if missing:
        return [f"missing required variants: {', '.join(missing)}"]
    full = report.metrics_by_variant["full_runtime"].values
    requirements = {
        "task_success_rate": (1.0, "min"),
        "constraint_violation_rate": (0.0, "max"),
        "unsafe_side_effect_rate": (0.0, "max"),
        "verifier_false_accept_rate": (0.0, "max"),
        "stale_detection_recall": (1.0, "min"),
        "recovery_success_rate": (1.0, "min"),
    }
    for metric, (threshold, direction) in requirements.items():
        value = full.get(metric, 0.0)
        if (direction == "min" and value < threshold) or (direction == "max" and value > threshold):
            errors.append(f"full_runtime {metric}={value:.4f} violates {direction} threshold {threshold:.4f}")
    signals = {
        "no_preflight": ("stale_detection_recall", "lower"),
        "no_structural_verifier": ("verifier_false_accept_rate", "higher"),
        "no_capability_gate": ("unsafe_side_effect_rate", "higher"),
        "no_recovery": ("task_success_rate", "lower"),
    }
    for variant, (metric, direction) in signals.items():
        value = report.metrics_by_variant[variant].values.get(metric, 0.0)
        full_value = full.get(metric, 0.0)
        if (direction == "lower" and value >= full_value) or (direction == "higher" and value <= full_value):
            errors.append(f"{variant} did not produce expected {direction} signal for {metric}")
    return errors


@dataclass
class BenchmarkRunner:
    tasks: list[BenchmarkTask]
    run_case: RunCase
    suite_version: str = "local-saas-v1"
    variants: tuple[str, ...] = REQUIRED_VARIANTS
    seeds: tuple[int, ...] = (0,)

    def run(self) -> BenchmarkReport:
        runs = [self.run_case(task, variant, seed) for task in self.tasks for variant in self.variants for seed in self.seeds]
        return BenchmarkReport.build(self.suite_version, runs)


@dataclass(frozen=True)
class BenchmarkReportWriter:
    output_dir: Path

    def write(self, report: BenchmarkReport) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / "benchmark-report.json"
        markdown_path = self.output_dir / "benchmark-report.md"
        csv_path = self.output_dir / "benchmark-runs.csv"
        json_path.write_text(
            json.dumps(
                {
                    "suite_version": report.suite_version,
                    "metrics_by_variant": {
                        variant: metric.values for variant, metric in report.metrics_by_variant.items()
                    },
                    "acceptance_errors": report.acceptance_errors,
                    "environment": report.environment,
                    "generated_at": report.generated_at,
                    "runs": [asdict(run) for run in report.runs],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        markdown_path.write_text(self._markdown(report), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(report.runs[0]).keys()) if report.runs else ["task_id"])
            writer.writeheader()
            writer.writerows(asdict(run) for run in report.runs)
        manifest_path = self.output_dir / "environment.json"
        manifest_path.write_text(json.dumps(report.environment, indent=2, sort_keys=True), encoding="utf-8")
        commit = str(report.environment.get("runtime_commit") or "working-tree")[:12]
        version_dir = self.output_dir / "versions"
        version_dir.mkdir(parents=True, exist_ok=True)
        versioned_json = version_dir / f"benchmark-{report.suite_version}-{commit}.json"
        versioned_markdown = version_dir / f"benchmark-{report.suite_version}-{commit}.md"
        versioned_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
        versioned_markdown.write_text(markdown_path.read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "json": json_path,
            "markdown": markdown_path,
            "csv": csv_path,
            "manifest": manifest_path,
            "versioned_json": versioned_json,
            "versioned_markdown": versioned_markdown,
        }

    @staticmethod
    def _markdown(report: BenchmarkReport) -> str:
        metrics = sorted({name for value in report.metrics_by_variant.values() for name in value.values})
        lines = [f"# Benchmark Report: {report.suite_version}", "", "| Variant | " + " | ".join(metrics) + " |"]
        lines.append("| --- | " + " | ".join("---:" for _ in metrics) + " |")
        for variant, values in sorted(report.metrics_by_variant.items()):
            lines.append("| " + variant + " | " + " | ".join(f"{values.values.get(metric, 0.0):.4f}" for metric in metrics) + " |")
        lines.extend(["", f"Runs: {len(report.runs)}", ""])
        if report.environment:
            lines.extend(
                [
                    "## Environment",
                    "",
                    f"- Runtime commit: `{report.environment.get('runtime_commit', 'unknown')}`",
                    f"- Browser: `{report.environment.get('browser_version', 'unknown')}`",
                    f"- Fixture: `{report.environment.get('fixture_version', 'unknown')}`",
                    f"- Seed semantics: `{report.environment.get('seed_semantics', 'unknown')}`",
                    "",
                ]
            )
        lines.extend(
            [
                "## Release Acceptance",
                "",
                "PASS" if not report.acceptance_errors else "FAIL",
                "",
            ]
        )
        lines.extend(f"- {error}" for error in report.acceptance_errors)
        if report.acceptance_errors:
            lines.append("")
        return "\n".join(lines)
