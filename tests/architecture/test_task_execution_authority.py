from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"


def _python_sources() -> tuple[Path, ...]:
    return tuple(sorted(RUNTIME.rglob("*.py")))


def _class_owners(name: str) -> tuple[str, ...]:
    owners = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(node, ast.ClassDef) and node.name == name for node in ast.walk(tree)):
            owners.append(path.relative_to(RUNTIME).as_posix())
    return tuple(owners)


def test_task_plan_has_exactly_one_production_owner() -> None:
    assert _class_owners("TaskPlan") == ("task_plan_contracts.py",)
    assert _class_owners("TaskProgram") == ()
    assert _class_owners("Milestone") == ()
    assert not (RUNTIME / "task" / "task_program.py").exists()


def test_agent_loop_and_model_projection_use_the_canonical_task_plan() -> None:
    for relative in ("agent/state.py", "model_boundary/projection.py"):
        source = (RUNTIME / relative).read_text(encoding="utf-8")
        assert "from affordance_runtime.task_plan_contracts import TaskPlan" in source
        assert "from affordance_runtime.task.planning_contracts import" not in source or "TaskPlan" not in next(
            line
            for line in source.splitlines()
            if line.startswith("from affordance_runtime.task.planning_contracts import")
        )


def test_agent_loop_has_one_step_execution_slot() -> None:
    source = (RUNTIME / "agent" / "state.py").read_text(encoding="utf-8")
    assert "active_step_execution: StepExecutionState | None" in source
    for duplicate in (
        "active_set_objective",
        "active_objective_sequence",
        "active_aggregate_objective",
    ):
        assert duplicate not in "\n".join(
            path.read_text(encoding="utf-8") for path in _python_sources()
        )


def test_temporary_model_semantic_producers_cannot_spread() -> None:
    """Ratchet the known ingress debt until canonical-plan cutover deletes it."""

    markers = (
        "EstablishSetObjective",
        "EstablishObjectiveSequence",
        "EstablishAggregateObjective",
        "establish_set_objective",
        "establish_objective_sequence",
        "establish_aggregate_objective",
    )
    producers = {
        path.relative_to(RUNTIME).as_posix()
        for path in (RUNTIME / "model_policy").rglob("*.py")
        if any(marker in path.read_text(encoding="utf-8") for marker in markers)
    }
    assert producers == {
        "model_policy/grounded_tool_catalog.py",
        "model_policy/grounded_tool_port_bridge.py",
        "model_policy/spec.py",
    }


def test_normative_architecture_links_the_authority_map() -> None:
    assert "task-execution-authority-map.md" in (ROOT / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "Task Execution Authority Map" in (
        ROOT / "docs" / "architecture-governance-track.md"
    ).read_text(encoding="utf-8")
    authoritative = (
        ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-08-05-task-contract-centered-runtime-authoritative-architecture.md"
    ).read_text(encoding="utf-8")
    assert "TaskSpecAuthority -> TaskPlanAuthority -> TaskPlan<StepSpec>" in authoritative
    assert "task-execution-authority-map.md" in authoritative
