"""Benchmark-only projection from typed Runtime and fixed-size session facts."""

from __future__ import annotations

import re
from dataclasses import fields
from enum import Enum
from typing import Any, cast

from affordance_runtime.agent import AgentFailureCode, AgentLoopStatus
from affordance_runtime.agent.session_snapshot import PartialEpisodeSnapshot
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    FailureFacts,
    MetricMeasurement,
    TerminalReasonCode,
)
from affordance_runtime.benchmarks.target_loop.failure_origin import observation_failure_origin
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.metric_registry import canonical_metric_collisions
from affordance_runtime.benchmarks.target_loop.terminal_reasons import project_terminal_reason_code

_BOUNDED_CODE = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
_ACQUISITION_FAILURE_CODES = {
    item.value for item in AgentFailureCode
    if item is not AgentFailureCode.NO_PROGRESS_REPETITION
}
_POST_ACTION_FAILURE_CODES = {
    AgentFailureCode.POST_ACTION_CAPABILITY_UNAVAILABLE.value,
    AgentFailureCode.POST_ACTION_ACQUISITION_FAILED.value,
    AgentFailureCode.POST_ACTION_FRESHNESS_INVALID.value,
    AgentFailureCode.POST_ACTION_ORIGIN_INVALID.value,
}


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
    runtime_reason = _runtime_reason(result, metadata)
    agent_failure = _agent_failure_code(result)
    component_origin, normalized_component_code = _component_failure(
        instrumentation, metadata, agent_failure,
    )
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
    public_runtime_failure = runtime_reason if _is_failure_result(result) else ""
    if (
        result is None
        and not public_runtime_failure
        and component_origin is CaseFailureOrigin.NONE
        and not instrumentation.watchdog_code
        and not cleanup_code
        and not integrity_code
    ):
        public_runtime_failure = "runtime_failure"
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
    )
    case_failure_code = _primary_failure_code(facts)
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
        termination_origin=_termination_origin(
            result,
            component_origin,
            bool(instrumentation.watchdog_code),
            bool(instrumentation.cleanup_failures),
        ),
        case_failure_code=case_failure_code,
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


def public_case_evidence(result: BenchmarkCaseResult) -> dict[str, object]:
    """Serialize every declared public case field from one schema authority."""

    return {
        "schema_version": result.case_schema_version,
        **{
            item.name: _json_value(getattr(result, item.name))
            for item in fields(BenchmarkCaseResult)
            if item.name != "failure_reason"
        },
    }


def decode_public_case_evidence(payload: dict[str, object]) -> BenchmarkCaseResult:
    """Validate and reconstruct the complete public typed case evidence view."""

    expected = {
        item.name for item in fields(BenchmarkCaseResult) if item.name != "failure_reason"
    } | {"schema_version"}
    if set(payload) != expected:
        raise ValueError("public case evidence fields do not match the declared schema")
    if payload["schema_version"] != payload["case_schema_version"]:
        raise ValueError("public case schema identity is inconsistent")
    if payload["schema_version"] != "target-loop-case.v6":
        raise ValueError("public case evidence schema is unsupported")
    measurements = {}
    metric_fields = {item.name for item in fields(MetricMeasurement)}
    for name, value in _dict(payload["measurements"]).items():
        if not isinstance(name, str) or not isinstance(value, dict) or set(value) != metric_fields:
            raise ValueError("public case metric evidence is malformed")
        measurements[name] = MetricMeasurement(**value)
    raw_facts = _dict(payload["failure_facts"])
    fact_fields = {item.name for item in fields(FailureFacts)}
    if set(raw_facts) != fact_fields:
        raise ValueError("public failure facts are incomplete")
    if any(not isinstance(value, str) for value in raw_facts.values()):
        raise TypeError("public failure facts must use strings")
    raw_origin = raw_facts["component_origin"]
    assert isinstance(raw_origin, str)
    facts = FailureFacts(
        runtime_reason_code=raw_facts["runtime_reason_code"],
        agent_failure_code=raw_facts["agent_failure_code"],
        policy_failure_code=raw_facts["policy_failure_code"],
        component_origin=CaseFailureOrigin(raw_origin),
        component_code=raw_facts["component_code"],
        component_exception_class=raw_facts["component_exception_class"],
        watchdog_code=raw_facts["watchdog_code"],
        cleanup_code=raw_facts["cleanup_code"],
        cleanup_exception_class=raw_facts["cleanup_exception_class"],
        harness_integrity_code=raw_facts["harness_integrity_code"],
    )
    values = {
        item.name: payload[item.name]
        for item in fields(BenchmarkCaseResult)
        if item.name != "failure_reason"
    }
    values["failure_reason"] = ""
    values["measurements"] = measurements
    values["failure_facts"] = facts
    failure_origin = values["failure_origin"]
    if not isinstance(failure_origin, str):
        raise ValueError("public failure origin is malformed")
    values["failure_origin"] = CaseFailureOrigin(failure_origin)
    terminal = values["terminal_reason_code"]
    if terminal is not None and not isinstance(terminal, str):
        raise ValueError("terminal reason code is malformed")
    values["terminal_reason_code"] = TerminalReasonCode(terminal) if terminal else None
    return BenchmarkCaseResult(**cast(Any, values))


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, FailureFacts):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, MetricMeasurement):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _dict(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("public case evidence object is malformed")
    return value


def _metric_snapshot(instrumentation, timeout_snapshot, final_snapshot):
    if instrumentation.watchdog_code:
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


def _primary_failure_code(facts: FailureFacts) -> str:
    return (
        facts.watchdog_code
        or (f"policy_{facts.policy_failure_code}" if facts.policy_failure_code else "")
        or facts.agent_failure_code
        or facts.runtime_reason_code
        or facts.component_code
        or facts.cleanup_code
        or facts.harness_integrity_code
    )


def _agent_failure_code(result) -> str:
    if result is not None and result.failure_code is not None:
        return str(result.failure_code)
    return ""


def _component_failure(
    instrumentation, snapshot, agent_failure: str,
) -> tuple[CaseFailureOrigin, str]:
    origin = instrumentation.failure_origin
    code = instrumentation.failure_code
    if origin not in {CaseFailureOrigin.NONE, CaseFailureOrigin.UNKNOWN} or snapshot is None:
        return origin, code
    if (
        snapshot.latest_acquisition_request_kind
        and agent_failure in _ACQUISITION_FAILURE_CODES
    ):
        return (
            observation_failure_origin(snapshot.latest_acquisition_request_kind),
            snapshot.latest_attempt_reason_code or code or agent_failure,
        )
    if agent_failure in _POST_ACTION_FAILURE_CODES:
        return (
            CaseFailureOrigin.POST_ACTION_OBSERVATION,
            snapshot.latest_attempt_reason_code or code or agent_failure,
        )
    if snapshot.latest_attempt_operation == "execute":
        return CaseFailureOrigin.EXECUTION, snapshot.latest_attempt_reason_code or code
    return origin, code


def _is_failure_result(result) -> bool:
    return bool(result is None or result.status is not AgentLoopStatus.DONE)


def _termination_origin(
    result,
    origin: CaseFailureOrigin,
    watchdog: bool = False,
    cleanup: bool = False,
) -> str:
    if watchdog or origin is CaseFailureOrigin.HARNESS_WATCHDOG:
        return "harness_watchdog"
    if origin is not CaseFailureOrigin.NONE:
        return "component"
    if result is not None and _is_failure_result(result):
        return "runtime"
    if cleanup:
        return "cleanup"
    return "runtime"


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
            if metadata is not None else None
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
