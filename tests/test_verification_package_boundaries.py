from __future__ import annotations

import ast
from pathlib import Path


def test_legacy_verification_owner_is_absent_from_production() -> None:
    package = Path("src/affordance_runtime/verification")
    assert package.is_dir()
    assert not (package / "legacy.py").exists()

    for path in Path("src/affordance_runtime").rglob("*.py"):
        tree = ast.parse(path.read_text())
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        assert "affordance_runtime.verification.legacy" not in imported


def test_staged_step_completion_owner_is_physically_absent() -> None:
    package = Path("src/affordance_runtime")
    for relative in (
        "verification/step_completion.py",
        "verification/predicates.py",
        "verification_report_adapter.py",
        "progress_phase.py",
        "task_plan_progress.py",
        "task_plan_progress_flow.py",
    ):
        assert not (package / relative).exists()


def test_legacy_step_and_criterion_contracts_are_physically_absent() -> None:
    importers = []
    for path in Path("src/affordance_runtime").rglob("*.py"):
        tree = ast.parse(path.read_text())
        modules = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        if "affordance_runtime.legacy_criterion_adapter" in modules:
            importers.append(path.as_posix())
    assert importers == []
    assert not Path("src/affordance_runtime/legacy_criterion_adapter.py").exists()
    assert not Path("src/affordance_runtime/simplified_runtime_contracts.py").exists()
    assert not Path("src/affordance_runtime/task_plan_contracts.py").exists()
