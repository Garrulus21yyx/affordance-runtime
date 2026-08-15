import json

from affordance_runtime.benchmarks.target_loop.full_validation import (
    REQUIRED_CHECKS,
    create_full_validation_attestation,
)


def test_full_validation_attestation_binds_counts_checks_and_collection(monkeypatch, tmp_path) -> None:
    sha = "a" * 40
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.target_loop.full_validation._git",
        lambda *args: sha if args[:2] == ("rev-parse", "HEAD") else "",
    )
    collection = tmp_path / "collection.txt"
    collection.write_text(
        "tests/test_a.py::test_one\ntests/test_b.py::test_two\n"
        "tests/test_b.py::test_skip\n3 tests collected in 0.01s\n"
    )
    pytest_log = tmp_path / "pytest.txt"
    pytest_log.write_text(".. [100%]\n2 passed, 1 skipped in 0.20s\n")
    output = tmp_path / "full-validation.json"

    result = create_full_validation_attestation(
        collection, pytest_log, output, frozenset(REQUIRED_CHECKS),
    )

    assert result.accepted
    assert result.git_sha == sha and not result.git_dirty
    assert result.collected == 3 and result.passed == 2 and result.skipped == 1
    assert result.shard_manifest_digest.startswith("sha256:")
    assert json.loads(output.read_text())["attestation_schema_version"]


def test_full_validation_attestation_fails_closed_for_dirty_or_missing_check(monkeypatch, tmp_path) -> None:
    sha = "b" * 40
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.target_loop.full_validation._git",
        lambda *args: sha if args[:2] == ("rev-parse", "HEAD") else " M dirty",
    )
    collection = tmp_path / "collection.txt"
    collection.write_text("tests/test_a.py::test_one\n1 test collected in 0.01s\n")
    pytest_log = tmp_path / "pytest.txt"
    pytest_log.write_text("1 passed in 0.20s\n")

    result = create_full_validation_attestation(
        collection, pytest_log, tmp_path / "result.json",
        frozenset(REQUIRED_CHECKS) - {"docs_governance"},
    )

    assert not result.accepted
    assert any("clean" in error for error in result.acceptance_errors)
    assert any("docs_governance" in error for error in result.acceptance_errors)


def test_full_validation_attestation_rejects_failed_or_mismatched_pytest(monkeypatch, tmp_path) -> None:
    sha = "c" * 40
    monkeypatch.setattr(
        "affordance_runtime.benchmarks.target_loop.full_validation._git",
        lambda *args: sha if args[:2] == ("rev-parse", "HEAD") else "",
    )
    collection = tmp_path / "collection.txt"
    collection.write_text("tests/test_a.py::test_one\n2 tests collected in 0.01s\n")
    pytest_log = tmp_path / "pytest.txt"
    pytest_log.write_text("1 failed, 1 passed in 0.20s\n")

    result = create_full_validation_attestation(
        collection, pytest_log, tmp_path / "result.json", frozenset(REQUIRED_CHECKS),
    )

    assert not result.accepted
    assert result.failed == 1
    assert any("pytest" in error for error in result.acceptance_errors)
