"""Secret-free exact-head attestation for the complete local validation gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

ATTESTATION_SCHEMA_VERSION = "target-loop-full-validation.v1"
REQUIRED_CHECKS = (
    "ruff", "mypy", "diff_check", "compose_config", "target_boundaries",
    "docs_governance",
)


@dataclass(frozen=True)
class FullValidationAttestation:
    attestation_schema_version: str
    git_sha: str
    git_dirty: bool
    collected: int
    passed: int
    skipped: int
    failed: int
    shard_manifest_digest: str
    pytest_passed: bool
    ruff_passed: bool
    mypy_passed: bool
    diff_check_passed: bool
    compose_config_passed: bool
    target_boundaries_passed: bool
    docs_governance_passed: bool
    accepted: bool
    acceptance_errors: tuple[str, ...]


def create_full_validation_attestation(
    collection_path: Path,
    pytest_log_path: Path,
    output: Path,
    completed_checks: frozenset[str],
) -> FullValidationAttestation:
    sha = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--short"))
    collection = collection_path.read_text(encoding="utf-8")
    pytest_log = pytest_log_path.read_text(encoding="utf-8")
    nodes, collected = _collection(collection)
    passed, skipped, failed = _pytest_counts(pytest_log)
    errors: list[str] = []
    if dirty:
        errors.append("full validation attestation requires a clean exact tree")
    if len(nodes) != collected:
        errors.append("pytest collection node manifest does not match collected count")
    pytest_ok = failed == 0 and passed + skipped == collected
    if not pytest_ok:
        errors.append("full pytest result does not match the exact collection")
    unknown = completed_checks - set(REQUIRED_CHECKS)
    if unknown:
        errors.append(f"unknown validation checks: {','.join(sorted(unknown))}")
    missing = set(REQUIRED_CHECKS) - completed_checks
    errors.extend(f"required validation check missing: {item}" for item in sorted(missing))
    checks = {name: name in completed_checks for name in REQUIRED_CHECKS}
    digest = "sha256:" + hashlib.sha256("\n".join(nodes).encode()).hexdigest()
    result = FullValidationAttestation(
        ATTESTATION_SCHEMA_VERSION, sha, dirty, collected, passed, skipped, failed,
        digest, pytest_ok, checks["ruff"], checks["mypy"], checks["diff_check"],
        checks["compose_config"], checks["target_boundaries"],
        checks["docs_governance"], not errors, tuple(errors),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(result), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def _collection(text: str) -> tuple[tuple[str, ...], int]:
    nodes = tuple(sorted(line.strip() for line in text.splitlines() if "::" in line))
    matches = re.findall(r"(\d+) tests? collected", text)
    if len(matches) != 1:
        raise ValueError("collection output must contain one collected count")
    return nodes, int(matches[0])


def _pytest_counts(text: str) -> tuple[int, int, int]:
    return tuple(_summary_count(text, name) for name in ("passed", "skipped", "failed"))  # type: ignore[return-value]


def _summary_count(text: str, name: str) -> int:
    matches = re.findall(rf"(\d+) {name}", text)
    return int(matches[-1]) if matches else 0


def _git(*args: str) -> str:
    result = subprocess.run(("git", *args), check=True, capture_output=True, text=True)
    value = result.stdout.strip()
    if args[:2] == ("rev-parse", "HEAD") and len(value) != 40:
        raise RuntimeError("full validation requires an exact git SHA")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    parser.add_argument("--pytest-log", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--check", action="append", choices=REQUIRED_CHECKS, default=[])
    args = parser.parse_args()
    result = create_full_validation_attestation(
        Path(args.collection), Path(args.pytest_log), Path(args.output), frozenset(args.check),
    )
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
