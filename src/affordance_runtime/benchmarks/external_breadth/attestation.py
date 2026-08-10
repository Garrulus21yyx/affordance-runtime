"""Read-only validation for a completed breadth report tree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.target_loop.case_projection import decode_public_case_evidence


def validate_campaign_tree(output_dir: Path) -> tuple[str, ...]:
    errors: list[str] = []
    attestation = _object(output_dir / "attestation.json")
    campaign = _object(output_dir / "campaign.json")
    _validate_root_identity(attestation, campaign, errors)
    cases = attestation.get("case_report_sha256")
    if not isinstance(cases, dict) or len(cases) != 60:
        errors.append("attestation does not bind exactly 60 case reports")
        return tuple(errors)
    campaign_cases = campaign.get("cases")
    expected_order = tuple(
        str(item.get("case_id", ""))
        for item in campaign_cases
        if isinstance(item, dict)
    ) if isinstance(campaign_cases, list) else ()
    expected = tuple(f"miniwob-60-{index:02d}" for index in range(1, 61))
    if expected_order != expected or tuple(cases) != expected:
        errors.append("attested case IDs are missing, extra, or duplicated")
    case_files = tuple(sorted(path.name for path in (output_dir / "cases").glob("*.json")))
    if case_files != tuple(f"{case_id}.json" for case_id in expected):
        errors.append("case report files are missing, extra, or unordered")
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
            _validate_case_binding(decoded, payload, attestation, errors)
            decoded_cases.append(decoded)
    for name, field in (("summary.json", "summary_sha256"), ("campaign.json", "campaign_sha256")):
        path = output_dir / name
        if not path.is_file() or attestation.get(field) != _sha256(path):
            errors.append(f"{name}: report digest mismatch")
    capacity = attestation.get("provider_capacity")
    if not _valid_capacity(capacity, attestation):
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
    from affordance_runtime.benchmarks.external_breadth.reporting import privacy_scan

    errors.extend(privacy_scan(output_dir))
    return tuple(errors)


def _validate_root_identity(attestation, campaign, errors) -> None:
    if (
        attestation.get("schema_version") != "miniwob-breadth-attestation.v1"
        or attestation.get("classification") != "MINIWOB_60_SEEDED_BREADTH_PROFILE"
        or attestation.get("evidence_valid") is not True
        or attestation.get("git_dirty") is not False
        or attestation.get("planned_cases") != 60
        or attestation.get("completed_cases") != 60
        or attestation.get("harness_schema_version") != "target-loop-harness.v6"
        or attestation.get("case_schema_version") != "target-loop-case.v6"
    ):
        errors.append("attestation identity/schema/acceptance is invalid")
    acceptance = campaign.get("acceptance")
    if (
        campaign.get("schema_version") != "miniwob-breadth-campaign.v1"
        or campaign.get("classification") != attestation.get("classification")
        or campaign.get("git_sha") != attestation.get("git_sha")
        or campaign.get("git_dirty") is not False
        or campaign.get("manifest_digest") != attestation.get("manifest_digest")
        or campaign.get("complete") is not True
        or not isinstance(acceptance, dict)
        or acceptance.get("evidence_valid") is not True
        or acceptance.get("planned_cases") != 60
        or acceptance.get("completed_cases") != 60
    ):
        errors.append("campaign identity/schema/acceptance is invalid")


def _validate_case_binding(result, payload, attestation, errors) -> None:
    if (
        result.suite_id != attestation.get("campaign_id")
        or result.profile_id != attestation.get("profile_id")
        or result.seed != attestation.get("seed")
        or result.manifest_digest != attestation.get("target_manifest_digest")
        or result.case_schema_version != attestation.get("case_schema_version")
        or result.harness_schema_version != attestation.get("harness_schema_version")
    ):
        errors.append(f"{result.case_id}: formal case identity/schema mismatch")
    classified = classify_case(result)
    if (
        payload.get("typed_outcome") != classified.outcome.value
        or payload.get("classification_source") != classified.source
    ):
        errors.append(f"{result.case_id}: classification is not reproducible")


def _valid_capacity(value, attestation) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("schema_version") == "provider-capacity-preflight.v1"
        and value.get("provider_id") == attestation.get("provider_id")
        and value.get("model_id") == attestation.get("model_id")
        and value.get("manifest_digest") == attestation.get("manifest_digest")
        and value.get("grounding_profile") == attestation.get("grounding_profile")
        and value.get("checked") is True
        and value.get("sufficient") is True
        and type(value.get("required_attempt_budget")) is int
        and type(value.get("declared_attempt_budget")) is int
        and value["required_attempt_budget"] > 0
        and value["declared_attempt_budget"] >= value["required_attempt_budget"]
        and value.get("retry_count") == 0
        and value.get("fallback_count") == 0
    )


def _object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
