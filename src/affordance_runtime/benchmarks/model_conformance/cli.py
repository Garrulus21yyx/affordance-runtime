"""Narrow CLI for explicit exact-profile conformance diagnostics."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from affordance_runtime.model_port import ModelPort, OllamaModelPort, model_port_from_environment

from .attestation import attest_results, write_attestation
from .profile_identity import (
    identity_from_ollama_inventory,
    ollama_inventory,
    remote_profile_identity,
)
from .runner import run_profile


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--profile", choices=("ollama", "environment"), required=True)
    run.add_argument("--model", default="")
    run.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    run.add_argument("--execution-profile", default="")
    run.add_argument("--levels", required=True)
    run.add_argument("--grounding", required=True)
    run.add_argument("--repetitions", type=int)
    run.add_argument("--support-attestation", action="store_true")
    run.add_argument("--output-dir", required=True)
    attest = sub.add_parser("attest")
    attest.add_argument("--result", action="append", required=True)
    attest.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "attest":
        import subprocess

        sha = subprocess.run(
            ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ("git", "status", "--short"), check=True, capture_output=True, text=True,
        ).stdout.strip())
        value = attest_results(tuple(Path(item) for item in args.result), git_sha=sha, git_dirty=dirty)
        write_attestation(Path(args.output), value)
        return 0 if value.accepted else 1
    if args.profile == "environment" and os.environ.get("RUN_MODEL_PROFILE_CONFORMANCE") != "1":
        parser.error("remote environment profile requires RUN_MODEL_PROFILE_CONFORMANCE=1")
    levels = tuple(item.strip() for item in args.levels.split(",") if item.strip())
    admitted_levels = {"0", "1", "2", "3", "4", "D0", "D1", "D2", "D3", "D4"}
    if set(levels) - admitted_levels:
        parser.error("levels must be selected from 0,1,2,3,4,D0,D1,D2,D3,D4")
    grounding = tuple(item.strip() for item in args.grounding.split(",") if item.strip())
    identity_grounding = grounding[0] if len(grounding) == 1 else ""
    repetitions = args.repetitions or (5 if args.profile == "ollama" else 1)
    factory: Callable[[], ModelPort]
    if args.profile == "ollama":
        version, models = ollama_inventory(args.ollama_base_url)
        identity = identity_from_ollama_inventory(
            args.model,
            runtime_version=version,
            models=models,
            grounding_variant=identity_grounding,
            execution_profile=args.execution_profile,
        )
        installed = {str(item.get("name") or item.get("model") or "") for item in models}
        if args.model not in installed:
            parser.error("requested Ollama model is not already installed")
        factory = lambda: OllamaModelPort(  # noqa: E731
            model=args.model,
            base_url=args.ollama_base_url,
        )
    else:
        configured = model_port_from_environment()
        identity = remote_profile_identity(
            configured.provider,
            configured.model,
            configured.endpoint_class,
            grounding_variant=identity_grounding,
            execution_profile=args.execution_profile or "provider-managed",
        )
        factory = lambda: model_port_from_environment()  # noqa: E731
    asyncio.run(run_profile(
        identity, factory, levels=levels, grounding_variants=grounding,
        repetitions=repetitions, output_dir=Path(args.output_dir),
        support_attestation=args.support_attestation,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
