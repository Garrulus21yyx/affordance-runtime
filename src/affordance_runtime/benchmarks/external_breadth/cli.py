"""Explicitly gated MiniWoB-60 census, preflight, and formal campaign CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.attestation import validate_campaign_tree
from affordance_runtime.benchmarks.external_breadth.campaign_contracts import ProviderCapacityEvidence
from affordance_runtime.benchmarks.external_breadth.capability_inventory import (
    build_capability_inventory,
    capability_inventory_digest,
    supported_candidates,
)
from affordance_runtime.benchmarks.external_breadth.manifest import (
    CAMPAIGN_ID,
    breadth_manifest_digest,
    build_breadth_manifest,
)
from affordance_runtime.benchmarks.external_breadth.registry import SOURCE_COMMIT, load_registry_census
from affordance_runtime.benchmarks.external_breadth.reporting import write_campaign_reports
from affordance_runtime.benchmarks.external_breadth.runner import run_breadth_campaign
from affordance_runtime.benchmarks.external_breadth.selection import selection_key
from affordance_runtime.benchmarks.external_smoke.adapter_reporting import _atomic_json
from affordance_runtime.model.policy import model_policy_from_environment
from affordance_runtime.model.policy.model_port_bridge import ModelPortDecisionAdapter
from affordance_runtime.model.policy.provider_orchestrator import ProviderCallOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze-manifest")
    freeze.add_argument("--output", type=Path, required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--manifest", choices=(CAMPAIGN_ID,), required=True)
    run = commands.add_parser("run")
    run.add_argument("--manifest", choices=(CAMPAIGN_ID,), required=True)
    run.add_argument("--profile", choices=("mistral-format-only-v1",), required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--min-policy-call-interval-s", type=float, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    census = load_registry_census()
    manifest = build_breadth_manifest(census)
    if args.command == "freeze-manifest":
        _write_frozen_evidence(args.output, census, manifest)
        return 0
    errors = _configuration_errors(manifest)
    capacity = _provider_capacity(manifest)
    if not capacity.sufficient:
        errors.append("declared provider attempt capacity is insufficient")
    if args.command == "preflight":
        print(json.dumps({
            "available": not errors,
            "errors": errors,
            "provider_capacity": asdict(capacity),
        }, sort_keys=True))
        return int(bool(errors))
    errors.extend(_argument_errors(args))
    if errors:
        print(json.dumps({"status": "NOT_RUN_UNAVAILABLE_CONFIG", "errors": errors}, sort_keys=True))
        return 1
    policy = model_policy_from_environment(
        grounding_variant="format-only", provider_recovery=False,
    )
    outcome = asyncio.run(run_breadth_campaign(
        manifest, policy, args.output_dir, provider_capacity=capacity,
    ))
    attestation = write_campaign_reports(outcome, args.output_dir)
    tree_errors = validate_campaign_tree(args.output_dir, manifest)
    evidence = json.loads(attestation.read_text(encoding="utf-8"))
    if tree_errors or evidence.get("evidence_valid") is not True:
        return 1
    return 0


def _write_frozen_evidence(path, census, manifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    inventory = build_capability_inventory(census)
    selected = {item.task_id for item in manifest.cases}
    profiles = {item.task_id: item for item in inventory}
    _atomic_json(path, {
        "schema_version": manifest.schema_version,
        "campaign_id": manifest.campaign_id,
        "package_name": census.package_name,
        "package_version": census.package_version,
        "core_version": census.core_version,
        "source_commit": census.source_commit,
        "registry_task_count": len(census.task_ids),
        "registry_digest": census.registry_digest,
        "capability_inventory_digest": capability_inventory_digest(inventory),
        "capability_counts": _capability_counts(inventory),
        "supported_candidate_pool_size": len(supported_candidates(inventory)),
        "selection_namespace": manifest.selection_namespace,
        "manifest_digest": breadth_manifest_digest(manifest),
        "cases": [
            {
                **asdict(case),
                "selection_key": selection_key(case.task_id),
                "reason_code": profiles[case.task_id].reason_code,
                "source_reference": profiles[case.task_id].source_reference,
            }
            for case in manifest.cases
        ],
        "excluded_tasks": [
            {
                "task_id": item.task_id,
                "status": item.status.value,
                "required_primitives": item.required_primitives,
                "reason_code": item.reason_code,
                "source_reference": item.source_reference,
            }
            for item in inventory if item.task_id not in selected
        ],
    })


def _configuration_errors(manifest, *, provider_recovery: bool = False) -> list[str]:
    errors = []
    expected = {
        "LLM_ACTIVE_PROFILE": "mistral",
        "LLM_MISTRAL_MODEL": manifest.model_profile,
        "LLM_DECISION_GROUNDING": "format-only",
        "LLM_PROFILE_FALLBACK_TO_LOCAL": "false",
    }
    for name, value in expected.items():
        if os.environ.get(name, "").strip().casefold() != value.casefold():
            errors.append(f"{name} does not match the frozen campaign profile")
    for name in ("LLM_MISTRAL_BASE_URL", "LLM_MISTRAL_API_KEY"):
        if not os.environ.get(name, "").strip():
            errors.append(f"{name} is unavailable")
    source = os.environ.get("MINIWOB_SOURCE_DIR", "").strip()
    url = os.environ.get("MINIWOB_URL", "").strip()
    if not source or _source_commit(Path(source)) != SOURCE_COMMIT:
        errors.append("MINIWOB_SOURCE_DIR is not the reviewed source commit")
    if not url.startswith("file://"):
        errors.append("MINIWOB_URL must use the reviewed local source fixture")
    try:
        policy = model_policy_from_environment(
            grounding_variant="format-only", provider_recovery=provider_recovery,
        )
        composed = policy.port
        if provider_recovery and not isinstance(composed, ProviderCallOrchestrator):
            errors.append("model policy does not use the admitted provider orchestrator")
        elif provider_recovery:
            assert isinstance(composed, ProviderCallOrchestrator)
            orchestrator = composed
            adapter = orchestrator.primary_port
            if not isinstance(adapter, ModelPortDecisionAdapter):
                errors.append("provider orchestrator does not wrap the one-attempt bridge")
            elif adapter.config.rate_limit_retries or adapter.config.transient_retries:
                errors.append("model transport retry count is nonzero")
            if orchestrator.configured_retry_count != 2:
                errors.append("provider orchestrator retry profile is invalid")
        elif not isinstance(composed, ModelPortDecisionAdapter):
            errors.append("model policy does not use the admitted one-attempt bridge")
        elif composed.config.rate_limit_retries or composed.config.transient_retries:
            errors.append("model transport retry count is nonzero")
    except (AttributeError, ValueError):
        errors.append("Mistral model policy composition is unavailable")
    return errors


def _provider_capacity(manifest) -> ProviderCapacityEvidence:
    required = sum(item.max_turns for item in manifest.cases)
    raw = os.environ.get("MINIWOB_PROVIDER_ATTEMPT_BUDGET", "").strip()
    declared = int(raw) if raw.isdecimal() else 0
    return ProviderCapacityEvidence(
        "provider-capacity-preflight.v1",
        "mistral",
        manifest.model_profile,
        breadth_manifest_digest(manifest),
        required,
        declared,
        bool(raw),
        manifest.grounding_profile,
        0,
        0,
    )


def _argument_errors(args) -> list[str]:
    errors = []
    if os.environ.get("RUN_MINIWOB_60_CAMPAIGN") != "1":
        errors.append("RUN_MINIWOB_60_CAMPAIGN=1 is required")
    if args.seed != 7:
        errors.append("formal campaign seed must be 7")
    if args.min_policy_call_interval_s != 7.5:
        errors.append("formal campaign pacing must be 7.5 seconds")
    if args.output_dir.exists():
        errors.append("formal campaign output directory must be new")
    return errors


def _source_commit(path: Path) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(path), "rev-parse", "HEAD"), check=True,
            capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _capability_counts(inventory) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in inventory:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
