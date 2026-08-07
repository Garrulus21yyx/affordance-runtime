"""Validate release benchmark and evolution reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate_generalization_evidence(generalization: dict[str, object]) -> None:
    if generalization.get("suite_version") == "generalization-v1":
        if generalization.get("governance_status") != "legacy_unsegregated_diagnostic":
            raise RuntimeError("legacy generalization evidence lacks its diagnostic classification")
        if generalization.get("diagnostic_errors"):
            raise RuntimeError(
                f"legacy generalization diagnostics failed: {generalization['diagnostic_errors']}"
            )
        if (
            generalization.get("acceptance") != "incomplete"
            or generalization.get("g5_evidence_eligible") is not False
            or generalization.get("official_score_claimed") is not False
        ):
            raise RuntimeError("legacy generalization evidence made an invalid G5 or score claim")
        return
    if (
        generalization.get("schema_version") != "m8.6-generalization-evidence-v1"
        or generalization.get("acceptance") != "passed"
        or generalization.get("official_score_claimed") is not False
    ):
        raise RuntimeError(
            f"four-profile generalization gate failed: {generalization.get('acceptance_errors')}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--evolution", type=Path, required=True)
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--generalization", type=Path)
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
    if args.parent is not None:
        parent = json.loads(args.parent.read_text(encoding="utf-8"))
        if not parent.get("runtime_authoritative") or parent.get("primitive_gui_tools_exposed"):
            raise RuntimeError("external parent did not preserve runtime authority")
        if parent.get("pricing", {}).get("status") != "success":
            raise RuntimeError("external parent pricing flow failed")
        if parent.get("export", {}).get("preapproval_status") != "waiting_approval":
            raise RuntimeError("external parent export bypassed approval")
        if parent.get("export", {}).get("status") != "success":
            raise RuntimeError("external parent approved export failed")
    if args.generalization is not None:
        generalization = json.loads(args.generalization.read_text(encoding="utf-8"))
        validate_generalization_evidence(generalization)
    print("evidence_gate=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
