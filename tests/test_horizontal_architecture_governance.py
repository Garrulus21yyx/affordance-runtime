from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src" / "affordance_runtime"
GOVERNANCE_DOC = REPOSITORY_ROOT / "docs" / "architecture-governance-track.md"
GOVERNED_DOCUMENTS = (
    REPOSITORY_ROOT / "docs" / "architecture.md",
    REPOSITORY_ROOT / "docs" / "current-implementation-plan.md",
    REPOSITORY_ROOT / "docs" / "implementation-status.md",
    REPOSITORY_ROOT / "docs" / "responsibility-containment-boundary.md",
)

# Horizontal ratchets freeze current control hotspots. Ceilings may decrease as
# ownership is extracted; increases require an explicit, time-bounded exception.
CONTROL_MODULE_LINE_CEILINGS = {
    "coordinator.py": 3_473,
    "compatibility_planner_algorithms.py": 2_042,
    "task_planning.py": 1_642,
}

CONTROL_METHOD_LINE_CEILINGS = {
    ("coordinator.py", "RunCoordinator", "run_sync"): 2_039,
    ("generalist_planner.py", "GeneralistLMPlanner", "propose"): 222,
    ("intent_compiler.py", "LLMIntentCompiler", "compile"): 253,
    ("task_planning.py", "TaskPlanValidator", "validate"): 239,
}

RUN_COORDINATOR_METHOD_CEILING = 26

NEUTRAL_CONTRACT_MODULES = (
    "approval_contracts.py",
    "planning_contracts.py",
)

EXTRACTED_AUTHORITY_FREE_COLLABORATORS = (
    "active_perception_flow.py",
    "approval_contracts.py",
    "contract_execution_loop.py",
    "perception_session.py",
    "planner_context.py",
    "planner_model_orchestrator.py",
    "planning_contracts.py",
    "recovery_command_dispatcher.py",
    "recovery_handler.py",
    "recovery_trace_projection.py",
    "task_plan_flow.py",
    "task_plan_lifecycle.py",
)

FORBIDDEN_NEUTRAL_DEPENDENCIES = (
    "affordance_runtime.adapters",
    "affordance_runtime.benchmarks",
    "affordance_runtime.cli",
    "affordance_runtime.coordinator",
)

STATE_KERNEL_MUTATIONS = {
    "activate_task_skill",
    "active_subgoal",
    "add_obligation",
    "checkpoint_task_skill_step",
    "complete_grounding_recovery",
    "complete_subgoal",
    "expose_task_skill_step",
    "fall_through_task_skill",
    "install_task_plan",
    "remember_observation",
    "record_action_progress",
    "record_disproved_assumption",
    "record_grounding_reroute",
    "record_planner_proposal",
    "record_progress_guard",
    "record_receipt",
    "record_subgoal_action",
    "replace_task_plan",
    "satisfy_obligation",
    "transition",
    "update_task_skill_bindings",
}

STATE_KERNEL_READS = {
    "check_progress_guard",
    "constraint_summary",
    "current_page_revision",
    "current_revision",
    "excluded_candidates_for",
    "fallback_lineage_for",
}

EXECUTION_COMMIT_MUTATIONS = {
    "install_task_plan",
    "remember_observation",
    "replace_task_plan",
    "transition",
}

ALLOWED_STATE_MUTATION_MODULES = {
    "coordinator.py",
    "runtime.py",
}

LEGACY_NON_ADAPTER_BENCHMARK_IMPORTERS = {
    "cli.py",
    "conformance.py",
    "evolution.py",
    "evolution_replay.py",
}

EXTRACTED_MUTATION_DEBT = {
    ("planner_context.py", "active_subgoal"),
}


def _import_dependencies(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if not isinstance(node, ast.ImportFrom):
        return ()
    if node.level:
        base = "affordance_runtime"
        module = f"{base}.{node.module}" if node.module else base
    else:
        module = node.module or ""
    dependencies = [module] if module else []
    if module == "affordance_runtime":
        dependencies.extend(f"{module}.{alias.name}" for alias in node.names)
    return tuple(dependencies)


def _matches_module(dependency: str, prefix: str) -> bool:
    return dependency == prefix or dependency.startswith(f"{prefix}.")


def _class_method(path: Path, class_name: str, method_name: str) -> ast.AST:
    module = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in owner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name
    )


