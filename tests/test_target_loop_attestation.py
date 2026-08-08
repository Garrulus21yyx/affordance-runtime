import asyncio
import hashlib
import json
import subprocess

from affordance_runtime.benchmarks.target_loop.attestation import (
    ExpectedBenchmarkRun,
    ExpectedRunSet,
    create_attestation,
)
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.reporting import write_run_report
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def test_attestation_binds_exact_git_manifest_and_report_digests(monkeypatch, tmp_path) -> None:
    _clean_git(monkeypatch)
    run_dir = tmp_path / "core"
    result = asyncio.run(run_suite(get_manifest("internal-core", "deterministic", 7)))
    write_run_report(result, str(run_dir))
    output = tmp_path / "attestation.json"

    expected = ExpectedRunSet.from_manifests((get_manifest("internal-core", "deterministic", 7),))
    attestation = create_attestation(tmp_path, output, expected)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert attestation.accepted
    assert attestation.git_sha == result.identity.git_sha
    assert attestation.manifest_digests == (result.identity.manifest_digest,)
    assert len(attestation.report_files) == 7
    assert payload["report_files"][0]["sha256"]
    assert hashlib.sha256(output.read_bytes()).hexdigest()


def test_attestation_rejects_missing_unexpected_and_duplicate_runs(monkeypatch, tmp_path) -> None:
    _clean_git(monkeypatch)
    result = asyncio.run(run_suite(get_manifest("internal-core", "deterministic", 7)))
    write_run_report(result, str(tmp_path / "first"))
    expected = ExpectedRunSet((ExpectedBenchmarkRun.from_identity(result.identity),))

    assert create_attestation(tmp_path, tmp_path / "ok.json", expected).accepted

    write_run_report(result, str(tmp_path / "duplicate"))
    duplicate = create_attestation(tmp_path, tmp_path / "duplicate.json", expected)
    assert not duplicate.accepted
    assert any("duplicate" in item for item in duplicate.acceptance_errors)


def test_attestation_rejects_report_tree_inconsistency(monkeypatch, tmp_path) -> None:
    _clean_git(monkeypatch)
    result = asyncio.run(run_suite(get_manifest("internal-core", "deterministic", 7)))
    run_dir = tmp_path / "run"
    write_run_report(result, str(run_dir))
    expected = ExpectedRunSet((ExpectedBenchmarkRun.from_identity(result.identity),))
    case_file = next((run_dir / "cases").glob("*.json"))
    case_file.write_text("{}\n", encoding="utf-8")

    attestation = create_attestation(tmp_path, tmp_path / "attestation.json", expected)
    assert not attestation.accepted
    assert any("case report" in item for item in attestation.acceptance_errors)


def test_attestation_rejects_dirty_tree(monkeypatch, tmp_path) -> None:
    _clean_git(monkeypatch)
    result = asyncio.run(run_suite(get_manifest("internal-core", "deterministic", 7)))
    write_run_report(result, str(tmp_path / "run"))
    expected = ExpectedRunSet((ExpectedBenchmarkRun.from_identity(result.identity),))
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.target_loop.attestation._git",
        lambda *args: result.identity.git_sha if args[:2] == ("rev-parse", "HEAD") else " M dirty",
    )

    attestation = create_attestation(tmp_path, tmp_path / "attestation.json", expected)
    assert not attestation.accepted
    assert any("clean" in item for item in attestation.acceptance_errors)


def _clean_git(monkeypatch) -> None:
    sha = subprocess.run(
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True,
    ).stdout.strip()
    fake = lambda *args: sha if args[:2] == ("rev-parse", "HEAD") else ""  # noqa: E731
    monkeypatch.setattr("affordance_runtime.benchmarks.target_loop.contracts._git", fake)
    monkeypatch.setattr("affordance_runtime.benchmarks.target_loop.attestation._git", fake)
