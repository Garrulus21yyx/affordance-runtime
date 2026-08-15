from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"

_DISPLACED_MODULES = (
    "affordance_runtime.agent.composition",
    "affordance_runtime.agent.context.visual_annotation",
    "affordance_runtime.agent.runtime",
    "affordance_runtime.agent.types",
    "affordance_runtime.browser_session",
    "affordance_runtime.browser_thread_session",
    "affordance_runtime.execution_context",
    "affordance_runtime.model_boundary",
    "affordance_runtime.model.context",
    "affordance_runtime.model_evaluator",
    "affordance_runtime.model_policy",
    "affordance_runtime.model_port",
    "affordance_runtime.model_tool_transport",
    "affordance_runtime.provider_preflight",
    "affordance_runtime.surfaces.base",
    "affordance_runtime.target_cli",
    "affordance_runtime.target_composition",
    "affordance_runtime.unified_observation",
    "affordance_runtime.visual_grounding",
    "affordance_runtime.world.action_space",
    "affordance_runtime.world.binder",
    "affordance_runtime.world.interaction_capabilities",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    return imports


def test_package_root_retains_only_cross_cutting_bootstrap_modules() -> None:
    assert sorted(path.name for path in RUNTIME.glob("*.py")) == [
        "__init__.py",
        "__main__.py",
        "immutable.py",
        "schema_digest.py",
    ]


def test_displaced_owner_modules_are_absent_and_unimported() -> None:
    live_imports = {
        imported
        for path in RUNTIME.rglob("*.py")
        for imported in _imports(path)
    }
    violations = sorted(
        imported
        for imported in live_imports
        if any(
            imported == displaced or imported.startswith(f"{displaced}.")
            for displaced in _DISPLACED_MODULES
        )
    )
    assert violations == []

    for module in _DISPLACED_MODULES:
        relative = Path(*module.removeprefix("affordance_runtime.").split("."))
        assert not (RUNTIME / relative).with_suffix(".py").exists()
        assert not (RUNTIME / relative).is_dir()


def test_action_space_value_types_have_one_actions_owner() -> None:
    expected = {
        "ActionOption",
        "ActionRisk",
        "ActionSpace",
        "AdmittedActionSelection",
    }
    definitions: dict[str, list[str]] = {name: [] for name in expected}
    for path in RUNTIME.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in definitions:
                definitions[node.name].append(str(path.relative_to(RUNTIME)))
    assert definitions == {
        name: ["actions/space_contracts.py"] for name in expected
    }
    world_contracts = (RUNTIME / "world" / "contracts.py").read_text(encoding="utf-8")
    assert not any(f"class {name}" in world_contracts for name in expected)


def test_owner_packages_do_not_import_benchmark_authority() -> None:
    for package in (
        "actions",
        "agent",
        "app",
        "confirmation",
        "evaluation",
        "execution",
        "model",
        "risk",
        "surfaces",
        "task",
        "verification",
        "world",
    ):
        for path in (RUNTIME / package).rglob("*.py"):
            assert not any(
                imported.startswith(
                    (
                        "affordance_runtime.benchmarks",
                        "affordance_runtime.testing",
                    )
                )
                for imported in _imports(path)
            ), path


def test_app_runtime_delegates_episode_control_to_agent_loop() -> None:
    imports = _imports(RUNTIME / "app" / "runtime.py")
    assert "affordance_runtime.agent.loop" in imports
    assert "affordance_runtime.model.policy" not in imports
    assert not any(name.startswith("affordance_runtime.surfaces") for name in imports)


def test_surfaces_cannot_own_product_or_loop_lifecycle() -> None:
    forbidden = {
        "affordance_runtime.agent.loop",
        "affordance_runtime.agent.session",
        "affordance_runtime.app.composition",
        "affordance_runtime.app.runtime",
    }
    violations = {
        str(path.relative_to(ROOT)): sorted(_imports(path).intersection(forbidden))
        for path in (RUNTIME / "surfaces").rglob("*.py")
        if _imports(path).intersection(forbidden)
    }
    assert violations == {}


def test_world_ports_do_not_depend_on_concrete_surface_packages() -> None:
    violations = {
        str(path.relative_to(ROOT)): sorted(
            imported
            for imported in _imports(path)
            if imported.startswith("affordance_runtime.surfaces")
        )
        for path in (RUNTIME / "world").rglob("*.py")
        if any(
            imported.startswith("affordance_runtime.surfaces")
            for imported in _imports(path)
        )
    }
    assert violations == {}


def test_agent_and_model_adapter_direction_is_one_way() -> None:
    agent_imports = {
        imported
        for path in (RUNTIME / "agent").rglob("*.py")
        for imported in _imports(path)
    }
    model_imports = {
        imported
        for path in (RUNTIME / "model").rglob("*.py")
        for imported in _imports(path)
    }
    assert not any(
        imported.startswith(
            (
                "affordance_runtime.model",
                "affordance_runtime.surfaces",
            )
        )
        for imported in agent_imports
    )
    assert not any(
        imported.startswith(
            (
                "affordance_runtime.app",
                "affordance_runtime.surfaces",
            )
        )
        for imported in model_imports
    )
