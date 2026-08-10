from __future__ import annotations

import json
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.attestation import validate_campaign_tree
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCampaignAcceptance,
    MiniWobBreadthCampaignOutcome,
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
)
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobBreadthCase, MiniWobBreadthManifest
from affordance_runtime.benchmarks.external_breadth.reporting import privacy_scan, write_campaign_reports
from affordance_runtime.benchmarks.external_breadth.runner import REQUIRED_METRICS
from affordance_runtime.benchmarks.target_loop.contracts import (
    BenchmarkAcceptance,
    BenchmarkCaseResult,
    BenchmarkRunIdentity,
    BenchmarkSuiteResult,
    MetricMeasurement,
)


def test_report_tree_is_complete_private_and_zero_denominators_are_null(tmp_path: Path) -> None:
    manifest = _manifest()
    results = tuple(_result(index, failed=False) for index in range(1, 61))
    records = tuple(
        MiniWobBreadthCaseRecord(
            result.case_id, f"fake-{index:02d}", "current_primitives", ("activate",),
            MiniWobTaskOutcome.SUCCESS, "mechanical_verifier", result,
        )
        for index, result in enumerate(results, 1)
    )
    outcome = MiniWobBreadthCampaignOutcome(
        "opaque-run", manifest, "sha256:manifest",
        BenchmarkSuiteResult(_identity(), results, BenchmarkAcceptance(True, ()), {}),
        records, MiniWobBreadthCampaignAcceptance(True, (), 60, 60, 60),
        "mistral", "mistral-medium-3-5", "format-only.v1",
    )
    output = tmp_path / "reports"
    output.mkdir()
    attestation_path = write_campaign_reports(outcome, output)
    attestation = json.loads(attestation_path.read_text())
    assert attestation["evidence_valid"] is True
    assert len(attestation["case_report_sha256"]) == 60
    assert validate_campaign_tree(output) == ()
    assert privacy_scan(output) == ()
    serialized = "\n".join(path.read_text().casefold() for path in output.rglob("*.json"))
    assert "browsergym/miniwob." not in serialized
    assert "raw_response" not in serialized


def test_privacy_scan_fails_closed_for_forbidden_report_material(tmp_path: Path) -> None:
    path = tmp_path / "case.json"
    path.write_text('{"raw_response":"forbidden"}', encoding="utf-8")
    assert privacy_scan(tmp_path)


def _manifest() -> MiniWobBreadthManifest:
    cases = tuple(
        MiniWobBreadthCase(
            f"miniwob-60-{index:02d}", f"browsergym/miniwob.fake-{index:02d}",
            "current_primitives", ("activate",), 10, 120.0, 7,
        )
        for index in range(1, 61)
    )
    return MiniWobBreadthManifest(
        "miniwob-breadth-manifest.v1", "miniwob-60-seed7-v1", "browsergym-miniwob",
        "0.14.3", "source", "registry", "inventory", "selection", "mistral-medium-3-5",
        "format-only.v1", 7.5, cases,
    )


def _result(index: int, *, failed: bool) -> BenchmarkCaseResult:
    measurements = {name: MetricMeasurement(0, True) for name in REQUIRED_METRICS}
    measurements["official_success_count"] = MetricMeasurement(0 if failed else 1, True)
    return BenchmarkCaseResult(
        f"miniwob-60-{index:02d}", "failed" if failed else "done", True, "", 1.0, measurements,
    )


def _identity() -> BenchmarkRunIdentity:
    return BenchmarkRunIdentity(
        "opaque-run", "0" * 40, False, "suite", "digest", "profile", 7,
        "2026-08-10T00:00:00+00:00", "3.12", "test",
    )
