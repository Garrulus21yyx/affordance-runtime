"""Benchmark-only projection from typed Runtime and fixed-size session facts."""

from __future__ import annotations

import re

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.agent.session_snapshot import PartialEpisodeSnapshot
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    MetricMeasurement,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.metric_registry import canonical_metric_collisions
from affordance_runtime.benchmarks.target_loop.terminal_reasons import project_terminal_reason_code

_BOUNDED_CODE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")


def project_case_result(
    case_id: str,
    result,
    instrumentation: BenchmarkInstrumentation,
    latency_ms: float,
    failure: str,
    *,
    timeout_snapshot: PartialEpisodeSnapshot | None = None,
    final_snapshot: PartialEpisodeSnapshot | None = None,
) -> BenchmarkCaseResult:
    """Apply one explicit typed precedence; human failure text is display-only."""
    metric_collisions = canonical_metric_collisions(instrumentation.custom_metrics)
    metadata = _metric_snapshot(instrumentation, timeout_snapshot, final_snapshot)
    sent_unknown = (
        result.sent_unknown_count
        if result is not None
        else metadata.sent_unknown_count
        if metadata is not None
        else 0
    )
    values = _metric_values(result, instrumentation, sent_unknown, metadata)
    measurements = {
        name: MetricMeasurement(value, True) for name, value in values.items()
    }
    measurements["duplicate_unknown_attempts"] = MetricMeasurement(
        values["duplicate_unknown_attempts"], True, sent_unknown,
    )
    measurements["stale_zero_call_violations"] = MetricMeasurement(
        values["stale_zero_call_violations"], True, int(values["stale_opportunities"]),
    )
    runtime_reason = _runtime_reason(result, metadata)
    case_failure_code = _case_failure_code(
        result, instrumentation, runtime_reason, bool(metric_collisions)
    )
    failure_origin = _failure_origin(result, instrumentation, runtime_reason, metadata)
    if metric_collisions and failure_origin is CaseFailureOrigin.NONE:
        failure_origin = CaseFailureOrigin.UNKNOWN
    agent_failure = _agent_failure_code(result)
    return BenchmarkCaseResult(
        case_id=case_id,
        status=str(result.status) if result else str(AgentLoopStatus.FAILED),
        execution_completed=result is not None and not failure,
        failure_reason=failure,
        latency_ms=latency_ms,
        measurements=measurements,
        terminal_reason_code=(
            project_terminal_reason_code(result.status, result.reason_code, result.failure_code)
            if result is not None else None
        ),
        termination_origin=_termination_origin(result, failure_origin),
        case_failure_code=case_failure_code,
        partial_episode_available=result is None and metadata is not None,
        latest_semantic_attempt_key_digest=(
            metadata.latest_semantic_attempt_key_digest if metadata else ""
        ),
        same_attempt_streak=metadata.same_attempt_streak if metadata else 0,
        no_progress_count=metadata.no_progress_count if metadata else 0,
        last_progress_event_type=metadata.last_progress_event_type if metadata else "",
        failure_origin=failure_origin,
        failure_code=_component_failure_code(
            instrumentation, failure_origin, case_failure_code
        ),
        exception_class=_safe_exception_class(
            _primary_exception_class(instrumentation, failure_origin)
        ),
        last_decision_type=metadata.last_decision_type if metadata else "",
        last_policy_failure_code=(
            str(result.policy_failure.kind)
            if result is not None and result.policy_failure is not None else ""
        ),
        last_action_space_option_count=(metadata.last_action_space_option_count if metadata else 0),
        last_world_target_count=metadata.last_world_target_count if metadata else 0,
        last_world_coverage=metadata.last_world_coverage if metadata else "",
        pending_kind=metadata.pending_kind if metadata else "",
        latest_task_status=metadata.latest_task_status if metadata else "",
        latest_action_evaluation_status=(
            metadata.latest_action_evaluation_status if metadata else ""
        ),
        runtime_reason_code=runtime_reason,
        agent_failure_code=agent_failure,
        cleanup_failure_code=_safe_code(
            instrumentation.cleanup_failure_code, "cleanup_exception"
        ) if instrumentation.cleanup_failures else "",
        cleanup_exception_class=_safe_exception_class(
            instrumentation.cleanup_exception_class
        ),
        cleanup_failures=instrumentation.cleanup_failures,
        watchdog_triggered=(
            instrumentation.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG
        ),
        harness_integrity_code="metric_name_collision" if metric_collisions else "",
        harness_integrity_failures=int(bool(metric_collisions)),
    )


