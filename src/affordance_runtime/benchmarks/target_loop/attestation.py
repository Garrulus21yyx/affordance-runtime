"""Exact-tree digest attestation for secret-free target-loop report files."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AttestedFile:
    relative_path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class BenchmarkAttestation:
    git_sha: str
    git_dirty: bool
    harness_schema_version: str
    manifest_digests: tuple[str, ...]
    run_profiles: tuple[str, ...]
    report_files: tuple[AttestedFile, ...]
    accepted: bool
    acceptance_errors: tuple[str, ...]


def create_attestation(input_dir: Path, output: Path) -> BenchmarkAttestation:
    root = input_dir.resolve()
    destination = output.resolve()
    run_files = tuple(sorted(root.rglob("run.json")))
    if not run_files:
        raise ValueError("attestation requires at least one benchmark run report")
    current_sha = _git("rev-parse", "HEAD")
    current_dirty = bool(_git("status", "--short"))
    runs = tuple(json.loads(path.read_text(encoding="utf-8")) for path in run_files)
    errors = []
    for run in runs:
        identity = run.get("identity", {})
        acceptance = run.get("acceptance", {})
        if identity.get("git_sha") != current_sha or bool(identity.get("git_dirty")) != current_dirty:
            errors.append("report identity does not match the current exact tree")
        if not acceptance.get("accepted"):
            errors.extend(str(item) for item in acceptance.get("acceptance_errors", ()))
    files = tuple(
        _attested_file(path, root)
        for path in sorted(root.rglob("*.json"))
        if path.resolve() != destination
    )
    manifests = tuple(sorted({run["identity"]["manifest_digest"] for run in runs}))
    profiles = tuple(sorted({
        f"{run['identity']['suite_id']}:{run['identity']['profile_id']}" for run in runs
    }))
    schemas = {run["identity"]["harness_schema_version"] for run in runs}
    if len(schemas) != 1:
        errors.append("run reports do not share one harness schema")
    attestation = BenchmarkAttestation(
        current_sha, current_dirty, next(iter(schemas), ""), manifests, profiles,
        files, not errors, tuple(errors),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asdict(attestation), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return attestation


def _attested_file(path: Path, root: Path) -> AttestedFile:
    content = path.read_bytes()
    return AttestedFile(
        path.relative_to(root).as_posix(), hashlib.sha256(content).hexdigest(), len(content),
    )


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
    args = parser.parse_args()
    attestation = create_attestation(Path(args.input_dir), Path(args.output))
    return 0 if attestation.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
