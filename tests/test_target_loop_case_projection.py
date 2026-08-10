from __future__ import annotations

from types import SimpleNamespace

import pytest

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.agent.session_snapshot import PartialEpisodeSnapshot
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
from affordance_runtime.benchmarks.target_loop.contracts import CaseFailureOrigin
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation


def _snapshot(
    *, observations: int = 2, executions: int = 1, turns: int = 1,
    reason: str = "runtime_exception", control_status: str = "failed",
) -> PartialEpisodeSnapshot:
    return PartialEpisodeSnapshot(
        observations, executions, 3, turns, "unknown", "effect_confirmed",
        "sha256:test", 1, 0, "effect_confirmed", 0, "SelectAction", 2, 1,
        "complete", "", (("SelectAction", turns),), control_status, reason,
    )


def _result(reason: str, *, message: str = "display only"):
    del message
    return SimpleNamespace(
        status=AgentLoopStatus.FAILED,
        sent_unknown_count=0,
        observation_count=2,
        execution_count=1,
        currentness_probe_count=3,
        control_transition_total_count=1,
        control_transition_kind_counts=(("SelectAction", 1),),
        reason_code=reason,
        failure_code=None,
        policy_failure=None,
    )


@pytest.mark.parametrize(
    ("reason", "origin"),
    (
        ("task_evaluation_invalid", CaseFailureOrigin.TASK_EVALUATION),
        ("action_evaluation_invalid", CaseFailureOrigin.ACTION_EVALUATION),
        ("action_result_lineage_mismatch", CaseFailureOrigin.EXECUTION),
        ("action_not_dispatched", CaseFailureOrigin.EXECUTION),
        ("observation_budget_exhausted", CaseFailureOrigin.DECISION_CONTROL),
        ("abort_policy", CaseFailureOrigin.DECISION_CONTROL),
        ("runtime_exception", CaseFailureOrigin.UNKNOWN),
        ("confirmation_subject_unavailable", CaseFailureOrigin.DECISION_CONTROL),
        ("new_bounded_runtime_reason", CaseFailureOrigin.UNKNOWN),
    ),
)
def test_runtime_reason_is_never_dropped_or_inferred_from_message(
    reason: str, origin: CaseFailureOrigin,
) -> None:
    first = project_case_result(
        "case", _result(reason, message="first"), BenchmarkInstrumentation(), 1.0, "first"
    )
    second = project_case_result(
        "case", _result(reason, message="different"), BenchmarkInstrumentation(), 1.0, "different"
    )
    assert first.case_failure_code == second.case_failure_code == reason
    assert first.failure_code == second.failure_code == reason
    assert first.failure_origin is origin


def test_non_timeout_exception_uses_final_snapshot_exact_metrics_and_reason() -> None:
    projected = project_case_result(
        "case",
        None,
        BenchmarkInstrumentation(),
        1.0,
        "human exception display",
        final_snapshot=_snapshot(observations=4, executions=1, turns=2),
    )
    assert projected.case_failure_code == "runtime_exception"
    assert projected.measurements["observations"].value == 4
    assert projected.measurements["executions"].value == 1
    assert projected.measurements["turns"].value == 2
    assert projected.partial_episode_available is True


def test_success_reason_does_not_become_a_failure_code() -> None:
    result = _result("task_complete")
    result.status = AgentLoopStatus.DONE
    projected = project_case_result(
        "case", result, BenchmarkInstrumentation(), 1.0, ""
    )
    assert projected.case_failure_code == ""
    assert projected.failure_code == ""
    assert projected.failure_origin is CaseFailureOrigin.NONE


def test_watchdog_snapshot_has_explicit_precedence_over_final_snapshot() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.failure_origin = CaseFailureOrigin.HARNESS_WATCHDOG
    instrumentation.failure_code = "case_timeout"
    projected = project_case_result(
        "case",
        None,
        instrumentation,
        1.0,
        "timeout",
        timeout_snapshot=_snapshot(observations=3, executions=1, turns=1),
        final_snapshot=_snapshot(observations=9, executions=8, turns=7),
    )
    assert projected.case_failure_code == "case_timeout"
    assert projected.measurements["observations"].value == 3
    assert projected.measurements["executions"].value == 1
    assert projected.measurements["turns"].value == 1


