from __future__ import annotations

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    MetricMeasurement,
    TerminalReasonCode,
)


def _result(**changes) -> BenchmarkCaseResult:
    values = {
        "case_id": "miniwob-60-01",
        "status": "failed",
        "execution_completed": True,
        "failure_reason": "",
        "latency_ms": 1.0,
        "measurements": {
            "official_success_count": MetricMeasurement(0, True),
            "cleanup_failures": MetricMeasurement(0, True),
            "sent_unknown_count": MetricMeasurement(0, True),
        },
    }
    values.update(changes)
    return BenchmarkCaseResult(**values)


def test_success_provider_and_no_progress_are_typed_separately() -> None:
    success = _result(
        status="done",
        measurements={
            "official_success_count": MetricMeasurement(1, True),
            "cleanup_failures": MetricMeasurement(0, True),
            "sent_unknown_count": MetricMeasurement(0, True),
        },
    )
    assert classify_case(success).outcome is MiniWobTaskOutcome.SUCCESS
    assert classify_case(_result(policy_failure_kind="provider_unavailable")).outcome is MiniWobTaskOutcome.PROVIDER_UNAVAILABLE
    repeated = _result(terminal_reason_code=TerminalReasonCode.NO_PROGRESS_REPETITION)
    assert classify_case(repeated).outcome is MiniWobTaskOutcome.NO_PROGRESS_REPETITION


def test_timeout_and_runtime_rejection_do_not_use_free_text() -> None:
    timeout = _result(case_failure_code="case_timeout")
    assert classify_case(timeout).outcome is MiniWobTaskOutcome.CASE_TIMEOUT
    rejected = _result(
        status="blocked",
        terminal_reason_code=TerminalReasonCode.INVALID_ACTION_PARAMETERS,
    )
    assert classify_case(rejected).outcome is MiniWobTaskOutcome.WRONG_PARAMETERS
