"""Narrow fixed-suite target-loop benchmark command."""

import argparse
import asyncio

from affordance_runtime.benchmarks.target_loop.manifest import get_manifest
from affordance_runtime.benchmarks.target_loop.reporting import write_run_report
from affordance_runtime.benchmarks.target_loop.runner import run_suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--case-id")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    cases = get_manifest(args.suite, args.profile, args.seed)
    if args.case_id:
        cases = tuple(item for item in cases if item.case_id == args.case_id)
        if not cases:
            parser.error("case ID is not part of the selected fixed manifest")
    result = asyncio.run(run_suite(args.suite, args.profile, cases, args.seed))
    write_run_report(result, args.output_dir)
    return 0 if result.acceptance.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
