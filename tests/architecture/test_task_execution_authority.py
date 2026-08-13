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


def test_workflow_task_plan_projection_does_not_enter_agent_loop() -> None:
    projection = (RUNTIME / "model_boundary" / "projection.py").read_text(encoding="utf-8")
    assert "from affordance_runtime.task_plan_contracts import TaskPlan" in projection
    for relative in ("agent/loop.py", "agent/state.py", "agent/episode_runner.py"):
        source = (RUNTIME / relative).read_text(encoding="utf-8")
        assert "task_plan_contracts" not in source
        assert "TaskPlan" not in source


def test_agent_loop_uses_rolling_local_objective_not_workflow_plan_state() -> None:
    source = "\n".join(
        (RUNTIME / relative).read_text(encoding="utf-8")
        for relative in ("agent/loop.py", "agent/state.py", "agent/episode_runner.py")
    )
    for displaced in (
        "AdmittedTaskSpec",
        "task_plan_preparer",
        "task_spec_identity",
        "active_step_execution",
        "semantic_control_required",
        "install_plan(",
    ):
        assert displaced not in source
    for duplicate in (
        "active_set_objective",
        "active_objective_sequence",
        "active_aggregate_objective",
    ):
        assert duplicate not in "\n".join(
            path.read_text(encoding="utf-8") for path in _python_sources()
        )
    production = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources())
    assert "AgentSetControlView" not in production
    assert "set_control" not in production
    assert not (RUNTIME / "model_policy" / "set_objective_catalog.py").exists()
    assert not (RUNTIME / "model_policy" / "execution_control_catalog.py").exists()
    assert not (RUNTIME / "task" / "planning_contracts.py").exists()
    state_source = (RUNTIME / "agent" / "state.py").read_text(encoding="utf-8")
    assert state_source.count("local_objective_state:") == 1
    assert "refresh_local_objective(" in state_source


def test_target_loop_has_no_pre_observation_target_or_frontier_authority() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources())
    task_contract = (RUNTIME / "task" / "contracts.py").read_text(encoding="utf-8")
    loop = (RUNTIME / "agent" / "loop.py").read_text(encoding="utf-8")

    assert "target_id:" not in task_contract.split("class TaskGoal", 1)[1].split("class ", 1)[0]
    assert "require_initial_observation" in loop
    assert loop.index("require_initial_observation") < loop.index("AgentLoopState(")
    for displaced in (
        "AgentDecisionPackage",
        "TaskFrontier",
        "RequirementHypothesis",
        "objective_operation",
        "active_objective",
        "verified_task_state",
    ):
        assert displaced not in production
    for removed in (
        "agent/frontier_control.py",
        "model_policy/requirement_proposer.py",
        "task/frontier.py",
        "task/frontier_contracts.py",
        "task/hypothesis_contracts.py",
        "task/hypothesis_runtime.py",
    ):
        assert not (RUNTIME / removed).exists()


def test_model_decision_is_parsed_once_and_objectives_have_no_reverse_wire_projection() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources())
    policy = (RUNTIME / "model_policy" / "policy.py").read_text(encoding="utf-8")
    adapters = "\n".join(
        (RUNTIME / "model_policy" / relative).read_text(encoding="utf-8")
        for relative in ("model_port_bridge.py", "tool_port_bridge.py", "grounded_tool_port_bridge.py")
    )
    spec = (RUNTIME / "model_policy" / "spec.py").read_text(encoding="utf-8")
    predicate = (RUNTIME / "task" / "predicate_transport.py").read_text(encoding="utf-8")

    assert "ResolvedModelDecision" in adapters
    assert "if isinstance(outcome, ResolvedModelDecision)" in policy
    assert "ModelDecisionResponse" not in production
    assert "parse_agent_decision" not in policy
    assert "local_objective_to_payload" not in spec
    assert "predicate_to_transport" not in predicate


def test_model_policy_has_no_task_semantic_producers() -> None:

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
    assert producers == set()


def test_agent_decisions_cannot_install_task_execution_semantics() -> None:
    source = (RUNTIME / "agent" / "decisions.py").read_text(encoding="utf-8")
    assert "EstablishSetObjective" not in source
    assert "EstablishObjectiveSequence" not in source
    assert "EstablishAggregateObjective" not in source


def test_normative_architecture_links_the_authority_map() -> None:
    assert "task-execution-authority-map.md" in (ROOT / "docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "Task Execution Authority Map" in (
        ROOT / "docs" / "architecture-governance-track.md"
    ).read_text(encoding="utf-8")
    authoritative = (ROOT / "docs" / "task-execution-authority-map.md").read_text(encoding="utf-8")
    assert "TaskGoal boundary" in authoritative
    assert "No exact GUI target identity is required before `WorldObservation`" in authoritative
