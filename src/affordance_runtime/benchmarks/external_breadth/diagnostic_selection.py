"""Deterministic historical-case selection for local no-model diagnostics."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_NAMESPACE = "miniwob-m4-4-diagnostic-v1"


@dataclass(frozen=True)
class DiagnosticSelection:
    case_id: str
    task_family_label: str
    original_outcome: str
    selection_key: str


def select_representative_cases(archive: Path) -> tuple[DiagnosticSelection, ...]:
    grouped: dict[str, list[DiagnosticSelection]] = defaultdict(list)
    for path in (archive / "cases").glob("*.json"):
        case = json.loads(path.read_text(encoding="utf-8"))
        outcome = str(case["typed_outcome"])
        if outcome == "provider_unavailable":
            continue
        case_id = str(case["case_id"])
        key = hashlib.sha256(f"{_NAMESPACE}\0{outcome}\0{case_id}".encode()).hexdigest()
        grouped[outcome].append(
            DiagnosticSelection(case_id, str(case["task_family_label"]), outcome, key),
        )
    selected = []
    for outcome in sorted(grouped):
        selected.extend(sorted(grouped[outcome], key=lambda item: (item.selection_key, item.case_id))[:3])
    return tuple(selected)
