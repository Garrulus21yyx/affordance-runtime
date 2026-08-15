from __future__ import annotations

import ast
from pathlib import Path

from setuptools.discovery import PackageFinder

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
RUNTIME = ROOT / "src" / "affordance_runtime"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    return imports


def test_executable_tests_are_classified_by_kind_and_owner() -> None:
    assert list(TESTS.glob("test_*.py")) == []
    for category in ("unit", "integration", "conformance", "benchmarks"):
        category_root = TESTS / category
        assert category_root.is_dir()
        assert any(category_root.rglob("test_*.py"))
        assert all(path.parent != category_root for path in category_root.glob("test_*.py"))


def test_former_production_testing_package_is_absent_from_source_and_package_discovery() -> None:
    assert not (RUNTIME / "testing").exists()
    assert not (ROOT / "build" / "lib" / "affordance_runtime" / "testing").exists()
    packages = set(PackageFinder.find(str(ROOT / "src")))
    assert "affordance_runtime.testing" not in packages
    assert not any(name.startswith("affordance_runtime.testing.") for name in packages)


def test_production_and_benchmark_code_cannot_import_test_support() -> None:
    violations = {
        str(path.relative_to(ROOT)): sorted(
            imported
            for imported in _imports(path)
            if imported == "tests" or imported.startswith("tests.")
        )
        for path in RUNTIME.rglob("*.py")
        if any(
            imported == "tests" or imported.startswith("tests.")
            for imported in _imports(path)
        )
    }
    assert violations == {}


def test_test_support_is_consumed_only_by_executable_tests() -> None:
    allowed_roots = tuple((TESTS / category).resolve() for category in (
        "unit", "integration", "conformance", "benchmarks",
    ))
    violations: list[str] = []
    for path in ROOT.rglob("*.py"):
        imports_support = any(
            imported == "tests.support" or imported.startswith("tests.support.")
            for imported in _imports(path)
        )
        if not imports_support:
            continue
        resolved = path.resolve()
        if not path.name.startswith("test_") or not any(
            resolved.is_relative_to(owner) for owner in allowed_roots
        ):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_no_implicit_root_test_module_imports_or_test_path_injection_remain() -> None:
    forbidden: dict[str, list[str]] = {}
    for path in TESTS.rglob("*.py"):
        imports = sorted(
            imported for imported in _imports(path)
            if imported.startswith("test_") or imported.startswith("tests.test_")
        )
        if imports:
            forbidden[str(path.relative_to(ROOT))] = imports
    assert forbidden == {}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'pythonpath = ["src", "."]' in pyproject


def test_benchmark_fixture_owner_is_private_to_benchmarks() -> None:
    owners = {
        str(path.relative_to(ROOT))
        for path in RUNTIME.rglob("*.py")
        if any(
            imported == "affordance_runtime.benchmarks.support"
            or imported.startswith("affordance_runtime.benchmarks.support.")
            for imported in _imports(path)
        )
    }
    assert owners
    assert all(path.startswith("src/affordance_runtime/benchmarks/") for path in owners)
