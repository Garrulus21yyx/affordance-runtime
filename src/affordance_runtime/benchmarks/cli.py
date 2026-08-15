"""Offline benchmark and provider-preflight command collection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="affordance-runtime-benchmark")
    subcommands = parser.add_subparsers(dest="command", required=True)

    screenspot = subcommands.add_parser(
        "benchmark-screenspot",
        help="evaluate offline ScreenSpot point-grounding predictions",
    )
    screenspot.add_argument("--annotations", type=Path, required=True)
    screenspot.add_argument("--images", type=Path, required=True)
    screenspot.add_argument("--predictions", type=Path, required=True)
    screenspot.add_argument("--output", type=Path, default=Path("screenspot-results"))

    screenspot_grounder = subcommands.add_parser(
        "benchmark-screenspot-grounder",
        help="generate and score ScreenSpot predictions with the configured visual grounder",
    )
    screenspot_grounder.add_argument("--annotations", type=Path, required=True)
    screenspot_grounder.add_argument("--images", type=Path, required=True)
    screenspot_grounder.add_argument("--output", type=Path, default=Path("screenspot-grounder-results"))

    workarena = subcommands.add_parser(
        "benchmark-workarena-preflight",
        help="inspect isolated WorkArena L1 prerequisites without loading credentials",
    )
    workarena.add_argument("--output", type=Path, default=Path("workarena-results"))
    workarena.add_argument("--runtime-python", type=Path)

    webarena_verified = subcommands.add_parser(
        "prepare-webarena-verified-subset",
        help="write a reproducible WebArena-Verified manifest for official offline scoring",
    )
    webarena_verified.add_argument("--dataset", type=Path, required=True)
    webarena_verified.add_argument("--output", type=Path, default=Path("webarena-verified-subset.json"))
    webarena_verified.add_argument("--count", type=int, default=30)

    webarena_evaluate = subcommands.add_parser(
        "evaluate-webarena-verified",
        help="delegate a prepared manifest to the upstream deterministic evaluator",
    )
    webarena_evaluate.add_argument("--manifest", type=Path, required=True)
    webarena_evaluate.add_argument("--agent-logs", type=Path, required=True)
    webarena_evaluate.add_argument("--config", type=Path)
    webarena_evaluate.add_argument("--executable", default="webarena-verified")
    webarena_evaluate.add_argument("--output", type=Path, default=Path("webarena-verified-evaluation.json"))

    wasp = subcommands.add_parser(
        "prepare-wasp-subset",
        help="write a digest-bound WASP security subset without copying malicious prompt content",
    )
    wasp.add_argument("--config", type=Path, required=True)
    wasp.add_argument("--output", type=Path, default=Path("wasp-subset.json"))
    wasp.add_argument("--count", type=int, default=12)

    ollama_preflight = subcommands.add_parser(
        "provider-preflight-ollama",
        help="record Ollama identity, container GPU visibility, and non-zero model VRAM residency",
    )
    ollama_preflight.add_argument("--output", type=Path, default=Path("artifacts/ollama-preflight.json"))
    ollama_preflight.add_argument("--base-url", default="http://127.0.0.1:11434")
    ollama_preflight.add_argument("--model", default="qwen2.5:7b")
    ollama_preflight.add_argument("--container", default="ollama")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "benchmark-screenspot":
        from affordance_runtime.benchmarks.screenspot import run_screenspot_offline_suite

        report = run_screenspot_offline_suite(args.annotations, args.images, args.predictions, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "benchmark-screenspot-grounder":
        from affordance_runtime.benchmarks.screenspot import run_screenspot_grounder_suite
        from affordance_runtime.surfaces.visual.grounding import visual_grounder_from_environment

        report = run_screenspot_grounder_suite(
            args.annotations, args.images, visual_grounder_from_environment(), args.output
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "benchmark-workarena-preflight":
        from affordance_runtime.benchmarks.workarena import write_workarena_preflight

        report = write_workarena_preflight(args.output, runtime_python=args.runtime_python)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ready"] else 1
    if args.command == "prepare-webarena-verified-subset":
        from affordance_runtime.benchmarks.webarena_verified import write_webarena_verified_subset

        manifest = write_webarena_verified_subset(args.dataset, args.output, count=args.count)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if args.command == "evaluate-webarena-verified":
        from affordance_runtime.benchmarks.webarena_verified import evaluate_webarena_verified_manifest

        report = evaluate_webarena_verified_manifest(
            args.manifest, args.agent_logs, config_path=args.config, executable=args.executable
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not report["acceptance_errors"] else 1
    if args.command == "prepare-wasp-subset":
        from affordance_runtime.benchmarks.wasp import write_wasp_subset

        manifest = write_wasp_subset(args.config, args.output, count=args.count)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if args.command == "provider-preflight-ollama":
        from affordance_runtime.model.providers.preflight import write_ollama_gpu_preflight

        ollama_report = write_ollama_gpu_preflight(
            args.output,
            base_url=args.base_url,
            model=args.model,
            container_name=args.container,
        )
        print(json.dumps(ollama_report.to_dict(), indent=2, sort_keys=True))
        return 0 if ollama_report.ready else 1
    return 2
