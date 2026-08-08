import json
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.benchmarks.model_conformance.attestation import attest_results
from affordance_runtime.benchmarks.model_conformance.contracts import (
    ConformanceAttempt,
    ModelConformanceStage,
    ModelInputComplexity,
    ModelProfileConformanceResult,
    ModelProfileIdentity,
)
from affordance_runtime.immutable import to_json_compatible


def _result() -> ModelProfileConformanceResult:
    identity = ModelProfileIdentity(
        "ollama", "qwen2.5:7b", "local", "ollama", "0.32.0", "digest", "qwen2",
        "7.6B", "Q4_K_M", "p5-m1.1", "agent-decision.v1", "default-64k",
    )
    attempt = ConformanceAttempt(
        "attempt:format-only:0:1", "0", "format-only", ModelConformanceStage.SUCCESS,
        True, "", "select_action", 2, 3, 2, 4, 9, 0, 0, 0, 0, 1, 1, 2, 10,
        "sha256:abc", 1.0,
    )
    complexity = ModelInputComplexity(2, 3, 4, 1, 7, 5, 0, 0, 0, 0, 0, 0, 0, 9)
    return ModelProfileConformanceResult(
        identity, (attempt,), ("0",), (), "diagnostic_pass", ("level 0: 1/1",), complexity,
    )


def test_attestation_hashes_reports_and_retains_no_raw_response(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    path.write_text(json.dumps(asdict(_result()), sort_keys=True), encoding="utf-8")
    attestation = attest_results((path,), git_sha="abc123", git_dirty=False)
    assert attestation.accepted
    assert attestation.report_files[0].sha256.startswith("sha256:")
    encoded = json.dumps(to_json_compatible(asdict(attestation)), sort_keys=True).casefold()
    assert "raw_response" not in encoded
    assert "endpoint_url" not in encoded


def test_dirty_tree_fails_attestation(tmp_path: Path) -> None:
    path = tmp_path / "result.json"
    path.write_text(json.dumps(asdict(_result()), sort_keys=True), encoding="utf-8")
    result = attest_results((path,), git_sha="abc123", git_dirty=True)
    assert not result.accepted
    assert "clean" in result.errors[0]
