"""CLI for exact two-stage candidate/support/remote diagnostic runs."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.model_policy.grounding import DecisionGroundingVariant
from affordance_runtime.model_port import ModelPort, OllamaModelPort, model_port_from_environment

from ..matrix_progress import write_json_report
from ..profile_identity import identity_from_ollama_inventory, ollama_inventory, remote_profile_identity
from .attestation import attest_two_stage
from .contracts import PacingConfiguration
from .suite import run_candidate_suite


async def _run(args) -> int:
    output = Path(args.output_dir)
    pacing = PacingConfiguration(args.inter_stage_delay_s, args.inter_attempt_delay_s)
    if args.profile == "ollama":
        version, models = ollama_inventory(args.ollama_base_url)
        identity = identity_from_ollama_inventory(
            args.model, runtime_version=version, models=models,
            grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2.value,
            execution_profile="gpu-serial-two-stage",
        )
        def factory() -> ModelPort:
            return OllamaModelPort(args.model, args.ollama_base_url)
    else:
        if os.environ.get("RUN_TWO_STAGE_REMOTE_DIAGNOSTIC") != "1":
            raise ValueError("remote two-stage diagnostic requires explicit opt-in")
        port = model_port_from_environment()
        identity = remote_profile_identity(
            port.provider, port.model, port.endpoint_class,
            grounding_variant=DecisionGroundingVariant.COMPACT_CONTRACT_V2.value,
            execution_profile="provider-managed-two-stage-diagnostic",
        )
        def factory() -> ModelPort:
            return model_port_from_environment()
    support = args.mode == "support"
    report = await run_candidate_suite(
        identity, factory, repetitions=args.repetitions, output_dir=output,
        pacing=pacing, support=support, diagnostic=args.mode == "diagnostic",
    )
    qualification_path = output / "qualification.json"
    write_json_report(qualification_path, asdict(report.qualification))
    sha = subprocess.run(
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True,
    ).stdout.strip()
    dirty = bool(subprocess.run(
        ("git", "status", "--porcelain"), check=True, capture_output=True, text=True,
    ).stdout.strip())
    attestation = attest_two_stage(
        report, (output / "suite-report.json", qualification_path),
        git_sha=sha, git_dirty=dirty,
    )
    write_json_report(output / "attestation.json", asdict(attestation))
    return 0 if report.qualification.admitted else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--profile", choices=("ollama", "environment"), required=True)
    run.add_argument("--model", default="")
    run.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    run.add_argument("--mode", choices=("candidate", "support", "diagnostic"), required=True)
    run.add_argument("--repetitions", type=int, required=True)
    run.add_argument("--inter-stage-delay-s", type=float, default=0)
    run.add_argument("--inter-attempt-delay-s", type=float, default=0)
    run.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    if args.profile == "ollama" and not args.model:
        parser.error("--model is required for the Ollama profile")
    if args.mode == "candidate" and args.repetitions != 5:
        parser.error("candidate mode requires exactly 5 repetitions")
    if args.mode == "support" and args.repetitions != 20:
        parser.error("support mode requires exactly 20 repetitions")
    if args.mode == "diagnostic" and args.profile != "environment":
        parser.error("diagnostic mode is reserved for explicit environment profiles")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
