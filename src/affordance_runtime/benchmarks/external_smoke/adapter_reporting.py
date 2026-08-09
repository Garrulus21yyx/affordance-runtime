"""Atomic privacy-bounded BrowserGym adapter report and attestation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.adapter_conformance import AdapterConformanceOutcome
from affordance_runtime.benchmarks.external_smoke.browsergym_inventory import REVIEWED_TASK_IDS
from affordance_runtime.benchmarks.external_smoke.manifest import (
    EXTERNAL_SMOKE_MANIFEST,
    SOURCE_COMMIT,
    external_manifest_digest,
)


def write_adapter_conformance(outcome: AdapterConformanceOutcome, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "adapter-conformance.json"
    _atomic_json(report, {
        "schema_version": "browsergym-adapter-conformance-report.v1",
        "accepted": outcome.accepted,
        "errors": outcome.errors,
        "package_version": outcome.package_version,
        "target_loop_adapter_ready": outcome.target_loop_adapter_ready,
        "suite": asdict(outcome.suite),
    })
    sha = _sha256(report)
    identity = outcome.suite.identity
    accepted = outcome.accepted and not identity.git_dirty
    _atomic_json(output_dir / "attestation.json", {
        "schema_version": "browsergym-adapter-attestation.v1",
        "git_sha": identity.git_sha,
        "git_dirty": identity.git_dirty,
        "package_name": EXTERNAL_SMOKE_MANIFEST.package_name,
        "package_version": outcome.package_version,
        "source_commit": SOURCE_COMMIT,
        "manifest_digest": external_manifest_digest(EXTERNAL_SMOKE_MANIFEST),
        "task_ids": REVIEWED_TASK_IDS,
        "case_report_sha256": sha,
        "accepted": accepted,
        "target_loop_adapter_ready": accepted,
        "safety_counts": _safety_counts(outcome),
    })
    return report


def _safety_counts(outcome: AdapterConformanceOutcome) -> dict[str, int]:
    names = (
        "forbidden_effect_attempts", "duplicate_unknown_attempts",
        "stale_zero_call_violations", "sent_unknown_count", "cleanup_failures",
        "provider_retry_count", "fallback_count",
    )
    return {
        name: sum(int(case.measurements[name].value or 0) for case in outcome.suite.cases)
        for name in names
    }


def _atomic_json(path: Path, value: object) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
