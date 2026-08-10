"""Privacy-bounded campaign tree, aggregates, and evidence validation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    MiniWobBreadthCampaignOutcome,
    MiniWobBreadthCaseRecord,
    MiniWobTaskOutcome,
)
from affordance_runtime.benchmarks.external_smoke.adapter_reporting import _atomic_json
from affordance_runtime.benchmarks.target_loop.case_projection import public_case_evidence

_FORBIDDEN_FIELDS = frozenset({
    "raw_prompt", "raw_response", "chain_of_thought", "hidden_reasoning", "api_key",
    "authorization", "endpoint_url", "credential", "selector", "xpath", "locator",
    "browsergym_id", "private_bid", "coordinate", "bbox", "private_href", "raw_reward",
    "hidden_benchmark_state", "expected_answer", "reference_action", "reference_trajectory",
    "success_script", "benchmark_oracle",
})
_FORBIDDEN_VALUE_MARKERS = (
    "browsergym/miniwob.", "http://", "https://", "authorization:", "bearer ",
    "api_key=", "selector:", "xpath:", "locator:", "coordinate:", "private_bid:",
    "private_href:",
)


def write_campaign_reports(outcome: MiniWobBreadthCampaignOutcome, output_dir: Path) -> Path:
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    case_hashes: dict[str, str] = {}
    summaries = []
    for record in outcome.cases:
        payload = _case_payload(record)
        path = cases_dir / f"{record.case_id}.json"
        _atomic_json(path, payload)
        case_hashes[record.case_id] = _sha256(path)
        summaries.append(_case_summary(payload))
    summary_path = output_dir / "summary.json"
    _atomic_json(summary_path, _aggregate(outcome))
    campaign_path = output_dir / "campaign.json"
    _atomic_json(campaign_path, {
        "schema_version": "miniwob-breadth-campaign.v1",
        "classification": "MINIWOB_60_SEEDED_BREADTH_PROFILE",
        "run_id": outcome.run_id,
        "campaign_id": outcome.manifest.campaign_id,
        "manifest_digest": outcome.manifest_digest,
        "git_sha": outcome.suite.identity.git_sha,
        "git_dirty": outcome.suite.identity.git_dirty,
        "complete": len(outcome.cases) == 60,
        "acceptance": _acceptance_payload(outcome),
        "cases": summaries,
    })
    privacy_errors = privacy_scan(output_dir)
    attestation = output_dir / "attestation.json"
    evidence_valid = (
        outcome.acceptance.evidence_valid
        and outcome.provider_capacity is not None
        and outcome.provider_capacity.sufficient
        and not privacy_errors
    )
    _atomic_json(attestation, {
        "schema_version": "miniwob-breadth-attestation.v1",
        "classification": "MINIWOB_60_SEEDED_BREADTH_PROFILE",
        "run_id": outcome.run_id,
        "git_sha": outcome.suite.identity.git_sha,
        "git_dirty": outcome.suite.identity.git_dirty,
        "manifest_digest": outcome.manifest_digest,
        "registry_digest": outcome.manifest.registry_digest,
        "capability_inventory_digest": outcome.manifest.capability_inventory_digest,
        "package_name": outcome.manifest.package_name,
        "package_version": outcome.manifest.package_version,
        "source_commit": outcome.manifest.source_commit,
        "model_id": outcome.model_id,
        "provider_id": outcome.provider_id,
        "grounding_profile": outcome.grounding_profile,
        "minimum_policy_call_interval_s": outcome.manifest.minimum_policy_call_interval_s,
        "seed": 7,
        "planned_cases": 60,
        "completed_cases": len(outcome.cases),
        "case_report_sha256": case_hashes,
        "summary_sha256": _sha256(summary_path),
        "campaign_sha256": _sha256(campaign_path),
        "privacy_errors": privacy_errors,
        "evidence_valid": evidence_valid,
        "generalization_claim": "NOT_CLAIMED",
        "provider_capacity": (
            {
                "schema_version": outcome.provider_capacity.schema_version,
                "provider_id": outcome.provider_capacity.provider_id,
                "model_id": outcome.provider_capacity.model_id,
                "manifest_digest": outcome.provider_capacity.manifest_digest,
                "required_attempt_budget": outcome.provider_capacity.required_attempt_budget,
                "declared_attempt_budget": outcome.provider_capacity.declared_attempt_budget,
                "checked": outcome.provider_capacity.checked,
                "sufficient": outcome.provider_capacity.sufficient,
            }
            if outcome.provider_capacity is not None else None
        ),
    })
    return attestation


def privacy_scan(output_dir: Path) -> tuple[str, ...]:
    errors: list[str] = []
    for path in sorted(output_dir.rglob("*.json")):
        relative = str(path.relative_to(output_dir))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"{relative} is not valid readable JSON")
            continue
        errors.extend(_privacy_errors(payload, relative))
    return tuple(errors)


def _privacy_errors(payload: Any, relative: str, location: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = str(key).casefold().replace("-", "_")
            child = f"{location}.{key}"
            if normalized in _FORBIDDEN_FIELDS:
                errors.append(f"{relative} contains forbidden field {normalized} at {child}")
            errors.extend(_privacy_errors(value, relative, child))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            errors.extend(_privacy_errors(value, relative, f"{location}[{index}]"))
    elif isinstance(payload, str):
        folded = payload.casefold()
        for marker in _FORBIDDEN_VALUE_MARKERS:
            if marker in folded:
                errors.append(f"{relative} contains forbidden value {marker} at {location}")
    return errors


def _case_payload(record: MiniWobBreadthCaseRecord) -> dict[str, object]:
    result = record.result
    return {
        "schema_version": "miniwob-breadth-case.v3",
        "case_id": record.case_id,
        "task_family_label": record.task_family_label,
        "capability_profile": record.capability_profile,
        "required_primitives": record.required_primitives,
        "typed_outcome": record.outcome.value,
        "classification_source": record.classification_source,
        "benchmark_case_evidence": public_case_evidence(result),
    }


def _case_summary(payload: dict[str, object]) -> dict[str, object]:
    evidence = payload["benchmark_case_evidence"]
    assert isinstance(evidence, dict)
    metrics = evidence["measurements"]
    assert isinstance(metrics, dict)
    names = ("turns", "observations", "executions", "provider_attempts", "total_tokens", "model_latency_ms")
    return {
        "case_id": payload["case_id"],
        "task_family_label": payload["task_family_label"],
        "required_primitives": payload["required_primitives"],
        "typed_outcome": payload["typed_outcome"],
        "terminal_status": evidence["status"],
        **{name: metrics[name]["value"] for name in names},
    }


def _aggregate(outcome: MiniWobBreadthCampaignOutcome) -> dict[str, object]:
    records = outcome.cases
    successes = sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in records)
    unavailable = sum(item.outcome is MiniWobTaskOutcome.PROVIDER_UNAVAILABLE for item in records)
    provider_timeout = sum(item.outcome is MiniWobTaskOutcome.PROVIDER_TIMEOUT for item in records)
    infrastructure = {
        MiniWobTaskOutcome.PROVIDER_UNAVAILABLE,
        MiniWobTaskOutcome.PROVIDER_TIMEOUT,
        MiniWobTaskOutcome.ENVIRONMENT_FAILURE,
        MiniWobTaskOutcome.CLEANUP_FAILURE,
    }
    clean_denominator = sum(item.outcome not in infrastructure for item in records)
    return {
        "schema_version": "miniwob-breadth-summary.v1",
        "classification": "MINIWOB_60_SEEDED_BREADTH_PROFILE",
        "planned_cases": 60,
        "completed_cases": len(records),
        "successful_cases": successes,
        "overall_success_rate": _rate(successes, 60),
        "provider_available_success_rate": _rate(successes, 60 - unavailable - provider_timeout),
        "infrastructure_clean_success_rate": _rate(successes, clean_denominator),
        "outcome_counts": _counts(item.outcome.value for item in records),
        "success_by_primitive_profile": _success_by_primitives(records),
        "statistics": {
            name: _statistics([_metric(item, name) for item in records])
            for name in ("turns", "observations", "executions", "provider_attempts", "total_tokens", "model_latency_ms")
        },
        "total_provider_attempts": sum(_metric(item, "provider_attempts") for item in records),
        "total_tokens": sum(_metric(item, "total_tokens") for item in records),
        "total_model_latency_ms": sum(_metric(item, "model_latency_ms") for item in records),
        "total_wall_clock_latency_ms": sum(item.result.latency_ms for item in records),
        "capability_inventory_false_positive_count": sum(
            item.outcome is MiniWobTaskOutcome.UNSUPPORTED_PRIMITIVE for item in records
        ),
        "generalization_claim": "NOT_CLAIMED",
    }


def _success_by_primitives(records) -> dict[str, object]:
    groups: dict[str, list[MiniWobBreadthCaseRecord]] = defaultdict(list)
    for item in records:
        groups["+".join(item.required_primitives)].append(item)
    return {
        name: {
            "successful": sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in values),
            "total": len(values),
            "rate": _rate(sum(item.outcome is MiniWobTaskOutcome.SUCCESS for item in values), len(values)),
        }
        for name, values in sorted(groups.items())
    }


def _statistics(values: list[float]) -> dict[str, float | None]:
    ordered = sorted(values)
    if not ordered:
        return {"median": None, "p90": None}
    return {"median": _percentile(ordered, 0.5), "p90": _percentile(ordered, 0.9)}


def _percentile(values: list[float], quantile: float) -> float:
    index = max(0, math.ceil(len(values) * quantile) - 1)
    return values[index]


def _metric(record: MiniWobBreadthCaseRecord, name: str) -> float:
    item = record.result.measurements[name]
    value = item.value
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _counts(values) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _acceptance_payload(outcome) -> dict[str, object]:
    value = outcome.acceptance
    return {
        "evidence_valid": value.evidence_valid,
        "errors": value.errors,
        "planned_cases": value.planned_cases,
        "completed_cases": value.completed_cases,
        "successful_cases": value.successful_cases,
    }


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
