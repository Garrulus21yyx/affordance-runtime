"""Read-only post-run analysis for archived MiniWoB breadth evidence."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.inventory_v2 import (
    build_capability_inventory_v2,
    capability_inventory_v2_digest,
    current_declared_capabilities,
    task_readiness,
)
from affordance_runtime.benchmarks.external_breadth.registry import load_registry_census
from affordance_runtime.benchmarks.external_breadth.rerun_readiness import (
    BreadthRerunEvidence,
    evaluate_rerun_readiness,
)


def reclassify_archive(archive: Path) -> dict[str, object]:
    records = []
    for path in sorted((archive / "cases").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        revised, confidence, missing = _legacy_classification(case)
        records.append({
            "case_id": case["case_id"],
            "task_family_label": case["task_family_label"],
            "original_outcome": case["typed_outcome"],
            "revised_category": revised,
            "confidence": confidence,
            "missing_evidence_fields": missing,
        })
    counts = Counter(str(item["revised_category"]) for item in records)
    return {
        "schema_version": "miniwob-archive-reclassification.v1",
        "source_archive": archive.name,
        "historical_results_modified": False,
        "case_count": len(records),
        "revised_category_counts": dict(sorted(counts.items())),
        "unresolved_count": counts["unresolved_legacy_evidence"],
        "cases": records,
    }


def capability_overlay(archive: Path, source_root: Path | None = None) -> dict[str, object]:
    census = load_registry_census()
    capabilities = current_declared_capabilities()
    inventory = build_capability_inventory_v2(census, source_root)
    by_task = {item.task_id: item for item in inventory}
    cases = []
    for path in sorted((archive / "cases").glob("*.json")):
        historical = json.loads(path.read_text(encoding="utf-8"))
        task_id = f"browsergym/miniwob.{historical['task_family_label']}"
        requirements = by_task[task_id]
        cases.append({
            "case_id": historical["case_id"],
            "task_family_label": historical["task_family_label"],
            "historical_outcome": historical["typed_outcome"],
            "v1_primitive_profile": historical["required_primitives"],
            "v2_requirements": requirements.__dict__,
            "v2_readiness": task_readiness(requirements, capabilities).value,
        })
    counts = Counter(str(item["v2_readiness"]) for item in cases)
    return {
        "schema_version": "miniwob-60-capability-overlay.v1",
        "historical_results_modified": False,
        "inventory_schema_version": "miniwob-capability-inventory.v2",
        "inventory_digest": capability_inventory_v2_digest(census, inventory, capabilities),
        "registry_task_count": len(inventory),
        "readiness_counts": dict(sorted(counts.items())),
        "cases": cases,
    }


def rerun_readiness_report(
    reclassification: dict[str, object],
    overlay: dict[str, object],
    diagnostics: dict[str, object],
    *,
    full_local_validation_passed: bool = False,
) -> dict[str, object]:
    capacity = diagnostics.get("provider_capacity")
    provider = capacity if isinstance(capacity, dict) else {}
    evidence = BreadthRerunEvidence(
        new_report_schema_typed=True,
        unclassified_outcome_count=_bounded_int(reclassification.get("unresolved_count")),
        failure_origins_complete=True,
        capability_inventory_v2_complete=overlay.get("registry_task_count") == 125,
        capability_inventory_digest=str(overlay.get("inventory_digest", "")),
        representative_diagnostics_complete=(
            diagnostics.get("selected_cases") == diagnostics.get("completed_cases")
        ),
        unresolved_diagnostic_count=_bounded_int(diagnostics.get("unresolved_diagnostic_count")),
        provider_capacity_declared=provider.get("capacity_declared") is True,
        provider_capacity_sufficient=provider.get("capacity_sufficient") is True,
        privacy_passed=diagnostics.get("privacy_passed") is True,
        full_local_validation_passed=full_local_validation_passed,
    )
    readiness = evaluate_rerun_readiness(evidence)
    return {
        "schema_version": "miniwob-breadth-rerun-readiness.v1",
        "admitted": readiness.admitted,
        "errors": readiness.errors,
        "evidence": evidence.__dict__,
        "p5_e_admission": "blocked_by_short_loop_breadth",
    }


def _legacy_classification(case: dict[str, object]) -> tuple[str, str, list[str]]:
    outcome = str(case.get("typed_outcome", ""))
    metrics = case.get("metrics")
    measured = metrics if isinstance(metrics, dict) else {}
    ask_user = measured.get("ask_user_count")
    ask_value = ask_user.get("value") if isinstance(ask_user, dict) else 0
    if outcome == "other_typed_failure" and ask_value:
        return "ask_user_unresolved", "high", ["last_decision_type"]
    if outcome in {"other_typed_failure", "environment_failure"}:
        return (
            "unresolved_legacy_evidence",
            "insufficient",
            [
                "failure_origin",
                "failure_code",
                "exception_class",
                "last_decision_type",
                "last_action_observed_change",
                "last_action_local_postcondition",
                "last_action_evidence_method",
                "last_task_evaluation_status",
                "pending_kind",
            ],
        )
    return outcome or "unresolved_legacy_evidence", "high", []


def _bounded_int(value: object) -> int:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    reclassify = commands.add_parser("reclassify-archive")
    reclassify.add_argument("--input", type=Path, required=True)
    reclassify.add_argument("--output", type=Path, required=True)
    overlay = commands.add_parser("capability-overlay")
    overlay.add_argument("--archive", type=Path, required=True)
    overlay.add_argument("--output", type=Path, required=True)
    readiness = commands.add_parser("rerun-readiness")
    readiness.add_argument("--reclassification", type=Path, required=True)
    readiness.add_argument("--capability-overlay", type=Path, required=True)
    readiness.add_argument("--diagnostics", type=Path, required=True)
    readiness.add_argument("--output", type=Path, required=True)
    readiness.add_argument("--full-local-validation-passed", action="store_true")
    args = parser.parse_args()
    if args.command == "reclassify-archive":
        payload = reclassify_archive(args.input)
    elif args.command == "capability-overlay":
        configured = os.environ.get("MINIWOB_SOURCE_DIR", "").strip()
        payload = capability_overlay(args.archive, Path(configured) if configured else None)
    elif args.command == "rerun-readiness":
        payload = rerun_readiness_report(
            json.loads(args.reclassification.read_text(encoding="utf-8")),
            json.loads(args.capability_overlay.read_text(encoding="utf-8")),
            json.loads(args.diagnostics.read_text(encoding="utf-8")),
            full_local_validation_passed=args.full_local_validation_passed,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
