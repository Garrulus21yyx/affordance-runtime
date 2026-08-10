from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
COORDINATOR_PATH = REPOSITORY_ROOT / "src" / "affordance_runtime" / "coordinator.py"

# Method count remains a responsibility signal for the feature-frozen legacy owner.
# File length is intentionally not a correctness gate.
COORDINATOR_METHOD_CEILING = 26


def test_run_coordinator_feature_freeze_cannot_expand() -> None:
    source = COORDINATOR_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    coordinator = next(
        item
        for item in module.body
        if isinstance(item, ast.ClassDef) and item.name == "RunCoordinator"
    )
    methods = [
        item
        for item in coordinator.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert len(methods) <= COORDINATOR_METHOD_CEILING
