from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "src" / "affordance_runtime"
AUTHORITY = ROOT / "docs" / "task-execution-authority-map.md"
STATUS = ROOT / "docs" / "implementation-status.md"


def _python_sources() -> tuple[Path, ...]:
    return tuple(sorted(RUNTIME.rglob("*.py")))


def _class_owners(name: str) -> tuple[str, ...]:
    owners = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(node, ast.ClassDef) and node.name == name for node in ast.walk(tree)):
            owners.append(path.relative_to(RUNTIME).as_posix())
    return tuple(owners)


def test_task_plan_has_exactly_one_production_contract() -> None:
    assert _class_owners("TaskPlan") == ("task_plan_contracts.py",)
    assert _class_owners("TaskProgram") == ()
    assert _class_owners("Milestone") == ()
    assert not (RUNTIME / "task" / "task_program.py").exists()


def test_canonical_step_execution_and_choice_contracts_exist() -> None:
    step_execution = (RUNTIME / "task" / "step_execution.py").read_text(encoding="utf-8")
    choice_builder = (RUNTIME / "action_choice_builder.py").read_text(encoding="utf-8")
    choice_flow = (RUNTIME / "step_choice_flow.py").read_text(encoding="utf-8")

    assert "StepExecutionSpec" in step_execution
    assert "materialize_step_execution" in step_execution
    assert "ActionChoiceCatalogBuilder" in choice_builder
    assert "StepChoiceFlow" in choice_flow


def test_no_pre_observation_gui_identity_enters_task_goal() -> None:
    task_contract = (RUNTIME / "task" / "contracts.py").read_text(encoding="utf-8")
    loop = (RUNTIME / "agent" / "loop.py").read_text(encoding="utf-8")

    task_goal = task_contract.split("class TaskGoal", 1)[1].split("class ", 1)[0]
    assert "target_id:" not in task_goal
    assert "require_initial_observation" in loop
    assert loop.index("require_initial_observation") < loop.index("AgentLoopState(")


def test_one_canonical_authority_document_is_execution_complete() -> None:
    authoritative = AUTHORITY.read_text(encoding="utf-8")
    required_sections = (
        "## 1. Decision",
        "## 2. Non-negotiable invariants",
        "## 3. Canonical owners and contracts",
        "## 4. Authoritative state model",
        "## 5. Identity and temporal ordering",
        "## 6. Exact per-turn algorithm",
        "## 7. Main Agent interface",
        "## 8. Projection and losslessness",
        "## 9. Unified evidence lifecycle",
        "## 10. Typed fail-closed outcomes",
        "## 11. Current repository mapping and convergence",
        "## 12. Change-impact protocol",
        "## 13. Verification and exit criteria",
    )
    assert all(section in authoritative for section in required_sections)
    assert "admitted TaskPlan<StepSpec.execution>" in authoritative
    assert "Action-only Agent boundary" in authoritative
    assert "No pre-observation GUI identity" in authoritative
    assert "Evidence source is not lifecycle authority" in authoritative


def test_current_implementation_cutover_is_reported_without_live_closure() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert "AUTHORITY_CUTOVER_IMPLEMENTED_NOT_LIVE_VERIFIED" in status
    assert "fresh five-case" in status
    assert "GENERALIZATION_OPEN" in status


def test_architecture_discovery_and_governance_use_the_authority_map() -> None:
    assert "task-execution-authority-map.md" in (
        ROOT / "docs" / "architecture.md"
    ).read_text(encoding="utf-8")
    governance = (ROOT / "docs" / "architecture-governance-track.md").read_text(
        encoding="utf-8"
    )
    assert "Canonical GUI Agent Execution Architecture" in governance
    assert "mandatory before implementation" in governance
    assert "change-impact table from section 12" in governance


def test_main_agent_cutover_properties_are_recorded_before_implementation() -> None:
    authoritative = AUTHORITY.read_text(encoding="utf-8")
    assert "the main Agent decision union contains no semantic-state constructor" in authoritative
    assert "action catalogs do not import LocalObjective" in authoritative
    assert "every active execution state is materialized from the active StepSpec" in authoritative
    assert "fresh real benchmark evidence" in authoritative


def test_recurrent_agent_and_grounded_catalog_are_action_only() -> None:
    decisions = (RUNTIME / "agent" / "decisions.py").read_text(encoding="utf-8")
    catalog = (RUNTIME / "model_policy" / "grounded_tool_catalog.py").read_text(encoding="utf-8")
    spec = (RUNTIME / "model_policy" / "spec.py").read_text(encoding="utf-8")

    assert "EstablishLocalObjective" not in decisions
    assert "LocalObjective" not in catalog
    assert "LocalObjective" not in spec
    assert "establish_local_objective" not in catalog


def test_agent_loop_composes_plan_authority_explicitly_and_has_one_execution_slot() -> None:
    loop = (RUNTIME / "agent" / "loop.py").read_text(encoding="utf-8")
    state = (RUNTIME / "agent" / "state.py").read_text(encoding="utf-8")

    assert "task_plan_preparer: AgentTaskPlanPreparerPort | None" in loop
    assert "self.task_plan_preparer.prepare(task, current)" in loop
    assert "state.install_plan(" in loop
    assert "getattr(self.policy" not in loop
    assert "active_step_execution: StepExecutionState | None" in state
    assert "local_objective_state" not in state


def test_architecture_change_template_forces_owner_and_deletion_analysis() -> None:
    template = (
        ROOT / "docs" / "change-admission" / "architecture-change-template.md"
    ).read_text(encoding="utf-8")
    required = (
        "Which exact stage in authority-map section 3 changes?",
        "Who is the single primary owner?",
        "Which section-2 invariant is affected?",
        "Which complete consumers read that output?",
        "Does any projection become authoritative?",
        "Which old owner/path will be deleted?",
        "Held-out or generated variations",
        "Fresh real benchmark/profile",
    )
    assert all(marker in template for marker in required)
