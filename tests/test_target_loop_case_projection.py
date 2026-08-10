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
    reason: str = "runtime_exception",
) -> PartialEpisodeSnapshot:
    return PartialEpisodeSnapshot(
        observations, executions, 3, turns, "unknown", "effect_confirmed",
        "sha256:test", 1, 0, "effect_confirmed", 0, "SelectAction", 2, 1,
        "complete", "", (("SelectAction", turns),), "failed", reason,
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
    "reason",
    (
        "task_evaluation_invalid",
        "action_evaluation_invalid",
        "action_result_lineage_mismatch",
        "action_not_dispatched",
        "observation_budget_exhausted",
        "abort_policy",
        "runtime_exception",
        "confirmation_subject_unavailable",
        "new_bounded_runtime_reason",
    ),
)
def test_runtime_reason_is_never_dropped_or_inferred_from_message(reason: str) -> None:
    first = project_case_result(
        "case", _result(reason, message="first"), BenchmarkInstrumentation(), 1.0, "first"
    )
    second = project_case_result(
        "case", _result(reason, message="different"), BenchmarkInstrumentation(), 1.0, "different"
    )
    assert first.case_failure_code == second.case_failure_code == reason
    assert first.failure_code == second.failure_code == reason
    assert first.failure_origin is CaseFailureOrigin.DECISION_CONTROL


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
