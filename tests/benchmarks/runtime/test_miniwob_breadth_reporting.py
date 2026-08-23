from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from affordance_runtime.benchmarks.external_breadth.attestation import validate_campaign_tree
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCampaignAcceptance,
    MiniWobBreadthCampaignOutcome,
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
    ProviderCapacityEvidence,
)
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobBreadthCase, MiniWobBreadthManifest
from affordance_runtime.benchmarks.external_breadth.manifest import breadth_manifest_digest
from affordance_runtime.benchmarks.external_breadth.progress import (
    CampaignProgressWriter,
    case_progress_digest,
)
from affordance_runtime.benchmarks.external_breadth.reporting import (
    _case_payload,
    privacy_scan,
    write_campaign_reports,
)
from affordance_runtime.benchmarks.external_breadth.runner import (
    REQUIRED_METRICS,
    expected_target_manifest_digest,
)
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkAcceptance,
    BenchmarkCaseResult,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    CaseFailureOrigin,
    FailureFacts,
    MetricMeasurement,
)


def test_report_tree_is_complete_private_and_zero_denominators_are_null(tmp_path: Path) -> None:
    manifest = _manifest()
    results = tuple(_result(index, failed=False) for index in range(1, 61))
    records = tuple(
        MiniWobBreadthCaseRecord(
            result.case_id, f"fake-{index:02d}", "current_primitives", ("activate",),
                MiniWobTaskOutcome.SUCCESS, "canonical_task_outcome", result,
        )
        for index, result in enumerate(results, 1)
    )
    outcome = MiniWobBreadthCampaignOutcome(
        "opaque-run", manifest, breadth_manifest_digest(manifest),
        BenchmarkSuiteResult(_identity(), results, BenchmarkAcceptance(True, ()), {}),
        records, MiniWobBreadthCampaignAcceptance(True, (), 60, 60, 60),
        "mistral", "mistral-medium-3-5", "format-only.v1",
        ProviderCapacityEvidence(
            "provider-capacity-preflight.v1", "mistral", "mistral-medium-3-5",
            breadth_manifest_digest(manifest), 600, 600, True, "format-only.v1", 0, 0,
        ),
    )
    output = tmp_path / "reports"
    output.mkdir()
    _write_progress(output, outcome)
    attestation_path = write_campaign_reports(outcome, output)
    attestation = json.loads(attestation_path.read_text())
    assert attestation["evidence_valid"] is True
    assert len(attestation["case_report_sha256"]) == 60
    assert validate_campaign_tree(output, manifest) == ()
    assert privacy_scan(output) == ()
    serialized = "\n".join(path.read_text().casefold() for path in output.rglob("*.json"))
    assert "browsergym/miniwob." not in serialized
    assert "raw_response" not in serialized


def test_privacy_scan_fails_closed_for_forbidden_report_material(tmp_path: Path) -> None:
    path = tmp_path / "case.json"
    path.write_text('{"raw_response":"forbidden"}', encoding="utf-8")
    assert privacy_scan(tmp_path)


def test_privacy_scan_allows_public_task_family_containing_coordinate(tmp_path: Path) -> None:
    path = tmp_path / "case.json"
    path.write_text('{"task_family_label":"grid-coordinate"}', encoding="utf-8")
    assert privacy_scan(tmp_path) == ()


def test_privacy_scan_rejects_private_coordinate_field_and_route_value(tmp_path: Path) -> None:
    coordinate = tmp_path / "coordinate.json"
    coordinate.write_text('{"coordinate":[10,20]}', encoding="utf-8")
    route = tmp_path / "route.json"
    route.write_text('{"detail":"selector:#private"}', encoding="utf-8")
    errors = privacy_scan(tmp_path)
    assert any("forbidden field coordinate" in error for error in errors)
    assert any("forbidden value selector:" in error for error in errors)


