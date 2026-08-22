from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from affordance_runtime.agent import AgentFailureCode, RunStatus
from affordance_runtime.agent.episode_snapshot import EpisodeSnapshot
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
from affordance_runtime.benchmarks.target_loop.contracts import CaseFailureOrigin
from affordance_runtime.benchmarks.target_loop.failure_origin import observation_failure_origin
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.evaluation import TaskOutcomeFact, TaskOutcomeKind


def _snapshot(
    *,
    observations: int = 2,
    executions: int = 1,
    turns: int = 1,
    reason: str = "runtime_exception",
    control_status: str = "failed",
    task_outcome_kind: str = "",
    task_outcome_code: str = "",
    runtime_failure: RuntimeFailure | None = None,
) -> EpisodeSnapshot:
    snapshot = EpisodeSnapshot(
        observations,
        executions,
        3,
        turns,
        "unknown",
        "changed",
        "satisfied",
        "native",
        "sha256:" + "0" * 64,
        1,
        0,
        "action_postcondition_satisfied",
        0,
        "select_action",
        2,
        1,
        "complete",
        "",
        (("select_action", turns),),
        control_status,
        reason,
    )
    return replace(
        snapshot,
        task_outcome_kind=task_outcome_kind,
        task_outcome_code=task_outcome_code,
        runtime_failure=runtime_failure,
    )


def _result(reason: str, *, message: str = "display only"):
    del message
    return SimpleNamespace(
        status=RunStatus.FAILED,
        sent_unknown_count=0,
        observation_count=2,
        execution_count=1,
        currentness_probe_count=3,
        step_count=1,
        reason_code=reason,
        failure_code=None,
        policy_failure=None,
        runtime_failure=RuntimeFailure(
            FailureStage.CONTROL,
            FailureKind.REJECTED,
            reason,
        ),
        task_outcome=None,
    )


def _runtime_failure_snapshot(reason: str) -> EpisodeSnapshot:
    return _snapshot(
        runtime_failure=RuntimeFailure(
            FailureStage.CONTROL,
            FailureKind.REJECTED,
            reason,
        )
    )


def test_blocked_run_does_not_publish_incompatible_verifier_unavailable_outcome() -> None:
    result = SimpleNamespace(
        status=RunStatus.BLOCKED,
        sent_unknown_count=0,
        observation_count=5,
        execution_count=1,
        currentness_probe_count=0,
        step_count=10,
        reason_code="",
        failure_code=None,
        policy_failure=None,
        runtime_failure=None,
        task_outcome=TaskOutcomeFact(
            TaskOutcomeKind.VERIFIER_UNAVAILABLE,
            "source_insufficient",
        ),
    )

    projected = project_case_result(
        "case",
        result,
        BenchmarkInstrumentation(),
        1.0,
        "",
        final_snapshot=_snapshot(
            observations=5,
            executions=1,
            turns=10,
            control_status="blocked",
            reason="",
        ),
    )

    assert projected.status == "blocked"
    assert projected.terminal_reason_code is not None
    assert projected.failure_facts.task_outcome_kind == ""
    assert projected.failure_facts.task_outcome_code == ""


@pytest.mark.parametrize(
    "reason",
    (
        "task_evaluation_invalid",
        "action_outcome_invalid",
        "action_result_lineage_mismatch",
        "action_not_dispatched",
        "observation_budget_exhausted",
        "abort_policy",
        "runtime_exception",
        "confirmation_subject_unavailable",
        "new_bounded_runtime_reason",
    ),
)
def test_runtime_reason_is_never_dropped_or_inferred_from_message(
    reason: str,
) -> None:
    first = project_case_result(
        "case",
        _result(reason, message="first"),
        BenchmarkInstrumentation(),
        1.0,
        "first",
        final_snapshot=_runtime_failure_snapshot(reason),
    )
    second = project_case_result(
        "case",
        _result(reason, message="different"),
        BenchmarkInstrumentation(),
        1.0,
        "different",
        final_snapshot=_runtime_failure_snapshot(reason),
    )
    assert first.case_failure_code == second.case_failure_code == reason
    assert first.runtime_reason_code == second.runtime_reason_code == reason
    assert first.failure_facts.runtime_reason_code == reason
    assert first.failure_code == second.failure_code == ""
    assert first.failure_origin is CaseFailureOrigin.NONE


