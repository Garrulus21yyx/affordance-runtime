#!/usr/bin/env python3
"""Run the executable recovery-cascade evolution gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from affordance_runtime.recovery_evolution import run_recovery_cascade_evolution


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_recovery_cascade_evolution(args.output)
    print(json.dumps(asdict(report), indent=2, sort_keys=True, default=str))
    return 0 if report.decision.value == "accepted" and report.rollback_verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