def test_case_json_preserves_watchdog_and_integrity_typed_truth() -> None:
    result = replace(
        _result(1, failed=True),
        failure_facts=FailureFacts(
            component_origin=CaseFailureOrigin.ACTION_EVALUATION,
            component_code="action_outcome_projector_exception",
            component_exception_class="RuntimeError",
            watchdog_code="case_timeout",
            harness_integrity_code="metric_name_collision",
        ),
    )
    record = MiniWobBreadthCaseRecord(
        result.case_id, "fake-01", "current_primitives", ("activate",),
        MiniWobTaskOutcome.CASE_TIMEOUT, "typed_case_code", result,
    )
    evidence = _case_payload(record)["benchmark_case_evidence"]
    assert isinstance(evidence, dict)
    assert evidence["failure_facts"] == {
        "runtime_reason_code": "",
        "agent_failure_code": "",
        "policy_failure_code": "",
        "component_origin": "action_outcome",
        "component_code": "action_outcome_projector_exception",
        "component_exception_class": "RuntimeError",
        "watchdog_code": "case_timeout",
        "cleanup_code": "",
        "cleanup_exception_class": "",
            "harness_integrity_code": "metric_name_collision",
            "runtime_failure": None,
            "task_outcome_kind": "",
            "task_outcome_code": "",
        }


def test_tree_validator_rejects_coherently_rehashed_case_identity_mutation(
    tmp_path: Path,
) -> None:
    output = _write_valid_tree(tmp_path)
    case_path = output / "cases" / "miniwob-60-01.json"
    payload = json.loads(case_path.read_text())
    payload["benchmark_case_evidence"]["suite_id"] = "spoof-suite"
    case_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    attestation_path = output / "attestation.json"
    attestation = json.loads(attestation_path.read_text())
    attestation["case_report_sha256"]["miniwob-60-01"] = (
        "sha256:" + hashlib.sha256(case_path.read_bytes()).hexdigest()
    )
    attestation_path.write_text(json.dumps(attestation, sort_keys=True), encoding="utf-8")
    assert any(
        "formal case identity" in item
        for item in validate_campaign_tree(output, _manifest())
    )


def test_tree_validator_fails_closed_for_missing_required_metric(tmp_path: Path) -> None:
    output = _write_valid_tree(tmp_path)
    case_path = output / "cases" / "miniwob-60-01.json"
    payload = json.loads(case_path.read_text())
    del payload["benchmark_case_evidence"]["measurements"]["observations"]
    case_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _rebind_file(output, "miniwob-60-01", case_path)
    errors = validate_campaign_tree(output, _manifest())
    assert any("required formal metrics" in item for item in errors)


def test_tree_validator_binds_progress_to_exact_last_case(tmp_path: Path) -> None:
    output = _write_valid_tree(tmp_path)
    progress_path = output / "campaign-progress.json"
    payload = json.loads(progress_path.read_text())
    payload["last_completed_case_digest"] = "anything"
    progress_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    attestation_path = output / "attestation.json"
    attestation = json.loads(attestation_path.read_text())
    attestation["progress_sha256"] = (
        "sha256:" + hashlib.sha256(progress_path.read_bytes()).hexdigest()
    )
    attestation_path.write_text(json.dumps(attestation, sort_keys=True), encoding="utf-8")
    assert any(
        "progress is not" in item
        for item in validate_campaign_tree(output, _manifest())
    )


def test_tree_validator_rejects_fractional_count_metric(tmp_path: Path) -> None:
    output = _write_valid_tree(tmp_path)
    case_path = output / "cases" / "miniwob-60-01.json"
    payload = json.loads(case_path.read_text())
    payload["benchmark_case_evidence"]["measurements"]["observations"]["value"] = 0.5
    case_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _rebind_file(output, "miniwob-60-01", case_path)
    assert any(
        "required formal metrics" in item
        for item in validate_campaign_tree(output, _manifest())
    )


