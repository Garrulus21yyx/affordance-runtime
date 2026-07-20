"""Validate release benchmark and evolution reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--evolution", type=Path, required=True)
    args = parser.parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    evolution = json.loads(args.evolution.read_text(encoding="utf-8"))
    if benchmark.get("acceptance_errors"):
        raise RuntimeError(f"benchmark gate failed: {benchmark['acceptance_errors']}")
    environment = benchmark.get("environment") or {}
    required_environment = {
        "runtime_commit",
        "python_version",
        "playwright_version",
        "browser_version",
        "fixture_version",
        "suite_version",
        "seed_semantics",
    }
    missing = sorted(required_environment - set(environment))
    if missing:
        raise RuntimeError(f"environment manifest is missing fields: {missing}")
    if evolution.get("decision") != "accepted":
        raise RuntimeError(f"evolution gate did not accept candidate: {evolution.get('decision')}")
    if not evolution.get("rollback_verified"):
        raise RuntimeError("evolution gate did not verify persisted load and rollback")
    replay = evolution.get("replay_evidence") or []
    categories = {item.get("category") for item in replay if item.get("success")}
    required_categories = {"original", "task_family", "global_smoke", "safety_smoke"}
    if not required_categories <= categories:
        raise RuntimeError(f"evolution gate is missing successful replay categories: {required_categories - categories}")
    print("evidence_gate=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
