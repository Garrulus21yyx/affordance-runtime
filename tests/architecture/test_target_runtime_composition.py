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
    assert "affordance_runtime.app.composition" in _imports(runner)


def test_target_composition_owner_has_no_benchmark_dependency() -> None:
    composition = RUNTIME / "app" / "composition.py"

    assert not any(
        name.startswith("affordance_runtime.benchmarks")
        for name in _imports(composition)
    )


def test_target_runtime_owns_lifecycle_without_legacy_coordinator_or_runner() -> None:
    runtime = RUNTIME / "app" / "runtime.py"
    imports = _imports(runtime)

    assert "affordance_runtime.agent.loop" in imports
    assert "affordance_runtime.agent.episode_runner" not in imports
    assert "affordance_runtime.coordinator" not in imports
    assert "affordance_runtime.runtime_client" not in imports
    assert "affordance_runtime.composition" not in imports


def test_product_action_evaluator_has_no_benchmark_dependency() -> None:
    evaluator = RUNTIME / "evaluation" / "action_evaluator.py"

    assert not any(
        name.startswith("affordance_runtime.benchmarks")
        for name in _imports(evaluator)
    )


def test_http_fact_surface_is_product_owned_and_has_no_fixture_or_benchmark_oracle() -> None:
    surface = RUNTIME / "surfaces" / "http_json"
    imports = {
        imported
        for path in surface.rglob("*.py")
        for imported in _imports(path)
    }

    assert not any(name.startswith("affordance_runtime.benchmarks") for name in imports)
    assert "affordance_runtime.fixtures" not in imports
    assert "affordance_runtime.reference_scenarios" not in imports
    assert "affordance_runtime.benchmarks.target_loop.reference_readiness" not in imports


def test_dom_document_projection_is_product_owned_and_has_no_reference_oracle() -> None:
    surface = RUNTIME / "surfaces" / "dom"
    imports = {
        imported
        for path in surface.rglob("*.py")
        for imported in _imports(path)
    }

    assert not any(name.startswith("affordance_runtime.benchmarks") for name in imports)
    assert "affordance_runtime.fixtures" not in imports
    assert "affordance_runtime.reference_scenarios" not in imports
    assert "affordance_runtime.benchmarks.target_loop.reference_readiness" not in imports


def test_target_product_entry_has_no_legacy_or_benchmark_dependency() -> None:
    for relative in (
        "app/runtime.py",
        "app/composition.py",
        "app/cli.py",
        "surfaces/dom/thread_session.py",
    ):
        imports = _imports(RUNTIME / relative)
        assert not any(
            name.startswith("affordance_runtime.benchmarks")
            for name in imports
        )
        assert "affordance_runtime.coordinator" not in imports
        assert "affordance_runtime.composition" not in imports
        assert "affordance_runtime.runtime_client" not in imports


def test_reference_cutover_readiness_cannot_enter_runtime_or_model_policy() -> None:
    forbidden_import = "affordance_runtime.benchmarks.target_loop.reference_readiness"
    violations = []
    for directory in (RUNTIME / "agent", RUNTIME / "model" / "policy", RUNTIME / "world"):
        for path in sorted(directory.rglob("*.py")):
            if forbidden_import in _imports(path):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_pass_through_target_wrappers_are_physically_deleted() -> None:
    assert not (RUNTIME / "target_runtime_client.py").exists()
    assert not (RUNTIME / "agent" / "episode_runner.py").exists()
    assert not (RUNTIME / "agent" / "runtime.py").exists()
    assert not (RUNTIME / "agent" / "composition.py").exists()
    assert not (RUNTIME / "target_cli.py").exists()
    assert not (RUNTIME / "target_composition.py").exists()
    facade = (RUNTIME / "agent" / "__init__.py").read_text(encoding="utf-8")
    root = (RUNTIME / "__init__.py").read_text(encoding="utf-8")
    assert "AgentEpisodeRunner" not in facade
    assert "TargetRuntimeClient" not in root


