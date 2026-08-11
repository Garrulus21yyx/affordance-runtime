from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from test_miniwob_breadth_reporting import _manifest, _result

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCampaignAcceptance,
    MiniWobBreadthCampaignOutcome,
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
    ProviderCapacityEvidence,
)
from affordance_runtime.benchmarks.external_breadth.control_feedback_targeted import (
    _FEEDBACK_METRICS,
    TARGETED_CAMPAIGN_ID,
    TARGETED_CASE_IDS,
    _targeted_derived_metrics,
    targeted_manifest,
    validate_targeted_evidence,
    write_targeted_evidence,
)
from affordance_runtime.benchmarks.external_breadth.control_feedback_targeted_cli import (
    _provider_capacity,
)
from affordance_runtime.benchmarks.external_breadth.manifest import breadth_manifest_digest
from affordance_runtime.benchmarks.external_breadth.progress import CampaignProgressWriter
from affordance_runtime.benchmarks.external_breadth.runner import expected_target_manifest_digest
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkAcceptance,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    MetricMeasurement,
)


def test_control_feedback_selector_is_exact_ordered_and_data_only() -> None:
    manifest = targeted_manifest(_manifest())

    assert manifest.campaign_id == TARGETED_CAMPAIGN_ID
    assert tuple(item.case_id for item in manifest.cases) == TARGETED_CASE_IDS
    assert len(set(TARGETED_CASE_IDS)) == 25
    assert all(item.seed == 7 for item in manifest.cases)


def test_control_feedback_provider_capacity_preflight_checks_declared_budget(
    monkeypatch,
) -> None:
    manifest = targeted_manifest(_manifest())
    required = sum(item.max_turns for item in manifest.cases)
    monkeypatch.setenv("MINIWOB_PROVIDER_ATTEMPT_BUDGET", str(required - 1))

    insufficient = _provider_capacity(manifest)
    monkeypatch.setenv("MINIWOB_PROVIDER_ATTEMPT_BUDGET", str(required))
    sufficient = _provider_capacity(manifest)

    assert insufficient.sufficient is False
    assert sufficient.sufficient is True


def test_control_feedback_targeted_derivation_preserves_canonical_d_metrics() -> None:
    base = _result(37, failed=False)
    measurements = dict(base.measurements)
    for name in _FEEDBACK_METRICS:
        measurements[name] = MetricMeasurement(1, True)

    derived = _targeted_derived_metrics(replace(base, measurements=measurements))

    assert all(derived.measurements[name].value == 1 for name in _FEEDBACK_METRICS)


def test_control_feedback_evidence_validator_redecodes_and_detects_tamper(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    output.mkdir()
    outcome = _outcome()
    _write_progress(output, outcome)
    write_targeted_evidence(outcome, output)

    assert validate_targeted_evidence(output) == ()

    case_path = output / "cases" / "miniwob-60-37.json"
    payload = json.loads(case_path.read_text())
    payload["feedback_metrics"]["feedback_context_delivery_count"] = 0
    case_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    errors = validate_targeted_evidence(output)
    assert any("digest mismatch" in item for item in errors)


def _outcome() -> MiniWobBreadthCampaignOutcome:
    manifest = targeted_manifest(_manifest())
    target_digest = expected_target_manifest_digest(manifest)
    results = []
    for case_id in TARGETED_CASE_IDS:
        index = int(case_id[-2:])
        base = _result(index, failed=False)
        metrics = dict(base.measurements)
        for name in _FEEDBACK_METRICS:
            metrics[name] = MetricMeasurement(0, True)
        if case_id == "miniwob-60-37":
            metrics["first_policy_repair_feedback_count"] = MetricMeasurement(1, True)
            metrics["feedback_context_delivery_count"] = MetricMeasurement(1, True)
            metrics["feedback_repairable_rejection_count"] = MetricMeasurement(1, True)
            metrics["feedback_action_admission_source_count"] = MetricMeasurement(1, True)
            metrics["feedback_invalid_action_parameters_code_count"] = MetricMeasurement(1, True)
            metrics["control_issue_budget_consumption_count"] = MetricMeasurement(1, True)
            metrics["first_opportunity_policy_decision_count"] = MetricMeasurement(1, True)
            metrics["first_opportunity_admission_corrected_count"] = MetricMeasurement(1, True)
        results.append(replace(
            base,
            measurements=metrics,
            suite_id=manifest.campaign_id,
            manifest_digest=target_digest,
        ))
    records = tuple(
        MiniWobBreadthCaseRecord(
            result.case_id,
            f"fake-{result.case_id[-2:]}",
            "current_primitives",
            ("activate",),
            MiniWobTaskOutcome.SUCCESS,
            "canonical_task_outcome",
            result,
        )
        for result in results
    )
    implementation = "0" * 40
    identity = BenchmarkRunIdentity(
        "miniwob-control-feedback-25:" + "a" * 32,
        implementation,
        False,
        manifest.campaign_id,
        target_digest,
        "mistral-format-only-v1",
        7,
        "2026-08-11T00:00:00+00:00",
        "3.12",
        "test",
    )
    capacity = ProviderCapacityEvidence(
        "provider-capacity-preflight.v1",
        "mistral",
        "mistral-medium-3-5",
        breadth_manifest_digest(manifest),
        sum(item.max_turns for item in manifest.cases),
        sum(item.max_turns for item in manifest.cases),
        True,
        "format-only.v1",
        0,
        0,
    )
    return MiniWobBreadthCampaignOutcome(
        identity.run_id,
        manifest,
        breadth_manifest_digest(manifest),
        BenchmarkSuiteResult(identity, tuple(results), BenchmarkAcceptance(True, ()), {}),
        records,
        MiniWobBreadthCampaignAcceptance(True, (), 25, 25, 25),
        "mistral",
        "mistral-medium-3-5",
        "format-only.v1",
        capacity,
    )


def _write_progress(output: Path, outcome: MiniWobBreadthCampaignOutcome) -> None:
    writer = CampaignProgressWriter(
        output / "campaign-progress.json",
        outcome.manifest.campaign_id,
        outcome.run_id,
        outcome.suite.identity.git_sha,
        outcome.manifest_digest,
        25,
        completed_cases=25,
        success_count=25,
        failure_category_counts={"success": 25},
    )
    writer.write(current_case_id=TARGETED_CASE_IDS[-1], complete=True)
