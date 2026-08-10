"""Read-only post-run analysis for archived MiniWoB breadth evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


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
                "last_action_evaluation_status",
                "last_task_evaluation_status",
                "pending_kind",
            ],
        )
    return outcome or "unresolved_legacy_evidence", "high", []


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    reclassify = commands.add_parser("reclassify-archive")
    reclassify.add_argument("--input", type=Path, required=True)
    reclassify.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "reclassify-archive":
        payload = reclassify_archive(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
