from affordance_runtime.benchmarks.metrics import aggregate
from affordance_runtime.benchmarks.spec import BenchmarkRun


def test_benchmark_metrics_cover_runtime_specific_rates() -> None:
    report = aggregate(
        [
            BenchmarkRun(
                task_id="a",
                success=True,
                steps=2,
                latency_ms=10,
                stale_actions_blocked=1,
                effect_receipts=2,
                recovery_attempts=1,
                recovery_successes=1,
                semantic_replay_success=True,
                cost=0.5,
            ),
            BenchmarkRun(task_id="b", success=False, steps=2, latency_ms=20, unsafe_side_effects=1),
        ]
    )

    assert report.values["task_success_rate"] == 0.5
    assert report.values["stale_action_block_rate"] == 0.25
    assert report.values["recovery_success_rate"] == 1.0
    assert report.values["cost_per_success"] == 0.5

