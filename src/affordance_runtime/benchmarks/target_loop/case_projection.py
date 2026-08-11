"""Benchmark-only projection from typed Runtime and fixed-size session facts."""

from __future__ import annotations

import re

from affordance_runtime.agent import AgentLoopStatus
from affordance_runtime.agent.session_snapshot import PartialEpisodeSnapshot
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
        result.sent_unknown_count
        if result is not None
        else metadata.sent_unknown_count
        if metadata is not None
        else 0
    )
    values = _metric_values(result, instrumentation, sent_unknown, metadata)
    measurements = {
        name: MetricMeasurement(value, value is not None) for name, value in values.items()
    }
    measurements["duplicate_unknown_attempts"] = MetricMeasurement(
        values["duplicate_unknown_attempts"], True, sent_unknown,
    )
    stale_opportunities = values["stale_opportunities"]
    assert isinstance(stale_opportunities, int)
    measurements["stale_zero_call_violations"] = MetricMeasurement(
        values["stale_zero_call_violations"], True, stale_opportunities,
    )
    agent_failure = _agent_failure_code(result)
    component_origin, normalized_component_code = _component_failure(instrumentation)
    component_code = (
        _safe_code(normalized_component_code, "runtime_failure")
        if component_origin is not CaseFailureOrigin.NONE else ""
    )
    exception_class = _safe_exception_class(
        instrumentation.exception_class
    )
    policy_code = (
        str(result.policy_failure.kind)
        if result is not None and result.policy_failure is not None else ""
    )
    cleanup_code = _safe_code(
        instrumentation.cleanup_failure_code, "cleanup_exception"
    ) if instrumentation.cleanup_failures else ""
    integrity_code = "metric_name_collision" if metric_collisions else ""
    canonical_runtime_failure = (
        getattr(result, "runtime_failure", None) if result is not None else None
    )
    public_runtime_failure = (
        canonical_runtime_failure.code if canonical_runtime_failure is not None else ""
    )
    if (
        result is None
        and not public_runtime_failure
        and component_origin is CaseFailureOrigin.NONE
        and not instrumentation.watchdog_code
        and not cleanup_code
        and not integrity_code
    ):
        public_runtime_failure = "runtime_failure"
    task_outcome = getattr(result, "task_outcome", None) if result is not None else None
    task_outcome_kind = (
        str(task_outcome.kind)
        if task_outcome is not None
        else metadata.task_outcome_kind
        if metadata is not None
        else ""
    )
    task_outcome_code = (
        task_outcome.code
        if task_outcome is not None
        else metadata.task_outcome_code
        if metadata is not None
        else ""
    )
    facts = FailureFacts(
        public_runtime_failure,
        agent_failure,
        policy_code,
        component_origin,
        component_code,
        exception_class,
        _safe_code(instrumentation.watchdog_code, "case_timeout")
        if instrumentation.watchdog_code else "",
        cleanup_code,
        _safe_exception_class(instrumentation.cleanup_exception_class),
        integrity_code,
        canonical_runtime_failure,
        task_outcome_kind,
        task_outcome_code,
    )
    status = str(result.status) if result else str(AgentLoopStatus.FAILED)
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
        latest_semantic_attempt_key_digest=(
            metadata.latest_semantic_attempt_key_digest if metadata else ""
        ),
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
        pending_kind=metadata.pending_kind if metadata else "",
        latest_task_status=metadata.latest_task_status if metadata else "",
        latest_action_evaluation_status=(
            metadata.latest_action_evaluation_status if metadata else ""
        ),
        runtime_reason_code=public_runtime_failure,
        agent_failure_code=agent_failure,
        cleanup_failure_code=cleanup_code,
        cleanup_exception_class=_safe_exception_class(
            instrumentation.cleanup_exception_class
        ),
        cleanup_failures=instrumentation.cleanup_failures,
        watchdog_triggered=(
            bool(instrumentation.watchdog_code)
        ),
        harness_integrity_code=integrity_code,
        harness_integrity_failures=int(bool(metric_collisions)),
        failure_facts=facts,
    )


def _metric_snapshot(instrumentation, timeout_snapshot, final_snapshot):
    if instrumentation.watchdog_code:
        return timeout_snapshot or final_snapshot
    return final_snapshot or timeout_snapshot


def _agent_failure_code(result) -> str:
    if result is not None and result.failure_code is not None:
        return str(result.failure_code)
    return ""


def _component_failure(instrumentation) -> tuple[CaseFailureOrigin, str]:
    """Copy component-owned truth; snapshots and latest operations are non-authoritative."""

    return instrumentation.failure_origin, instrumentation.failure_code


def _metric_values(result, state, sent_unknown, snapshot) -> dict[str, int | float | None]:
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
            if metadata is not None else state.configured_provider_retry_count
        ),
        "prompt_tokens": state.prompt_tokens,
        "completion_tokens": state.completion_tokens,
        "total_tokens": state.total_tokens,
        "model_latency_ms": state.model_latency_ms,
        "cleanup_failures": state.cleanup_failures,
        "observation_contract_exceptions": int(
            state.failure_origin in {
                CaseFailureOrigin.INITIAL_OBSERVATION,
                CaseFailureOrigin.OBSERVATION_PROJECTION,
                CaseFailureOrigin.POST_ACTION_OBSERVATION,
                CaseFailureOrigin.CURRENTNESS,
                CaseFailureOrigin.ACTION_BINDING,
            }
            and bool(state.exception_class)
        ),
    }
    values.update(_control_feedback_metrics(result, snapshot))
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


