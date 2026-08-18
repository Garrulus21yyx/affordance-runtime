"""Narrow fixed-suite target-loop benchmark command."""

import argparse
import asyncio
from dataclasses import replace
from pathlib import Path

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.reporting import write_run_report
from affordance_runtime.benchmarks.target_loop.runner import run_suite
from affordance_runtime.benchmarks.webarena_verified import (
    inspect_webarena_verified_w1b_world,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite")
    parser.add_argument("--profile")
    parser.add_argument("--case-id")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--w1b-world", action="store_true")
    args = parser.parse_args()
    if args.w1b_world:
        result = asyncio.run(
            inspect_webarena_verified_w1b_world(Path(args.output_dir), seed=args.seed)
        )
        return 0 if result["ready"] else 1
    if not args.suite or not args.profile:
        parser.error("--suite and --profile are required unless --w1b-world is used")
    manifest = get_manifest(args.suite, args.profile, args.seed)
    if args.case_id:
        cases = tuple(item for item in manifest.cases if item.case_id == args.case_id)
        if not cases:
            parser.error("case ID is not part of the selected fixed manifest")
        manifest = replace(manifest, cases=cases)
    result = asyncio.run(run_suite(manifest, trace_dir=Path(args.output_dir)))
    write_run_report(result, args.output_dir)
    return 0 if result.acceptance.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
