from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[4]
EXTERNAL = ROOT / "external" / "interaction-shell"


def production_python_files():
    return tuple((EXTERNAL / "backend" / "interaction_shell").rglob("*.py"))


def test_external_production_has_no_forbidden_runtime_imports():
    forbidden = {
        "affordance_runtime.agent.core_loop",
        "affordance_runtime.actions.binder",
        "affordance_runtime.execution",
        "affordance_runtime.agent.monitor",
        "affordance_runtime.agent.run_state",
    }
    for path in production_python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module} | {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        assert not any(name == item or name.startswith(item + ".") for name in imports for item in forbidden), path


def test_external_runtime_imports_are_limited_to_the_versioned_public_session_port():
    runtime_imports: set[str] = set()
    for path in production_python_files():
        if path.name == "deployment_app.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        runtime_imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("affordance_runtime")
        )
        runtime_imports.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name.startswith("affordance_runtime")
        )
    assert runtime_imports == {"affordance_runtime.app.public_session"}


def test_deployment_composition_imports_only_named_core_owners():
    path = EXTERNAL / "backend" / "interaction_shell" / "deployment_app.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("affordance_runtime")
    }
    assert imports == {
        "affordance_runtime.agent.decision_capability",
            "affordance_runtime.agent.observability",
            "affordance_runtime.app.checkpoint",
            "affordance_runtime.app.composition",
        "affordance_runtime.app.public_session",
        "affordance_runtime.evaluation",
        "affordance_runtime.model.policy",
        "affordance_runtime.surfaces.browsergym",
        "affordance_runtime.task",
        "affordance_runtime.world.orchestrator",
    }
    assert not any("benchmarks" in name for name in imports)


def test_external_scope_contains_no_platform_or_custom_media_implementation():
    source_roots = (EXTERNAL / "backend" / "interaction_shell", EXTERNAL / "frontend" / "src")
    relative = {
        path.relative_to(EXTERNAL).as_posix().lower() for source_root in source_roots for path in source_root.rglob("*")
    }
    assert not any("android" in path or "desktop" in path for path in relative)
    production = "\n".join(path.read_text(errors="ignore") for path in production_python_files())
    forbidden_symbols = ("screenshot_poll", "video_encoder", "mouse_protocol", "keyboard_protocol")
    assert not any(symbol in production for symbol in forbidden_symbols)


def test_core_paths_are_outside_external_product_scope():
    assert not (EXTERNAL / "src" / "affordance_runtime").exists()
    assert not (EXTERNAL / "docs" / "architecture.md").exists()
    assert not (EXTERNAL / "docs" / "benchmark.md").exists()
