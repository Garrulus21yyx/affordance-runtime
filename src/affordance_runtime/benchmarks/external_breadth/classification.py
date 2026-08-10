"""Typed, bounded attribution of one completed campaign case."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    TerminalReasonCode,
)


@dataclass(frozen=True)
class ClassifiedOutcome:
    outcome: MiniWobTaskOutcome
    source: str


def classify_case(result: BenchmarkCaseResult) -> ClassifiedOutcome:
    value = _metric(result, "official_success_count")
    if result.status == "done" and value == 1:
        return ClassifiedOutcome(MiniWobTaskOutcome.SUCCESS, "mechanical_verifier")
    if result.failure_origin is CaseFailureOrigin.CLEANUP:
        return ClassifiedOutcome(MiniWobTaskOutcome.CLEANUP_FAILURE, "typed_metric")
    if _metric(result, "sent_unknown_count"):
        return ClassifiedOutcome(MiniWobTaskOutcome.SENT_UNKNOWN, "typed_metric")
    if result.case_failure_code == "case_timeout":
        return ClassifiedOutcome(MiniWobTaskOutcome.CASE_TIMEOUT, "typed_case_code")
    if result.case_failure_code == "turn_budget_exhausted":
        return ClassifiedOutcome(MiniWobTaskOutcome.TURN_BUDGET_EXHAUSTED, "typed_case_code")
    policy = result.case_failure_code.removeprefix("policy_").casefold()
    if policy == "provider_unavailable":
        return ClassifiedOutcome(MiniWobTaskOutcome.PROVIDER_UNAVAILABLE, "typed_policy_failure")
    if policy == "timeout":
        return ClassifiedOutcome(MiniWobTaskOutcome.PROVIDER_TIMEOUT, "typed_policy_failure")
    if policy in {"invalid_response", "schema_error", "refused"}:
        outcome = (
            MiniWobTaskOutcome.PROVIDER_REFUSED
            if policy == "refused"
            else MiniWobTaskOutcome.STRUCTURED_OUTPUT_FAILURE
        )
        return ClassifiedOutcome(outcome, "typed_policy_failure")
    reason = result.terminal_reason_code
    if reason is TerminalReasonCode.NO_PROGRESS_REPETITION:
        return ClassifiedOutcome(MiniWobTaskOutcome.NO_PROGRESS_REPETITION, "typed_runtime_reason")
    if reason is TerminalReasonCode.INVALID_ACTION_PARAMETERS:
        return ClassifiedOutcome(MiniWobTaskOutcome.WRONG_PARAMETERS, "typed_runtime_reason")
    if reason is TerminalReasonCode.DESTINATION_OUTSIDE_CURRENT_PAGE:
        return ClassifiedOutcome(MiniWobTaskOutcome.WRONG_DESTINATION, "typed_runtime_reason")
    if reason is TerminalReasonCode.OBSERVATION_CAPABILITY_NOT_OFFERED:
        return ClassifiedOutcome(MiniWobTaskOutcome.OBSERVATION_COVERAGE_FAILURE, "typed_runtime_reason")
    if (
        reason is TerminalReasonCode.ACTION_OUTSIDE_ACTION_SPACE
        and result.last_action_space_option_count == 0
    ):
        return ClassifiedOutcome(MiniWobTaskOutcome.NO_ACTION_OFFERED, "typed_runtime_reason")
    if reason is not None:
        return ClassifiedOutcome(MiniWobTaskOutcome.RUNTIME_REJECTED, "typed_runtime_reason")
    if result.last_decision_type == "Abort":
        return ClassifiedOutcome(MiniWobTaskOutcome.POLICY_ABORTED, "typed_last_decision")
    if result.status == "waiting_user":
        if result.last_decision_type == "AskUser" or result.pending_kind == "user_question":
            return ClassifiedOutcome(MiniWobTaskOutcome.ASK_USER_UNRESOLVED, "typed_pending_kind")
        if result.pending_kind == "unknown_effect":
            return ClassifiedOutcome(
                MiniWobTaskOutcome.WAITING_USER_EFFECT_UNKNOWN, "typed_pending_kind",
            )
        if result.latest_task_status == "unknown":
            return ClassifiedOutcome(MiniWobTaskOutcome.WAITING_USER_TASK_UNKNOWN, "typed_task_status")
    origin = _ORIGIN_OUTCOMES.get(result.failure_origin)
    if origin is not None:
        return ClassifiedOutcome(origin, "typed_failure_origin")
    if result.failure_reason or result.failure_code or result.exception_class:
        return ClassifiedOutcome(
            MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE, "bounded_unclassified_failure",
        )
    return ClassifiedOutcome(MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE, "bounded_fallback")


_ORIGIN_OUTCOMES = {
    CaseFailureOrigin.ENVIRONMENT_RESET: MiniWobTaskOutcome.RESET_FAILURE,
    CaseFailureOrigin.INITIAL_OBSERVATION: MiniWobTaskOutcome.INITIAL_OBSERVATION_FAILURE,
    CaseFailureOrigin.OBSERVATION_PROJECTION: MiniWobTaskOutcome.PROJECTION_FAILURE,
    CaseFailureOrigin.POLICY_DECISION: MiniWobTaskOutcome.POLICY_DECISION_FAILURE,
    CaseFailureOrigin.CURRENTNESS: MiniWobTaskOutcome.CURRENTNESS_FAILURE,
    CaseFailureOrigin.EXECUTION: MiniWobTaskOutcome.EXECUTION_FAILURE,
    CaseFailureOrigin.POST_ACTION_OBSERVATION: MiniWobTaskOutcome.POST_OBSERVATION_FAILURE,
    CaseFailureOrigin.ACTION_EVALUATION: MiniWobTaskOutcome.ACTION_EVALUATOR_FAILURE,
    CaseFailureOrigin.TASK_EVALUATION: MiniWobTaskOutcome.TASK_EVALUATOR_FAILURE,
    CaseFailureOrigin.HARNESS_WATCHDOG: MiniWobTaskOutcome.CASE_TIMEOUT,
    CaseFailureOrigin.CLEANUP: MiniWobTaskOutcome.CLEANUP_FAILURE,
    CaseFailureOrigin.ENVIRONMENT_FACTORY: MiniWobTaskOutcome.ENVIRONMENT_FAILURE,
    CaseFailureOrigin.TASK_FACTORY: MiniWobTaskOutcome.ENVIRONMENT_FAILURE,
    CaseFailureOrigin.COMPOSITION_FACTORY: MiniWobTaskOutcome.ENVIRONMENT_FAILURE,
    CaseFailureOrigin.LOOP_CONSTRUCTION: MiniWobTaskOutcome.ENVIRONMENT_FAILURE,
    CaseFailureOrigin.SESSION_START: MiniWobTaskOutcome.INITIAL_OBSERVATION_FAILURE,
    CaseFailureOrigin.ACTION_BINDING: MiniWobTaskOutcome.RUNTIME_REJECTED,
    CaseFailureOrigin.DECISION_CONTROL: MiniWobTaskOutcome.RUNTIME_REJECTED,
    CaseFailureOrigin.UNKNOWN: MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE,
}


def _metric(result: BenchmarkCaseResult, name: str) -> int | float:
    item = result.measurements.get(name)
    value = item.value if item is not None and item.measured else 0
    return value if isinstance(value, int | float) and not isinstance(value, bool) else 0
