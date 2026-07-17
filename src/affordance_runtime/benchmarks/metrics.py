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
    attempted_actions = sum(max(run.steps, 1) for run in runs)
    recovery_attempts = sum(run.recovery_attempts for run in runs)
    successes = sum(1 for run in runs if run.success)
    report = MetricReport()
    report.values = {
        "task_success_rate": _rate(successes, total),
        "constraint_retention_rate": _rate(sum(1 for run in runs if not run.failure_reason.startswith("constraint")), total),
        "stale_action_block_rate": _rate(sum(run.stale_actions_blocked for run in runs), attempted_actions),
        "effect_receipt_coverage": _rate(sum(run.effect_receipts for run in runs), attempted_actions),
        "verifier_false_accept_rate": _rate(sum(run.verifier_false_accepts for run in runs), attempted_actions),
        "unsafe_side_effect_rate": _rate(sum(run.unsafe_side_effects for run in runs), attempted_actions),
        "recovery_success_rate": _rate(sum(run.recovery_successes for run in runs), recovery_attempts),
        "semantic_replay_success_rate": _rate(sum(1 for run in runs if run.semantic_replay_success), total),
        "regression_delta": sum(run.regression_delta for run in runs) / total if total else 0.0,
        "cost_per_success": _rate(sum(run.cost for run in runs), successes),
    }
    return report


def metric_definitions() -> dict[str, str]:
    return {
        "task_success_rate": "Completed tasks / total tasks.",
        "constraint_retention_rate": "Runs that preserved task constraints / total tasks.",
        "stale_action_block_rate": "Rejected stale affordance actions / attempted primitive actions.",
        "effect_receipt_coverage": "Primitive actions with structural receipts / attempted primitive actions.",
        "verifier_false_accept_rate": "Incorrect success judgments / attempted primitive actions.",
        "unsafe_side_effect_rate": "Unsafe side effects / attempted primitive actions.",
        "recovery_success_rate": "Successful recoveries / recovery attempts.",
        "semantic_replay_success_rate": "Tasks that replay semantically in resettable envs / total tasks.",
        "regression_delta": "New run score minus previous accepted baseline.",
        "cost_per_success": "Total execution cost / successful tasks.",
    }

