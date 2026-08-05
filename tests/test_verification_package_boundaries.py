from __future__ import annotations

import ast
from pathlib import Path


def test_legacy_verification_owner_is_absent_from_production() -> None:
    package = Path("src/affordance_runtime/verification")
    assert package.is_dir()
    assert not (package / "legacy.py").exists()

    for path in Path("src/affordance_runtime").rglob("*.py"):
        tree = ast.parse(path.read_text())
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert "affordance_runtime.verification.legacy" not in imported