def test_tree_validator_rejects_recursive_extra_and_unknown_schema_fields(
    tmp_path: Path,
) -> None:
    output = _write_valid_tree(tmp_path)
    extra = output / "cases" / "raw_prompt.txt"
    extra.write_text("Authorization: Bearer PRIVATE-CREDENTIAL", encoding="utf-8")
    errors = validate_campaign_tree(output, _manifest())
    assert any("recursive file set" in item for item in errors)
    assert any("non-JSON evidence" in item for item in errors)
    extra.unlink()

    attestation_path = output / "attestation.json"
    attestation = json.loads(attestation_path.read_text())
    attestation["unexpected"] = 1
    attestation_path.write_text(json.dumps(attestation, sort_keys=True), encoding="utf-8")
    assert any(
        "attestation fields" in item
        for item in validate_campaign_tree(output, _manifest())
    )


def test_tree_validator_rejects_unknown_outer_case_field(tmp_path: Path) -> None:
    output = _write_valid_tree(tmp_path)
    case_path = output / "cases" / "miniwob-60-01.json"
    payload = json.loads(case_path.read_text())
    payload["unexpected"] = 1
    case_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _rebind_file(output, "miniwob-60-01", case_path)
    assert any(
        "outer case" in item
        for item in validate_campaign_tree(output, _manifest())
    )


def _rebind_file(output: Path, case_id: str, case_path: Path) -> None:
    attestation_path = output / "attestation.json"
    attestation = json.loads(attestation_path.read_text())
    attestation["case_report_sha256"][case_id] = (
        "sha256:" + hashlib.sha256(case_path.read_bytes()).hexdigest()
    )
    attestation_path.write_text(json.dumps(attestation, sort_keys=True), encoding="utf-8")


def test_provider_capacity_requires_explicit_zero_retry_fallback_identity() -> None:
    with pytest.raises(ValueError, match="frozen identity"):
        ProviderCapacityEvidence(
            "provider-capacity-preflight.v1", "mistral", "model", "sha256:m",
            1, 1, True,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("required_attempt_budget", True),
        ("declared_attempt_budget", True),
        ("retry_count", False),
        ("fallback_count", False),
    ),
)
def test_tree_validator_rejects_capacity_scalar_type_spoofs(
    tmp_path: Path, field: str, value: object,
) -> None:
    output = _write_valid_tree(tmp_path)
    path = output / "attestation.json"
    payload = json.loads(path.read_text())
    payload["provider_capacity"][field] = value
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    assert any("provider capacity" in item for item in validate_campaign_tree(output, _manifest()))


def test_tree_validator_rejects_extra_nested_formal_fields(tmp_path: Path) -> None:
    output = _write_valid_tree(tmp_path)
    attestation_path = output / "attestation.json"
    attestation = json.loads(attestation_path.read_text())
    attestation["provider_capacity"]["derived_from_result"] = True
    attestation_path.write_text(json.dumps(attestation, sort_keys=True), encoding="utf-8")
    assert any("provider capacity" in item for item in validate_campaign_tree(output, _manifest()))

    acceptance_root = tmp_path / "acceptance"
    acceptance_root.mkdir()
    output = _write_valid_tree(acceptance_root)
    campaign_path = output / "campaign.json"
    campaign = json.loads(campaign_path.read_text())
    campaign["acceptance"]["legacy_ok"] = True
    campaign_path.write_text(json.dumps(campaign, sort_keys=True), encoding="utf-8")
    attestation_path = output / "attestation.json"
    attestation = json.loads(attestation_path.read_text())
    attestation["campaign_sha256"] = "sha256:" + hashlib.sha256(
        campaign_path.read_bytes()
    ).hexdigest()
    attestation_path.write_text(json.dumps(attestation, sort_keys=True), encoding="utf-8")
    assert any("formal acceptance" in item for item in validate_campaign_tree(output, _manifest()))


