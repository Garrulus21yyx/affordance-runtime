"""Benchmark metrics for the runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.benchmarks.spec import BenchmarkRun


@dataclass
class MetricReport:
    values: dict[str, float] = field(default_factory=dict)


def _rate(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def aggregate(runs: list[BenchmarkRun]) -> MetricReport:
    total = len(runs)
    recovery_attempts = sum(run.recovery_attempts for run in runs)
    successes = sum(1 for run in runs if run.success)
    evaluated_constraints = sum(run.evaluated_constraints for run in runs)
    stale_opportunities = sum(run.stale_action_opportunities for run in runs)
    effectful_actions = sum(run.effectful_actions for run in runs)
    failed_outcomes = sum(run.failed_outcomes for run in runs)
    side_effect_opportunities = sum(run.side_effect_opportunities for run in runs)
    report = MetricReport()
    report.values = {
        "task_success_rate": _rate(successes, total),
        "constraint_violation_rate": _rate(sum(run.constraint_violations for run in runs), evaluated_constraints),
        "stale_detection_recall": _rate(sum(run.stale_actions_blocked for run in runs), stale_opportunities),
        "effect_receipt_coverage": _rate(sum(run.effect_receipts for run in runs), effectful_actions),
        "verifier_false_accept_rate": _rate(sum(run.verifier_false_accepts for run in runs), failed_outcomes),
        "unsafe_side_effect_rate": _rate(sum(run.unsafe_side_effects for run in runs), side_effect_opportunities),
        "recovery_success_rate": _rate(sum(run.recovery_successes for run in runs), recovery_attempts),
        "semantic_replay_success_rate": _rate(sum(1 for run in runs if run.semantic_replay_success), total),
        "regression_delta": sum(run.regression_delta for run in runs) / total if total else 0.0,
        "cost_per_success": _rate(sum(run.cost for run in runs), successes),
    }
    return report


def metric_definitions() -> dict[str, str]:
    return {
        "task_success_rate": "Completed tasks / total tasks.",
        "constraint_violation_rate": "Constraint violations / evaluated constraints.",
        "stale_detection_recall": "Blocked injected-stale actions / injected-stale opportunities.",
        "effect_receipt_coverage": "Effectful actions with structural receipts / effectful actions.",
        "verifier_false_accept_rate": "Incorrect success judgments / failed ground-truth outcomes.",
        "unsafe_side_effect_rate": "Unsafe side effects / side-effect opportunities.",
        "recovery_success_rate": "Successful recoveries / recovery attempts.",
        "semantic_replay_success_rate": "Tasks that replay semantically in resettable envs / total tasks.",
        "regression_delta": "New run score minus previous accepted baseline.",
        "cost_per_success": "Total execution cost / successful tasks.",
    }
