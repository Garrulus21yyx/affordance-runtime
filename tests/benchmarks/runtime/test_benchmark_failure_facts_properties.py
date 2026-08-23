from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.runtime_failure import (
    FailureKind,
    FailureStage,
    RuntimeFailure,
)
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
        runtime_failure=RuntimeFailure(
            FailureStage.SESSION,
            FailureKind.CALL_FAILED,
            "runtime_exception",
        ),
        component_origin=CaseFailureOrigin.ACTION_EVALUATION,
        component_code="action_outcome_projector_exception",
        component_exception_class="RuntimeError",
        watchdog_code="case_timeout" if watchdog else "",
        cleanup_code="cleanup_exception" if cleanup else "",
        cleanup_exception_class="RuntimeError" if cleanup else "",
        harness_integrity_code="metric_name_collision" if integrity else "",
    )
    result = BenchmarkCaseResult(
        "case:one",
        "failed",
        True,
        "",
        1.0,
        cleanup_status="failed" if cleanup else "not_run",
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


def test_runtime_failure_stage_is_frozen_and_codec_round_trip_preserves_authority() -> None:
    failure = RuntimeFailure(
        FailureStage.ACQUISITION,
        FailureKind.CALL_FAILED,
        "observation_acquisition_failed",
        "transition:1:00000000000000000000",
        "attempt:1",
        "RuntimeError",
    )
    facts = FailureFacts(
        runtime_reason_code=failure.code,
        runtime_failure=failure,
    )
    result = BenchmarkCaseResult(
        "case:one",
        "failed",
        True,
        "display only",
        1.0,
        failure_facts=facts,
    )

    decoded = decode_public_case_evidence(public_case_evidence(result))
    assert decoded.failure_facts.runtime_failure == failure
    with pytest.raises(FrozenInstanceError):
        failure.stage = FailureStage.CONTROL


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

    legacy = public_case_evidence(BenchmarkCaseResult("case:legacy", "failed", True, "", 1.0))
    legacy["schema_version"] = legacy["case_schema_version"] = "target-loop-case.v11"
    with pytest.raises(ValueError, match="unsupported"):
        decode_public_case_evidence(legacy)

    wrong_scalars = public_case_evidence(
        BenchmarkCaseResult(
            "case:one",
            "failed",
            True,
            "",
            1.0,
            {"observations": MetricMeasurement(1, True)},
        )
    )
    wrong_scalars["measurements"]["observations"] = {
        "value": "secret",
        "measured": "yes",
        "opportunities": None,
        "unit": "count",
    }
    with pytest.raises((TypeError, ValueError)):
        decode_public_case_evidence(wrong_scalars)

    null_fact = public_case_evidence(BenchmarkCaseResult("case:one", "failed", True, "", 1.0))
    null_fact["failure_facts"]["runtime_reason_code"] = None
    with pytest.raises(TypeError, match="strings"):
        decode_public_case_evidence(null_fact)

    bad_status = public_case_evidence(BenchmarkCaseResult("case:one", "failed", True, "", 1.0))
    bad_status["status"] = "gibberish"
    with pytest.raises(ValueError, match="scalar"):
        decode_public_case_evidence(bad_status)


def test_failure_algebras_reject_contradictory_or_unsupported_truth() -> None:
    with pytest.raises(ValueError, match="stage and kind"):
        RuntimeFailure(
            FailureStage.POLICY,
            FailureKind.CAPABILITY_UNAVAILABLE,
            "unsupported_failure_pair",
        )
    for code in ("123", "UPPER", "秘密"):
        with pytest.raises(ValueError, match="bounded identifiers"):
            FailureFacts(component_origin=CaseFailureOrigin.EXECUTION, component_code=code)
    with pytest.raises(ValueError, match="policy failure facts conflict"):
        FailureFacts(
            policy_failure_code="timeout",
            runtime_failure=RuntimeFailure(
                FailureStage.POLICY,
                FailureKind.INVALID_OUTPUT,
                "invalid_response",
            ),
        )


def test_official_success_cannot_coexist_with_canonical_runtime_failure() -> None:
    facts = FailureFacts(
        runtime_failure=RuntimeFailure(
            FailureStage.EXECUTION,
            FailureKind.CALL_FAILED,
            "execution_failed",
        )
    )
    with pytest.raises(ValueError, match="cannot carry failure facts"):
        BenchmarkCaseResult(
            "case:success",
            "done",
            True,
            "",
            1.0,
            measurements={"official_success_count": MetricMeasurement(1, True)},
            failure_facts=facts,
        )


def test_current_schema_has_no_unbound_legacy_failure_fields() -> None:
    names = {item.name for item in fields(BenchmarkCaseResult)}
    assert not names.intersection({"failure_code", "case_failure_code", "exception_class"})


@pytest.mark.parametrize(
    "changes",
    (
        {"last_decision_kind": "invented_decision"},
        {"pending_kind": "invented_pending"},
        {"latest_task_status": "invented_task_status"},
        {"latest_action_observed_change": "invented_action_status"},
        {"latest_action_local_postcondition": "invented_local_postcondition"},
        {"latest_action_evidence_method": "invented_method"},
        {"last_world_coverage": "private coverage marker"},
        {"latest_semantic_attempt_key_digest": "sha256:not-a-digest"},
    ),
)
def test_public_typed_projection_strings_use_closed_vocabularies(changes) -> None:
    with pytest.raises(ValueError, match="vocabulary|coverage|digest"):
        BenchmarkCaseResult("case:one", "failed", True, "", 1.0, **changes)


def test_final_response_is_in_the_closed_decision_vocabulary() -> None:
    result = BenchmarkCaseResult(
        "case:final-response",
        "failed",
        True,
        "",
        1.0,
        last_decision_kind="submit_final_response",
    )

    assert result.last_decision_kind == "submit_final_response"


def test_partial_and_completed_episode_truth_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="partial"):
        BenchmarkCaseResult(
            "case:one",
            "failed",
            True,
            "",
            1.0,
            partial_episode_available=True,
        )


