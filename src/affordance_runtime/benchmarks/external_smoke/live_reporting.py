"""Privacy-bounded fixed external smoke report and exact-head attestation."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.benchmarks.external_smoke.adapter_reporting import _atomic_json
from affordance_runtime.benchmarks.external_smoke.live_runner import FixedExternalSmokeOutcome
from affordance_runtime.benchmarks.external_smoke.manifest import (
    EXTERNAL_SMOKE_MANIFEST,
    REVIEWED_TASK_IDS,
    SOURCE_COMMIT,
    external_manifest_digest,
)


def write_fixed_external_smoke(outcome: FixedExternalSmokeOutcome, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "external-smoke-report.json"
    _atomic_json(report_path, {
        "schema_version": "external-smoke-report.v2",
        "classification": (
            "EXTERNAL_SMOKE_ATTESTED_FOR_FIXED_MANIFEST"
            if outcome.accepted else "EXTERNAL_SMOKE_FAILED_WITH_RECORDED_REASON"
        ),
        "accepted": outcome.accepted,
        "errors": outcome.errors,
        "provider_id": outcome.provider_id,
        "model_id": outcome.model_id,
        "grounding_profile": outcome.grounding_profile,
        "minimum_policy_call_interval_s": outcome.minimum_policy_call_interval_s,
        "suite": asdict(outcome.suite),
    })
    identity = outcome.suite.identity
    report_sha = "sha256:" + hashlib.sha256(report_path.read_bytes()).hexdigest()
    safety = _safety(outcome)
    accepted = outcome.accepted and not identity.git_dirty and not any(safety.values())
    _atomic_json(output_dir / "attestation.json", {
        "schema_version": "external-smoke-attestation.v1",
        "git_sha": identity.git_sha,
        "git_dirty": identity.git_dirty,
        "package_name": EXTERNAL_SMOKE_MANIFEST.package_name,
        "package_version": EXTERNAL_SMOKE_MANIFEST.package_version,
        "source_commit": SOURCE_COMMIT,
        "manifest_digest": external_manifest_digest(EXTERNAL_SMOKE_MANIFEST),
        "task_ids": REVIEWED_TASK_IDS,
        "policy_profile": "one-stage ModelBackedAgentPolicy",
        "grounding_profile": outcome.grounding_profile,
        "provider_id": outcome.provider_id,
        "model_id": outcome.model_id,
        "minimum_policy_call_interval_s": outcome.minimum_policy_call_interval_s,
        "case_report_sha256": report_sha,
        "accepted": accepted,
        "safety_counts": safety,
    })


def _safety(outcome: FixedExternalSmokeOutcome) -> dict[str, int]:
    names = (
        "sent_unknown_count", "duplicate_unknown_attempts", "forbidden_effect_attempts",
        "stale_zero_call_violations", "provider_retry_count", "fallback_count", "cleanup_failures",
    )
    return {
        name: sum(int(case.measurements[name].value or 0) for case in outcome.suite.cases)
        for name in names
    }
