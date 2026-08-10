from __future__ import annotations

import pytest

from affordance_runtime.agent import AgentFailureCode
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    FailureFacts,
    MetricMeasurement,
    TerminalReasonCode,
)
from affordance_runtime.model_boundary.failures import ModelFailureKind


def _result(**changes) -> BenchmarkCaseResult:
    values = {
        "case_id": "miniwob-60-01",
        "status": "failed",
        "execution_completed": True,
        "failure_reason": "",
        "latency_ms": 1.0,
        "measurements": {
            "official_success_count": MetricMeasurement(0, True),
            "cleanup_failures": MetricMeasurement(0, True),
            "sent_unknown_count": MetricMeasurement(0, True),
        },
    }
    values.update(changes)
    return BenchmarkCaseResult(**values)


def test_success_provider_and_no_progress_are_typed_separately() -> None:
    success = _result(
        status="done",
        measurements={
            "official_success_count": MetricMeasurement(1, True),
            "cleanup_failures": MetricMeasurement(0, True),
            "sent_unknown_count": MetricMeasurement(0, True),
        },
    )
    assert classify_case(success).outcome is MiniWobTaskOutcome.SUCCESS
    policy_facts = FailureFacts(policy_failure_code="provider_unavailable")
    provider = _result(
        case_failure_code="policy_provider_unavailable",
        last_policy_failure_code="provider_unavailable",
        failure_facts=policy_facts,
    )
    assert classify_case(provider).outcome is MiniWobTaskOutcome.PROVIDER_UNAVAILABLE
    progress_facts = FailureFacts(agent_failure_code="no_progress_repetition")
    repeated = _result(
        terminal_reason_code=TerminalReasonCode.NO_PROGRESS_REPETITION,
        case_failure_code="no_progress_repetition",
        agent_failure_code="no_progress_repetition",
        failure_facts=progress_facts,
    )
    assert classify_case(repeated).outcome is MiniWobTaskOutcome.NO_PROGRESS_REPETITION


def test_timeout_and_runtime_rejection_do_not_use_free_text() -> None:
    timeout_facts = FailureFacts(watchdog_code="case_timeout")
    timeout = _result(
        case_failure_code="case_timeout",
        termination_origin="harness_watchdog",
        watchdog_triggered=True,
        failure_facts=timeout_facts,
    )
    assert classify_case(timeout).outcome is MiniWobTaskOutcome.CASE_TIMEOUT
    rejected_facts = FailureFacts(runtime_reason_code="invalid_action_parameters")
    rejected = _result(
        status="blocked",
        terminal_reason_code=TerminalReasonCode.INVALID_ACTION_PARAMETERS,
        case_failure_code="invalid_action_parameters",
        runtime_reason_code="invalid_action_parameters",
        failure_facts=rejected_facts,
    )
    assert classify_case(rejected).outcome is MiniWobTaskOutcome.WRONG_PARAMETERS


def test_integrity_watchdog_cleanup_and_success_precedence() -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        _result(
            status="done",
            harness_integrity_code="metric_name_collision",
            harness_integrity_failures=1,
            measurements={
                "official_success_count": MetricMeasurement(1, True),
                "cleanup_failures": MetricMeasurement(0, True),
                "sent_unknown_count": MetricMeasurement(0, True),
            },
        )
    integrity = _result(
        case_failure_code="metric_name_collision",
        harness_integrity_code="metric_name_collision",
        harness_integrity_failures=1,
        failure_facts=FailureFacts(harness_integrity_code="metric_name_collision"),
    )
    assert classify_case(integrity).outcome is MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE
    watchdog = _result(
        case_failure_code="case_timeout",
        termination_origin="harness_watchdog",
        watchdog_triggered=True,
        failure_facts=FailureFacts(watchdog_code="case_timeout"),
        measurements={
            "official_success_count": MetricMeasurement(0, True),
            "cleanup_failures": MetricMeasurement(1, True),
            "sent_unknown_count": MetricMeasurement(1, True),
        },
    )
    assert classify_case(watchdog).outcome is MiniWobTaskOutcome.CASE_TIMEOUT


@pytest.mark.parametrize(
    ("base_facts", "expected"),
    (
        (
            FailureFacts(
                component_origin=CaseFailureOrigin.EXECUTION,
                component_code="execution_exception",
            ),
            MiniWobTaskOutcome.EXECUTION_FAILURE,
        ),
        (
            FailureFacts(runtime_reason_code="runtime_failure"),
            MiniWobTaskOutcome.RUNTIME_REJECTED,
        ),
        (
            FailureFacts(policy_failure_code="provider_unavailable"),
            MiniWobTaskOutcome.PROVIDER_UNAVAILABLE,
        ),
    ),
)
def test_adding_cleanup_preserves_existing_primary_classification(
    base_facts, expected,
) -> None:
    from dataclasses import replace

    with_cleanup = replace(
        base_facts,
        cleanup_code="cleanup_exception",
        cleanup_exception_class="RuntimeError",
    )
    changes = {
        "case_failure_code": (
            f"policy_{base_facts.policy_failure_code}"
            if base_facts.policy_failure_code
            else base_facts.runtime_reason_code or base_facts.component_code
        ),
        "termination_origin": (
            "component"
            if base_facts.component_origin is not CaseFailureOrigin.NONE else "runtime"
        ),
        "runtime_reason_code": base_facts.runtime_reason_code,
        "last_policy_failure_code": base_facts.policy_failure_code,
        "failure_origin": base_facts.component_origin,
        "failure_code": base_facts.component_code,
        "cleanup_failure_code": "cleanup_exception",
        "cleanup_exception_class": "RuntimeError",
        "cleanup_failures": 1,
        "failure_facts": with_cleanup,
    }
    assert classify_case(_result(**changes)).outcome is expected


@pytest.mark.parametrize("kind", tuple(ModelFailureKind))
def test_every_policy_failure_kind_has_a_typed_outcome(kind) -> None:
    facts = FailureFacts(policy_failure_code=kind.value)
    result = _result(
        case_failure_code=f"policy_{kind.value}",
        last_policy_failure_code=kind.value,
        failure_facts=facts,
    )
    assert classify_case(result).outcome is not MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE


@pytest.mark.parametrize("code", tuple(AgentFailureCode))
def test_every_agent_failure_code_has_a_typed_outcome(code) -> None:
    facts = FailureFacts(agent_failure_code=code.value)
    result = _result(
        case_failure_code=code.value,
        agent_failure_code=code.value,
        terminal_reason_code=(
            TerminalReasonCode.NO_PROGRESS_REPETITION
            if code is AgentFailureCode.NO_PROGRESS_REPETITION else None
        ),
        failure_facts=facts,
    )
    assert classify_case(result).outcome is not MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE
