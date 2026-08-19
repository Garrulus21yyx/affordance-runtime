"""Benchmark-only projection from typed Runtime and a bounded episode snapshot."""

from __future__ import annotations

import re

from affordance_runtime.agent import RunStatus
from affordance_runtime.agent.episode_snapshot import PartialEpisodeSnapshot
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.benchmarks.target_loop.case_evidence_codec import (
    decode_public_case_evidence,
    public_case_evidence,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    FailureFacts,
    MetricMeasurement,
)
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.legacy_case_projection import (
    project_legacy_case_fields,
)
from affordance_runtime.benchmarks.target_loop.metric_registry import canonical_metric_collisions
from affordance_runtime.evaluation import TaskOutcomeKind

__all__ = (
    "decode_public_case_evidence",
    "project_case_result",
    "public_case_evidence",
)

_BOUNDED_CODE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_BOUNDED_EXCEPTION = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


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
        getattr(result, "sent_unknown_count", 0)
        if result is not None
        else metadata.sent_unknown_count
        if metadata is not None
        else 0
    )
    values = _metric_values(result, instrumentation, sent_unknown, metadata)
    measurements = {name: MetricMeasurement(value, value is not None) for name, value in values.items()}
    measurements["duplicate_unknown_attempts"] = MetricMeasurement(
        values["duplicate_unknown_attempts"],
        True,
        sent_unknown,
    )
    stale_opportunities = values["stale_opportunities"]
    assert isinstance(stale_opportunities, int)
    measurements["stale_zero_call_violations"] = MetricMeasurement(
        values["stale_zero_call_violations"],
        True,
        stale_opportunities,
    )
    agent_failure = _agent_failure_code(result)
    component_origin, normalized_component_code = _component_failure(instrumentation)
    component_code = (
        _safe_code(normalized_component_code, "runtime_failure")
        if component_origin is not CaseFailureOrigin.NONE
        else ""
    )
    exception_class = _safe_exception_class(instrumentation.exception_class)
    policy_failure = getattr(result, "policy_failure", None) if result is not None else None
    if policy_failure is None and result is not None:
        last_step = getattr(result, "last_step", None)
        candidate = getattr(last_step, "decision", None)
        policy_failure = candidate if isinstance(candidate, PolicyFailure) else None
    policy_code = str(policy_failure.kind) if policy_failure is not None else ""
    cleanup_code = (
        _safe_code(instrumentation.cleanup_failure_code, "cleanup_exception")
        if instrumentation.cleanup_failures
        else ""
    )
    integrity_code = "metric_name_collision" if metric_collisions else ""
    canonical_runtime_failure = getattr(result, "runtime_failure", None) if result is not None else None
    public_runtime_failure = canonical_runtime_failure.code if canonical_runtime_failure is not None else ""
    if (
        result is None
        and not public_runtime_failure
        and component_origin is CaseFailureOrigin.NONE
        and not instrumentation.watchdog_code
        and not cleanup_code
        and not integrity_code
    ):
        public_runtime_failure = "runtime_failure"
    status = str(result.status) if result else str(RunStatus.FAILED)
    mission_outcome = str(getattr(result, "outcome", ""))
    supervisor_state = getattr(result, "supervisor_state", None)
    mission_last_ref = str(getattr(supervisor_state, "last_ref", "") or "")
    task_outcome = getattr(result, "task_outcome", None) if result is not None else None
    candidate_task_outcome_kind = (
        str(task_outcome.kind)
        if task_outcome is not None
        else metadata.task_outcome_kind
        if metadata is not None
        else ""
    )
    candidate_task_outcome_code = (
        task_outcome.code if task_outcome is not None else metadata.task_outcome_code if metadata is not None else ""
    )
    task_outcome_kind, task_outcome_code = (
        (candidate_task_outcome_kind, candidate_task_outcome_code)
        if candidate_task_outcome_kind
        and _task_outcome_matches_status(candidate_task_outcome_kind, status)
        else ("", "")
    )
    facts = FailureFacts(
        public_runtime_failure,
        agent_failure,
        policy_code,
        component_origin,
        component_code,
        exception_class,
        _safe_code(instrumentation.watchdog_code, "case_timeout") if instrumentation.watchdog_code else "",
        cleanup_code,
        _safe_exception_class(instrumentation.cleanup_exception_class),
        integrity_code,
        canonical_runtime_failure,
        task_outcome_kind,
        task_outcome_code,
    )
    legacy = project_legacy_case_fields(status, facts)
    return BenchmarkCaseResult(
        case_id=case_id,
        status=status,
        execution_completed=result is not None and not failure,
        failure_reason=failure,
        latency_ms=latency_ms,
        measurements=measurements,
        terminal_reason_code=legacy.terminal_reason_code,
        termination_origin=legacy.termination_origin,
        case_failure_code=legacy.case_failure_code,
        partial_episode_available=result is None and metadata is not None,
        latest_semantic_attempt_key_digest=(metadata.latest_semantic_attempt_key_digest if metadata else ""),
        same_attempt_streak=metadata.same_attempt_streak if metadata else 0,
        no_progress_count=metadata.no_progress_count if metadata else 0,
        last_progress_event_type=metadata.last_progress_event_type if metadata else "",
        failure_origin=component_origin,
        failure_code=component_code,
        exception_class=exception_class,
        last_decision_type=metadata.last_decision_type if metadata else "",
        last_policy_failure_code=policy_code,
        last_action_space_option_count=(metadata.last_action_space_option_count if metadata else 0),
        last_world_target_count=metadata.last_world_target_count if metadata else 0,
        last_world_coverage=metadata.last_world_coverage if metadata else "",
        pending_kind=(
            "user_question"
            if mission_outcome == "needs_user_input" and getattr(result, "user_question", "")
            else metadata.pending_kind
            if metadata
            else ""
        ),
        latest_task_status=metadata.latest_task_status if metadata else "",
        latest_action_observed_change=(metadata.latest_action_observed_change if metadata else ""),
        latest_action_local_postcondition=(metadata.latest_action_local_postcondition if metadata else ""),
        latest_action_evidence_method=(metadata.latest_action_evidence_method if metadata else ""),
        runtime_reason_code=public_runtime_failure,
        agent_failure_code=agent_failure,
        cleanup_failure_code=cleanup_code,
        cleanup_exception_class=_safe_exception_class(instrumentation.cleanup_exception_class),
        cleanup_failures=instrumentation.cleanup_failures,
        watchdog_triggered=(bool(instrumentation.watchdog_code)),
        harness_integrity_code=integrity_code,
        harness_integrity_failures=int(bool(metric_collisions)),
        mission_outcome=mission_outcome,
        mission_last_ref=mission_last_ref,
        failure_facts=facts,
    )


