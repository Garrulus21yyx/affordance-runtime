from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "affordance_runtime"


def test_inventory_authority_dependency_is_one_way_and_task_agnostic() -> None:
    world_owner = (ROOT / "world" / "semantic_inventory.py").read_text(encoding="utf-8")
    context_builder = (ROOT / "agent" / "context" / "context_builder.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "TaskGoal",
        "ActionSpace",
        "AgentLoop",
        "browsergym",
        "benchmarks",
    ):
        assert forbidden not in world_owner
    assert "SemanticInventoryStatus" not in context_builder
    assert "recognized_target_count" not in context_builder


def test_browsergym_diagnostics_and_projection_define_no_second_role_taxonomy() -> None:
    diagnostics = (
        ROOT / "surfaces" / "browsergym" / "diagnostics.py"
    ).read_text(encoding="utf-8")
    coverage_probe = (
        ROOT / "benchmarks" / "external_breadth" / "coverage_probe.py"
    ).read_text(encoding="utf-8")
    projection = (
        ROOT / "surfaces" / "browsergym" / "projection.py"
    ).read_text(encoding="utf-8")
    environment = (
        ROOT / "surfaces" / "browsergym" / "environment.py"
    ).read_text(encoding="utf-8")

    assert "_INTERACTIVE_ROLES" not in diagnostics
    assert "_INTERACTIVE_ROLES" not in coverage_probe
    assert "axtree_object" not in diagnostics
    assert "browsergym_role_spec" not in projection
    assert "diagnostic_snapshot(raw)" not in environment
