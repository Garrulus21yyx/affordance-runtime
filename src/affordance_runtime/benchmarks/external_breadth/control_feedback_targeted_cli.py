"""Explicit CLI for the frozen M4.6-D control-feedback diagnostic."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.campaign_contracts import ProviderCapacityEvidence
from affordance_runtime.benchmarks.external_breadth.cli import _configuration_errors
from affordance_runtime.benchmarks.external_breadth.control_feedback_targeted import (
    PROVIDER_FALLBACK_COUNT,
    PROVIDER_MAX_ATTEMPTS,
    PROVIDER_MAX_RETRIES,
    TARGETED_PROFILE,
    run_control_feedback_targeted_diagnostic,
    targeted_manifest,
    validate_targeted_evidence,
    write_targeted_evidence,
)
from affordance_runtime.benchmarks.external_breadth.manifest import (
    breadth_manifest_digest,
    build_breadth_manifest,
)
from affordance_runtime.benchmarks.external_breadth.registry import load_registry_census
from affordance_runtime.model.policy import model_policy_from_environment


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=(TARGETED_PROFILE,), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--min-policy-call-interval-s", type=float, required=True)
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-capture-dir", type=Path)
    parser.add_argument("--validate-existing", type=Path)
    args = parser.parse_args()
    if args.validate_existing is not None:
        return int(bool(validate_targeted_evidence(args.validate_existing)))
    manifest = targeted_manifest(build_breadth_manifest(load_registry_census()))
    errors = _configuration_errors(manifest, provider_recovery=True)
    capacity = _provider_capacity(manifest)
    if not capacity.sufficient:
        errors.append("declared provider attempt capacity is insufficient")
    if os.environ.get("RUN_MINIWOB_CONTROL_FEEDBACK_25_DIAGNOSTIC") != "1":
        errors.append("RUN_MINIWOB_CONTROL_FEEDBACK_25_DIAGNOSTIC=1 is required")
    if args.seed != 7:
        errors.append("control-feedback diagnostic seed must be 7")
    if args.min_policy_call_interval_s != manifest.minimum_policy_call_interval_s:
        errors.append("control-feedback pacing must match the frozen source profile")
    if args.output_dir.exists():
        errors.append("control-feedback output directory must be new")
    if args.private_capture_dir is not None:
        output = args.output_dir.resolve()
        private = args.private_capture_dir.resolve()
        if private == output or output in private.parents or private in output.parents:
            errors.append("private model capture must be outside the public evidence tree")
        if private.exists() and any(private.iterdir()):
            errors.append("private model capture directory must be new or empty")
    if errors:
        return 1
    policy_environment = dict(os.environ)
    if args.private_capture_dir is not None:
        policy_environment["LLM_ENABLE_PRIVATE_MODEL_CAPTURE"] = "true"
        policy_environment["LLM_PRIVATE_MODEL_CAPTURE_DIR"] = str(
            args.private_capture_dir.resolve()
        )
    policy = model_policy_from_environment(
        policy_environment,
        grounding_variant="format-only", provider_recovery=True,
    )
    outcome = asyncio.run(run_control_feedback_targeted_diagnostic(
        manifest,
        policy,
        args.output_dir,
        implementation_sha=args.implementation_sha,
        provider_capacity=capacity,
    ))
    write_targeted_evidence(outcome, args.output_dir)
    return int(bool(validate_targeted_evidence(args.output_dir)))


def _provider_capacity(manifest) -> ProviderCapacityEvidence:
    raw = os.environ.get("MINIWOB_PROVIDER_ATTEMPT_BUDGET", "").strip()
    declared = int(raw) if raw.isdecimal() else 0
    required = sum(item.max_turns for item in manifest.cases) * PROVIDER_MAX_ATTEMPTS
    return ProviderCapacityEvidence(
        "provider-capacity-preflight.v2",
        "mistral",
        manifest.model_profile,
        breadth_manifest_digest(manifest),
        required,
        declared,
        bool(raw) and declared >= required,
        manifest.grounding_profile,
        PROVIDER_MAX_RETRIES,
        PROVIDER_FALLBACK_COUNT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
