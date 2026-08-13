from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.add(node.module or "")
    return result


def test_target_benchmark_uses_production_runtime_composition_root() -> None:
    runner = RUNTIME / "benchmarks" / "target_loop" / "runner.py"
    source = runner.read_text(encoding="utf-8")

    assert "compose_target_runtime(" in source
    assert "TargetRuntime(" not in source
    assert "AgentLoop(" not in source
    assert "AgentEpisodeRunner(" not in source
    assert "affordance_runtime.agent.loop" not in _imports(runner)
    assert "affordance_runtime.agent.episode_runner" not in _imports(runner)
    assert "affordance_runtime.agent.composition" in _imports(runner)


def test_target_composition_owner_has_no_benchmark_dependency() -> None:
    composition = RUNTIME / "agent" / "composition.py"

    assert not any(
        name.startswith("affordance_runtime.benchmarks")
        for name in _imports(composition)
    )


def test_target_client_uses_target_runtime_without_legacy_coordinator() -> None:
    client = RUNTIME / "target_runtime_client.py"
    imports = _imports(client)

    assert "affordance_runtime.agent.runtime" in imports
    assert "affordance_runtime.coordinator" not in imports
    assert "affordance_runtime.runtime_client" not in imports
    assert "affordance_runtime.composition" not in imports


def test_all_benchmark_modules_use_product_target_composition_owner() -> None:
    violations = []
    for path in sorted((RUNTIME / "benchmarks").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            if name in {"AgentLoop", "AgentEpisodeRunner", "TargetRuntime"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{name}")
    assert violations == []


def test_product_composition_is_only_source_target_runtime_constructor() -> None:
    violations = []
    composition = RUNTIME / "agent" / "composition.py"
    for path in sorted(RUNTIME.rglob("*.py")):
        if path == composition:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            if name == "TargetRuntime":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{name}")
    assert violations == []


def test_target_intake_does_not_import_workflow_or_gui_execution_authority() -> None:
    intake = RUNTIME / "task" / "intake.py"
    imports = _imports(intake)

    assert not any(
        name.startswith((
            "affordance_runtime.benchmarks",
            "affordance_runtime.surfaces",
            "affordance_runtime.executors",
        ))
        for name in imports
    )
    assert imports.isdisjoint({
        "affordance_runtime.task_intake",
        "affordance_runtime.task_spec_authority",
        "affordance_runtime.task_plan_contracts",
        "affordance_runtime.state_kernel",
        "affordance_runtime.runtime_committer",
        "affordance_runtime.world.binder",
    })


def test_browsergym_goal_uses_target_thin_intake() -> None:
    adapter = RUNTIME / "benchmarks" / "external_smoke" / "browsergym_environment.py"
    source = adapter.read_text(encoding="utf-8")

    assert "ThinTaskIntake().compile(" in source
    assert "NaturalLanguageTaskRequest(" in source
    assert "TaskBoundary(" in source
