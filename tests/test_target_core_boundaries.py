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
)
FORBIDDEN = {
    "affordance_runtime.contracts",
    "affordance_runtime.environment_port",
    "affordance_runtime.runtime_committer",
    "affordance_runtime.state_kernel",
    "affordance_runtime.task.legacy_projection",
}


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
