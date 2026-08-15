"""Architecture redlines for the sole adaptive observation selection owner."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "affordance_runtime"


def test_deleted_parallel_selection_paths_remain_physically_absent() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8") for path in ROOT.rglob("*.py")
    )
    forbidden = (
        "_compatibility_observe_all",
        "compatibility_source",
        "_evidence_gated_plan",
        "last_visual_escalation",
        "observe_visual",
        "refresh_observation",
        "async def observe(self, reason",
        "observe_group",
    )
    assert all(item not in production for item in forbidden)


def test_observation_orchestrator_is_the_only_selection_plan_constructor() -> None:
    violations: list[str] = []
    owner = Path("world/observation_orchestrator.py")
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name == "ObservationSelectionPlan" and relative != owner:
                violations.append(f"{relative}:{node.lineno}")
    assert violations == []


def test_surface_port_requires_explicit_observation_offers() -> None:
    surface_port = (ROOT / "world" / "surface_adapter.py").read_text(encoding="utf-8")
    assert "def observation_offers" in surface_port
    assert "SelectedObservationRequest" in surface_port
    assert "SelectedObservationResult" in surface_port
    assert "acquire_group" in surface_port
    assert "getattr" not in surface_port
