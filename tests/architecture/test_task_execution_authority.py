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


def test_workflow_task_plan_owner_is_physically_absent() -> None:
    assert _class_owners("TaskPlan") == ()
    assert _class_owners("TaskProgram") == ()
    assert _class_owners("Milestone") == ()
    assert not (RUNTIME / "task_plan_contracts.py").exists()
    assert not (RUNTIME / "task" / "task_program.py").exists()


def test_workflow_task_plan_projection_does_not_enter_agent_loop() -> None:
    projection = (RUNTIME / "agent" / "context" / "projection.py").read_text(encoding="utf-8")
    assert "task_plan_contracts" not in projection
    assert "project_plan" not in projection
    for relative in ("agent/core_loop.py", "agent/run_state.py"):
        source = (RUNTIME / relative).read_text(encoding="utf-8")
        assert "task_plan_contracts" not in source
        assert "TaskPlan" not in source


def test_agent_loop_has_no_staged_objective_or_workflow_plan_state() -> None:
    source = "\n".join(
        (RUNTIME / relative).read_text(encoding="utf-8")
        for relative in ("agent/core_loop.py", "agent/run_state.py")
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
        "local_objective_state",
        "scope_enumerator",
        "objective_proposer",
    ):
        assert duplicate not in "\n".join(
            path.read_text(encoding="utf-8") for path in _python_sources()
        )
    production = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources())
    assert "AgentSetControlView" not in production
    assert "set_control" not in production
    assert not (RUNTIME / "model" / "policy" / "set_objective_catalog.py").exists()
    assert not (RUNTIME / "model" / "policy" / "execution_control_catalog.py").exists()
    assert not (RUNTIME / "task" / "planning_contracts.py").exists()
    for removed in (
        "agent/local_objective_proposal.py",
        "agent/local_objective_evidence.py",
        "model_policy/objective_policy.py",
        "model_policy/objective_spec.py",
        "task/local_objective.py",
        "task/set_objective.py",
        "task/set_objective_state.py",
        "task/objective_sequence.py",
        "task/aggregate_objective.py",
        "task/scope_enumerator.py",
        "task/selector_resolution.py",
    ):
        assert not (RUNTIME / removed).exists()


def test_target_loop_has_no_pre_observation_target_or_frontier_authority() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources())
    task_contract = (RUNTIME / "task" / "contracts.py").read_text(encoding="utf-8")
    loop = (RUNTIME / "agent" / "core_loop.py").read_text(encoding="utf-8")

    assert "target_id:" not in task_contract.split("class TaskGoal", 1)[1].split("class ", 1)[0]
    assert "environment.reset(task)" in loop
    assert loop.index("environment.reset(task)") < loop.index("RunState(")
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


def test_model_decision_is_parsed_once_and_has_no_staged_objective_transport() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources())
    policy = (RUNTIME / "model" / "policy" / "policy.py").read_text(encoding="utf-8")
    adapters = (RUNTIME / "model" / "policy" / "grounded_tool_port_bridge.py").read_text(
        encoding="utf-8"
    )
    assert "ResolvedModelDecision" in adapters
    assert "if isinstance(outcome, ResolvedModelDecision)" in policy
    assert "ModelDecisionResponse" not in production
    assert "parse_agent_decision" not in policy
    assert not (RUNTIME / "model" / "policy" / "spec.py").exists()
    assert not (RUNTIME / "model" / "policy" / "parser.py").exists()
    assert not (RUNTIME / "model" / "policy" / "serialization.py").exists()
    assert "LocalObjective" not in production
    assert "OBJECTIVE_PROPOSAL" not in production


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
        for path in (RUNTIME / "model" / "policy").rglob("*.py")
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

    catalog = (RUNTIME / "model" / "policy" / "grounded_tool_catalog.py").read_text(encoding="utf-8")
    assert "GroundedToolPhase.ACTION_SELECTION" in catalog
    assert "OBJECTIVE_PROPOSAL" not in catalog
    assert "propose_local_objective" not in catalog
    assert "establish_local_objective" not in catalog


def test_grounded_action_candidates_have_one_model_boundary_projection_chain() -> None:
    builder = (RUNTIME / "agent" / "context" / "context_builder.py").read_text(encoding="utf-8")
    catalog = (RUNTIME / "model" / "policy" / "grounded_tool_catalog.py").read_text(encoding="utf-8")
    binder = (RUNTIME / "model" / "policy" / "grounded_policy_context.py").read_text(encoding="utf-8")

    assert "close_action_candidates(actions, grounding.index, context_id=identity.context_id)" in builder
    assert "GroundedToolCompiler().compile(" in catalog
    assert "context.grounding.target_refs" not in catalog
    assert 'public["actions"]' not in binder
    assert '"groups": tuple(' not in binder and '"shared_target"' not in binder
    assert "selection_key" not in catalog and "_verb_schema" not in catalog
    assert '"screen_coordinate"' not in binder and '"x"' not in binder and '"y"' not in binder


def test_step_result_has_one_root_owned_projection_chain() -> None:
    state = (RUNTIME / "agent" / "run_state.py").read_text(encoding="utf-8")
    loop = (RUNTIME / "agent" / "core_loop.py").read_text(encoding="utf-8")
    projection = (RUNTIME / "agent" / "context" / "step_projection.py").read_text(encoding="utf-8")

    assert "class StepResult:" in state
    assert "def project_step_result" in projection
    assert "project_step_result(" in loop
    assert "ControlTransition" not in "\n".join(
        path.read_text(encoding="utf-8") for path in RUNTIME.rglob("*.py")
    )
    assert "ModelPort" not in projection and "provider" not in projection


def test_named_local_tool_semantics_remain_catalog_owned() -> None:
    owners = {
        path.relative_to(RUNTIME).as_posix()
        for path in _python_sources()
        if "count_children" in path.read_text(encoding="utf-8")
    }

    assert owners == {
        "agent/decision_capability.py",
        "model/policy/grounded_tool_catalog.py",
    }


def test_normative_architecture_contains_the_single_authority_map() -> None:
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "## Authority" in architecture
    assert "What is the current unified world? | WorldFusion / WorldObservation" in architecture
    assert "What semantic action should be attempted? | Model policy" in architecture
    assert "Is the task complete? | TaskEvaluator" in architecture
    assert not (ROOT / "docs" / "task-execution-authority-map.md").exists()
