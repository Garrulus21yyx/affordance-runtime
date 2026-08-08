import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "affordance_runtime"
TARGET_CORE = (
    PACKAGE / "agent",
    PACKAGE / "task" / "contracts.py",
    PACKAGE / "task" / "planning_contracts.py",
    PACKAGE / "world",
    PACKAGE / "execution" / "contracts.py",
    PACKAGE / "evaluation",
    PACKAGE / "risk",
    PACKAGE / "confirmation",
    PACKAGE / "model_boundary",
)
SIZE_GATED = TARGET_CORE + (
    PACKAGE / "surfaces" / "visual",
    PACKAGE / "surfaces" / "wot",
)
FORBIDDEN = {
    "affordance_runtime.contracts",
    "affordance_runtime.environment_port",
    "affordance_runtime.runtime_committer",
    "affordance_runtime.state_kernel",
    "affordance_runtime.task.legacy_projection",
}
POLICY_FORBIDDEN_PREFIXES = (
    "affordance_runtime.executors",
    "affordance_runtime.grounding",
    "affordance_runtime.surfaces",
)


def _files(root: Path) -> tuple[Path, ...]:
    return (root,) if root.is_file() else tuple(root.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.add(node.module or "")
    return result


def test_target_core_does_not_import_legacy_contract_or_transaction_owners() -> None:
    violations = []
    for root in TARGET_CORE:
        for path in _files(root):
            imported = _imports(path)
            matches = imported.intersection(FORBIDDEN)
            if matches:
                violations.append(f"{path.relative_to(ROOT)}: {sorted(matches)}")
    assert violations == []


def test_agent_and_surface_dependency_directions_are_one_way() -> None:
    agent_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "agent")))
    surface_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "surfaces")))

    assert "affordance_runtime.browser_session" not in agent_imports
    assert not any(name.startswith("affordance_runtime.surfaces") for name in agent_imports)
    assert "affordance_runtime.agent.loop" not in surface_imports


def test_risk_and_confirmation_keep_surface_private_dependencies_out() -> None:
    risk_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "risk")))
    confirmation_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "confirmation")))

    assert not any(name.startswith("affordance_runtime.surfaces") for name in risk_imports)
    assert not any(name.startswith("affordance_runtime.surfaces") for name in confirmation_imports)
    assert "affordance_runtime.browser_session" not in confirmation_imports


def test_policy_and_evaluators_do_not_import_concrete_execution_owners() -> None:
    policy_imports = _imports(PACKAGE / "agent" / "policy.py")
    policy_text = (PACKAGE / "agent" / "policy.py").read_text(encoding="utf-8")

    assert not any(name.startswith(POLICY_FORBIDDEN_PREFIXES) for name in policy_imports)
    assert "affordance_runtime.world.binder" not in policy_imports
    assert "affordance_runtime.world.orchestrator" not in policy_imports
    assert "ActionSpace" not in policy_text.replace("AgentActionSpaceView", "")
    assert "Turn" not in policy_text.replace("AgentTurnView", "")


def test_model_boundary_has_no_concrete_surface_execution_or_fixture_dependencies() -> None:
    imports = set().union(*(_imports(path) for path in _files(PACKAGE / "model_boundary")))

    assert not any(name.startswith("affordance_runtime.surfaces") for name in imports)
    assert not any(name.startswith("affordance_runtime.executors") for name in imports)
    assert not any(name.startswith("affordance_runtime.benchmarks") for name in imports)
    assert "affordance_runtime.world.binder" not in imports


def test_target_core_does_not_import_benchmark_modules_or_behavioral_recorder() -> None:
    imports = set()
    agent_text = ""
    for root in TARGET_CORE:
        for path in _files(root):
            imports.update(_imports(path))
            if path.parent.name == "agent":
                agent_text += path.read_text(encoding="utf-8")

    assert not any(name.startswith("affordance_runtime.benchmarks") for name in imports)
    assert "TurnRecorder" not in agent_text


def test_target_core_size_review_gates_remain_closed() -> None:
    violations = []
    for root in SIZE_GATED:
        for path in _files(root):
            text = path.read_text(encoding="utf-8")
            line_count = len(text.splitlines())
            if line_count > 350:
                violations.append(f"{path.relative_to(ROOT)} has {line_count} lines")
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    function_lines = (node.end_lineno or node.lineno) - node.lineno + 1
                    if function_lines > 80:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} {node.name} has {function_lines} lines"
                        )
    assert violations == []
