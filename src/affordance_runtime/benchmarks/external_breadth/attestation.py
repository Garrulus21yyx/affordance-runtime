"""Read-only contract validation for one completed formal breadth report tree."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
)
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobBreadthManifest
from affordance_runtime.benchmarks.external_breadth.manifest import breadth_manifest_digest
from affordance_runtime.benchmarks.external_breadth.progress import case_progress_digest
from affordance_runtime.benchmarks.external_breadth.runner import (
    REQUIRED_METRICS,
    expected_target_manifest_digest,
)
from affordance_runtime.benchmarks.target_loop.case_projection import (
    decode_public_case_evidence,
)

_SHA = re.compile(r"[0-9a-f]{40}")


def validate_campaign_tree(
    output_dir: Path,
    manifest: MiniWobBreadthManifest,
) -> tuple[str, ...]:
    errors: list[str] = []
    attestation = _object(output_dir / "attestation.json")
    campaign = _object(output_dir / "campaign.json")
    summary = _object(output_dir / "summary.json")
    progress = _object(output_dir / "campaign-progress.json")
    expected_breadth_digest = breadth_manifest_digest(manifest)
    expected_target_digest = expected_target_manifest_digest(manifest)
    _validate_root_identity(
        attestation,
        campaign,
        manifest,
        expected_breadth_digest,
        expected_target_digest,
        errors,
    )
    cases = attestation.get("case_report_sha256")
    if not isinstance(cases, dict) or len(cases) != len(manifest.cases):
        errors.append("attestation does not bind exactly the frozen case set")
        return tuple(errors)
    expected_ids = tuple(item.case_id for item in manifest.cases)
    expected_files = {
        "attestation.json",
        "campaign.json",
        "summary.json",
        "campaign-progress.json",
        *(f"cases/{case_id}.json" for case_id in expected_ids),
    }
    actual_files = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        errors.append("formal report recursive file set is incomplete or contains extras")
    campaign_cases = campaign.get("cases")
    campaign_order = tuple(
        item.get("case_id") for item in campaign_cases if isinstance(item, dict)
    ) if isinstance(campaign_cases, list) else ()
    if tuple(cases) != expected_ids or campaign_order != expected_ids:
        errors.append("attested case IDs/order do not match the frozen manifest")
    case_files = tuple(sorted(path.name for path in (output_dir / "cases").glob("*.json")))
    if case_files != tuple(sorted(f"{case_id}.json" for case_id in expected_ids)):
        errors.append("case report file set does not match the frozen manifest")
    root_files = {path.name for path in output_dir.iterdir() if path.is_file()}
    if root_files != {
        "attestation.json", "campaign.json", "summary.json", "campaign-progress.json",
    }:
        errors.append("formal report root file set is incomplete or contains extras")

    records: list[MiniWobBreadthCaseRecord] = []
    case_payloads: list[dict[str, object]] = []
    for case, (case_id, digest) in zip(manifest.cases, cases.items(), strict=True):
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
        if decoded is None:
            errors.append(f"{case_id}: public case evidence is malformed")
            continue
        if not _required_metrics_are_measured(decoded):
            errors.append(f"{case_id}: required formal metrics are incomplete")
            continue
        classified = classify_case(decoded)
        raw_required = payload.get("required_primitives")
        required_primitives = (
            tuple(raw_required)
            if isinstance(raw_required, list)
            and all(isinstance(item, str) for item in raw_required)
            else ()
        )
        expected_outer = (
            set(payload) == {
                "schema_version", "case_id", "task_family_label", "capability_profile",
                "required_primitives", "typed_outcome", "classification_source",
                "benchmark_case_evidence",
            }
            and payload.get("schema_version") == "miniwob-breadth-case.v3"
            and payload.get("case_id") == case.case_id
            and payload.get("task_family_label")
            == case.task_id.removeprefix("browsergym/miniwob.")
            and payload.get("capability_profile") == case.capability_profile
            and required_primitives == case.required_primitives
            and payload.get("typed_outcome") == classified.outcome.value
            and payload.get("classification_source") == classified.source
        )
        if not expected_outer:
            errors.append(f"{case_id}: outer case identity/classification mismatch")
        _validate_case_binding(
            decoded, case, attestation, expected_target_digest, errors,
        )
        records.append(MiniWobBreadthCaseRecord(
            case.case_id,
            case.task_id.removeprefix("browsergym/miniwob."),
            case.capability_profile,
            case.required_primitives,
            classified.outcome,
            classified.source,
            decoded,
        ))
        case_payloads.append(payload)

    for name, field in (
        ("summary.json", "summary_sha256"),
        ("campaign.json", "campaign_sha256"),
        ("campaign-progress.json", "progress_sha256"),
    ):
        path = output_dir / name
        if not path.is_file() or attestation.get(field) != _sha256(path):
            errors.append(f"{name}: report digest mismatch")
    _validate_capacity(attestation.get("provider_capacity"), attestation, manifest, errors)
    try:
        _validate_aggregates(
            records, case_payloads, summary, campaign, progress, manifest, errors,
        )
    except (ArithmeticError, KeyError, TypeError, ValueError):
        errors.append("campaign aggregate projection is malformed")
    for result in (item.result for item in records):
        _validate_formal_case_gates(result, errors)
    from affordance_runtime.benchmarks.external_breadth.reporting import privacy_scan

    errors.extend(privacy_scan(output_dir))
    return tuple(errors)


def _validate_root_identity(
    attestation,
    campaign,
    manifest,
    breadth_digest,
    target_digest,
    errors,
) -> None:
    sha = attestation.get("git_sha")
    acceptance = campaign.get("acceptance")
    expected_attestation = {
        "schema_version": "miniwob-breadth-attestation.v1",
        "classification": "MINIWOB_60_SEEDED_BREADTH_PROFILE",
        "campaign_id": manifest.campaign_id,
        "manifest_digest": breadth_digest,
        "manifest_schema_version": manifest.schema_version,
        "selection_namespace": manifest.selection_namespace,
        "target_manifest_digest": target_digest,
        "profile_id": "mistral-format-only-v1",
        "harness_schema_version": "target-loop-harness.v6",
        "case_schema_version": "target-loop-case.v6",
        "registry_digest": manifest.registry_digest,
        "capability_inventory_digest": manifest.capability_inventory_digest,
        "package_name": manifest.package_name,
        "package_version": manifest.package_version,
        "source_commit": manifest.source_commit,
        "model_id": manifest.model_profile,
        "provider_id": "mistral",
        "grounding_profile": manifest.grounding_profile,
        "minimum_policy_call_interval_s": manifest.minimum_policy_call_interval_s,
        "seed": 7,
        "planned_cases": len(manifest.cases),
        "completed_cases": len(manifest.cases),
        "git_dirty": False,
        "evidence_valid": True,
        "privacy_errors": [],
        "generalization_claim": "NOT_CLAIMED",
    }
    if any(attestation.get(name) != value for name, value in expected_attestation.items()):
        errors.append("attestation identity/schema/profile is not the frozen contract")
    if (
        type(attestation.get("git_dirty")) is not bool
        or type(attestation.get("evidence_valid")) is not bool
        or type(attestation.get("seed")) is not int
        or type(attestation.get("planned_cases")) is not int
        or type(attestation.get("completed_cases")) is not int
        or isinstance(attestation.get("minimum_policy_call_interval_s"), bool)
        or not isinstance(attestation.get("minimum_policy_call_interval_s"), int | float)
    ):
        errors.append("attestation scalar types are invalid")
    expected_attestation_fields = set(expected_attestation) | {
        "run_id", "git_sha", "case_report_sha256", "summary_sha256", "campaign_sha256",
        "progress_sha256", "provider_capacity",
    }
    if set(attestation) != expected_attestation_fields:
        errors.append("attestation fields do not match the formal schema")
    if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
        errors.append("attestation git SHA is invalid")
    if not isinstance(attestation.get("run_id"), str) or not attestation["run_id"]:
        errors.append("attestation run identity is invalid")
    expected_campaign = {
        "schema_version": "miniwob-breadth-campaign.v1",
        "classification": "MINIWOB_60_SEEDED_BREADTH_PROFILE",
        "run_id": attestation.get("run_id"),
        "campaign_id": manifest.campaign_id,
        "manifest_digest": breadth_digest,
        "manifest_schema_version": manifest.schema_version,
        "selection_namespace": manifest.selection_namespace,
        "target_manifest_digest": target_digest,
        "profile_id": "mistral-format-only-v1",
        "harness_schema_version": "target-loop-harness.v6",
        "case_schema_version": "target-loop-case.v6",
        "git_sha": sha,
        "git_dirty": False,
        "complete": True,
    }
    if any(campaign.get(name) != value for name, value in expected_campaign.items()):
        errors.append("campaign identity/schema/profile is not cross-bound")
    if (
        type(campaign.get("git_dirty")) is not bool
        or type(campaign.get("complete")) is not bool
    ):
        errors.append("campaign scalar types are invalid")
    if set(campaign) != set(expected_campaign) | {"acceptance", "cases"}:
        errors.append("campaign fields do not match the formal schema")
    if (
        not isinstance(acceptance, dict)
        or set(acceptance) != {
            "evidence_valid", "errors", "planned_cases", "completed_cases",
            "successful_cases",
        }
        or acceptance.get("evidence_valid") is not True
        or acceptance.get("errors") not in ([], ())
        or type(acceptance.get("planned_cases")) is not int
        or acceptance.get("planned_cases") != len(manifest.cases)
        or type(acceptance.get("completed_cases")) is not int
        or acceptance.get("completed_cases") != len(manifest.cases)
        or type(acceptance.get("successful_cases")) is not int
    ):
        errors.append("campaign formal acceptance is invalid")


def _validate_case_binding(result, case, attestation, target_digest, errors) -> None:
    if (
        result.case_id != case.case_id
        or result.suite_id != attestation.get("campaign_id")
        or result.profile_id != attestation.get("profile_id")
        or result.seed != case.seed
        or result.manifest_digest != target_digest
        or result.case_schema_version != "target-loop-case.v6"
        or result.harness_schema_version != "target-loop-harness.v6"
    ):
        errors.append(f"{case.case_id}: formal case identity/schema mismatch")


def _validate_capacity(value, attestation, manifest, errors) -> None:
    required = sum(item.max_turns for item in manifest.cases)
    fields = {
        "schema_version", "provider_id", "model_id", "manifest_digest",
        "required_attempt_budget", "declared_attempt_budget", "checked", "sufficient",
        "grounding_profile", "retry_count", "fallback_count",
    }
    valid = bool(
        isinstance(value, dict)
        and set(value) == fields
        and value.get("schema_version") == "provider-capacity-preflight.v1"
        and value.get("provider_id") == "mistral"
        and value.get("model_id") == manifest.model_profile
        and value.get("manifest_digest") == breadth_manifest_digest(manifest)
        and value.get("grounding_profile") == manifest.grounding_profile
        and value.get("checked") is True
        and value.get("sufficient") is True
        and type(value.get("required_attempt_budget")) is int
        and value.get("required_attempt_budget") == required
        and type(value.get("declared_attempt_budget")) is int
        and value["declared_attempt_budget"] >= required
        and type(value.get("retry_count")) is int
        and value.get("retry_count") == 0
        and type(value.get("fallback_count")) is int
        and value.get("fallback_count") == 0
        and value.get("provider_id") == attestation.get("provider_id")
        and value.get("model_id") == attestation.get("model_id")
    )
    if not valid:
        errors.append("explicit provider capacity evidence is misbound or insufficient")


def _validate_aggregates(records, payloads, summary, campaign, progress, manifest, errors) -> None:
    if len(records) != len(manifest.cases):
        errors.append("decoded case set is incomplete")
        return
    from affordance_runtime.benchmarks.external_breadth.reporting import (
        _aggregate,
        _case_summary,
    )

    aggregate_input = cast(Any, SimpleNamespace(cases=tuple(records)))
    expected_summary = _aggregate(aggregate_input)
    if summary != expected_summary:
        errors.append("summary is not a pure aggregate of decoded case evidence")
    expected_campaign_cases = [_case_summary(payload) for payload in payloads]
    if campaign.get("cases") != expected_campaign_cases:
        errors.append("campaign case summaries are not a pure case projection")
    acceptance = campaign.get("acceptance")
    successful = sum(item.outcome.value == "success" for item in records)
    if not isinstance(acceptance, dict) or acceptance.get("successful_cases") != successful:
        errors.append("campaign acceptance success count is not derived from cases")
    expected_progress = {
        "schema_version": "miniwob-breadth-progress.v1",
        "campaign_id": manifest.campaign_id,
        "run_id": campaign.get("run_id"),
        "git_sha": campaign.get("git_sha"),
        "manifest_digest": breadth_manifest_digest(manifest),
        "planned_cases": len(manifest.cases),
        "completed_cases": len(records),
        "current_case_id": manifest.cases[-1].case_id,
        "complete": True,
        "success_count": successful,
        "failure_category_counts": expected_summary["outcome_counts"],
        "provider_attempts": expected_summary["total_provider_attempts"],
        "total_tokens": expected_summary["total_tokens"],
        "model_latency_ms": expected_summary["total_model_latency_ms"],
        "last_completed_case_digest": case_progress_digest(records[-1].result),
    }
    if set(progress) != set(expected_progress) or any(
        progress.get(name) != value for name, value in expected_progress.items()
    ):
        errors.append("campaign progress is not a complete aggregate projection")


def _validate_formal_case_gates(result, errors) -> None:
    if classify_case(result).outcome is MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE:
        errors.append(f"{result.case_id}: formal outcome is unclassified")
    if result.harness_integrity_failures or result.failure_facts.harness_integrity_code:
        errors.append(f"{result.case_id}: harness integrity failed")
    if result.cleanup_failures or result.failure_facts.cleanup_code:
        errors.append(f"{result.case_id}: cleanup failed")
    for metric in (
        "provider_retry_count",
        "fallback_count",
        "forbidden_effect_attempts",
        "duplicate_unknown_attempts",
        "stale_zero_call_violations",
        "observation_contract_exceptions",
    ):
        measurement = result.measurements.get(metric)
        if (
            measurement is None
            or not measurement.measured
            or type(measurement.value) is not int
            or measurement.value != 0
        ):
            errors.append(f"{result.case_id}: formal gate {metric} is unavailable or nonzero")


def _required_metrics_are_measured(result) -> bool:
    if set(result.measurements) != set(REQUIRED_METRICS):
        return False
    for name in REQUIRED_METRICS:
        measurement = result.measurements.get(name)
        if measurement is None or not measurement.measured:
            return False
        if name == "model_latency_ms":
            if isinstance(measurement.value, bool) or not isinstance(
                measurement.value, int | float
            ):
                return False
        elif type(measurement.value) is not int:
            return False
    return True


def _object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