def _metric_snapshot(instrumentation, timeout_snapshot, final_snapshot):
    if instrumentation.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG:
        return timeout_snapshot or final_snapshot
    return final_snapshot or timeout_snapshot


def _runtime_reason(result, snapshot) -> str:
    if result is not None:
        candidate = result.reason_code
    elif (
        snapshot is not None
        and snapshot.latest_control_status in {"failed", "blocked", "cancelled"}
    ):
        candidate = snapshot.latest_control_reason_code
    else:
        candidate = ""
    if not candidate:
        return ""
    return candidate if _BOUNDED_CODE.fullmatch(candidate) else "runtime_failure"


def _case_failure_code(
    result, instrumentation, runtime_reason: str, integrity_failure: bool
) -> str:
    if instrumentation.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG:
        return "case_timeout"
    if result is not None and result.status is not AgentLoopStatus.DONE and result.policy_failure is not None:
        return f"policy_{result.policy_failure.kind}"
    if result is not None and result.status is not AgentLoopStatus.DONE and result.failure_code is not None:
        return str(result.failure_code)
    if runtime_reason and _is_failure_result(result):
        return runtime_reason
    if instrumentation.failure_origin not in {
        CaseFailureOrigin.NONE, CaseFailureOrigin.CLEANUP,
    } and instrumentation.failure_code:
        return _safe_code(instrumentation.failure_code, "runtime_failure")
    if instrumentation.cleanup_failures:
        return _safe_code(
            instrumentation.cleanup_failure_code, "cleanup_exception"
        )
    if integrity_failure:
        return "metric_name_collision"
    return "runtime_failure" if result is None else ""


def _agent_failure_code(result) -> str:
    if result is not None and result.failure_code is not None:
        return str(result.failure_code)
    return ""


def _failure_origin(result, instrumentation, runtime_reason, snapshot) -> CaseFailureOrigin:
    if instrumentation.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG:
        return instrumentation.failure_origin
    if instrumentation.failure_origin not in {
        CaseFailureOrigin.NONE, CaseFailureOrigin.CLEANUP,
    }:
        return instrumentation.failure_origin
    if result is not None and result.status is not AgentLoopStatus.DONE and result.policy_failure is not None:
        return CaseFailureOrigin.POLICY_DECISION
    if result is not None and result.failure_code is not None:
        failure_code = str(result.failure_code)
        if failure_code.startswith("post_action_"):
            return CaseFailureOrigin.POST_ACTION_OBSERVATION
        request_kind = snapshot.latest_acquisition_request_kind if snapshot else ""
        if request_kind == "binding_refresh":
            return CaseFailureOrigin.ACTION_BINDING
        if request_kind == "currentness_refresh":
            return CaseFailureOrigin.CURRENTNESS
        return _runtime_origin(runtime_reason)
    if runtime_reason and _is_failure_result(result):
        return _runtime_origin(runtime_reason)
    if instrumentation.cleanup_failures:
        return CaseFailureOrigin.CLEANUP
    return CaseFailureOrigin.NONE


def _runtime_origin(reason: str) -> CaseFailureOrigin:
    exact = {
        "action_evaluation_invalid": CaseFailureOrigin.ACTION_EVALUATION,
        "task_evaluation_invalid": CaseFailureOrigin.TASK_EVALUATION,
        "action_result_lineage_mismatch": CaseFailureOrigin.EXECUTION,
        "action_not_dispatched": CaseFailureOrigin.EXECUTION,
        "invalid_currentness_probe_count": CaseFailureOrigin.EXECUTION,
        "stale_bound_request": CaseFailureOrigin.ACTION_BINDING,
        "binding_refresh_failed": CaseFailureOrigin.ACTION_BINDING,
        "currentness_refresh_failed": CaseFailureOrigin.CURRENTNESS,
        "observation_budget_exhausted": CaseFailureOrigin.DECISION_CONTROL,
        "turn_budget_exhausted": CaseFailureOrigin.DECISION_CONTROL,
        "abort_policy": CaseFailureOrigin.DECISION_CONTROL,
        "invalid_confirmation_decision": CaseFailureOrigin.DECISION_CONTROL,
        "confirmation_subject_unavailable": CaseFailureOrigin.DECISION_CONTROL,
        "already_satisfied": CaseFailureOrigin.DECISION_CONTROL,
    }
    return exact.get(reason, CaseFailureOrigin.UNKNOWN)


