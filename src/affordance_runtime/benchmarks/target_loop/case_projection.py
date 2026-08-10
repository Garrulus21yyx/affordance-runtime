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
    case_failure_code = _case_failure_code(result, instrumentation, runtime_reason)
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
        termination_origin=_termination_origin(result, instrumentation),
        case_failure_code=case_failure_code,
        partial_episode_available=timeout_snapshot is not None,
        latest_semantic_attempt_key_digest=(
            metadata.latest_semantic_attempt_key_digest if metadata else ""
        ),
        same_attempt_streak=metadata.same_attempt_streak if metadata else 0,
        no_progress_count=metadata.no_progress_count if metadata else 0,
        last_progress_event_type=metadata.last_progress_event_type if metadata else "",
        failure_origin=_failure_origin(result, instrumentation, runtime_reason),
        failure_code=instrumentation.failure_code or _agent_failure_code(result, runtime_reason),
        exception_class=instrumentation.exception_class,
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
    )


def _metric_snapshot(instrumentation, timeout_snapshot, final_snapshot):
    if instrumentation.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG:
        return timeout_snapshot or final_snapshot
    return final_snapshot or timeout_snapshot


def _runtime_reason(result, snapshot) -> str:
    candidate = (
        result.reason_code
        if result is not None and result.reason_code
        else snapshot.latest_control_reason_code
        if snapshot is not None
        else ""
    )
    if not candidate:
        return ""
    return candidate if _BOUNDED_CODE.fullmatch(candidate) else "runtime_failure"


def _case_failure_code(result, instrumentation, runtime_reason: str) -> str:
    if instrumentation.failure_origin is CaseFailureOrigin.HARNESS_WATCHDOG:
        return "case_timeout"
    if instrumentation.failure_origin is CaseFailureOrigin.CLEANUP:
        return instrumentation.failure_code or "cleanup_exception"
    if result is not None and result.policy_failure is not None:
        return f"policy_{result.policy_failure.kind}"
    if result is not None and result.failure_code is not None:
        return str(result.failure_code)
    if runtime_reason and _is_failure_result(result):
        return runtime_reason
    if instrumentation.failure_code:
        return instrumentation.failure_code
    return "runtime_failure" if result is None else ""


def _agent_failure_code(result, runtime_reason: str) -> str:
    if result is not None and result.failure_code is not None:
        return str(result.failure_code)
    return runtime_reason if _is_failure_result(result) else ""


def _failure_origin(result, instrumentation, runtime_reason) -> CaseFailureOrigin:
    if instrumentation.failure_origin is not CaseFailureOrigin.NONE:
        return instrumentation.failure_origin
    if result is not None and result.failure_code is not None:
        if str(result.failure_code).startswith("post_action_"):
            return CaseFailureOrigin.POST_ACTION_OBSERVATION
    if runtime_reason and _is_failure_result(result):
        return CaseFailureOrigin.DECISION_CONTROL
    return CaseFailureOrigin.NONE


def _is_failure_result(result) -> bool:
    return bool(result is None or result.status is not AgentLoopStatus.DONE)


def _termination_origin(result, instrumentation) -> str:
    origin = instrumentation.failure_origin
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
    values.update(state.custom_metrics)
    return values
