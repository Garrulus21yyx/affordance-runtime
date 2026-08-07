"""Run the real DOM, screenshot, and node-wot conformance profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from affordance_runtime.conformance import run_cross_surface_conformance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-url", required=True)
    parser.add_argument("--wot-td-url", required=True)
    parser.add_argument("--oracle-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_cross_surface_conformance(
        args.output,
        fixture_url=args.fixture_url,
        wot_td_url=args.wot_td_url,
        oracle_url=args.oracle_url,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["acceptance"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