def test_non_timeout_exception_uses_final_snapshot_exact_metrics_and_reason() -> None:
    projected = project_case_result(
        "case",
        None,
        BenchmarkInstrumentation(),
        1.0,
        "human exception display",
        final_snapshot=_snapshot(observations=4, executions=1, turns=2),
    )
    assert projected.case_failure_code == "runtime_failure"
    assert projected.measurements["observations"].value == 4
    assert projected.measurements["executions"].value == 1
    assert projected.measurements["turns"].value == 2
    assert projected.partial_episode_available is True


def test_repeated_no_progress_event_is_in_the_benchmark_vocabulary() -> None:
    projected = project_case_result(
        "case",
        None,
        BenchmarkInstrumentation(),
        1.0,
        "stopped",
        final_snapshot=replace(
            _snapshot(),
            last_progress_event_type="repeated_no_progress_selection",
        ),
    )

    assert projected.last_progress_event_type == "repeated_no_progress_selection"


def test_success_reason_does_not_become_a_failure_code() -> None:
    result = _result("task_complete")
    result.status = RunStatus.DONE
    result.runtime_failure = None
    projected = project_case_result("case", result, BenchmarkInstrumentation(), 1.0, "")
    assert projected.case_failure_code == ""
    assert projected.failure_code == ""
    assert projected.failure_origin is CaseFailureOrigin.NONE


def test_watchdog_snapshot_has_explicit_precedence_over_final_snapshot() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_watchdog("case_timeout", TimeoutError())
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
        final_snapshot=_snapshot(reason="action_unknown", control_status="waiting_user"),
    )
    assert projected.case_failure_code == "policy_exception"
    assert projected.runtime_reason_code == ""
    assert projected.failure_origin is CaseFailureOrigin.POLICY_DECISION


def test_cleanup_is_secondary_to_runtime_reason() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_cleanup_failure("cleanup_exception", RuntimeError("private cleanup detail"))
    projected = project_case_result(
        "case",
        _result("task_evaluation_invalid"),
        instrumentation,
        1.0,
        "runtime failed; cleanup failed",
        final_snapshot=_runtime_failure_snapshot("task_evaluation_invalid"),
    )
    assert projected.case_failure_code == "task_evaluation_invalid"
    assert projected.failure_origin is CaseFailureOrigin.NONE
    assert projected.termination_origin == "runtime"
    assert projected.cleanup_failure_code == "cleanup_exception"
    assert projected.cleanup_exception_class == "RuntimeError"
    assert projected.measurements["cleanup_failures"].value == 1


def test_cleanup_timeout_does_not_mask_provider_failure() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_cleanup_failure("cleanup_timeout", TimeoutError("bounded cleanup expired"))

    projected = project_case_result(
        "case",
        _result("provider_failure"),
        instrumentation,
        1.0,
        "provider failed; cleanup timed out",
        final_snapshot=_runtime_failure_snapshot("provider_failure"),
    )

    assert projected.case_failure_code == "provider_failure"
    assert projected.cleanup_failure_code == "cleanup_timeout"
    assert projected.secondary_failure_codes == ("cleanup_timeout",)


def test_cleanup_timeout_does_not_mask_terminal_task_failure() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_cleanup_failure("cleanup_timeout", TimeoutError("bounded cleanup expired"))
    result = SimpleNamespace(
        status=RunStatus.BLOCKED,
        sent_unknown_count=0,
        observation_count=1,
        execution_count=0,
        currentness_probe_count=0,
        step_count=0,
        failure_code=None,
        policy_failure=None,
        runtime_failure=None,
        task_outcome=TaskOutcomeFact(
            TaskOutcomeKind.TERMINAL_FAILURE,
            "verified_terminal_task_failure",
            ("fact:terminal-task-failure",),
        ),
    )

    projected = project_case_result(
        "case",
        result,
        instrumentation,
        1.0,
        "cleanup timed out",
        final_snapshot=replace(
            _snapshot(
                observations=1,
                executions=0,
                turns=0,
                control_status="blocked",
                reason="",
                task_outcome_kind=TaskOutcomeKind.TERMINAL_FAILURE.value,
                task_outcome_code="verified_terminal_task_failure",
            ),
            latest_task_status="blocked",
        ),
    )

    assert projected.case_failure_code == "verified_terminal_task_failure"
    assert projected.termination_origin == ""
    assert projected.cleanup_failure_code == "cleanup_timeout"


