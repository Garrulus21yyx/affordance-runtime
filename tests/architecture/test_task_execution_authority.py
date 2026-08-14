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
    objective_spec = (RUNTIME / "model_policy" / "objective_spec.py").read_text(encoding="utf-8")
    predicate = (RUNTIME / "task" / "predicate_transport.py").read_text(encoding="utf-8")

    assert "ResolvedModelDecision" in adapters
    assert "if isinstance(outcome, ResolvedModelDecision)" in policy
    assert "ModelDecisionResponse" not in production
    assert "parse_agent_decision" not in policy
    assert "local_objective_to_payload" not in spec
    assert "LocalObjective" not in spec
    assert "LocalObjectiveProposal" in objective_spec
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
    assert "EstablishLocalObjective" not in source
    assert "LocalObjective" not in source

    catalog = (RUNTIME / "model_policy" / "grounded_tool_catalog.py").read_text(encoding="utf-8")
    assert "GroundedToolPhase.OBJECTIVE_PROPOSAL" in catalog
    assert "GroundedToolPhase.ACTION_SELECTION" in catalog
    assert "propose_local_objective" in catalog
    assert "establish_local_objective" not in catalog


def test_grounded_action_candidates_have_one_model_boundary_projection_chain() -> None:
    builder = (RUNTIME / "model_boundary" / "context_builder.py").read_text(encoding="utf-8")
    catalog = (RUNTIME / "model_policy" / "grounded_tool_catalog.py").read_text(encoding="utf-8")
    binder = (RUNTIME / "model_policy" / "grounded_policy_context.py").read_text(encoding="utf-8")

    assert "close_action_candidates(actions, grounding.index, context_id=identity.context_id)" in builder
    assert "GroundedToolCompiler().compile(" in catalog
    assert "context.grounding.target_refs" not in catalog
    assert 'public["actions"]' not in binder
    assert '"groups": tuple(' not in binder and '"shared_target"' not in binder
    assert "selection_key" not in catalog and "_verb_schema" not in catalog
    assert '"screen_coordinate"' not in binder and '"x"' not in binder and '"y"' not in binder


def test_latest_transition_has_one_root_owned_projection_chain() -> None:
    transition = (RUNTIME / "agent" / "control_transition.py").read_text(encoding="utf-8")
    reducer = (RUNTIME / "agent" / "control_reducer.py").read_text(encoding="utf-8")
    builder = (RUNTIME / "model_boundary" / "context_builder.py").read_text(encoding="utf-8")
    projection = (
        RUNTIME / "model_boundary" / "transition_digest_projection.py"
    ).read_text(encoding="utf-8")

    assert "class ControlTransition:" in transition
    assert "before_task_evaluation" in transition
    assert "project_latest_transition(" in builder
    assert "state.recent_control_transitions" in builder
    assert "values[index] = updated" in reducer
    assert "continued_root_ids" in reducer
    assert "class RuntimeTransitionDigest" not in "\n".join(
        path.read_text(encoding="utf-8") for path in RUNTIME.rglob("*.py")
    )
    assert "ModelPort" not in projection and "provider" not in projection


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
