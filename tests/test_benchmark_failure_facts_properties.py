from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.benchmarks.target_loop.case_projection import (
    decode_public_case_evidence,
    public_case_evidence,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    FailureFacts,
    MetricMeasurement,
)


@given(
    watchdog=st.booleans(),
    cleanup=st.booleans(),
    integrity=st.booleans(),
)
def test_failure_facts_are_orthogonal_and_round_trip(watchdog, cleanup, integrity) -> None:
    facts = FailureFacts(
        runtime_reason_code="runtime_exception",
        component_origin=CaseFailureOrigin.ACTION_EVALUATION,
        component_code="action_evaluator_exception",
        component_exception_class="RuntimeError",
        watchdog_code="case_timeout" if watchdog else "",
        cleanup_code="cleanup_exception" if cleanup else "",
        cleanup_exception_class="RuntimeError" if cleanup else "",
        harness_integrity_code="metric_name_collision" if integrity else "",
    )
    result = BenchmarkCaseResult(
        "case:one", "failed", True, "", 1.0,
        runtime_reason_code=facts.runtime_reason_code,
        agent_failure_code=facts.agent_failure_code,
        last_policy_failure_code=facts.policy_failure_code,
        cleanup_failure_code=facts.cleanup_code,
        cleanup_exception_class=facts.cleanup_exception_class,
        cleanup_failures=int(cleanup),
        harness_integrity_code=facts.harness_integrity_code,
        harness_integrity_failures=int(integrity),
        watchdog_triggered=watchdog,
        failure_origin=facts.component_origin,
        failure_code=facts.component_code,
        exception_class=facts.component_exception_class,
        failure_facts=facts,
    )
    decoded = decode_public_case_evidence(public_case_evidence(result))
    assert decoded.failure_facts == facts


def test_adding_watchdog_does_not_erase_component_failure() -> None:
    facts = FailureFacts(
        component_origin=CaseFailureOrigin.EXECUTION,
        component_code="execution_exception",
        component_exception_class="RuntimeError",
    )
    changed = replace(facts, watchdog_code="case_timeout")
    assert changed.component_origin is facts.component_origin
    assert changed.component_code == facts.component_code


def test_public_decoder_rejects_malformed_metrics_and_unknown_schema() -> None:
    payload = public_case_evidence(BenchmarkCaseResult("case:one", "failed", True, "", 1.0))
    malformed = dict(payload)
    malformed["measurements"] = {"observations": "not-a-measurement"}
    with pytest.raises(ValueError, match="metric"):
        decode_public_case_evidence(malformed)

    future = dict(payload)
    future["schema_version"] = future["case_schema_version"] = "target-loop-case.v999"
    with pytest.raises(ValueError, match="unsupported"):
        decode_public_case_evidence(future)


def test_public_evidence_omits_unrestricted_human_failure_reason() -> None:
    result = BenchmarkCaseResult(
        "case:one", "failed", True, "private selector:#secret", 1.0,
    )
    payload = public_case_evidence(result)
    assert "failure_reason" not in payload
    assert "private selector" not in repr(payload)


def test_contradictory_component_fact_without_origin_is_rejected() -> None:
    with pytest.raises(ValueError, match="origin and code"):
        FailureFacts(component_code="execution_exception")


def test_mechanical_success_cannot_coexist_with_component_failure() -> None:
    facts = FailureFacts(
        component_origin=CaseFailureOrigin.EXECUTION,
        component_code="execution_exception",
        component_exception_class="RuntimeError",
    )
    with pytest.raises(ValueError, match="cannot carry failure facts"):
        BenchmarkCaseResult(
            "case:one", "done", True, "", 1.0,
            {"official_success_count": MetricMeasurement(1, True)},
            failure_origin=CaseFailureOrigin.EXECUTION,
            failure_code="execution_exception",
            exception_class="RuntimeError",
            failure_facts=facts,
        )