def _control_feedback_metrics(result, snapshot) -> dict[str, int]:
    transitions = tuple(getattr(result, "control_transitions", ())) if result is not None else ()
    feedback = tuple(
        (index, item.control_feedback)
        for index, item in enumerate(transitions)
        if item.control_feedback is not None
    )
    kind_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    code_counts: dict[str, int] = {}
    opportunity_counts = {1: 0, 2: 0}
    corrected_counts = {1: 0, 2: 0}
    scope_ordinals: dict[str, int] = {}
    for index, item in feedback:
        assert item is not None
        kind_counts[item.kind.value] = kind_counts.get(item.kind.value, 0) + 1
        source_counts[item.source.value] = source_counts.get(item.source.value, 0) + 1
        code_counts[item.code] = code_counts.get(item.code, 0) + 1
        if not item.consumes_issue_budget:
            continue
        ordinal = scope_ordinals.get(item.scope_digest, 0) + 1
        scope_ordinals[item.scope_digest] = ordinal
        if ordinal not in opportunity_counts or index + 1 >= len(transitions):
            continue
        opportunity_counts[ordinal] += 1
        following = transitions[index + 1]
        if _feedback_opportunity_corrected(item, following):
            corrected_counts[ordinal] += 1
    return {
        "feedback_repairable_rejection_count": kind_counts.get("repairable_rejection", 0),
        "feedback_no_information_gain_count": kind_counts.get("no_information_gain", 0),
        "feedback_strategy_transition_required_count": kind_counts.get(
            "strategy_transition_required", 0,
        ),
        "feedback_action_admission_source_count": source_counts.get("action_admission", 0),
        "feedback_action_page_source_count": source_counts.get("action_page", 0),
        "feedback_policy_observation_source_count": source_counts.get("policy_observation", 0),
        "feedback_action_evaluation_source_count": source_counts.get("action_evaluation", 0),
        "feedback_progress_event_source_count": source_counts.get("progress_event", 0),
        "feedback_context_delivery_count": (
            getattr(result, "control_feedback_delivery_count", 0)
            if result is not None else snapshot.control_feedback_delivery_count
            if snapshot is not None else 0
        ),
        "control_issue_budget_consumption_count": (
            getattr(result, "control_issue_consumption_count", 0)
            if result is not None else snapshot.control_issue_consumption_count
            if snapshot is not None else 0
        ),
        "control_repetition_termination_count": (
            getattr(result, "control_repetition_count", 0)
            if result is not None else snapshot.control_repetition_count
            if snapshot is not None else 0
        ),
        "first_opportunity_policy_decision_count": opportunity_counts[1],
        "first_opportunity_admission_corrected_count": corrected_counts[1],
        "second_opportunity_policy_decision_count": opportunity_counts[2],
        "second_opportunity_admission_corrected_count": corrected_counts[2],
        "strategy_transition_feedback_count": kind_counts.get(
            "strategy_transition_required", 0,
        ),
        "first_policy_repair_feedback_count": int(any(
            item is not None
            and item.kind.value == "repairable_rejection"
            and transitions[index].sequence == 1
            for index, item in feedback
        )),
        "repair_feedback_zero_call_violation_count": sum(
            bool(
                item is not None
                and item.kind.value == "repairable_rejection"
                and (
                    transitions[index].execution_attempts
                    or transitions[index].acquisition_attempts
                    or transitions[index].attempt_receipts
                )
            )
            for index, item in feedback
        ),
        "feedback_invalid_action_parameters_code_count": code_counts.get(
            "invalid_action_parameters", 0,
        ),
        "feedback_action_outside_action_space_code_count": code_counts.get(
            "action_outside_action_space", 0,
        ),
        "feedback_action_outside_current_page_code_count": code_counts.get(
            "action_outside_current_page", 0,
        ),
        "feedback_destination_outside_current_page_code_count": code_counts.get(
            "destination_outside_current_page", 0,
        ),
        "feedback_action_page_no_information_gain_code_count": code_counts.get(
            "action_page_no_information_gain", 0,
        ),
        "feedback_observation_no_information_gain_code_count": code_counts.get(
            "observation_no_information_gain", 0,
        ),
    }


def _feedback_opportunity_corrected(feedback, following) -> bool:
    """Apply the frozen owner-validation definition to the next ordinary root."""

    if following.control_feedback is not None:
        return False
    if feedback.source.value == "action_admission":
        return (
            following.admission is not None
            and following.admission.status.value in {"admitted", "confirmation_required"}
        )
    if feedback.source.value == "action_page":
        return following.decision_result == "page_changed"
    if feedback.source.value == "policy_observation":
        return following.reason_code == "observation_semantic_gain"
    return False


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
    if _BOUNDED_EXCEPTION.fullmatch(value) is not None:
        return value
    return "Exception"