def test_horizontal_governance_document_is_active_and_non_blocking() -> None:
    assert GOVERNANCE_DOC.exists()
    text = " ".join(GOVERNANCE_DOC.read_text(encoding="utf-8").split()).casefold()

    assert "independent horizontal governance track" in text
    assert "not a unified-rewrite prerequisite" in text
    assert "synchronous change-admission gate" in text
    for path in GOVERNED_DOCUMENTS:
        assert "architecture-governance-track.md" in path.read_text(encoding="utf-8"), path
    for ceiling in CONTROL_MODULE_LINE_CEILINGS.values():
        assert f"{ceiling:,}" in text
    for ceiling in CONTROL_METHOD_LINE_CEILINGS.values():
        assert f"{ceiling:,}" in text
    assert f"{RUN_COORDINATOR_METHOD_CEILING} `runcoordinator` methods" in text


def test_control_module_growth_ratchets_cannot_expand() -> None:
    for filename, ceiling in CONTROL_MODULE_LINE_CEILINGS.items():
        source = (SOURCE_ROOT / filename).read_text(encoding="utf-8")
        assert len(source.splitlines()) <= ceiling, filename


def test_control_method_growth_ratchets_cannot_expand() -> None:
    for (filename, class_name, method_name), ceiling in CONTROL_METHOD_LINE_CEILINGS.items():
        method = _class_method(SOURCE_ROOT / filename, class_name, method_name)
        assert method.end_lineno is not None
        assert method.end_lineno - method.lineno + 1 <= ceiling, (
            filename,
            class_name,
            method_name,
        )

    coordinator = ast.parse((SOURCE_ROOT / "coordinator.py").read_text(encoding="utf-8"))
    run_coordinator = next(
        node
        for node in coordinator.body
        if isinstance(node, ast.ClassDef) and node.name == "RunCoordinator"
    )
    coordinator_methods = [
        node
        for node in run_coordinator.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert len(coordinator_methods) <= RUN_COORDINATOR_METHOD_CEILING
    oversized_new_methods = [
        node.name
        for node in run_coordinator.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name != "run_sync"
        and node.end_lineno is not None
        and node.end_lineno - node.lineno + 1 > 250
    ]
    assert oversized_new_methods == []


def test_neutral_contracts_do_not_depend_on_orchestration_or_adapters() -> None:
    violations: list[tuple[str, str]] = []
    for filename in NEUTRAL_CONTRACT_MODULES:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for dependency in _import_dependencies(node):
                if any(
                    _matches_module(dependency, prefix)
                    for prefix in FORBIDDEN_NEUTRAL_DEPENDENCIES
                ):
                    violations.append((filename, dependency))
    assert violations == []


def test_extracted_collaborators_cannot_reacquire_state_or_trace_authority() -> None:
    violations: list[tuple[str, int, str]] = []
    mutation_debt: set[tuple[str, str]] = set()
    for filename in EXTRACTED_AUTHORITY_FREE_COLLABORATORS:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for dependency in _import_dependencies(node):
                if any(
                    _matches_module(dependency, prefix)
                    for prefix in (
                        "affordance_runtime.coordinator",
                        "affordance_runtime.trace",
                    )
                ):
                    violations.append((filename, node.lineno, dependency))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in STATE_KERNEL_MUTATIONS
            ):
                identity = (filename, node.func.attr)
                if identity in EXTRACTED_MUTATION_DEBT:
                    mutation_debt.add(identity)
                else:
                    violations.append((filename, node.lineno, node.func.attr))
    assert violations == []
    assert mutation_debt == EXTRACTED_MUTATION_DEBT


def test_every_state_kernel_method_is_classified_as_read_or_mutation() -> None:
    tree = ast.parse((SOURCE_ROOT / "state_kernel.py").read_text(encoding="utf-8"))
    state_kernel = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StateKernel"
    )
    public_methods = {
        node.name
        for node in state_kernel.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_methods == STATE_KERNEL_MUTATIONS | STATE_KERNEL_READS


def test_execution_commit_calls_remain_in_runtime_committers() -> None:
    violations: list[tuple[str, int, str]] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        if relative in ALLOWED_STATE_MUTATION_MODULES or relative == "state_kernel.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in EXECUTION_COMMIT_MUTATIONS
            ):
                violations.append((relative, node.lineno, node.func.attr))
    assert violations == []


def test_non_adapter_benchmark_dependency_debt_cannot_spread() -> None:
    importers: set[str] = set()
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        if relative.startswith("benchmarks/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            _matches_module(dependency, "affordance_runtime.benchmarks")
            for node in ast.walk(tree)
            for dependency in _import_dependencies(node)
        ):
            importers.add(relative)
    assert importers == LEGACY_NON_ADAPTER_BENCHMARK_IMPORTERS
