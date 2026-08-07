import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_CORE = (
    ROOT / "src" / "affordance_runtime" / "agent",
    ROOT / "src" / "affordance_runtime" / "execution",
    ROOT / "src" / "affordance_runtime" / "memory",
    ROOT / "src" / "affordance_runtime" / "environment_port.py",
    ROOT / "src" / "affordance_runtime" / "routing_policy.py",
)
FORBIDDEN_MODULES = {
    "affordance_runtime.runtime_committer",
    "affordance_runtime.state_kernel",
    "affordance_runtime.recovery_coordinator",
    "affordance_runtime.recovery_phase",
    "affordance_runtime.recovery_protocol",
}
FORBIDDEN_LEGACY_NAMES = {
    "CognitiveMap",
    "ContinuousInteractionManager",
    "FailureLedger",
    "RecoveryCascade",
    "TransitionLedger",
}


def _python_files(path: Path) -> tuple[Path, ...]:
    return (path,) if path.is_file() else tuple(path.rglob("*.py"))


def test_migrated_core_does_not_import_legacy_authority_layers() -> None:
    violations: list[str] = []
    for root in NEW_CORE:
        for path in _python_files(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = {item.name for item in node.names}
                elif isinstance(node, ast.ImportFrom):
                    imported = {node.module or ""}
                else:
                    continue
                forbidden = imported & FORBIDDEN_MODULES
                if forbidden:
                    violations.append(f"{path.relative_to(ROOT)} imports {sorted(forbidden)}")
    assert violations == []


def test_migrated_core_does_not_recreate_forbidden_legacy_classes() -> None:
    definitions: set[str] = set()
    for root in NEW_CORE:
        for path in _python_files(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            definitions.update(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))

    assert definitions.isdisjoint(FORBIDDEN_LEGACY_NAMES)
