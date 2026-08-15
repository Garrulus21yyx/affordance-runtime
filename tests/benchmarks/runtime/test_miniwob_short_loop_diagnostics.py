from __future__ import annotations

import json
from pathlib import Path

from affordance_runtime.benchmarks.external_breadth.coverage_probe import (
    BreadthDiagnosticDisposition,
    diagnostic_disposition,
)
from affordance_runtime.benchmarks.external_breadth.diagnostic_selection import (
    select_representative_cases,
)
from affordance_runtime.benchmarks.external_breadth.diagnostics import analyze_provider_capacity
from affordance_runtime.benchmarks.external_breadth.requirements import TaskReadiness


def test_representative_selection_is_deterministic_and_excludes_provider(tmp_path: Path) -> None:
    archive = _archive(tmp_path, reversed_order=False)
    first = select_representative_cases(archive)
    second = select_representative_cases(_archive(tmp_path / "other", reversed_order=True))
    assert [(item.original_outcome, item.case_id) for item in first] == [
        (item.original_outcome, item.case_id) for item in second
    ]
    assert all(item.original_outcome != "provider_unavailable" for item in first)
    assert max(sum(item.original_outcome == value for item in first) for value in {i.original_outcome for i in first}) <= 3


def test_disposition_is_conservative() -> None:
    assert diagnostic_disposition(TaskReadiness.DECLARED_UNSUPPORTED, True, True, 2, 2) is BreadthDiagnosticDisposition.REQUIREMENT_UNSUPPORTED
    assert diagnostic_disposition(TaskReadiness.UNASSESSED, True, True, 2, 2) is BreadthDiagnosticDisposition.REQUIREMENT_UNASSESSED
    assert diagnostic_disposition(TaskReadiness.DECLARED_SUPPORTED, False, False, 0, 0) is BreadthDiagnosticDisposition.ENVIRONMENT_LIFECYCLE_GAP
    assert diagnostic_disposition(TaskReadiness.DECLARED_SUPPORTED, True, True, 2, 0) is BreadthDiagnosticDisposition.ACTION_SPACE_GAP
    assert diagnostic_disposition(TaskReadiness.DECLARED_SUPPORTED, True, True, 2, 2) is BreadthDiagnosticDisposition.POLICY_OR_REASONING_CANDIDATE


def test_provider_capacity_analysis_is_read_only_and_tail_aware(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    report = analyze_provider_capacity(archive)
    assert report["provider_calls_made"] == 0
    assert report["unavailable_case_positions"] == [5]
    assert report["tail_concentrated"] is True
    assert report["capacity_sufficient"] is False


def _archive(root: Path, reversed_order: bool = False) -> Path:
    cases = root / "archive" / "cases"
    cases.mkdir(parents=True)
    outcomes = ["success", "environment_failure", "environment_failure", "runtime_rejected", "provider_unavailable"]
    values = list(enumerate(outcomes, 1))
    if reversed_order:
        values.reverse()
    for index, outcome in values:
        payload = {
            "case_id": f"miniwob-60-{index:02d}",
            "task_family_label": f"family-{index}",
            "typed_outcome": outcome,
            "metrics": {
                "provider_attempts": {"measured": True, "value": 1},
                "total_tokens": {"measured": True, "value": 10},
            },
        }
        (cases / f"case-{index}.json").write_text(json.dumps(payload), encoding="utf-8")
    return root / "archive"
