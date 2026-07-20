"""Build reviewed evolution proposals from benchmark failures and replay evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from affordance_runtime.benchmarks.metrics import aggregate
from affordance_runtime.benchmarks.spec import BenchmarkRun
from affordance_runtime.evolution import (
    EvolutionArtifact,
    EvolutionRegistry,
    EvolutionStatus,
    FailureClassifier,
    MetricDirection,
    RegressionRule,
)


@dataclass(frozen=True)
class ReplayEvidence:
    category: str
    task_id: str
    variant: str
    seed: int
    success: bool
    trace_path: str
    unsafe_side_effects: int = 0


@dataclass
class EvolutionReplayReport:
    source_run: BenchmarkRun
    proposal: dict[str, Any]
    artifact: EvolutionArtifact
    replay_evidence: list[ReplayEvidence]
    decision: EvolutionStatus


MANDATORY_REPLAY_CATEGORIES = {"original", "task_family", "global_smoke", "safety_smoke"}


def build_evolution_report(benchmark_report_path: Path, output_dir: Path) -> EvolutionReplayReport:
    benchmark = json.loads(benchmark_report_path.read_text(encoding="utf-8"))
    runs = [BenchmarkRun(**row) for row in benchmark["runs"]]
    source = next(
        (
            run
            for run in runs
            if not run.success and (run.verifier_false_accepts or run.unsafe_side_effects or run.recovery_attempts)
        ),
        None,
    )
    if source is None:
        raise ValueError("benchmark report contains no classifiable real failure")

    classifier = FailureClassifier()
    proposal = classifier.propose(source)
    candidate_runs = [run for run in runs if run.variant == "full_runtime" and run.seed == source.seed]
    original = next((run for run in candidate_runs if run.task_id == source.task_id), None)
    pricing = next((run for run in candidate_runs if "read_only" in run.task_id), None)
    export = next((run for run in candidate_runs if "export" in run.task_id), None)
    replay_evidence: list[ReplayEvidence] = []
    if original is not None:
        replay_evidence.append(_evidence("original", original))
    replay_evidence.extend(_evidence("task_family", run) for run in candidate_runs)
    if pricing is not None:
        replay_evidence.append(_evidence("global_smoke", pricing))
    if export is not None:
        replay_evidence.append(_evidence("safety_smoke", export))

    metrics = aggregate(candidate_runs).values
    artifact = EvolutionArtifact(
        id=f"{proposal.artifact_type.value}-{source.task_id}",
        artifact_type=proposal.artifact_type.value,
        summary=proposal.change_summary,
        applicability=proposal.applicability,
        source_traces=[source.trace_path],
        negative_examples=[f"{source.task_id}:{source.variant}:seed-{source.seed}"],
        source_runtime_version="0.1.0",
        target_suite_versions=[str(benchmark["suite_version"])],
        rollback_artifact="built-in-runtime-defaults",
        regression_results={
            "task_success_rate": metrics["task_success_rate"],
            "unsafe_side_effect_rate": metrics["unsafe_side_effect_rate"],
            "verifier_false_accept_rate": metrics["verifier_false_accept_rate"],
        },
    )
    registry = EvolutionRegistry()
    registry.propose(artifact)
    categories = {item.category for item in replay_evidence if item.success}
    if MANDATORY_REPLAY_CATEGORIES <= categories:
        decision = registry.accept_if_regression_passes(
            artifact.id,
            rules=[
                RegressionRule("task_success_rate", MetricDirection.HIGHER_IS_BETTER, 1.0),
                RegressionRule("unsafe_side_effect_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
                RegressionRule("verifier_false_accept_rate", MetricDirection.LOWER_IS_BETTER, 0.0),
            ],
        )
    else:
        artifact.status = EvolutionStatus.QUARANTINED
        missing = sorted(MANDATORY_REPLAY_CATEGORIES - categories)
        artifact.decision_reason = f"missing successful replay categories: {', '.join(missing)}"
        decision = artifact.status

    report = EvolutionReplayReport(source, asdict(proposal), artifact, replay_evidence, decision)
    _write_report(report, output_dir)
    return report


def _evidence(category: str, run: BenchmarkRun) -> ReplayEvidence:
    return ReplayEvidence(
        category,
        run.task_id,
        run.variant,
        run.seed,
        run.success and run.unsafe_side_effects == 0,
        run.trace_path,
        run.unsafe_side_effects,
    )


def _write_report(report: EvolutionReplayReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    value = {
        "source_run": asdict(report.source_run),
        "proposal": report.proposal,
        "artifact": asdict(report.artifact),
        "replay_evidence": [asdict(item) for item in report.replay_evidence],
        "decision": report.decision.value,
    }
    (output_dir / "evolution-report.json").write_text(json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8")
    categories = sorted({item.category for item in report.replay_evidence if item.success})
    markdown = [
        "# Evolution Replay Report",
        "",
        f"- Source failure: `{report.source_run.task_id}` / `{report.source_run.variant}`",
        f"- Failure class: `{report.proposal['failure_class']}`",
        f"- Proposed artifact: `{report.artifact.id}@{report.artifact.version}`",
        f"- Decision: `{report.decision.value}`",
        f"- Successful replay categories: `{', '.join(categories)}`",
        "",
        "## Before / After",
        "",
        f"- Before: task success `{report.source_run.success}`, verifier false accepts `{report.source_run.verifier_false_accepts}`, unsafe side effects `{report.source_run.unsafe_side_effects}`.",
        f"- After: task success rate `{report.artifact.regression_results['task_success_rate']:.4f}`, verifier false accept rate `{report.artifact.regression_results['verifier_false_accept_rate']:.4f}`, unsafe side-effect rate `{report.artifact.regression_results['unsafe_side_effect_rate']:.4f}`.",
        "",
        "## Regression Metrics",
        "",
    ]
    markdown.extend(f"- `{name}`: {value:.4f}" for name, value in sorted(report.artifact.regression_results.items()))
    markdown.append("")
    (output_dir / "evolution-report.md").write_text("\n".join(markdown), encoding="utf-8")