def test_root_public_api_exports_only_target_lifecycle_contracts() -> None:
    root = (RUNTIME / "__init__.py").read_text(encoding="utf-8")
    for legacy in (
        "ActionContract",
        "LegacyRuntimeClient",
        "PlannerPort",
        "PlanningRequest",
        "RunRequest",
        "RunResult",
        "RuntimeClient",
        "UnifiedAffordance",
        "UnifiedObservation",
    ):
        assert f'"{legacy}"' not in root
    for target in (
        "AgentRunSession",
        "NaturalLanguageTaskRequest",
        "TargetRuntime",
        "TargetRuntimeRunOutcome",
        "TaskBoundary",
        "TaskGoal",
        "compose_target_runtime_from_environment",
    ):
        assert f'"{target}"' in root
    assert '"compose_target_runtime"' not in root


def test_installed_product_and_benchmark_commands_have_separate_entrypoints() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'affordance-runtime = "affordance_runtime.app.cli:main"' in project
    assert 'affordance-runtime-benchmark = "affordance_runtime.benchmarks.cli:main"' in project
    assert (RUNTIME / "__main__.py").read_text(encoding="utf-8").strip() == (
        "from affordance_runtime.app.cli import main\n\nraise SystemExit(main())"
    )
    product_cli = (RUNTIME / "app" / "cli.py").read_text(encoding="utf-8")
    benchmark_cli = (RUNTIME / "benchmarks" / "cli.py").read_text(encoding="utf-8")
    assert 'subcommands.add_parser(\n        "run"' in product_cli
    assert "target-run" not in product_cli
    assert 'subcommands.add_parser("run"' not in benchmark_cli


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
    composition = RUNTIME / "app" / "composition.py"
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


def test_target_loop_and_session_have_one_physical_definition_each() -> None:
    definitions: dict[str, list[str]] = {"AgentLoop": [], "AgentRunSession": []}
    for path in sorted(RUNTIME.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in definitions:
                definitions[node.name].append(str(path.relative_to(ROOT)))
    assert definitions == {
        "AgentLoop": ["src/affordance_runtime/agent/loop.py"],
        "AgentRunSession": ["src/affordance_runtime/agent/session.py"],
    }


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
        "affordance_runtime.actions.binder",
    })


def test_browsergym_case_policy_owns_intake_and_surface_is_task_list_agnostic() -> None:
    case_policy = RUNTIME / "benchmarks" / "external_smoke" / "case_environment.py"
    surface = RUNTIME / "surfaces" / "browsergym" / "environment.py"
    source = case_policy.read_text(encoding="utf-8")
    surface_source = surface.read_text(encoding="utf-8")

    assert "ThinTaskIntake().compile(" in source
    assert "NaturalLanguageTaskRequest(" in source
    assert "TaskBoundary(" in source
    assert "REVIEWED_TASK_IDS" not in surface_source
    assert "ThinTaskIntake" not in surface_source
    assert "ExternalVerifier" not in surface_source


def test_browsergym_reusable_implementation_has_one_surface_owner() -> None:
    surface = RUNTIME / "surfaces" / "browsergym"
    benchmark = RUNTIME / "benchmarks" / "external_smoke"
    assert surface.is_dir()
    assert not tuple(benchmark.glob("browsergym_*.py"))
    for path in surface.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "affordance_runtime.benchmarks" not in source, path
    benchmark_environment = (benchmark / "case_environment.py").read_text(encoding="utf-8")
    assert "BrowserGymCaseEnvironment" in benchmark_environment
    assert "open_browsergym_case" in benchmark_environment
    benchmark_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in benchmark.glob("*.py")
    )
    for implementation_owner in (
        "class BrowserGymEnvironment",
        "class ThreadBoundBrowserGym",
        "class BrowserGymBindingStore",
        "def project_browsergym_observation",
        "def browsergym_action",
    ):
        assert implementation_owner not in benchmark_sources