def _is_failure_result(result) -> bool:
    return bool(result is None or result.status is not AgentLoopStatus.DONE)


def _termination_origin(result, origin: CaseFailureOrigin) -> str:
    if origin is CaseFailureOrigin.HARNESS_WATCHDOG:
        return "harness_watchdog"
    if origin is CaseFailureOrigin.CLEANUP:
        return "cleanup"
    if origin is not CaseFailureOrigin.NONE:
        return "component"
    return "runtime" if result is not None else ""


def _metric_values(result, state, sent_unknown, snapshot) -> dict[str, int | float]:
    metadata = state.model_metadata
    values = {
        "observations": result.observation_count if result else snapshot.observation_count if snapshot else 0,
        "executions": result.execution_count if result else snapshot.execution_count if snapshot else 0,
        "currentness_probes": result.currentness_probe_count if result else snapshot.currentness_probe_count if snapshot else 0,
        "turns": result.control_transition_total_count if result else snapshot.completed_turn_count if snapshot else 0,
        "policy_calls": state.policy_calls,
        "semantic_judge_calls": state.semantic_judge_calls,
        "provider_attempts": state.provider_attempts,
        "confirmations": state.confirmations_submitted,
        "sent_unknown_count": sent_unknown,
        "duplicate_unknown_attempts": state.duplicate_unknown_attempts,
        "forbidden_effect_attempts": state.forbidden_effect_attempts,
        "stale_opportunities": state.stale_opportunities,
        "stale_zero_call_violations": state.stale_zero_call_violations,
        "effectful_dispatches": state.effectful_dispatches,
        "reset_acquisitions": state.environment_reset_acquisitions,
        "independent_capture_calls": state.environment_capture_calls,
        "post_action_acquisitions": state.environment_post_acquisitions,
        "provider_retry_count": (
            metadata.rate_limit_retry_count + metadata.transient_retry_count
            if metadata is not None else -1
        ),
        "prompt_tokens": state.prompt_tokens,
        "completion_tokens": state.completion_tokens,
        "total_tokens": state.total_tokens,
        "model_latency_ms": state.model_latency_ms,
        "cleanup_failures": state.cleanup_failures,
    }
    kind_counts = dict(
        result.control_transition_kind_counts
        if result is not None
        else snapshot.decision_kind_counts
        if snapshot is not None
        else ()
    )
    values.update({
        "ask_user_count": kind_counts.get("AskUser", 0),
        "wait_count": kind_counts.get("Wait", 0),
        "page_request_count": kind_counts.get("RequestActionPage", 0),
    })
    values.update({name: value for name, value in state.custom_metrics.items() if name not in values})
    return values


def _safe_code(value: str, fallback: str) -> str:
    return value if _BOUNDED_CODE.fullmatch(value) else fallback


def _primary_exception_class(
    instrumentation: BenchmarkInstrumentation,
    origin: CaseFailureOrigin,
) -> str:
    if origin is CaseFailureOrigin.CLEANUP:
        return instrumentation.cleanup_exception_class
    return instrumentation.exception_class


def _component_failure_code(
    instrumentation: BenchmarkInstrumentation,
    origin: CaseFailureOrigin,
    primary_code: str,
) -> str:
    if origin is CaseFailureOrigin.CLEANUP:
        return _safe_code(instrumentation.cleanup_failure_code, "cleanup_exception")
    if instrumentation.failure_origin not in {
        CaseFailureOrigin.NONE, CaseFailureOrigin.CLEANUP,
    } and instrumentation.failure_code:
        return _safe_code(instrumentation.failure_code, "runtime_failure")
    return primary_code


def _safe_exception_class(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 128 and value.replace("_", "").isalnum():
        return value
    return "Exception"
