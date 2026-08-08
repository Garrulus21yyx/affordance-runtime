from dataclasses import fields

from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCaseResult


def test_case_result_has_one_metric_authority() -> None:
    names = {item.name for item in fields(BenchmarkCaseResult)}
    assert names == {
        "case_id", "status", "execution_completed", "failure_reason", "latency_ms",
        "measurements",
    }