def _write_valid_tree(tmp_path: Path) -> Path:
    manifest = _manifest()
    results = tuple(_result(index, failed=False) for index in range(1, 61))
    records = tuple(
        MiniWobBreadthCaseRecord(
            result.case_id, f"fake-{index:02d}", "current_primitives", ("activate",),
                MiniWobTaskOutcome.SUCCESS, "canonical_task_outcome", result,
        )
        for index, result in enumerate(results, 1)
    )
    outcome = MiniWobBreadthCampaignOutcome(
        "opaque-run", manifest, breadth_manifest_digest(manifest),
        BenchmarkSuiteResult(_identity(), results, BenchmarkAcceptance(True, ()), {}),
        records, MiniWobBreadthCampaignAcceptance(True, (), 60, 60, 60),
        "mistral", "mistral-medium-3-5", "format-only.v1",
        ProviderCapacityEvidence(
            "provider-capacity-preflight.v1", "mistral", "mistral-medium-3-5",
            breadth_manifest_digest(manifest), 600, 600, True, "format-only.v1", 0, 0,
        ),
    )
    output = tmp_path / "valid-tree"
    output.mkdir()
    _write_progress(output, outcome)
    write_campaign_reports(outcome, output)
    assert validate_campaign_tree(output, manifest) == ()
    return output


def _write_progress(output: Path, outcome: MiniWobBreadthCampaignOutcome) -> None:
    counts: dict[str, int] = {}
    for record in outcome.cases:
        counts[record.outcome.value] = counts.get(record.outcome.value, 0) + 1
    writer = CampaignProgressWriter(
        output / "campaign-progress.json",
        outcome.manifest.campaign_id,
        outcome.run_id,
        outcome.suite.identity.git_sha,
        outcome.manifest_digest,
        len(outcome.cases),
        completed_cases=len(outcome.cases),
        success_count=sum(record.outcome is MiniWobTaskOutcome.SUCCESS for record in outcome.cases),
        failure_category_counts=counts,
        provider_attempts=sum(
            int(record.result.measurements["provider_attempts"].value or 0)
            for record in outcome.cases
        ),
        total_tokens=sum(
            int(record.result.measurements["total_tokens"].value or 0)
            for record in outcome.cases
        ),
        model_latency_ms=sum(
            float(record.result.measurements["model_latency_ms"].value or 0)
            for record in outcome.cases
        ),
        last_completed_case_digest=case_progress_digest(outcome.cases[-1].result),
    )
    writer.write(current_case_id=outcome.cases[-1].case_id, complete=True)


def _manifest() -> MiniWobBreadthManifest:
    cases = tuple(
        MiniWobBreadthCase(
            f"miniwob-60-{index:02d}", f"browsergym/miniwob.fake-{index:02d}",
            "current_primitives", ("activate",), 10, 180.0, 7,
        )
        for index in range(1, 61)
    )
    return MiniWobBreadthManifest(
        "miniwob-breadth-manifest.v1", "miniwob-60-seed7-v2", "browsergym-miniwob",
        "0.14.3", "source", "registry", "inventory", "selection", "mistral-medium-3-5",
        "format-only.v1", 7.5, cases,
    )


def _result(index: int, *, failed: bool) -> BenchmarkCaseResult:
    measurements = {name: MetricMeasurement(0, True) for name in REQUIRED_METRICS}
    measurements["official_success_count"] = MetricMeasurement(0 if failed else 1, True)
    facts = FailureFacts() if failed else FailureFacts(
        task_outcome_kind="terminal_success",
        task_outcome_code="verified_success",
    )
    return BenchmarkCaseResult(
        f"miniwob-60-{index:02d}", "failed" if failed else "done", True, "", 1.0,
        measurements,
        latest_task_status="" if failed else "complete",
        failure_facts=facts,
        suite_id="miniwob-60-seed7-v2",
        profile_id="mistral-format-only-v1",
        seed=7,
        manifest_digest=expected_target_manifest_digest(_manifest()),
    )


def _identity() -> BenchmarkRunIdentity:
    return BenchmarkRunIdentity(
        "opaque-run", "0" * 40, False, "miniwob-60-seed7-v2",
        expected_target_manifest_digest(_manifest()),
        "mistral-format-only-v1", 7,
        "2026-08-10T00:00:00+00:00", "3.12", "test",
    )