def _task_outcome_matches_status(kind: str, status: str) -> bool:
    return {
        TaskOutcomeKind.TERMINAL_SUCCESS.value: RunStatus.DONE.value,
        TaskOutcomeKind.TERMINAL_FAILURE.value: RunStatus.BLOCKED.value,
        TaskOutcomeKind.VERIFIER_UNAVAILABLE.value: RunStatus.WAITING_USER.value,
        TaskOutcomeKind.RUNNING_INCOMPLETE.value: RunStatus.RUNNING.value,
    }.get(kind) == status


def _metric_snapshot(instrumentation, timeout_snapshot, final_snapshot):
    if instrumentation.watchdog_code:
        return timeout_snapshot or final_snapshot
    return final_snapshot or timeout_snapshot


def _agent_failure_code(result) -> str:
    failure_code = getattr(result, "failure_code", None) if result is not None else None
    if failure_code is not None:
        return str(failure_code)
    return ""


def _component_failure(instrumentation) -> tuple[CaseFailureOrigin, str]:
    """Copy component-owned truth; snapshots and latest operations are non-authoritative."""

    return instrumentation.failure_origin, instrumentation.failure_code


def _metric_values(result, state, sent_unknown, snapshot) -> dict[str, int | float | None]:
    values = {
        "observations": result.observation_count if result else snapshot.observation_count if snapshot else 0,
        "executions": result.execution_count if result else snapshot.execution_count if snapshot else 0,
        "currentness_probes": state.currentness_probe_count
        if result
        else snapshot.currentness_probe_count
        if snapshot
        else 0,
        "turns": getattr(result, "step_count", 0)
        if result
        else snapshot.completed_turn_count
        if snapshot
        else 0,
        "policy_calls": state.policy_calls,
        "policy_schema_repair_count": state.policy_schema_repair_count,
        "goal_compiler_calls": state.goal_compiler_calls,
        "goal_compiler_provider_attempts": state.goal_compiler_provider_attempts,
        "goal_compiler_schema_repair_count": state.goal_compiler_schema_repair_count,
        "goal_compiler_contract_repair_count": state.goal_compiler_contract_repair_count,
        "goal_compiler_ready_count": state.goal_compiler_ready_count,
        "goal_compiler_unavailable_count": state.goal_compiler_unavailable_count,
        "tool_argument_repair_count": state.tool_argument_repair_count,
        "valid_tool_call_count": state.valid_tool_call_count,
        "zero_tool_call_count": state.zero_tool_call_count,
        "multiple_tool_call_count": state.multiple_tool_call_count,
        "unknown_tool_call_count": state.unknown_tool_call_count,
        "invalid_tool_argument_count": state.invalid_tool_argument_count,
        "stale_tool_catalog_count": state.stale_tool_catalog_count,
        "tool_grounding_gap_count": state.tool_grounding_gap_count,
        "tool_catalog_count": state.tool_catalog_count,
        "tool_catalog_bytes": state.tool_catalog_bytes,
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
        "provider_retry_count": state.provider_retry_count,
        "fallback_count": state.fallback_count,
        "prompt_tokens": state.prompt_tokens,
        "completion_tokens": state.completion_tokens,
        "total_tokens": state.total_tokens,
        "system_tokens": state.system_tokens,
        "task_plan_tokens": state.task_plan_tokens,
        "actor_world_tokens": state.actor_world_tokens,
        "history_tokens": state.history_tokens,
        "working_set_tokens": state.working_set_tokens,
        "evidence_tokens": state.evidence_tokens,
        "tool_schema_tokens": state.tool_schema_tokens,
        "image_estimated_tokens": state.image_estimated_tokens,
        "repair_tokens": state.repair_tokens,
        "estimated_total_tokens": state.estimated_total_tokens,
        "provider_reported_prompt_tokens": state.provider_reported_prompt_tokens,
        "admission_limit": state.admission_limit,
        "context_capacity_rejections": state.context_capacity_rejections,
        "model_latency_ms": state.model_latency_ms,
        "cleanup_failures": state.cleanup_failures,
        "observation_contract_exceptions": int(
            state.failure_origin
            in {
                CaseFailureOrigin.INITIAL_OBSERVATION,
                CaseFailureOrigin.OBSERVATION_PROJECTION,
                CaseFailureOrigin.POST_ACTION_OBSERVATION,
                CaseFailureOrigin.CURRENTNESS,
                CaseFailureOrigin.ACTION_BINDING,
            }
            and bool(state.exception_class)
        ),
    }
    kind_counts = _decision_kind_counts(result, state, snapshot)
    values.update(
        {
            "ask_user_count": kind_counts.get("AskUser", 0),
            "wait_count": kind_counts.get("Wait", 0),
            "page_request_count": kind_counts.get("RequestActionPage", 0),
        }
    )
    values.update({name: value for name, value in state.custom_metrics.items() if name not in values})
    return values


def _decision_kind_counts(result, instrumentation, snapshot) -> dict[str, int]:
    del result
    if instrumentation.policy_trace:
        counts: dict[str, int] = {}
        for event in instrumentation.policy_trace:
            name = str(event.get("outcome") or "")
            if name and name not in {"exception", "policy_failure"}:
                counts[name] = counts.get(name, 0) + 1
        return counts
    return dict(snapshot.decision_kind_counts) if snapshot is not None else {}


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
    if (
        instrumentation.failure_origin
        not in {
            CaseFailureOrigin.NONE,
            CaseFailureOrigin.CLEANUP,
        }
        and instrumentation.failure_code
    ):
        return _safe_code(instrumentation.failure_code, "runtime_failure")
    return primary_code


def _safe_exception_class(value: str) -> str:
    if not value:
        return ""
    if _BOUNDED_EXCEPTION.fullmatch(value) is not None:
        return value
    return "Exception"
