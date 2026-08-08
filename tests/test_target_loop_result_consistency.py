from dataclasses import fields

import pytest

from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCaseResult, MetricMeasurement


def test_case_result_has_one_metric_authority() -> None:
    names = {item.name for item in fields(BenchmarkCaseResult)}
    assert names == {
        "case_id", "status", "execution_completed", "failure_reason", "latency_ms",
        "measurements",
    }


def test_case_measurements_mapping_is_immutable() -> None:
    result = BenchmarkCaseResult(
        "case", "done", True, "", 1.0, {"executions": MetricMeasurement(1, True)},
    )
    with pytest.raises(TypeError, match="immutable"):
        result.measurements["executions"] = MetricMeasurement(2, True)  # type: ignore[index]
