"""Run held-out, real visual, and official MiniWoB++ M8 gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from affordance_runtime.benchmarks.generalization import run_generalization_suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-acceptance-fail",
        action="store_true",
        help="Exit 0 after writing diagnostic evidence even when promotion acceptance fails.",
    )
    args = parser.parse_args()
    report = run_generalization_suite(args.output, training_report_path=args.benchmark)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if args.allow_acceptance_fail:
        return 0
    return 0 if report["acceptance"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
