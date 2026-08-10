from __future__ import annotations

import json
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.analysis import reclassify_archive
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import MiniWobTaskOutcome
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkCaseResult,
    CaseFailureOrigin,
    FailureFacts,
    MetricMeasurement,
    TerminalReasonCode,
)


def test_waiting_user_effect_and_task_unknown_are_distinct() -> None:
    effect = _result(
        status="waiting_user",
        pending_kind="unknown_effect",
        latest_action_evaluation_status="unknown",
    )
    task = _result(status="waiting_user", latest_task_status="unknown")
    assert classify_case(effect).outcome is MiniWobTaskOutcome.WAITING_USER_EFFECT_UNKNOWN
    assert classify_case(task).outcome is MiniWobTaskOutcome.WAITING_USER_TASK_UNKNOWN


def test_policy_abort_provider_and_no_action_are_typed() -> None:
    aborted = _result(status="failed", last_decision_type="Abort")
    provider = _result(status="failed", case_failure_code="policy_provider_unavailable")
    no_action = _result(
        status="blocked",
        terminal_reason_code=TerminalReasonCode.ACTION_OUTSIDE_ACTION_SPACE,
        last_action_space_option_count=0,
    )
    assert classify_case(aborted).outcome is MiniWobTaskOutcome.POLICY_ABORTED
    assert classify_case(provider).outcome is MiniWobTaskOutcome.PROVIDER_UNAVAILABLE
    assert classify_case(no_action).outcome is MiniWobTaskOutcome.NO_ACTION_OFFERED


def test_component_origins_are_classified_without_exception_text() -> None:
    cases = (
        (CaseFailureOrigin.ACTION_EVALUATION, MiniWobTaskOutcome.ACTION_EVALUATOR_FAILURE),
        (CaseFailureOrigin.TASK_EVALUATION, MiniWobTaskOutcome.TASK_EVALUATOR_FAILURE),
        (CaseFailureOrigin.EXECUTION, MiniWobTaskOutcome.EXECUTION_FAILURE),
        (CaseFailureOrigin.POST_ACTION_OBSERVATION, MiniWobTaskOutcome.POST_OBSERVATION_FAILURE),
        (CaseFailureOrigin.CLEANUP, MiniWobTaskOutcome.CLEANUP_FAILURE),
    )
    for origin, expected in cases:
        if origin is CaseFailureOrigin.CLEANUP:
            result = _result(
                status="failed",
                failure_origin=origin,
                cleanup_failure_code="cleanup_exception",
                cleanup_exception_class="SentinelError",
                cleanup_failures=1,
                failure_facts=FailureFacts(
                    cleanup_code="cleanup_exception",
                    cleanup_exception_class="SentinelError",
                ),
            )
        else:
            result = _result(
                status="failed",
                failure_origin=origin,
                failure_code="component_exception",
                exception_class="SentinelError",
                failure_facts=FailureFacts(
                    component_origin=origin,
                    component_code="component_exception",
                    component_exception_class="SentinelError",
                ),
            )
        assert classify_case(result).outcome is expected
        assert "secret exception text" not in repr(result)


def test_historical_fallback_stays_unresolved_and_archive_is_unchanged(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    cases = archive / "cases"
    cases.mkdir(parents=True)
    case = {
        "case_id": "miniwob-60-01",
        "task_family_label": "public-family",
        "typed_outcome": "other_typed_failure",
        "terminal_status": "waiting_user",
        "classification_source": "fallback",
        "terminal_reason_code": None,
        "case_failure_code": "",
        "metrics": {},
    }
    path = cases / "miniwob-60-01.json"
    path.write_text(json.dumps(case), encoding="utf-8")
    before = path.read_bytes()
    report = reclassify_archive(archive)
    assert report["cases"][0]["revised_category"] == "unresolved_legacy_evidence"
    assert "failure_origin" in report["cases"][0]["missing_evidence_fields"]
    assert path.read_bytes() == before


def _result(**changes) -> BenchmarkCaseResult:
    values = {
        "case_id": "case",
        "status": "failed",
        "execution_completed": True,
        "failure_reason": "",
        "latency_ms": 1.0,
        "measurements": {"official_success_count": MetricMeasurement(0, True)},
    }
    values.update(changes)
    return BenchmarkCaseResult(**values)
