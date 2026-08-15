"""Physical absence and import redlines for the deleted staged Runtime."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "src"
MANIFEST = Path(__file__).with_name("legacy_runtime_paths.txt")


def _deleted_modules() -> frozenset[str]:
    modules: set[str] = set()
    for relative in MANIFEST.read_text(encoding="utf-8").splitlines():
        module = relative.removeprefix("src/").removesuffix(".py").replace("/", ".")
        if module.endswith(".__init__"):
            module = module.removesuffix(".__init__")
        modules.add(module)
    return frozenset(modules)


def test_legacy_runtime_owner_manifest_is_physically_absent() -> None:
    paths = tuple(
        line for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line
    )

    assert len(paths) == len(set(paths))
    assert len(paths) >= 140
    assert all(not (ROOT / relative).exists() for relative in paths)


def test_live_source_cannot_import_a_deleted_runtime_owner() -> None:
    deleted = _deleted_modules()
    violations: list[str] = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported = (node.module or "",)
            else:
                continue
            for name in imported:
                if any(name == module or name.startswith(module + ".") for module in deleted):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")

    assert violations == []


def test_active_tests_and_scripts_cannot_import_a_deleted_runtime_owner() -> None:
    deleted = _deleted_modules()
    violations: list[str] = []
    for root in (ROOT / "tests", ROOT / "scripts"):
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported = (node.module or "",)
                else:
                    continue
                for name in imported:
                    if any(
                        name == module or name.startswith(module + ".")
                        for module in deleted
                    ):
                        violations.append(f"{path.relative_to(ROOT)} imports {name}")

    assert violations == []


def test_legacy_runtime_public_symbols_are_not_reintroduced_at_package_root() -> None:
    root_facade = (SOURCE / "affordance_runtime" / "__init__.py").read_text(encoding="utf-8")
    for symbol in (
        "Coordinator",
        "LegacyRuntimeClient",
        "RunCoordinator",
        "RunRequest",
        "RunResult",
        "RuntimeClient",
        "TaskPlan",
    ):
        assert symbol not in root_facade