def test_uncertain_dispatch_remains_primary_when_cleanup_also_fails() -> None:
    instrumentation = BenchmarkInstrumentation(
        failure_origin=CaseFailureOrigin.EXECUTION,
        failure_code="action_dispatch_uncertain",
        exception_class="TimeoutError",
        primary_execution_failure_code="action_dispatch_uncertain",
        primary_execution_failure_phase="dispatch_wait",
        primary_execution_diagnostic_ref="execution-diagnostic:" + "a" * 24,
        recovery_failure_codes=["post_action_acquisition_failed"],
    )
    instrumentation.record_cleanup_failure("cleanup_exception", TimeoutError())

    projected = project_case_result(
        "case",
        None,
        instrumentation,
        30_000.0,
        "dispatch uncertain; acquisition failed; cleanup timed out",
        final_snapshot=_snapshot(reason="environment_unresponsive"),
    )

    assert projected.case_failure_code == "action_dispatch_uncertain"
    assert projected.failure_origin is CaseFailureOrigin.EXECUTION
    assert projected.primary_failure_code == "action_dispatch_uncertain"
    assert projected.primary_failure_phase == "dispatch_wait"
    assert projected.primary_diagnostic_ref.endswith("a" * 24)
    assert projected.recovery_failure_codes == ("post_action_acquisition_failed",)
    assert projected.secondary_failure_codes == ("cleanup_exception",)
    assert projected.cleanup_failure_code == "cleanup_exception"
    assert projected.cleanup_diagnostic is not None
    assert projected.cleanup_diagnostic.phase.value == "cleanup"
    assert projected.cleanup_diagnostic.exception_type == "TimeoutError"
    assert projected.cleanup_diagnostic.traceback_ref.startswith("traceback:sha256:")


def test_instrumentation_does_not_reconstruct_unresolved_runtime_state() -> None:
    recorder = SimpleNamespace(step_completed=lambda *_args: None)

    resolved = BenchmarkInstrumentation(trace_recorder=recorder)
    resolved.step_completed(
        1,
        SimpleNamespace(
            status_after=RunStatus.RUNNING,
            runtime_failure=None,
        ),
    )
    assert resolved.failure_origin is CaseFailureOrigin.NONE
    assert resolved.primary_execution_failure_code == ""

    unresolved = BenchmarkInstrumentation(trace_recorder=recorder)
    unresolved.step_completed(
        1,
        SimpleNamespace(
            status_after=RunStatus.BLOCKED,
            runtime_failure=None,
        ),
    )
    assert unresolved.failure_origin is CaseFailureOrigin.NONE
    assert unresolved.primary_execution_failure_code == ""
    assert unresolved.primary_execution_failure_phase == ""


def test_custom_metric_cannot_override_canonical_metric() -> None:
    instrumentation = BenchmarkInstrumentation()
    with pytest.raises(ValueError, match="canonical"):
        instrumentation.increment("observations", 99)


def test_dynamic_tool_metrics_are_canonical_and_projected() -> None:
    instrumentation = BenchmarkInstrumentation(
        valid_tool_call_count=2,
        zero_tool_call_count=1,
        multiple_tool_call_count=1,
        unknown_tool_call_count=1,
        invalid_tool_argument_count=1,
        stale_tool_catalog_count=1,
        tool_catalog_count=7,
        tool_catalog_bytes=2048,
        evidence_tokens=123,
    )

    projected = project_case_result("case", None, instrumentation, 1.0, "display")

    for name, expected in {
        "valid_tool_call_count": 2,
        "zero_tool_call_count": 1,
        "multiple_tool_call_count": 1,
        "unknown_tool_call_count": 1,
        "invalid_tool_argument_count": 1,
        "stale_tool_catalog_count": 1,
        "tool_catalog_count": 7,
        "tool_catalog_bytes": 2048,
        "evidence_tokens": 123,
    }.items():
        assert projected.measurements[name].value == expected


def test_projection_defends_against_direct_custom_metric_collision() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.custom_metrics["observations"] = 99
    projected = project_case_result("case", None, instrumentation, 1.0, "display only")
    assert projected.case_failure_code == "metric_name_collision"
    assert projected.failure_origin is CaseFailureOrigin.NONE
    assert projected.measurements["observations"].value == 0


def test_metric_collision_preserves_runtime_and_component_facts_independently() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_failure(
        CaseFailureOrigin.ACTION_EVALUATION,
        "action_outcome_projector_exception",
        RuntimeError("private detail"),
    )
    instrumentation.custom_metrics["observations"] = 99
    projected = project_case_result(
        "case",
        _result("runtime_exception"),
        instrumentation,
        1.0,
        "display only",
        final_snapshot=_snapshot(
            runtime_failure=RuntimeFailure(
                FailureStage.CONTROL,
                FailureKind.REJECTED,
                "runtime_exception",
            )
        ),
    )
    assert projected.runtime_reason_code == "runtime_exception"
    assert projected.case_failure_code == "runtime_exception"
    assert projected.failure_origin is CaseFailureOrigin.ACTION_EVALUATION
    assert projected.failure_code == "action_outcome_projector_exception"
    assert projected.exception_class == "RuntimeError"
    assert projected.harness_integrity_code == "metric_name_collision"
    assert projected.harness_integrity_failures == 1
    assert projected.measurements["observations"].value == 2


