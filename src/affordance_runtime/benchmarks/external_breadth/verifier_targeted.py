"""Frozen previous-verifier-unknown 14-case diagnostic; not a campaign platform."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCampaignAcceptance,
    MiniWobBreadthCampaignOutcome,
    MiniWobTaskOutcome,
    ProviderCapacityEvidence,
)
from affordance_runtime.benchmarks.external_breadth.classification import classify_case
from affordance_runtime.benchmarks.external_breadth.contracts import MiniWobBreadthManifest
from affordance_runtime.benchmarks.external_breadth.manifest import breadth_manifest_digest
from affordance_runtime.benchmarks.external_breadth.progress import CampaignProgressWriter
from affordance_runtime.benchmarks.external_breadth.reporting import privacy_scan
from affordance_runtime.benchmarks.external_breadth.runner import (
    REQUIRED_METRICS,
    _derived_metrics,
    _final_git_identity,
    _git_sha,
    _integer,
    _model_identity,
    _number,
    _outcome_counts,
    _progress_callback,
    _record,
    _target_manifest,
    _validate_formal_policy,
    expected_target_manifest_digest,
)
from affordance_runtime.benchmarks.external_smoke.adapter_reporting import _atomic_json
from affordance_runtime.benchmarks.external_smoke.pacing import (
    FixedPacingState,
    validate_pacing_budget,
)
from affordance_runtime.benchmarks.target_loop.case_projection import (
    decode_public_case_evidence,
    public_case_evidence,
)
from affordance_runtime.benchmarks.target_loop.contracts import CASE_SCHEMA_VERSION
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.manifest import (
    manifest_digest as target_manifest_digest,
)
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.evaluation import TaskOutcomeKind
from affordance_runtime.model.policy import ModelBackedAgentPolicy

TARGETED_CAMPAIGN_ID = "miniwob-verifier-14-targeted-seed7-v1"
TARGETED_PROFILE = "MINIWOB_VERIFIER_14_TARGETED_DIAGNOSTIC"
PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS = (
    "miniwob-60-01",
    "miniwob-60-03",
    "miniwob-60-08",
    "miniwob-60-10",
    "miniwob-60-11",
    "miniwob-60-21",
    "miniwob-60-22",
    "miniwob-60-32",
    "miniwob-60-35",
    "miniwob-60-41",
    "miniwob-60-42",
    "miniwob-60-46",
    "miniwob-60-54",
    "miniwob-60-59",
)
_SAFETY_METRICS = (
    "provider_retry_count",
    "fallback_count",
    "cleanup_failures",
    "forbidden_effect_attempts",
    "duplicate_unknown_attempts",
    "stale_zero_call_violations",
)


def targeted_manifest(full_manifest: MiniWobBreadthManifest) -> MiniWobBreadthManifest:
    if len(full_manifest.cases) != 60:
        raise ValueError("targeted selector requires the frozen 60-case source manifest")
    by_id = {item.case_id: item for item in full_manifest.cases}
    if any(case_id not in by_id for case_id in PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS):
        raise ValueError("targeted selector is not present in the frozen source manifest")
    return replace(
        full_manifest,
        campaign_id=TARGETED_CAMPAIGN_ID,
        selection_namespace="previous-verifier-unknown.v1",
        cases=tuple(by_id[case_id] for case_id in PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS),
    )


async def run_verifier_targeted_diagnostic(
    manifest: MiniWobBreadthManifest,
    policy: ModelBackedAgentPolicy,
    output_dir: Path,
    *,
    provider_capacity: ProviderCapacityEvidence,
) -> MiniWobBreadthCampaignOutcome:
    if (
        manifest.campaign_id != TARGETED_CAMPAIGN_ID
        or tuple(item.case_id for item in manifest.cases)
        != PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS
        or any(item.seed != 7 for item in manifest.cases)
    ):
        raise ValueError("targeted diagnostic manifest is not the frozen 14-case selector")
    for case in manifest.cases:
        validate_pacing_budget(
            case.max_turns,
            manifest.minimum_policy_call_interval_s,
            case.timeout_s,
            5.0,
        )
    configured_identity = _validate_formal_policy(policy, manifest)
    output_dir.mkdir(parents=True, exist_ok=False)
    digest = breadth_manifest_digest(manifest)
    run_id = f"miniwob-verifier-14:{uuid.uuid4().hex}"
    progress = CampaignProgressWriter(
        output_dir / "campaign-progress.json",
        manifest.campaign_id,
        run_id,
        _git_sha(),
        digest,
        len(manifest.cases),
    )
    progress.write()
    instrumentations: list[BenchmarkInstrumentation] = []
    target = _target_manifest(
        manifest, policy, FixedPacingState(), instrumentations,
    )
    if expected_target_manifest_digest(manifest) != target_manifest_digest(target):
        raise ValueError("targeted target-loop manifest identity is not canonical")
    suite = await run_suite(target, _progress_callback(progress))
    suite = replace(suite, cases=tuple(_derived_metrics(item) for item in suite.cases))
    records = tuple(
        _record(case, result)
        for case, result in zip(manifest.cases, suite.cases, strict=True)
    )
    provider, model, grounding = _model_identity(instrumentations, configured_identity)
    final_sha, final_dirty = _final_git_identity()
    errors = _acceptance_errors(
        manifest,
        suite,
        records,
        provider,
        model,
        grounding,
        provider_capacity,
        final_sha,
        final_dirty,
    )
    successful = sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in records)
    acceptance = MiniWobBreadthCampaignAcceptance(
        not errors, tuple(errors), 14, len(records), successful,
    )
    progress.completed_cases = len(records)
    progress.success_count = successful
    progress.failure_category_counts = _outcome_counts(records)
    progress.provider_attempts = sum(_integer(item.result, "provider_attempts") for item in records)
    progress.total_tokens = sum(_integer(item.result, "total_tokens") for item in records)
    progress.model_latency_ms = sum(_number(item.result, "model_latency_ms") for item in records)
    progress.write(
        current_case_id=records[-1].case_id,
        complete=True,
    )
    return MiniWobBreadthCampaignOutcome(
        run_id,
        manifest,
        digest,
        suite,
        records,
        acceptance,
        provider,
        model,
        grounding,
        provider_capacity,
    )


def write_targeted_evidence(
    outcome: MiniWobBreadthCampaignOutcome,
    output_dir: Path,
) -> Path:
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(exist_ok=True)
    hashes: dict[str, str] = {}
    summaries: list[dict[str, object]] = []
    for record in outcome.cases:
        facts = record.result.failure_facts
        verifier_status = _verifier_status(facts.task_outcome_kind)
        payload = {
            "schema_version": "miniwob-verifier-targeted-case.v1",
            "run_id": outcome.run_id,
            "implementation_sha": outcome.suite.identity.git_sha,
            "case_id": record.case_id,
            "task_family_label": record.task_family_label,
            "verifier_status": verifier_status,
            "verifier_reason": facts.task_outcome_code,
            "task_outcome_kind": facts.task_outcome_kind,
            "task_outcome_code": facts.task_outcome_code,
            "typed_outcome": record.outcome.value,
            "classification_source": record.classification_source,
            "benchmark_case_evidence": public_case_evidence(record.result),
        }
        path = cases_dir / f"{record.case_id}.json"
        _atomic_json(path, payload)
        hashes[record.case_id] = _sha256(path)
        summaries.append({
            "case_id": record.case_id,
            "verifier_status": verifier_status,
            "verifier_reason": facts.task_outcome_code,
            "task_outcome_kind": facts.task_outcome_kind,
            "typed_outcome": record.outcome.value,
        })
    summary_path = output_dir / "summary.json"
    _atomic_json(summary_path, {
        "schema_version": "miniwob-verifier-targeted-summary.v1",
        "profile": TARGETED_PROFILE,
        "run_id": outcome.run_id,
        "planned_cases": 14,
        "completed_cases": len(outcome.cases),
        "outcome_counts": _outcome_counts(outcome.cases),
        "verifier_status_counts": _counts(item["verifier_status"] for item in summaries),
        "task_outcome_counts": _counts(item["task_outcome_kind"] for item in summaries),
        "generalization_claim": "NOT_CLAIMED",
        "performance_claim": "NOT_CLAIMED",
    })
    campaign_path = output_dir / "campaign.json"
    _atomic_json(campaign_path, {
        "schema_version": "miniwob-verifier-targeted-campaign.v1",
        "profile": TARGETED_PROFILE,
        "run_id": outcome.run_id,
        "campaign_id": outcome.manifest.campaign_id,
        "implementation_sha": outcome.suite.identity.git_sha,
        "git_dirty": outcome.suite.identity.git_dirty,
        "provider_id": outcome.provider_id,
        "model_id": outcome.model_id,
        "grounding_profile": outcome.grounding_profile,
        "manifest_digest": outcome.manifest_digest,
        "target_manifest_digest": outcome.suite.identity.manifest_digest,
        "case_schema_version": outcome.cases[0].result.case_schema_version,
        "complete": len(outcome.cases) == 14,
        "evidence_valid": outcome.acceptance.evidence_valid,
        "errors": outcome.acceptance.errors,
        "cases": summaries,
    })
    privacy_errors = privacy_scan(output_dir)
    progress_path = output_dir / "campaign-progress.json"
    attestation_path = output_dir / "attestation.json"
    _atomic_json(attestation_path, {
        "schema_version": "miniwob-verifier-targeted-attestation.v1",
        "profile": TARGETED_PROFILE,
        "run_id": outcome.run_id,
        "implementation_sha": outcome.suite.identity.git_sha,
        "git_dirty": outcome.suite.identity.git_dirty,
        "provider_id": outcome.provider_id,
        "model_id": outcome.model_id,
        "grounding_profile": outcome.grounding_profile,
        "manifest_digest": outcome.manifest_digest,
        "target_manifest_digest": outcome.suite.identity.manifest_digest,
        "case_schema_version": outcome.cases[0].result.case_schema_version,
        "planned_cases": 14,
        "completed_cases": len(outcome.cases),
        "case_ids": PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS,
        "case_report_sha256": hashes,
        "summary_sha256": _sha256(summary_path),
        "campaign_sha256": _sha256(campaign_path),
        "progress_sha256": _sha256(progress_path),
        "provider_capacity": {
            "required_attempt_budget": outcome.provider_capacity.required_attempt_budget,
            "declared_attempt_budget": outcome.provider_capacity.declared_attempt_budget,
            "sufficient": outcome.provider_capacity.sufficient,
        } if outcome.provider_capacity is not None else None,
        "privacy_errors": privacy_errors,
        "evidence_valid": outcome.acceptance.evidence_valid and not privacy_errors,
        "generalization_claim": "NOT_CLAIMED",
        "performance_claim": "NOT_CLAIMED",
    })
    return attestation_path


def validate_targeted_evidence(output_dir: Path) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        attestation = json.loads((output_dir / "attestation.json").read_text())
        campaign = json.loads((output_dir / "campaign.json").read_text())
        summary = json.loads((output_dir / "summary.json").read_text())
        progress = json.loads((output_dir / "campaign-progress.json").read_text())
    except (OSError, UnicodeError, ValueError):
        return ("targeted evidence roots are malformed",)
    if (
        attestation.get("profile") != TARGETED_PROFILE
        or attestation.get("case_ids") != list(PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS)
        or attestation.get("planned_cases") != 14
        or attestation.get("completed_cases") != 14
        or attestation.get("git_dirty") is not False
        or attestation.get("evidence_valid") is not True
    ):
        errors.append("targeted attestation identity or acceptance is invalid")
    if campaign.get("run_id") != attestation.get("run_id") or summary.get("run_id") != attestation.get("run_id"):
        errors.append("targeted run identity is inconsistent")
    if (
        progress.get("run_id") != attestation.get("run_id")
        or progress.get("git_sha") != attestation.get("implementation_sha")
        or progress.get("manifest_digest") != attestation.get("manifest_digest")
        or progress.get("planned_cases") != 14
        or progress.get("completed_cases") != 14
        or progress.get("complete") is not True
        or campaign.get("implementation_sha") != attestation.get("implementation_sha")
        or campaign.get("manifest_digest") != attestation.get("manifest_digest")
        or campaign.get("target_manifest_digest") != attestation.get("target_manifest_digest")
        or summary.get("planned_cases") != 14
        or summary.get("completed_cases") != 14
    ):
        errors.append("targeted progress or evidence identity is inconsistent")
    hashes = attestation.get("case_report_sha256")
    if not isinstance(hashes, dict) or tuple(hashes) != PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS:
        errors.append("targeted case hash set/order is invalid")
        return tuple(errors)
    expected_files = {
        "attestation.json", "campaign.json", "summary.json", "campaign-progress.json",
        *(f"cases/{case_id}.json" for case_id in PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS),
    }
    actual_files = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*") if path.is_file()
    }
    if actual_files != expected_files:
        errors.append("targeted recursive file set is invalid")
    for case_id, digest in hashes.items():
        path = output_dir / "cases" / f"{case_id}.json"
        if not path.is_file() or _sha256(path) != digest:
            errors.append(f"{case_id}: targeted case digest mismatch")
            continue
        try:
            payload = json.loads(path.read_text())
            result = decode_public_case_evidence(payload["benchmark_case_evidence"])
        except (KeyError, OSError, TypeError, ValueError):
            errors.append(f"{case_id}: targeted case payload is malformed")
            continue
        classified = classify_case(result)
        if (
            payload.get("run_id") != attestation.get("run_id")
            or payload.get("implementation_sha") != attestation.get("implementation_sha")
            or payload.get("typed_outcome") != classified.outcome.value
            or payload.get("classification_source") != classified.source
            or payload.get("task_outcome_kind") != result.failure_facts.task_outcome_kind
            or payload.get("task_outcome_code") != result.failure_facts.task_outcome_code
            or payload.get("verifier_reason") != result.failure_facts.task_outcome_code
            or payload.get("verifier_status") != _verifier_status(
                result.failure_facts.task_outcome_kind
            )
        ):
            errors.append(f"{case_id}: targeted typed facts are inconsistent")
        if classified.outcome in {
            MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE,
            MiniWobTaskOutcome.OTHER_TYPED_FAILURE,
        }:
            errors.append(f"{case_id}: targeted outcome is unclassified")
        if result.harness_integrity_failures or result.cleanup_failures:
            errors.append(f"{case_id}: targeted integrity or cleanup gate failed")
        for name in _SAFETY_METRICS:
            metric = result.measurements.get(name)
            if metric is None or not metric.measured or metric.value != 0:
                errors.append(f"{case_id}: targeted safety metric {name} is nonzero")
    for name, path in (
        ("summary_sha256", output_dir / "summary.json"),
        ("campaign_sha256", output_dir / "campaign.json"),
        ("progress_sha256", output_dir / "campaign-progress.json"),
    ):
        if attestation.get(name) != _sha256(path):
            errors.append(f"targeted {name} is inconsistent")
    errors.extend(privacy_scan(output_dir))
    return tuple(errors)


def _acceptance_errors(
    manifest,
    suite,
    records,
    provider,
    model,
    grounding,
    capacity,
    final_sha,
    final_dirty,
) -> list[str]:
    errors: list[str] = []
    if len(records) != 14 or tuple(item.case_id for item in records) != PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS:
        errors.append("targeted result set does not match the frozen selector")
    if tuple(item.result.case_id for item in records) != PREVIOUS_VERIFIER_UNKNOWN_CASE_IDS:
        errors.append("targeted underlying case identities do not match the frozen selector")
    identity = suite.identity
    if (
        identity.suite_id != manifest.campaign_id
        or identity.profile_id != "mistral-format-only-v1"
        or identity.seed != 7
        or identity.manifest_digest != expected_target_manifest_digest(manifest)
        or identity.harness_schema_version != "target-loop-harness.v6"
    ):
        errors.append("targeted suite identity/schema/digest is invalid")
    if suite.identity.git_dirty or final_dirty or final_sha != suite.identity.git_sha:
        errors.append("targeted diagnostic requires one clean stable implementation SHA")
    if (provider, model, grounding) != (
        "mistral", manifest.model_profile, manifest.grounding_profile,
    ):
        errors.append("targeted provider/model/grounding identity is invalid")
    required = sum(item.max_turns for item in manifest.cases)
    if (
        capacity.manifest_digest != breadth_manifest_digest(manifest)
        or capacity.required_attempt_budget != required
        or capacity.provider_id != provider
        or capacity.model_id != model
        or capacity.grounding_profile != grounding
        or capacity.retry_count != 0
        or capacity.fallback_count != 0
        or not capacity.sufficient
    ):
        errors.append("targeted provider capacity is absent or insufficient")
    for record in records:
        if (
            record.result.case_schema_version != CASE_SCHEMA_VERSION
            or record.result.harness_schema_version != "target-loop-harness.v6"
            or record.result.suite_id != manifest.campaign_id
            or record.result.profile_id != "mistral-format-only-v1"
            or record.result.seed != 7
            or record.result.manifest_digest != identity.manifest_digest
        ):
            errors.append(f"{record.case_id}: targeted formal identity is invalid")
        if any(
            name not in record.result.measurements
            or not record.result.measurements[name].measured
            for name in REQUIRED_METRICS
        ):
            errors.append(f"{record.case_id}: targeted metrics are incomplete")
        if record.outcome in {
            MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE,
            MiniWobTaskOutcome.OTHER_TYPED_FAILURE,
        }:
            errors.append(f"{record.case_id}: targeted outcome is unclassified")
        if record.result.harness_integrity_failures or record.result.cleanup_failures:
            errors.append(f"{record.case_id}: targeted integrity or cleanup failed")
        for name in _SAFETY_METRICS:
            measurement = record.result.measurements.get(name)
            if measurement is None or not measurement.measured or measurement.value != 0:
                errors.append(f"{record.case_id}: targeted safety metric {name} is nonzero")
    return errors


def _verifier_status(task_outcome_kind: str) -> str:
    return {
        TaskOutcomeKind.TERMINAL_SUCCESS.value: "success",
        TaskOutcomeKind.RUNNING_INCOMPLETE.value: "incomplete",
        TaskOutcomeKind.TERMINAL_FAILURE.value: "terminal_task_failure",
        TaskOutcomeKind.VERIFIER_UNAVAILABLE.value: "unavailable",
        "": "absent",
    }[task_outcome_kind]


def _counts(values) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
