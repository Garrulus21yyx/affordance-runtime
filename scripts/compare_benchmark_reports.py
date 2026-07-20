#!/usr/bin/env python3
"""Compare host and container benchmark outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from affordance_runtime.benchmarks.agreement import compare_benchmark_reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("host_report", type=Path)
    parser.add_argument("container_report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare_benchmark_reports(args.host_report, args.container_report)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["acceptance"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
