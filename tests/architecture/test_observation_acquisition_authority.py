from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"


def _constructor_owners() -> list[tuple[str, str]]:
    owners: list[tuple[str, str]] = []
    for path in sorted(RUNTIME.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for parent in ast.walk(tree):
            if not isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ObservationAcquisition"
                for node in ast.walk(parent)
            ):
                owners.append((str(path.relative_to(ROOT)), parent.name))
    return owners


def test_terminal_acquisition_has_one_product_owner() -> None:
    owners = _constructor_owners()
    assert owners
    assert {path for path, _function in owners} == {
        "src/affordance_runtime/world/orchestrator.py",
    }
    source = (RUNTIME / "world" / "orchestrator.py").read_text(encoding="utf-8")
    assert "class ObservationAcquisitionCoordinator:" in source
    assert "class UnifiedWorldEnvironment:" in source


def test_browsergym_is_only_a_grouped_backend() -> None:
    package_sources = tuple(
        path.read_text(encoding="utf-8")
        for path in (RUNTIME / "surfaces" / "browsergym").rglob("*.py")
    )
    for forbidden in (
        "ObservationAcquisition(",
        "ObservationOrchestrator",
        "WorldFusion",
        "AcquisitionStage",
        "    AcquisitionStatus,",
    ):
        assert all(forbidden not in source for source in package_sources)
    source = (RUNTIME / "surfaces" / "browsergym" / "environment.py").read_text(
        encoding="utf-8"
    )
    assert "async def acquire_group(" in source
    assert "SelectedObservationResult" in source


def test_scripted_fixture_forwards_one_original_source_without_fusing() -> None:
    source = (RUNTIME / "benchmarks" / "support" / "scripted_environment.py").read_text(
        encoding="utf-8"
    )
    assert "WorldFusion" not in source
    assert "SurfaceObservation(" not in source
    assert "requires exactly one original source observation" in source


def test_deleted_acquisition_owners_and_static_fixtures_are_unreachable() -> None:
    assert not (RUNTIME / "surfaces" / "browsergym" / "acquisition.py").exists()
    assert not (RUNTIME / "benchmarks" / "support" / "static_environment.py").exists()
    assert not (ROOT / "tests" / "support" / "agent" / "static_environment.py").exists()
    violations = []
    deleted_names = ("Static" + "Environment", "BrowserGym" + "Environment")
    for base in (RUNTIME, ROOT / "tests"):
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if path == Path(__file__):
                continue
            if any(name in text for name in deleted_names):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_product_has_no_planless_successful_acquisition_constructor() -> None:
    acquisition = ast.parse(
        (RUNTIME / "world" / "acquisition.py").read_text(encoding="utf-8")
    )
    definition = next(
        node
        for node in acquisition.body
        if isinstance(node, ast.ClassDef) and node.name == "ObservationAcquisition"
    )
    fields = {
        node.target.id
        for node in definition.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert fields == {
        "acquisition_id",
        "origin",
        "request",
        "stage",
        "selection_plan",
        "activations",
        "fusion_outcome",
        "status",
        "reason",
    }