@pytest.mark.parametrize(
    ("pending_kind", "status"),
    (("confirmation", "done"), ("unknown_effect", "failed"), ("user_question", "done")),
)
def test_pending_kind_requires_matching_waiting_status(pending_kind, status) -> None:
    with pytest.raises(ValueError, match="pending kind contradicts"):
        BenchmarkCaseResult(
            "case:one",
            status,
            True,
            "",
            1.0,
            pending_kind=pending_kind,
        )


def test_abort_decision_requires_canonical_runtime_fact() -> None:
    with pytest.raises(ValueError, match="abort decision"):
        BenchmarkCaseResult(
            "case:one",
            "failed",
            True,
            "",
            1.0,
            last_decision_kind="abort",
        )


def test_component_termination_origin_is_derived_from_the_typed_fact() -> None:
    facts = FailureFacts(
        component_origin=CaseFailureOrigin.EXECUTION,
        component_code="execute_failed",
    )
    result = BenchmarkCaseResult("case:one", "failed", True, "", 1.0, failure_facts=facts)
    assert result.termination_origin == "component"


def test_public_evidence_omits_unrestricted_human_failure_reason() -> None:
    result = BenchmarkCaseResult(
        "case:one",
        "failed",
        True,
        "private selector:#secret",
        1.0,
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
            "case:one",
            "done",
            True,
            "",
            1.0,
            {"official_success_count": MetricMeasurement(1, True)},
            failure_facts=facts,
        )


def test_component_and_watchdog_project_without_erasing_either_fact() -> None:
    from affordance_runtime.benchmarks.target_loop.case_projection import project_case_result
    from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation

    instrumentation = BenchmarkInstrumentation()
    instrumentation.record_failure(
        CaseFailureOrigin.EXECUTION,
        "execution_exception",
        RuntimeError("private component detail"),
    )
    instrumentation.record_watchdog("case_timeout", TimeoutError())
    result = project_case_result("case:one", None, instrumentation, 1.0, "timeout")
    assert result.failure_origin is CaseFailureOrigin.EXECUTION
    assert result.failure_facts.component_origin is CaseFailureOrigin.EXECUTION
    assert result.watchdog_triggered
    assert result.failure_facts.watchdog_code == "case_timeout"
    assert result.termination_origin == "harness_watchdog"
