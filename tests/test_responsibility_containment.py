from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
COORDINATOR_PATH = REPOSITORY_ROOT / "src" / "affordance_runtime" / "coordinator.py"

# Ratchet from the audited f4c3308 tree. Lower both ceilings as ownership is
# extracted; do not raise them to admit new feature work.
COORDINATOR_LINE_CEILING = 3_732
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

    assert len(source.splitlines()) <= COORDINATOR_LINE_CEILING
    assert len(methods) <= COORDINATOR_METHOD_CEILING
