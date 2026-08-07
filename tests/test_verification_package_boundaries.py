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


def test_predicate_evaluator_is_the_default_step_completion_owner() -> None:
    step_tree = ast.parse(Path("src/affordance_runtime/verification/step_completion.py").read_text())
    imports = {node.module or "" for node in ast.walk(step_tree) if isinstance(node, ast.ImportFrom)}
    assert "affordance_runtime.verification.predicates" in imports
    assert "affordance_runtime.verification_report_adapter" not in imports

    progress_tree = ast.parse(Path("src/affordance_runtime/progress_phase.py").read_text())
    called_names = {
        node.func.id
        for node in ast.walk(progress_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "commit_current_state_completion" not in called_names
    attributes = {
        node.func.attr
        for node in ast.walk(progress_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "observation_evidence_context_metadata" not in called_names
    assert "observation_predicate_evidence" in called_names
    assert "unresolved_open_semantic_gaps" in called_names
    assert "evaluate" in attributes

    criteria_tree = ast.parse(Path("src/affordance_runtime/criteria.py").read_text())
    criteria_imports = {node.module or "" for node in ast.walk(criteria_tree) if isinstance(node, ast.ImportFrom)}
    assert "affordance_runtime.verification.mechanical" not in criteria_imports
    assert "affordance_runtime.verification_report_adapter" not in criteria_imports

    obsolete_names = {
        "CurrentStateStepCompletionEvaluator",
        "StepCompletionPreparation",
        "prepare_current_state_step_completion",
        "commit_current_state_completion",
    }
    for path in (
        Path("src/affordance_runtime/task_plan_progress.py"),
        Path("src/affordance_runtime/task_plan_progress_flow.py"),
    ):
        tree = ast.parse(path.read_text())
        defined_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert obsolete_names.isdisjoint(defined_names)


def test_canonical_step_spec_does_not_import_legacy_criterion_adapter() -> None:
    contracts_tree = ast.parse(Path("src/affordance_runtime/simplified_runtime_contracts.py").read_text())
    imports = {node.module or "" for node in ast.walk(contracts_tree) if isinstance(node, ast.ImportFrom)}
    assert "affordance_runtime.legacy_criterion_adapter" not in imports

    importers = []
    for path in Path("src/affordance_runtime").rglob("*.py"):
        tree = ast.parse(path.read_text())
        modules = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        if "affordance_runtime.legacy_criterion_adapter" in modules:
            importers.append(path.as_posix())
    assert importers == []
    assert not Path("src/affordance_runtime/legacy_criterion_adapter.py").exists()
