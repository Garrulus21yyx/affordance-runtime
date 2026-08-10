"""Exact-tree, expected-run-set attestation for target-loop reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from affordance_runtime.benchmarks.target_loop.contracts import BenchmarkManifest, BenchmarkRunIdentity
from affordance_runtime.benchmarks.target_loop.manifest import get_manifest, manifest_digest

ATTESTATION_SCHEMA_VERSION = "target-loop-attestation.v3"


@dataclass(frozen=True)
class AttestedFile:
    relative_path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ExpectedBenchmarkRun:
    suite_id: str
    profile_id: str
    seed: int
    git_sha: str
    manifest_digest: str
    manifest_schema_version: str
    harness_schema_version: str
    accepted: bool = True
    git_dirty: bool = False

    @classmethod
    def from_identity(cls, identity: BenchmarkRunIdentity) -> ExpectedBenchmarkRun:
        return cls(
            identity.suite_id, identity.profile_id, identity.seed, identity.git_sha,
            identity.manifest_digest, identity.manifest_schema_version,
            identity.harness_schema_version,
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.suite_id, self.profile_id


@dataclass(frozen=True)
class ExpectedRunSet:
    runs: tuple[ExpectedBenchmarkRun, ...]

    def __post_init__(self) -> None:
        if not self.runs:
            raise ValueError("expected run set cannot be empty")
        keys = tuple(item.key for item in self.runs)
        if len(keys) != len(set(keys)):
            raise ValueError("expected run set cannot contain duplicate suite/profile pairs")

    @classmethod
    def from_manifests(cls, manifests: tuple[BenchmarkManifest, ...]) -> ExpectedRunSet:
        sha = _git("rev-parse", "HEAD")
        return cls(tuple(
            ExpectedBenchmarkRun(
                item.suite_id, item.profile_id, item.seed, sha, manifest_digest(item),
                item.schema_version, "target-loop-harness.v4",
            )
            for item in manifests
        ))

    @property
    def digest(self) -> str:
        payload = [asdict(item) for item in sorted(self.runs, key=lambda item: item.key)]
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class BenchmarkAttestation:
    attestation_schema_version: str
    expected_run_set_digest: str
    git_sha: str
    git_dirty: bool
    harness_schema_version: str
    manifest_digests: tuple[str, ...]
    run_profiles: tuple[str, ...]
    forbidden_effect_attempts: int
    duplicate_unknown_attempts: int
    stale_zero_call_violations: int
    report_files: tuple[AttestedFile, ...]
    accepted: bool
    acceptance_errors: tuple[str, ...]


def create_attestation(
    input_dir: Path,
    output: Path,
    expected: ExpectedRunSet,
) -> BenchmarkAttestation:
    root = input_dir.resolve()
    destination = output.resolve()
    current_sha = _git("rev-parse", "HEAD")
    current_dirty = bool(_git("status", "--short"))
    run_files = tuple(sorted(root.rglob("run.json")))
    errors: list[str] = []
    if not run_files:
        errors.append("attestation requires at least one benchmark run report")
    runs = tuple(_read_object(path, errors) for path in run_files)
    _validate_expected_runs(runs, expected, current_sha, current_dirty, errors)
    for path, run in zip(run_files, runs, strict=True):
        _validate_report_tree(path.parent, run, errors)
    files = tuple(
        _attested_file(path, root)
        for path in sorted(root.rglob("*.json"))
        if path.resolve() != destination
    )
    manifests = tuple(sorted({str(run.get("identity", {}).get("manifest_digest", "")) for run in runs}))
    profiles = tuple(sorted({
        f"{run.get('identity', {}).get('suite_id', '')}:{run.get('identity', {}).get('profile_id', '')}"
        for run in runs
    }))
    schemas = {str(run.get("identity", {}).get("harness_schema_version", "")) for run in runs}
    if len(schemas) != 1:
        errors.append("run reports do not share one harness schema")
    safety = tuple(_safety_total(runs, name, errors) for name in (
        "forbidden_effect_attempts", "duplicate_unknown_attempts", "stale_zero_call_violations",
    ))
    attestation = BenchmarkAttestation(
        ATTESTATION_SCHEMA_VERSION, expected.digest, current_sha, current_dirty,
        next(iter(schemas), ""), manifests, profiles,
        safety[0], safety[1], safety[2], files, not errors, tuple(errors),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asdict(attestation), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return attestation


def _validate_expected_runs(runs, expected, current_sha, current_dirty, errors) -> None:
    if current_dirty:
        errors.append("attestation requires a clean exact tree")
    actual: dict[tuple[str, str], list[dict]] = {}
    for run in runs:
        identity = run.get("identity", {})
        key = str(identity.get("suite_id", "")), str(identity.get("profile_id", ""))
        actual.setdefault(key, []).append(run)
    for key, values in actual.items():
        if len(values) > 1:
            errors.append(f"duplicate benchmark run for {key[0]}:{key[1]}")
    expected_by_key = {item.key: item for item in expected.runs}
    for key in sorted(expected_by_key.keys() - actual.keys()):
        errors.append(f"missing expected benchmark run {key[0]}:{key[1]}")
    for key in sorted(actual.keys() - expected_by_key.keys()):
        errors.append(f"unexpected benchmark run {key[0]}:{key[1]}")
    for key in sorted(expected_by_key.keys() & actual.keys()):
        _validate_run(actual[key][0], expected_by_key[key], current_sha, current_dirty, errors)


def _validate_run(run, expected, current_sha, current_dirty, errors) -> None:
    identity = run.get("identity", {})
    acceptance = run.get("acceptance", {})
    checks = {
        "seed": expected.seed,
        "git_sha": expected.git_sha,
        "git_dirty": expected.git_dirty,
        "manifest_digest": expected.manifest_digest,
        "manifest_schema_version": expected.manifest_schema_version,
        "harness_schema_version": expected.harness_schema_version,
    }
    for field, value in checks.items():
        if identity.get(field) != value:
            errors.append(f"{expected.suite_id}:{expected.profile_id} identity mismatch: {field}")
    if identity.get("git_sha") != current_sha or bool(identity.get("git_dirty")) != current_dirty:
        errors.append("report identity does not match the current exact tree")
    if bool(acceptance.get("accepted")) != expected.accepted:
        errors.append(f"{expected.suite_id}:{expected.profile_id} acceptance mismatch")
    if not acceptance.get("accepted"):
        errors.extend(str(item) for item in acceptance.get("acceptance_errors", ()))


def _validate_report_tree(run_dir: Path, run: dict, errors: list[str]) -> None:
    identity = run.get("identity", {})
    summary_path = run_dir / "summary.json"
    summary = _read_object(summary_path, errors)
    expected_summary = {
        "identity": identity,
        "acceptance": run.get("acceptance", {}),
        "rates": run.get("rates", {}),
    }
    if summary != expected_summary:
        errors.append(f"summary report differs from run report: {run_dir.name}")
    cases = run.get("cases", [])
    expected_cases = {str(item.get("case_id", "")): item for item in cases if isinstance(item, dict)}
    case_files = tuple(sorted((run_dir / "cases").glob("*.json")))
    actual_ids = {path.stem for path in case_files}
    if actual_ids != set(expected_cases):
        errors.append(f"case report set differs from run report: {run_dir.name}")
    for path in case_files:
        if _read_object(path, errors) != expected_cases.get(path.stem):
            errors.append(f"case report differs from run report: {path.stem}")


def _read_object(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(f"invalid JSON report: {path.name}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"JSON report must be an object: {path.name}")
        return {}
    return value


def _safety_total(runs: tuple[dict, ...], name: str, errors: list[str]) -> int:
    total = 0
    for run in runs:
        for case in run.get("cases", ()):
            measurement = case.get("measurements", {}).get(name, {}) if isinstance(case, dict) else {}
            value = measurement.get("value") if measurement.get("measured") is True else None
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"required attestation safety metric is unavailable: {name}")
                continue
            total += value
    return total


def _attested_file(path: Path, root: Path) -> AttestedFile:
    content = path.read_bytes()
    return AttestedFile(path.relative_to(root).as_posix(), hashlib.sha256(content).hexdigest(), len(content))


def _git(*args: str) -> str:
    result = subprocess.run(("git", *args), check=True, capture_output=True, text=True)
    value = result.stdout.strip()
    if args[:2] == ("rev-parse", "HEAD") and len(value) != 40:
        raise RuntimeError("attestation requires an exact git SHA")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-run", action="append", required=True, metavar="SUITE:PROFILE:SEED")
    args = parser.parse_args()
    manifests = tuple(_manifest_arg(item) for item in args.expected_run)
    attestation = create_attestation(
        Path(args.input_dir), Path(args.output), ExpectedRunSet.from_manifests(manifests),
    )
    return 0 if attestation.accepted else 1


def _manifest_arg(value: str) -> BenchmarkManifest:
    try:
        suite, profile, seed = value.split(":", 2)
        return get_manifest(suite, profile, int(seed))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("expected run must be SUITE:PROFILE:SEED") from exc


if __name__ == "__main__":
    raise SystemExit(main())