def test_result_none_does_not_inherit_stale_nonterminal_snapshot_reason() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_failure(
        CaseFailureOrigin.POLICY_DECISION,
        "policy_exception",
        RuntimeError("private provider detail"),
    )
    projected = project_case_result(
        "case",
        None,
        instrumentation,
        1.0,
        "display only",
        final_snapshot=_snapshot(
            reason="action_unknown", control_status="waiting_user"
        ),
    )
    assert projected.case_failure_code == "policy_exception"
    assert projected.runtime_reason_code == ""
    assert projected.failure_origin is CaseFailureOrigin.POLICY_DECISION


def test_cleanup_is_secondary_to_runtime_reason() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_cleanup_failure(
        "cleanup_exception", RuntimeError("private cleanup detail")
    )
    projected = project_case_result(
        "case", _result("task_evaluation_invalid"), instrumentation, 1.0,
        "runtime failed; cleanup failed",
    )
    assert projected.case_failure_code == "task_evaluation_invalid"
    assert projected.failure_origin is CaseFailureOrigin.TASK_EVALUATION
    assert projected.cleanup_failure_code == "cleanup_exception"
    assert projected.cleanup_exception_class == "RuntimeError"
    assert projected.measurements["cleanup_failures"].value == 1


def test_custom_metric_cannot_override_canonical_metric() -> None:
    instrumentation = BenchmarkInstrumentation()
    with pytest.raises(ValueError, match="canonical"):
        instrumentation.increment("observations", 99)


def test_projection_defends_against_direct_custom_metric_collision() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.custom_metrics["observations"] = 99
    projected = project_case_result(
        "case", None, instrumentation, 1.0, "display only"
    )
    assert projected.case_failure_code == "metric_name_collision"
    assert projected.failure_origin is CaseFailureOrigin.UNKNOWN
    assert projected.measurements["observations"].value == 0


def test_metric_collision_preserves_runtime_and_component_facts_independently() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_failure(
        CaseFailureOrigin.ACTION_EVALUATION,
        "action_evaluator_exception",
        RuntimeError("private detail"),
    )
    instrumentation.custom_metrics["observations"] = 99
    projected = project_case_result(
        "case", _result("runtime_exception"), instrumentation, 1.0, "display only"
    )
    assert projected.runtime_reason_code == "runtime_exception"
    assert projected.case_failure_code == "runtime_exception"
    assert projected.failure_origin is CaseFailureOrigin.ACTION_EVALUATION
    assert projected.failure_code == "action_evaluator_exception"
    assert projected.exception_class == "RuntimeError"
    assert projected.harness_integrity_code == "metric_name_collision"
    assert projected.harness_integrity_failures == 1
    assert projected.measurements["observations"].value == 2


def test_watchdog_remains_primary_when_cleanup_also_fails() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_failure(
        CaseFailureOrigin.HARNESS_WATCHDOG,
        "case_timeout",
        TimeoutError(),
    )
    instrumentation.record_cleanup_failure(
        "cleanup_exception", RuntimeError("private cleanup detail")
    )
    projected = project_case_result(
        "case", None, instrumentation, 1.0, "timeout; cleanup failed",
        timeout_snapshot=_snapshot(observations=3, executions=1, turns=1),
    )
    assert projected.case_failure_code == "case_timeout"
    assert projected.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG
    assert projected.cleanup_failure_code == "cleanup_exception"
    assert projected.measurements["cleanup_failures"].value == 1


def test_done_with_cleanup_only_is_not_reported_as_success() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_cleanup_failure(
        "cleanup_exception", RuntimeError("private cleanup detail")
    )
    result = _result("task_complete")
    result.status = AgentLoopStatus.DONE
    projected = project_case_result(
        "case", result, instrumentation, 1.0, "cleanup failed"
    )
    assert projected.case_failure_code == "cleanup_exception"
    assert projected.failure_origin is CaseFailureOrigin.CLEANUP


def test_dynamic_exception_class_is_safely_normalized_without_losing_component() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.failure_origin = CaseFailureOrigin.ACTION_EVALUATION
    instrumentation.failure_code = "action_evaluator_exception"
    instrumentation.exception_class = "private.class/" + "x" * 200
    projected = project_case_result(
        "case", _result("runtime_exception"), instrumentation, 1.0, "display only"
    )
    assert projected.failure_origin is CaseFailureOrigin.ACTION_EVALUATION
    assert projected.failure_code == "action_evaluator_exception"
    assert projected.exception_class == "Exception"
