"""Run one immutable, provider-free M8.6 G5 Runtime rollout."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from affordance_runtime.benchmarks.generalization_rollout import (
    run_generalization_runtime_rollout,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="")
    args = parser.parse_args()
    revision = args.revision or _clean_revision()
    report = run_generalization_runtime_rollout(args.output, revision=revision)
    print(report.model_dump_json(indent=2))
    return 0 if report.acceptance == "passed" else 1


def _clean_revision() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        raise RuntimeError("G5 rollout requires a clean immutable git revision")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not revision:
        raise RuntimeError("G5 rollout could not resolve git revision")
    return revision


if __name__ == "__main__":
    raise SystemExit(main())
