from __future__ import annotations

import pytest

from affordance_runtime.agent import AgentFailureCode
from affordance_runtime.agent.runtime_failure import (
    FailureKind,
    FailureStage,
    RuntimeFailure,
)
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
    success_facts = FailureFacts(
        task_outcome_kind="terminal_success",
        task_outcome_code="verified_success",
    )
    success = _result(
        status="done",
        latest_task_status="complete",
        failure_facts=success_facts,
        measurements={
            "official_success_count": MetricMeasurement(1, True),
            "cleanup_failures": MetricMeasurement(0, True),
            "sent_unknown_count": MetricMeasurement(0, True),
        },
    )
    assert classify_case(success).outcome is MiniWobTaskOutcome.SUCCESS
    spoofed_metric = _result(
        status="done",
        measurements={
            "official_success_count": MetricMeasurement(1, True),
            "cleanup_failures": MetricMeasurement(0, True),
            "sent_unknown_count": MetricMeasurement(0, True),
        },
    )
    assert classify_case(spoofed_metric).outcome is MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE
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


def test_canonical_runtime_stage_and_kind_own_classification() -> None:
    runtime_failure = RuntimeFailure(
        FailureStage.ACQUISITION,
        FailureKind.CAPABILITY_UNAVAILABLE,
        "future_capability_code",
    )
    facts = FailureFacts(
        runtime_reason_code=runtime_failure.code,
        runtime_failure=runtime_failure,
    )
    result = _result(
        case_failure_code=runtime_failure.code,
        runtime_reason_code=runtime_failure.code,
        failure_facts=facts,
    )

    classified = classify_case(result)
    assert classified.outcome is MiniWobTaskOutcome.OBSERVATION_COVERAGE_FAILURE
    assert classified.source == "canonical_runtime_failure"


def test_terminal_task_failure_is_not_runtime_rejected_or_metric_inferred() -> None:
    facts = FailureFacts(
        task_outcome_kind="terminal_failure",
        task_outcome_code="verified_terminal_task_failure",
    )
    result = _result(
        status="blocked",
        latest_task_status="blocked",
        terminal_reason_code=None,
        termination_origin="",
        case_failure_code="verified_terminal_task_failure",
        failure_facts=facts,
        measurements={
            "official_success_count": MetricMeasurement(1, True),
            "cleanup_failures": MetricMeasurement(0, True),
            "sent_unknown_count": MetricMeasurement(0, True),
        },
    )
    classified = classify_case(result)
    assert classified.outcome is MiniWobTaskOutcome.TASK_FAILED
    assert classified.source == "canonical_task_outcome"
    assert result.failure_facts.runtime_failure is None


def test_task_outcome_precedence_preserves_watchdog_runtime_and_cleanup_truth() -> None:
    task = dict(
        task_outcome_kind="terminal_failure",
        task_outcome_code="verified_terminal_task_failure",
    )
    cleanup_facts = FailureFacts(
        **task,
        cleanup_code="cleanup_exception",
        cleanup_exception_class="RuntimeError",
    )
    cleanup = _result(
        status="blocked",
        latest_task_status="blocked",
        terminal_reason_code=None,
        termination_origin="cleanup",
        case_failure_code="verified_terminal_task_failure",
        cleanup_failure_code="cleanup_exception",
        cleanup_exception_class="RuntimeError",
        cleanup_failures=1,
        failure_facts=cleanup_facts,
    )
    assert classify_case(cleanup).outcome is MiniWobTaskOutcome.TASK_FAILED

    watchdog_facts = FailureFacts(**task, watchdog_code="case_timeout")
    watchdog = _result(
        status="blocked",
        latest_task_status="blocked",
        terminal_reason_code=None,
        case_failure_code="case_timeout",
        termination_origin="harness_watchdog",
        watchdog_triggered=True,
        failure_facts=watchdog_facts,
    )
    assert classify_case(watchdog).outcome is MiniWobTaskOutcome.CASE_TIMEOUT

    runtime = RuntimeFailure(
        FailureStage.EXECUTION, FailureKind.CALL_FAILED, "execution_failed",
    )
    runtime_facts = FailureFacts(
        **task,
        runtime_reason_code=runtime.code,
        runtime_failure=runtime,
    )
    with_runtime = _result(
        status="blocked",
        latest_task_status="blocked",
        terminal_reason_code=TerminalReasonCode.BLOCKED_OTHER,
        case_failure_code=runtime.code,
        runtime_reason_code=runtime.code,
        failure_facts=runtime_facts,
    )
    assert classify_case(with_runtime).outcome is MiniWobTaskOutcome.EXECUTION_FAILURE


def test_verifier_unavailable_waiting_user_maps_only_from_canonical_outcome() -> None:
    facts = FailureFacts(
        task_outcome_kind="verifier_unavailable",
        task_outcome_code="missing_facts",
    )
    result = _result(
        status="waiting_user",
        latest_task_status="unknown",
        failure_facts=facts,
    )
    classified = classify_case(result)
    assert classified.outcome is MiniWobTaskOutcome.VERIFIER_UNKNOWN
    assert classified.source == "canonical_task_outcome"


@pytest.mark.parametrize(
    "stage",
    (FailureStage.EXECUTION, FailureStage.EVALUATION),
)
def test_production_invalid_outputs_have_total_canonical_classification(stage) -> None:
    failure = RuntimeFailure(stage, FailureKind.INVALID_OUTPUT, "invalid_component_output")
    facts = FailureFacts(runtime_reason_code=failure.code, runtime_failure=failure)
    classified = classify_case(_result(
        case_failure_code=failure.code,
        runtime_reason_code=failure.code,
        failure_facts=facts,
    ))
    assert classified.outcome is (
        MiniWobTaskOutcome.EXECUTION_FAILURE
        if stage is FailureStage.EXECUTION
        else MiniWobTaskOutcome.TASK_FAILED
    )


def test_typed_policy_code_specializes_canonical_call_failure() -> None:
    failure = RuntimeFailure(FailureStage.POLICY, FailureKind.CALL_FAILED, "timeout")
    facts = FailureFacts(policy_failure_code="timeout", runtime_failure=failure)
    classified = classify_case(_result(
        case_failure_code="policy_timeout",
        last_policy_failure_code="timeout",
        failure_facts=facts,
    ))
    assert classified.outcome is MiniWobTaskOutcome.PROVIDER_TIMEOUT
    assert classified.source == "canonical_runtime_failure"


def test_typed_evaluation_origin_specializes_canonical_call_failure() -> None:
    failure = RuntimeFailure(
        FailureStage.EVALUATION,
        FailureKind.CALL_FAILED,
        "action_evaluation_call_failed",
    )
    facts = FailureFacts(
        component_origin=CaseFailureOrigin.ACTION_EVALUATION,
        component_code="action_evaluator_exception",
        component_exception_class="RuntimeError",
        runtime_failure=failure,
    )
    classified = classify_case(_result(
        case_failure_code=facts.component_code,
        failure_origin=facts.component_origin,
        failure_code=facts.component_code,
        exception_class=facts.component_exception_class,
        termination_origin="component",
        failure_facts=facts,
    ))
    assert classified.outcome is MiniWobTaskOutcome.ACTION_EVALUATOR_FAILURE


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
            if code is AgentFailureCode.NO_PROGRESS_REPETITION
            else TerminalReasonCode.NO_PROGRESS_CONTROL_REPETITION
            if code is AgentFailureCode.NO_PROGRESS_CONTROL_REPETITION
            else None
        ),
        failure_facts=facts,
    )
    assert classify_case(result).outcome is not MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE
