"""Typed, bounded attribution of one completed campaign case."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkCaseResult, TerminalReasonCode


@dataclass(frozen=True)
class ClassifiedOutcome:
    outcome: MiniWobTaskOutcome
    source: str


def classify_case(result: BenchmarkCaseResult) -> ClassifiedOutcome:
    value = _metric(result, "official_success_count")
    if result.status == "done" and value == 1:
        return ClassifiedOutcome(MiniWobTaskOutcome.SUCCESS, "mechanical_verifier")
    if _metric(result, "cleanup_failures"):
        return ClassifiedOutcome(MiniWobTaskOutcome.CLEANUP_FAILURE, "typed_metric")
    if _metric(result, "sent_unknown_count"):
        return ClassifiedOutcome(MiniWobTaskOutcome.SENT_UNKNOWN, "typed_metric")
    if result.case_failure_code == "case_timeout":
        return ClassifiedOutcome(MiniWobTaskOutcome.CASE_TIMEOUT, "typed_case_code")
    if result.case_failure_code == "turn_budget_exhausted":
        return ClassifiedOutcome(MiniWobTaskOutcome.TURN_BUDGET_EXHAUSTED, "typed_case_code")
    policy = result.policy_failure_kind.removeprefix("ModelFailureKind.").casefold()
    if policy == "provider_unavailable":
        return ClassifiedOutcome(MiniWobTaskOutcome.PROVIDER_UNAVAILABLE, "typed_policy_failure")
    if policy == "timeout":
        return ClassifiedOutcome(MiniWobTaskOutcome.PROVIDER_TIMEOUT, "typed_policy_failure")
    if policy in {"invalid_response", "schema_error", "refused"}:
        return ClassifiedOutcome(MiniWobTaskOutcome.STRUCTURED_OUTPUT_FAILURE, "typed_policy_failure")
    reason = result.terminal_reason_code
    if reason is TerminalReasonCode.NO_PROGRESS_REPETITION:
        return ClassifiedOutcome(MiniWobTaskOutcome.NO_PROGRESS_REPETITION, "typed_runtime_reason")
    if reason is TerminalReasonCode.INVALID_ACTION_PARAMETERS:
        return ClassifiedOutcome(MiniWobTaskOutcome.WRONG_PARAMETERS, "typed_runtime_reason")
    if reason is TerminalReasonCode.DESTINATION_OUTSIDE_CURRENT_PAGE:
        return ClassifiedOutcome(MiniWobTaskOutcome.WRONG_DESTINATION, "typed_runtime_reason")
    if reason is TerminalReasonCode.OBSERVATION_CAPABILITY_NOT_OFFERED:
        return ClassifiedOutcome(MiniWobTaskOutcome.OBSERVATION_COVERAGE_FAILURE, "typed_runtime_reason")
    if reason is not None:
        return ClassifiedOutcome(MiniWobTaskOutcome.RUNTIME_REJECTED, "typed_runtime_reason")
    if result.failure_reason:
        return ClassifiedOutcome(MiniWobTaskOutcome.ENVIRONMENT_FAILURE, "typed_harness_stage")
    return ClassifiedOutcome(MiniWobTaskOutcome.OTHER_TYPED_FAILURE, "fallback")


def _metric(result: BenchmarkCaseResult, name: str) -> int | float:
    item = result.measurements.get(name)
    value = item.value if item is not None and item.measured else 0
    return value if isinstance(value, int | float) and not isinstance(value, bool) else 0
