from __future__ import annotations

from dataclasses import replace

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
    result = BenchmarkCaseResult("case:one", "failed", True, "", 1.0, failure_facts=facts)
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
