"""Explicitly gated CLI for the frozen previous-verifier-unknown diagnostic."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import (
    ProviderCapacityEvidence,
)
from affordance_runtime.benchmarks.external_breadth.cli import _configuration_errors
from affordance_runtime.benchmarks.external_breadth.manifest import (
    breadth_manifest_digest,
    build_breadth_manifest,
)
from affordance_runtime.benchmarks.external_breadth.registry import load_registry_census
from affordance_runtime.benchmarks.external_breadth.verifier_targeted import (
    TARGETED_PROFILE,
    run_verifier_targeted_diagnostic,
    targeted_manifest,
    validate_targeted_evidence,
    write_targeted_evidence,
)
from affordance_runtime.model.policy import model_policy_from_environment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=(TARGETED_PROFILE,), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--min-policy-call-interval-s", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = targeted_manifest(build_breadth_manifest(load_registry_census()))
    errors = _configuration_errors(manifest)
    capacity = _provider_capacity(manifest)
    if not capacity.sufficient:
        errors.append("declared provider attempt capacity is insufficient")
    if os.environ.get("RUN_MINIWOB_VERIFIER_14_DIAGNOSTIC") != "1":
        errors.append("RUN_MINIWOB_VERIFIER_14_DIAGNOSTIC=1 is required")
    if args.seed != 7:
        errors.append("targeted diagnostic seed must be 7")
    if args.min_policy_call_interval_s != manifest.minimum_policy_call_interval_s:
        errors.append("targeted diagnostic pacing must match the frozen source profile")
    if args.output_dir.exists():
        errors.append("targeted diagnostic output directory must be new")
    if errors:
        return 1

    policy = model_policy_from_environment(provider_retry_budget=0)
    outcome = asyncio.run(run_verifier_targeted_diagnostic(
        manifest,
        policy,
        args.output_dir,
        provider_capacity=capacity,
    ))
    attestation = write_targeted_evidence(outcome, args.output_dir)
    if validate_targeted_evidence(args.output_dir):
        return 1
    return int(not attestation.is_file())


def _provider_capacity(manifest) -> ProviderCapacityEvidence:
    raw = os.environ.get("MINIWOB_PROVIDER_ATTEMPT_BUDGET", "").strip()
    declared = int(raw) if raw.isdecimal() else 0
    return ProviderCapacityEvidence(
        "provider-capacity-preflight.v1",
        "mistral",
        manifest.model_profile,
        breadth_manifest_digest(manifest),
        sum(item.max_turns for item in manifest.cases),
        declared,
        bool(raw),
        manifest.grounding_profile,
        0,
        0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
