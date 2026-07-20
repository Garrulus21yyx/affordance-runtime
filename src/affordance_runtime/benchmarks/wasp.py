"""Safe WASP subset-manifest preparation.

WASP configurations include live malicious instructions.  This module keeps
them in the official source configuration and emits only opaque case indices,
environment/safety metadata, and a source digest for reproducible execution.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class WaspCaseRef:
    case_index: int
    environment: str
    exfiltration: bool
    evaluator_types: tuple[str, ...]


def load_wasp_cases(config_path: Path) -> list[WaspCaseRef]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("WASP configuration must be a JSON object")
    cases = payload.get("prompt_injections_setup_config")
    if not isinstance(cases, list) or not cases:
        raise ValueError("WASP configuration must contain prompt_injections_setup_config")
    parsed: list[WaspCaseRef] = []
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise ValueError(f"WASP case {index} must be an object")
        environment = item.get("environment")
        exfiltration = item.get("exfil")
        evaluation = item.get("eval")
        if not isinstance(environment, str) or not environment:
            raise ValueError(f"WASP case {index}.environment must be non-empty text")
        if not isinstance(exfiltration, bool):
            raise ValueError(f"WASP case {index}.exfil must be boolean")
        if not isinstance(evaluation, dict):
            raise ValueError(f"WASP case {index}.eval must be an object")
        evaluator_types = evaluation.get("eval_types")
        if not isinstance(evaluator_types, list) or not evaluator_types or any(
            not isinstance(value, str) or not value for value in evaluator_types
        ):
            raise ValueError(f"WASP case {index}.eval.eval_types must be a non-empty string array")
        parsed.append(WaspCaseRef(index, environment, exfiltration, tuple(evaluator_types)))
    return parsed


def select_wasp_subset(cases: Iterable[WaspCaseRef], *, count: int = 12) -> list[WaspCaseRef]:
    """Deterministically round-robin source cases over environment and exfiltration."""

    if count <= 0:
        raise ValueError("WASP subset count must be positive")
    groups: dict[tuple[str, bool], list[WaspCaseRef]] = defaultdict(list)
    for case in sorted(cases, key=lambda item: item.case_index):
        groups[(case.environment, case.exfiltration)].append(case)
    selected: list[WaspCaseRef] = []
    cursors = {key: 0 for key in sorted(groups)}
    while len(selected) < count:
        progressed = False
        for key in sorted(groups):
            cursor = cursors[key]
            if cursor >= len(groups[key]):
                continue
            selected.append(groups[key][cursor])
            cursors[key] += 1
            progressed = True
            if len(selected) == count:
                break
        if not progressed:
            raise ValueError(f"WASP configuration has fewer than {count} cases")
    return selected


def write_wasp_subset(config_path: Path, output_path: Path, *, count: int = 12) -> dict[str, Any]:
    cases = load_wasp_cases(config_path)
    selected = select_wasp_subset(cases, count=count)
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    distribution = Counter(f"{case.environment}:exfil={str(case.exfiltration).lower()}" for case in selected)
    evaluator_distribution = Counter(kind for case in selected for kind in case.evaluator_types)
    manifest = {
        "schema_version": "wasp-subset-v1",
        "official_harness": "facebookresearch/wasp",
        "source_config_sha256": f"sha256:{config_hash}",
        "source_case_count": len(cases),
        "selection_policy": "sorted-environment-exfiltration-round-robin-v1",
        "selected_case_count": len(selected),
        "case_indices": [case.case_index for case in selected],
        "distribution": dict(sorted(distribution.items())),
        "evaluator_type_distribution": dict(sorted(evaluator_distribution.items())),
        "cases": [asdict(case) for case in selected],
        "malicious_instruction_content_in_manifest": False,
        "official_security_score_claimed": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
