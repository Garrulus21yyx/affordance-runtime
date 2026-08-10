from dataclasses import fields

import pytest

from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    FailureFacts,
    MetricMeasurement,
    TerminalReasonCode,
)


def test_case_result_has_one_metric_authority() -> None:
    names = {item.name for item in fields(BenchmarkCaseResult)}
    assert names == {
        "case_id", "status", "execution_completed", "failure_reason", "latency_ms",
        "measurements", "terminal_reason_code", "termination_origin", "case_failure_code",
        "partial_episode_available", "latest_task_status",
            "latest_action_evaluation_status", "latest_semantic_attempt_key_digest",
            "same_attempt_streak", "no_progress_count", "last_progress_event_type",
            "failure_origin", "failure_code", "exception_class", "last_decision_type",
            "last_policy_failure_code", "last_action_space_option_count",
            "last_world_target_count", "last_world_coverage", "pending_kind",
            "runtime_reason_code", "agent_failure_code", "cleanup_failure_code",
            "cleanup_exception_class", "cleanup_failures", "watchdog_triggered",
            "harness_integrity_code", "harness_integrity_failures",
            "failure_facts", "case_schema_version", "suite_id", "profile_id",
            "seed", "manifest_digest", "harness_schema_version",
        }


def test_case_measurements_mapping_is_immutable() -> None:
    result = BenchmarkCaseResult(
        "case", "done", True, "", 1.0, {"executions": MetricMeasurement(1, True)},
    )
    with pytest.raises(TypeError, match="immutable"):
        result.measurements["executions"] = MetricMeasurement(2, True)  # type: ignore[index]


def test_case_terminal_reason_is_required_exactly_for_blocked_status() -> None:
    with pytest.raises(ValueError, match="blocked case result"):
        BenchmarkCaseResult("case", "blocked", True, "", 1.0)
    with pytest.raises(ValueError, match="non-blocked case result"):
        BenchmarkCaseResult(
            "case", "done", True, "", 1.0, {}, TerminalReasonCode.BLOCKED_OTHER,
        )
    BenchmarkCaseResult(
        "case", "failed", True, "", 1.0, {}, TerminalReasonCode.NO_PROGRESS_REPETITION,
        case_failure_code="no_progress_repetition",
        agent_failure_code="no_progress_repetition",
        failure_facts=FailureFacts(agent_failure_code="no_progress_repetition"),
    )
