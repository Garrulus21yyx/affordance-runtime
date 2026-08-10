"""Orchestration and privacy-safe reporting for local short-loop diagnostics."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.coverage_probe import probe_case
from affordance_runtime.benchmarks.external_breadth.diagnostic_selection import select_representative_cases
from affordance_runtime.benchmarks.external_breadth.inventory_v2 import (
    build_capability_inventory_v2,
    current_declared_capabilities,
    task_readiness,
)
from affordance_runtime.benchmarks.external_breadth.registry import load_registry_census


def analyze_provider_capacity(archive: Path) -> dict[str, object]:
    cases = []
    total_attempts = 0
    total_tokens = 0
    for position, path in enumerate(sorted((archive / "cases").glob("*.json")), 1):
        case = json.loads(path.read_text(encoding="utf-8"))
        metrics = case.get("metrics", {})
        total_attempts += _metric(metrics, "provider_attempts")
        total_tokens += _metric(metrics, "total_tokens")
        if case.get("typed_outcome") == "provider_unavailable":
            cases.append(position)
    streak = _tail_streak(cases, position if 'position' in locals() else 0)
    return {
        "provider_calls_made": 0,
        "historical_provider_attempts": total_attempts,
        "historical_total_tokens": total_tokens,
        "unavailable_case_positions": cases,
        "consecutive_tail_unavailable_count": streak,
        "tail_concentrated": bool(cases and cases[-1] == position),
        "capacity_declared": False,
        "capacity_sufficient": False,
    }


async def run_local_diagnostics(
    archive: Path,
    seed: int,
    output_dir: Path,
    source_root: Path | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=False)
    cases_dir = output_dir / "cases"
    cases_dir.mkdir()
    selections = select_representative_cases(archive)
    _write(output_dir / "selection.json", {
        "schema_version": "miniwob-m4-4-diagnostic-selection.v1",
        "cases": [item.__dict__ for item in selections],
    })
    census = load_registry_census()
    inventory = build_capability_inventory_v2(census, source_root)
    capabilities = current_declared_capabilities()
    by_task = {item.task_id: item for item in inventory}
    admitted = frozenset(by_task)
    reports = []
    for selected in selections:
        requirement = by_task[f"browsergym/miniwob.{selected.task_family_label}"]
        report = await probe_case(
            selected, task_readiness(requirement, capabilities), seed, admitted,
        )
        reports.append(report)
        _write(cases_dir / f"{selected.case_id}.json", report)
    dispositions = Counter(str(item["disposition"]) for item in reports)
    semantic_actions: Counter[str] = Counter()
    verifier_statuses: Counter[str] = Counter()
    for item in reports:
        action_counts = item.get("semantic_action_counts")
        if isinstance(action_counts, dict):
            semantic_actions.update({str(key): _integer(value) for key, value in action_counts.items()})
        status = item.get("verifier_initial_status")
        if isinstance(status, str) and status:
            verifier_statuses[status] += 1
    raw_interactive = sum(_integer(item.get("raw_interactive_node_count")) for item in reports)
    projected_targets = sum(_integer(item.get("projected_target_count")) for item in reports)
    summary = {
        "schema_version": "miniwob-m4-4-diagnostics.v1",
        "selected_cases": len(selections),
        "completed_cases": len(reports),
        "reset_success_count": sum(bool(item.get("lifecycle_success")) for item in reports),
        "reset_failure_count": sum(not bool(item.get("lifecycle_success")) for item in reports),
        "projection_success_count": sum(bool(item.get("projection_success")) for item in reports),
        "projection_failure_count": sum(not bool(item.get("projection_success")) for item in reports),
        "disposition_counts": dict(sorted(dispositions.items())),
        "unresolved_diagnostic_count": dispositions.get("unresolved", 0),
        "raw_interactive_node_count": raw_interactive,
        "projected_target_count": projected_targets,
        "interactive_projection_coverage_rate": (
            projected_targets / raw_interactive if raw_interactive else None
        ),
        "blank_label_count": sum(_integer(item.get("blank_label_count")) for item in reports),
        "duplicate_label_count": sum(_integer(item.get("duplicate_label_count")) for item in reports),
        "action_option_count": sum(_integer(item.get("action_option_count")) for item in reports),
        "semantic_action_counts": dict(sorted(semantic_actions.items())),
        "verifier_initial_status_counts": dict(sorted(verifier_statuses.items())),
        "historical_environment_failures_reproduced": sum(
            int(item["original_outcome"] == "environment_failure" and not item.get("lifecycle_success"))
            for item in reports
        ),
        "historical_environment_failures_not_reproduced": sum(
            int(item["original_outcome"] == "environment_failure" and bool(item.get("lifecycle_success")))
            for item in reports
        ),
        "provider_capacity": analyze_provider_capacity(archive),
        "provider_calls_made": 0,
        "product_behavior_changed": False,
        "privacy_passed": True,
    }
    _write(output_dir / "summary.json", summary)
    from affordance_runtime.benchmarks.external_breadth.reporting import privacy_scan

    errors = privacy_scan(output_dir)
    summary["privacy_passed"] = not errors
    summary["privacy_error_count"] = len(errors)
    _write(output_dir / "summary.json", summary)
    return summary


def _metric(metrics: object, name: str) -> int:
    item = metrics.get(name) if isinstance(metrics, dict) else None
    value = item.get("value") if isinstance(item, dict) else 0
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _tail_streak(positions: list[int], total: int) -> int:
    values = set(positions)
    count = 0
    while total - count in values:
        count += 1
    return count


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