def test_watchdog_remains_primary_when_cleanup_also_fails() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_watchdog("case_timeout", TimeoutError())
    instrumentation.record_cleanup_failure("cleanup_exception", RuntimeError("private cleanup detail"))
    projected = project_case_result(
        "case",
        None,
        instrumentation,
        1.0,
        "timeout; cleanup failed",
        timeout_snapshot=_snapshot(observations=3, executions=1, turns=1),
    )
    assert projected.case_failure_code == "case_timeout"
    assert projected.failure_origin is CaseFailureOrigin.NONE
    assert projected.termination_origin == "harness_watchdog"
    assert projected.cleanup_failure_code == "cleanup_exception"
    assert projected.measurements["cleanup_failures"].value == 1


def test_done_with_cleanup_only_is_not_reported_as_success() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_cleanup_failure("cleanup_exception", RuntimeError("private cleanup detail"))
    result = _result("task_complete")
    result.status = RunStatus.DONE
    result.runtime_failure = None
    projected = project_case_result("case", result, instrumentation, 1.0, "cleanup failed")
    assert projected.case_failure_code == "cleanup_exception"
    assert projected.failure_origin is CaseFailureOrigin.NONE
    assert projected.termination_origin == "cleanup"


@pytest.mark.parametrize(
    "request_kind",
    ("policy_request", "wait_refresh", "confirmation_refresh", "post_action_fallback"),
)
def test_snapshot_request_kind_cannot_infer_component_origin(
    request_kind: str,
) -> None:
    snapshot = replace(
        _snapshot(reason="observation_acquisition_failed"),
        latest_acquisition_request_kind=request_kind,
        latest_attempt_operation=("execute" if request_kind == "post_action_fallback" else "capture"),
        latest_attempt_reason_code="capture_failed",
    )
    returned_result = _result("observation_acquisition_failed")
    returned_result.failure_code = (
        AgentFailureCode.POST_ACTION_ACQUISITION_FAILED
        if request_kind == "post_action_fallback"
        else AgentFailureCode.OBSERVATION_ACQUISITION_FAILED
    )
    returned_result.runtime_failure = RuntimeFailure(
        FailureStage.ACQUISITION,
        FailureKind.CALL_FAILED,
        str(returned_result.failure_code),
    )
    returned = project_case_result(
        "returned",
        returned_result,
        BenchmarkInstrumentation(),
        1.0,
        "failed",
        final_snapshot=snapshot,
    )
    thrown_metrics = BenchmarkInstrumentation()
    expected = observation_failure_origin(request_kind)
    thrown_metrics.record_failure(expected, "capture_exception", RuntimeError("private"))
    thrown = project_case_result(
        "thrown",
        None,
        thrown_metrics,
        1.0,
        "failed",
        final_snapshot=snapshot,
    )
    assert returned.failure_origin is CaseFailureOrigin.NONE
    assert thrown.failure_origin is expected
    assert returned.failure_facts.component_exception_class == ""
    assert thrown.failure_facts.component_exception_class == "RuntimeError"


def test_dynamic_exception_class_is_safely_normalized_without_losing_component() -> None:
    instrumentation = BenchmarkInstrumentation()
    instrumentation.failure_origin = CaseFailureOrigin.ACTION_EVALUATION
    instrumentation.failure_code = "action_outcome_projector_exception"
    instrumentation.exception_class = "private.class/" + "x" * 200
    projected = project_case_result("case", _result("runtime_exception"), instrumentation, 1.0, "display only")
    assert projected.failure_origin is CaseFailureOrigin.ACTION_EVALUATION
    assert projected.failure_code == "action_outcome_projector_exception"
    assert projected.exception_class == "Exception"


def test_configured_zero_retry_is_measured_when_provider_returns_no_metadata() -> None:
    instrumentation = BenchmarkInstrumentation(configured_provider_retry_count=0)
    projected = project_case_result(
        "provider-unavailable",
        None,
        instrumentation,
        1.0,
        "provider unavailable",
    )
    measurement = projected.measurements["provider_retry_count"]
    assert measurement.measured
    assert measurement.value == 0
