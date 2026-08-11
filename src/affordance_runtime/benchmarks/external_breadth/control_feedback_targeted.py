"""Frozen M4.6-D 25-case control-feedback diagnostic; not a campaign platform."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import replace
from pathlib import Path
from typing import cast

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
from affordance_runtime.benchmarks.external_smoke.pacing import FixedPacingState, validate_pacing_budget
from affordance_runtime.benchmarks.target_loop.case_projection import (
    decode_public_case_evidence,
    public_case_evidence,
)
from affordance_runtime.benchmarks.target_loop.contracts import CASE_SCHEMA_VERSION
from affordance_runtime.benchmarks.target_loop.instrumentation import BenchmarkInstrumentation
from affordance_runtime.benchmarks.target_loop.manifest import manifest_digest as target_manifest_digest
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.model_policy import ModelBackedAgentPolicy

TARGETED_CAMPAIGN_ID = "miniwob-control-feedback-25-targeted-seed7-v1"
TARGETED_PROFILE = "MINIWOB_CONTROL_FEEDBACK_25_TARGETED"
SELECTION_NAMESPACE = "m4.6-d-control-feedback-targeted.v1"
CASE_SCHEMA = "miniwob-control-feedback-targeted-case.v1"
CAMPAIGN_SCHEMA = "miniwob-control-feedback-targeted-campaign.v1"
SUMMARY_SCHEMA = "miniwob-control-feedback-targeted-summary.v1"
ATTESTATION_SCHEMA = "miniwob-control-feedback-targeted-attestation.v1"
TARGETED_CASE_IDS = tuple(
    f"miniwob-60-{number}"
    for number in (
        "02", "06", "07", "09", "12", "13", "14", "16", "17", "20",
        "26", "28", "33", "34", "37", "38", "39", "43", "44", "48",
        "49", "52", "53", "56", "60",
    )
)
_RUN_ID = re.compile(r"miniwob-control-feedback-25:[0-9a-f]{32}")
_SHA = re.compile(r"[0-9a-f]{40}")
_SAFETY_METRICS = (
    "provider_retry_count",
    "fallback_count",
    "cleanup_failures",
    "forbidden_effect_attempts",
    "duplicate_unknown_attempts",
    "stale_zero_call_violations",
    "repair_feedback_zero_call_violation_count",
)
_FEEDBACK_METRICS = (
    "feedback_repairable_rejection_count",
    "feedback_no_information_gain_count",
    "feedback_strategy_transition_required_count",
    "feedback_action_admission_source_count",
    "feedback_action_page_source_count",
    "feedback_policy_observation_source_count",
    "feedback_action_evaluation_source_count",
    "feedback_progress_event_source_count",
    "feedback_context_delivery_count",
    "control_issue_budget_consumption_count",
    "control_repetition_termination_count",
    "first_opportunity_policy_decision_count",
    "first_opportunity_admission_corrected_count",
    "second_opportunity_policy_decision_count",
    "second_opportunity_admission_corrected_count",
    "strategy_transition_feedback_count",
    "first_policy_repair_feedback_count",
    "feedback_invalid_action_parameters_code_count",
    "feedback_action_outside_action_space_code_count",
    "feedback_action_outside_current_page_code_count",
    "feedback_destination_outside_current_page_code_count",
    "feedback_action_page_no_information_gain_code_count",
    "feedback_observation_no_information_gain_code_count",
)


def targeted_manifest(full_manifest: MiniWobBreadthManifest) -> MiniWobBreadthManifest:
    if len(full_manifest.cases) != 60:
        raise ValueError("control-feedback selector requires the frozen 60-case source manifest")
    by_id = {item.case_id: item for item in full_manifest.cases}
    if any(case_id not in by_id for case_id in TARGETED_CASE_IDS):
        raise ValueError("control-feedback selector is absent from the frozen source manifest")
    return replace(
        full_manifest,
        campaign_id=TARGETED_CAMPAIGN_ID,
        selection_namespace=SELECTION_NAMESPACE,
        cases=tuple(by_id[case_id] for case_id in TARGETED_CASE_IDS),
    )


async def run_control_feedback_targeted_diagnostic(
    manifest: MiniWobBreadthManifest,
    policy: ModelBackedAgentPolicy,
    output_dir: Path,
    *,
    implementation_sha: str,
    provider_capacity: ProviderCapacityEvidence,
) -> MiniWobBreadthCampaignOutcome:
    _require_identity(manifest, implementation_sha, output_dir)
    for case in manifest.cases:
        validate_pacing_budget(
            case.max_turns, manifest.minimum_policy_call_interval_s, case.timeout_s, 5.0,
        )
    configured_identity = _validate_formal_policy(policy, manifest)
    output_dir.mkdir(parents=True, exist_ok=False)
    digest = breadth_manifest_digest(manifest)
    run_id = f"miniwob-control-feedback-25:{uuid.uuid4().hex}"
    progress = CampaignProgressWriter(
        output_dir / "campaign-progress.json",
        manifest.campaign_id,
        run_id,
        implementation_sha,
        digest,
        len(manifest.cases),
    )
    progress.write()
    instrumentations: list[BenchmarkInstrumentation] = []
    target = _target_manifest(manifest, policy, FixedPacingState(), instrumentations)
    if expected_target_manifest_digest(manifest) != target_manifest_digest(target):
        raise ValueError("control-feedback target-loop manifest identity is not canonical")
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
        implementation_sha,
    )
    successful = sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in records)
    acceptance = MiniWobBreadthCampaignAcceptance(
        not errors, tuple(errors), len(TARGETED_CASE_IDS), len(records), successful,
    )
    progress.completed_cases = len(records)
    progress.success_count = successful
    progress.failure_category_counts = _outcome_counts(records)
    progress.provider_attempts = sum(_integer(item.result, "provider_attempts") for item in records)
    progress.total_tokens = sum(_integer(item.result, "total_tokens") for item in records)
    progress.model_latency_ms = sum(_number(item.result, "model_latency_ms") for item in records)
    progress.write(current_case_id=records[-1].case_id, complete=True)
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
    feedback_metric_totals = {name: 0 for name in _FEEDBACK_METRICS}
    for record in outcome.cases:
        metrics = {name: _metric(record.result, name) for name in _FEEDBACK_METRICS}
        for name, value in metrics.items():
            feedback_metric_totals[name] += int(value)
        payload = {
            "schema_version": CASE_SCHEMA,
            "run_id": outcome.run_id,
            "implementation_sha": outcome.suite.identity.git_sha,
            "case_id": record.case_id,
            "task_family_label": record.task_family_label,
            "seed": 7,
            "typed_outcome": record.outcome.value,
            "classification_source": record.classification_source,
            "feedback_metrics": metrics,
            "policy_calls": _metric(record.result, "policy_calls"),
            "provider_attempts": _metric(record.result, "provider_attempts"),
            "prompt_tokens": _metric(record.result, "prompt_tokens"),
            "completion_tokens": _metric(record.result, "completion_tokens"),
            "total_tokens": _metric(record.result, "total_tokens"),
            "model_latency_ms": _metric(record.result, "model_latency_ms"),
            "executions": _metric(record.result, "executions"),
            "browsergym_reset_calls": _metric(record.result, "browsergym_reset_calls"),
            "browsergym_step_calls": _metric(record.result, "browsergym_step_calls"),
            "browsergym_probe_calls": _metric(record.result, "browsergym_probe_calls"),
            "independent_capture_calls": _metric(record.result, "independent_capture_calls"),
            "latest_task_status": record.result.latest_task_status,
            "latest_action_evaluation_status": record.result.latest_action_evaluation_status,
            "harness_integrity_failures": record.result.harness_integrity_failures,
            "cleanup_failures": record.result.cleanup_failures,
            "benchmark_case_evidence": public_case_evidence(record.result),
        }
        path = cases_dir / f"{record.case_id}.json"
        _atomic_json(path, payload)
        hashes[record.case_id] = _sha256(path)
        summaries.append({
            "case_id": record.case_id,
            "typed_outcome": record.outcome.value,
            "classification_source": record.classification_source,
            "feedback_metrics": metrics,
        })
    summary_path = output_dir / "summary.json"
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "profile": TARGETED_PROFILE,
        "run_id": outcome.run_id,
        "planned_cases": len(TARGETED_CASE_IDS),
        "completed_cases": len(outcome.cases),
        "outcome_counts": _outcome_counts(outcome.cases),
        "feedback_metric_totals": feedback_metric_totals,
        "correction_definition": (
            "the next ordinary accepted policy decision after feedback does not produce "
            "the same canonical issue and passes the current public owner validation"
        ),
        "generalization_claim": "NOT_CLAIMED",
        "performance_claim": "NOT_CLAIMED",
    }
    _atomic_json(summary_path, summary)
    campaign_path = output_dir / "campaign.json"
    _atomic_json(campaign_path, {
        "schema_version": CAMPAIGN_SCHEMA,
        "profile": TARGETED_PROFILE,
        "selection_namespace": SELECTION_NAMESPACE,
        "run_id": outcome.run_id,
        "campaign_id": outcome.manifest.campaign_id,
        "implementation_sha": outcome.suite.identity.git_sha,
        "git_dirty": outcome.suite.identity.git_dirty,
        "provider_id": outcome.provider_id,
        "model_id": outcome.model_id,
        "grounding_profile": outcome.grounding_profile,
        "minimum_policy_call_interval_s": outcome.manifest.minimum_policy_call_interval_s,
        "seed": 7,
        "manifest_digest": outcome.manifest_digest,
        "target_manifest_digest": outcome.suite.identity.manifest_digest,
        "case_schema_version": outcome.cases[0].result.case_schema_version,
        "complete": len(outcome.cases) == len(TARGETED_CASE_IDS),
        "evidence_valid": outcome.acceptance.evidence_valid,
        "errors": outcome.acceptance.errors,
        "cases": summaries,
    })
    progress_path = output_dir / "campaign-progress.json"
    attestation_path = output_dir / "attestation.json"
    _atomic_json(attestation_path, {
        "schema_version": ATTESTATION_SCHEMA,
        "profile": TARGETED_PROFILE,
        "selection_namespace": SELECTION_NAMESPACE,
        "run_id": outcome.run_id,
        "implementation_sha": outcome.suite.identity.git_sha,
        "git_dirty": outcome.suite.identity.git_dirty,
        "provider_id": outcome.provider_id,
        "model_id": outcome.model_id,
        "grounding_profile": outcome.grounding_profile,
        "seed": 7,
        "manifest_digest": outcome.manifest_digest,
        "target_manifest_digest": outcome.suite.identity.manifest_digest,
        "planned_cases": len(TARGETED_CASE_IDS),
        "completed_cases": len(outcome.cases),
        "case_ids": TARGETED_CASE_IDS,
        "case_report_sha256": hashes,
        "summary_sha256": _sha256(summary_path),
        "campaign_sha256": _sha256(campaign_path),
        "progress_sha256": _sha256(progress_path),
        "provider_capacity": {
            "required_attempt_budget": outcome.provider_capacity.required_attempt_budget,
            "declared_attempt_budget": outcome.provider_capacity.declared_attempt_budget,
            "sufficient": outcome.provider_capacity.sufficient,
            "provider_retry_count": outcome.provider_capacity.retry_count,
            "fallback_count": outcome.provider_capacity.fallback_count,
        } if outcome.provider_capacity is not None else None,
        "privacy_errors": privacy_scan(output_dir),
        "evidence_valid": outcome.acceptance.evidence_valid and not privacy_scan(output_dir),
        "generalization_claim": "NOT_CLAIMED",
        "performance_claim": "NOT_CLAIMED",
    })
    return attestation_path


def validate_targeted_evidence(output_dir: Path) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        attestation = _read(output_dir / "attestation.json")
        campaign = _read(output_dir / "campaign.json")
        summary = _read(output_dir / "summary.json")
        progress = _read(output_dir / "campaign-progress.json")
    except (OSError, UnicodeError, ValueError):
        return ("control-feedback evidence roots are malformed",)
    run_id = attestation.get("run_id")
    implementation_sha = attestation.get("implementation_sha")
    if (
        attestation.get("schema_version") != ATTESTATION_SCHEMA
        or attestation.get("profile") != TARGETED_PROFILE
        or attestation.get("selection_namespace") != SELECTION_NAMESPACE
        or attestation.get("case_ids") != list(TARGETED_CASE_IDS)
        or attestation.get("planned_cases") != len(TARGETED_CASE_IDS)
        or attestation.get("completed_cases") != len(TARGETED_CASE_IDS)
        or attestation.get("git_dirty") is not False
        or attestation.get("evidence_valid") is not True
        or not isinstance(run_id, str)
        or _RUN_ID.fullmatch(run_id) is None
        or not isinstance(implementation_sha, str)
        or _SHA.fullmatch(implementation_sha) is None
    ):
        errors.append("control-feedback attestation identity or acceptance is invalid")
    roots = (campaign, summary, progress)
    if any(root.get("run_id") != run_id for root in roots):
        errors.append("control-feedback run identity is inconsistent")
    if (
        campaign.get("implementation_sha") != implementation_sha
        or progress.get("git_sha") != implementation_sha
        or campaign.get("manifest_digest") != attestation.get("manifest_digest")
        or progress.get("manifest_digest") != attestation.get("manifest_digest")
        or campaign.get("target_manifest_digest") != attestation.get("target_manifest_digest")
        or campaign.get("provider_id") != "mistral"
        or campaign.get("model_id") != "mistral-medium-3-5"
        or campaign.get("grounding_profile") != "format-only.v1"
        or campaign.get("seed") != 7
        or campaign.get("complete") is not True
        or campaign.get("evidence_valid") is not True
        or progress.get("planned_cases") != len(TARGETED_CASE_IDS)
        or progress.get("completed_cases") != len(TARGETED_CASE_IDS)
        or progress.get("complete") is not True
    ):
        errors.append("control-feedback evidence identity is inconsistent")
    hashes = attestation.get("case_report_sha256")
    if not isinstance(hashes, dict) or tuple(hashes) != TARGETED_CASE_IDS:
        return (*errors, "control-feedback case hash set/order is invalid")
    expected_files = {
        "attestation.json", "campaign.json", "summary.json", "campaign-progress.json",
        *(f"cases/{case_id}.json" for case_id in TARGETED_CASE_IDS),
    }
    actual_files = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*") if path.is_file()
    }
    if actual_files != expected_files:
        errors.append("control-feedback recursive file set is invalid")
    metric_totals = {name: 0 for name in _FEEDBACK_METRICS}
    for case_id, digest in hashes.items():
        path = output_dir / "cases" / f"{case_id}.json"
        if not path.is_file() or _sha256(path) != digest:
            errors.append(f"{case_id}: control-feedback case digest mismatch")
            continue
        try:
            payload = _read(path)
            result = decode_public_case_evidence(cast(
                dict[str, object], payload["benchmark_case_evidence"],
            ))
        except (KeyError, OSError, TypeError, ValueError):
            errors.append(f"{case_id}: control-feedback case payload is malformed")
            continue
        classified = classify_case(result)
        if (
            payload.get("schema_version") != CASE_SCHEMA
            or payload.get("run_id") != run_id
            or payload.get("implementation_sha") != implementation_sha
            or payload.get("case_id") != case_id
            or payload.get("seed") != 7
            or payload.get("typed_outcome") != classified.outcome.value
            or payload.get("classification_source") != classified.source
        ):
            errors.append(f"{case_id}: control-feedback typed facts are inconsistent")
        if classified.outcome in {
            MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE,
            MiniWobTaskOutcome.OTHER_TYPED_FAILURE,
        }:
            errors.append(f"{case_id}: control-feedback outcome is unclassified")
        metrics = payload.get("feedback_metrics")
        if not isinstance(metrics, dict) or set(metrics) != set(_FEEDBACK_METRICS):
            errors.append(f"{case_id}: control-feedback metric set/order is invalid")
            continue
        for name in _FEEDBACK_METRICS:
            value = _metric(result, name)
            if metrics.get(name) != value or type(value) is not int or value < 0:
                errors.append(f"{case_id}: control-feedback metric {name} is inconsistent")
            metric_totals[name] += int(value)
        for name in _SAFETY_METRICS:
            if _metric(result, name) != 0:
                errors.append(f"{case_id}: safety metric {name} is nonzero")
        if result.harness_integrity_failures or result.cleanup_failures:
            errors.append(f"{case_id}: integrity or cleanup gate failed")
        if case_id == "miniwob-60-37" and (
            _metric(result, "first_policy_repair_feedback_count") != 1
            or _metric(result, "feedback_context_delivery_count") < 1
            or _metric(result, "repair_feedback_zero_call_violation_count") != 0
        ):
            errors.append("miniwob-60-37: direct repair witness is absent")
    if summary.get("feedback_metric_totals") != metric_totals:
        errors.append("control-feedback summary metric aggregate is inconsistent")
    for name, path in (
        ("summary_sha256", output_dir / "summary.json"),
        ("campaign_sha256", output_dir / "campaign.json"),
        ("progress_sha256", output_dir / "campaign-progress.json"),
    ):
        if attestation.get(name) != _sha256(path):
            errors.append(f"control-feedback {name} is inconsistent")
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
    implementation_sha,
) -> list[str]:
    errors: list[str] = []
    if tuple(item.case_id for item in records) != TARGETED_CASE_IDS:
        errors.append("control-feedback result set does not match the frozen selector")
    identity = suite.identity
    if (
        identity.suite_id != manifest.campaign_id
        or identity.profile_id != "mistral-format-only-v1"
        or identity.seed != 7
        or identity.manifest_digest != expected_target_manifest_digest(manifest)
        or identity.harness_schema_version != "target-loop-harness.v6"
        or identity.git_sha != implementation_sha
        or identity.git_dirty
        or final_dirty
        or final_sha != implementation_sha
    ):
        errors.append("control-feedback suite/implementation identity is invalid")
    if (provider, model, grounding) != (
        "mistral", "mistral-medium-3-5", "format-only.v1",
    ):
        errors.append("control-feedback provider/model/grounding identity is invalid")
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
        errors.append("control-feedback provider capacity is absent or insufficient")
    for record in records:
        if (
            record.result.case_schema_version != CASE_SCHEMA_VERSION
            or any(
                name not in record.result.measurements
                or not record.result.measurements[name].measured
                for name in (*REQUIRED_METRICS, *_FEEDBACK_METRICS)
            )
        ):
            errors.append(f"{record.case_id}: control-feedback metrics/schema are incomplete")
        if record.outcome in {
            MiniWobTaskOutcome.UNCLASSIFIED_TYPED_FAILURE,
            MiniWobTaskOutcome.OTHER_TYPED_FAILURE,
        }:
            errors.append(f"{record.case_id}: control-feedback outcome is unclassified")
        if record.result.harness_integrity_failures or record.result.cleanup_failures:
            errors.append(f"{record.case_id}: control-feedback integrity or cleanup failed")
        for name in _SAFETY_METRICS:
            if _metric(record.result, name) != 0:
                errors.append(f"{record.case_id}: safety metric {name} is nonzero")
    case37 = next((item.result for item in records if item.case_id == "miniwob-60-37"), None)
    if case37 is None or (
        _metric(case37, "first_policy_repair_feedback_count") != 1
        or _metric(case37, "feedback_context_delivery_count") < 1
    ):
        errors.append("miniwob-60-37: required direct repair witness is absent")
    return errors


def _require_identity(
    manifest: MiniWobBreadthManifest,
    implementation_sha: str,
    output_dir: Path,
) -> None:
    if (
        manifest.campaign_id != TARGETED_CAMPAIGN_ID
        or manifest.selection_namespace != SELECTION_NAMESPACE
        or tuple(item.case_id for item in manifest.cases) != TARGETED_CASE_IDS
        or any(item.seed != 7 for item in manifest.cases)
    ):
        raise ValueError("control-feedback manifest is not the frozen 25-case selector")
    if _SHA.fullmatch(implementation_sha) is None or _git_sha() != implementation_sha:
        raise ValueError("control-feedback diagnostic requires the exact implementation SHA")
    final_sha, dirty = _final_git_identity()
    if dirty or final_sha != implementation_sha:
        raise RuntimeError("control-feedback diagnostic requires a clean implementation tree")
    if output_dir.exists():
        raise FileExistsError("control-feedback diagnostic output directory must be new")


def _metric(result, name: str) -> int | float:
    item = result.measurements.get(name)
    if item is None or not item.measured or isinstance(item.value, bool):
        return 0
    return item.value if isinstance(item.value, int | float) else 0


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("evidence root must be an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
