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


def test_external_core_imports_are_limited_to_public_session_and_benchmark_lab_owners():
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
    assert runtime_imports == {
        "affordance_runtime.app.public_session",
        "affordance_runtime.benchmarks.lab",
    }


def test_deployment_composition_imports_only_named_core_owners():
    path = EXTERNAL / "backend" / "interaction_shell" / "deployment_app.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("affordance_runtime")
    }
    assert imports == {
        "affordance_runtime.agent.decision_capability",
        "affordance_runtime.agent.observability",
        "affordance_runtime.app.checkpoint",
        "affordance_runtime.app.composition",
        "affordance_runtime.app.interactive_environment",
        "affordance_runtime.app.public_session",
        "affordance_runtime.benchmarks.lab",
        "affordance_runtime.evaluation",
        "affordance_runtime.model.policy",
        "affordance_runtime.surfaces.browser_bundle",
        "affordance_runtime.surfaces.dom.thread_session",
        "affordance_runtime.task",
        "affordance_runtime.world.environment",
        "affordance_runtime.world.orchestrator",
    }
    assert {name for name in imports if "benchmarks" in name} == {"affordance_runtime.benchmarks.lab"}


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


def test_one_console_owns_session_labs_and_live_surface_presentation():
    legacy_console = ROOT / "src" / "affordance_runtime" / "benchmarks" / "console"
    frontend = EXTERNAL / "frontend" / "src"
    shell = (frontend / "components" / "shell-app.tsx").read_text()
    assert not (legacy_console / "server.py").exists()
    assert not (legacy_console / "static" / "index.html").exists()
    assert not (frontend / "app" / "diagnostics" / "page.tsx").exists()
    assert "useShellSession" in shell
    assert "useBenchmarkLabs" in shell
    assert "LiveView" in shell
    assert "INTERACTION FLIGHT DECK" not in shell


def test_authored_frontend_has_no_transport_or_domain_contract_mirror():
    frontend = EXTERNAL / "frontend" / "src"
    authored = tuple(
        path
        for path in frontend.rglob("*")
        if path.suffix in {".ts", ".tsx"}
        and "generated" not in path.parts
        and not path.name.endswith((".test.ts", ".test.tsx"))
    )
    source = "\n".join(path.read_text() for path in authored)
    assert "fetch(" not in source
    assert "fetchEventSource" not in source
    assert "interaction-shell.v2" not in source
    assert "runtime_conflict" not in source
    assert "@/lib/api" not in source
    assert "@/lib/types" not in source
    assert not (frontend / "lib" / "api.ts").exists()
    assert not (frontend / "lib" / "types.ts").exists()
    assert source.count('const BASE_URL = "/shell-api"') == 1
    assert "/sessions/" not in source


def test_v3_has_one_api_command_route_and_no_compatibility_models():
    api_source = (EXTERNAL / "backend" / "interaction_shell" / "api.py").read_text()
    contracts_source = (EXTERNAL / "backend" / "interaction_shell" / "contracts.py").read_text()
    assert api_source.count('"/sessions/{session_id}/commands"') == 1
    assert '"/sessions/{session_id}/tasks"' not in api_source
    assert '"/sessions/{session_id}/commands/' not in api_source
    assert "interaction-shell.v2" not in contracts_source
    assert "OptionalCommand" not in contracts_source
    assert "runtime_conflict" not in contracts_source
    assert "start_new_task" not in contracts_source


def test_surface_and_recovery_truth_have_one_projection_owner_each():
    backend = EXTERNAL / "backend" / "interaction_shell"
    core = (backend / "core_runtime_port.py").read_text()
    steel = (backend / "steel_viewer.py").read_text()
    registry = (backend / "session_registry.py").read_text()
    manager = (backend / "manager.py").read_text()
    assert "def _surface_view(" in core
    assert "ReadOnlySurface" not in steel
    assert "InteractiveSurface" not in steel
    schema = registry.split('_SCHEMA = """', 1)[1]
    assert "checkpoint" not in schema.lower()
    assert "checkpoint_store" not in manager
    assert "load_latest" not in manager


def test_manager_does_not_read_runtime_semantics_and_deployment_uses_one_target_factory():
    backend = EXTERNAL / "backend" / "interaction_shell"
    manager_tree = ast.parse((backend / "manager.py").read_text())
    manager_attributes = {node.attr for node in ast.walk(manager_tree) if isinstance(node, ast.Attribute)}
    assert not manager_attributes & {
        "run_status",
        "control_owner",
        "control_lease_id",
        "surface",
        "last_control_outcome",
    }
    deployment = (backend / "deployment_app.py").read_text()
    assert deployment.count("TargetRuntimeSessionFactory(") == 1
    assert "self._target_factory.open_prepared(" in deployment
    assert "self._target_factory.inspect(" in deployment
    assert "self._target_factory.recover_typed(" in deployment


def test_generated_contracts_are_tool_owned_and_named_sdk_is_present():
    generated = EXTERNAL / "frontend" / "src" / "generated"
    generated_files = tuple(generated.rglob("*.ts"))
    assert generated_files
    assert all("auto-generated by @hey-api/openapi-ts" in path.read_text() for path in generated_files)
    sdk = (generated / "sdk.gen.ts").read_text()
    for operation in (
        "createSession",
        "getSession",
        "submitCommand",
        "subscribeSessionEvents",
        "recoverSession",
    ):
        assert f"export const {operation}" in sdk
