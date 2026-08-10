"""Read-only validation for a completed breadth report tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from affordance_runtime.benchmarks.target_loop.case_projection import decode_public_case_evidence


def validate_campaign_tree(output_dir: Path) -> tuple[str, ...]:
    errors: list[str] = []
    attestation = _object(output_dir / "attestation.json")
    cases = attestation.get("case_report_sha256")
    if not isinstance(cases, dict) or len(cases) != 60:
        errors.append("attestation does not bind exactly 60 case reports")
        return tuple(errors)
    expected = {f"miniwob-60-{index:02d}" for index in range(1, 61)}
    if set(cases) != expected:
        errors.append("attested case IDs are missing, extra, or duplicated")
    decoded_cases = []
    for case_id, digest in cases.items():
        path = output_dir / "cases" / f"{case_id}.json"
        if not path.is_file() or digest != _sha256(path):
            errors.append(f"{case_id}: case report digest mismatch")
            continue
        payload = _object(path)
        evidence = payload.get("benchmark_case_evidence")
        try:
            decoded = decode_public_case_evidence(evidence) if isinstance(evidence, dict) else None
        except (TypeError, ValueError):
            decoded = None
        if decoded is None or decoded.case_id != case_id:
            errors.append(f"{case_id}: public case evidence is incomplete or misbound")
        else:
            decoded_cases.append(decoded)
    for name, field in (("summary.json", "summary_sha256"), ("campaign.json", "campaign_sha256")):
        path = output_dir / name
        if not path.is_file() or attestation.get(field) != _sha256(path):
            errors.append(f"{name}: report digest mismatch")
    capacity = attestation.get("provider_capacity")
    if not isinstance(capacity, dict) or capacity.get("sufficient") is not True:
        errors.append("explicit provider capacity evidence is missing or insufficient")
    for result in decoded_cases:
        if result.harness_integrity_failures or result.failure_facts.harness_integrity_code:
            errors.append(f"{result.case_id}: harness integrity failed")
        if result.cleanup_failures or result.failure_facts.cleanup_code:
            errors.append(f"{result.case_id}: cleanup failed")
        for metric in (
            "provider_retry_count", "fallback_count", "forbidden_effect_attempts",
            "duplicate_unknown_attempts", "stale_zero_call_violations",
            "observation_contract_exceptions",
        ):
            measurement = result.measurements.get(metric)
            if measurement is None or not measurement.measured or measurement.value != 0:
                errors.append(f"{result.case_id}: formal gate {metric} is unavailable or nonzero")
    return tuple(errors)


def _object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
