from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from affordance_runtime.benchmarks import browsergym as facade
from affordance_runtime.benchmarks import browsergym_encoder as encoder
from affordance_runtime.benchmarks import browsergym_episode_runner as episode_runner
from affordance_runtime.benchmarks import browsergym_observer as observer
from affordance_runtime.benchmarks import browsergym_protocol as protocol
from affordance_runtime.benchmarks import browsergym_report as report_adapter

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "affordance_runtime"
EXTRACTED_CORE_COLLABORATORS = (
    "approval_contracts.py",
    "contract_execution_loop.py",
    "compatibility_planner_algorithms.py",
    "compatibility_semantic_compilers.py",
    "perception_session.py",
    "planner_context.py",
    "planner_model_orchestrator.py",
    "planning_contracts.py",
    "task_plan_flow.py",
    "task_plan_lifecycle.py",
)

APPROVAL_ENTRYPOINT_MODULES = (
    "cli.py",
    "benchmarks/local.py",
)

PLANNER_IMPLEMENTATION_MODULES = (
    "generalist_planner.py",
    "planner_adapters.py",
    "planners.py",
)

COMPATIBILITY_TASK_GRAMMAR_DEFINITIONS = {
    "_autocomplete_prefix",
    "_calendar_date_operation",
    "_compiled_calendar_event_operation",
    "_compiled_form_field_operation",
    "_compiled_suggestion_selection_operation",
    "_explicit_text_transform_value",
    "_remaining_requested_selection_values",
    "_required_slider_direction",
    "_restrict_targets_to_objective",
    "_slider_progress_constraints",
    "_target_discovery_constraints",
}


def test_core_has_no_benchmark_vocabulary_or_adapter_imports() -> None:
    forbidden_terms = ("browsergym", "miniwob", "workarena", "webarena")
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        relative = path.relative_to(SOURCE_ROOT)
        if relative.parts[0] == "benchmarks" or relative.as_posix() == "cli.py":
            continue
        text = path.read_text(encoding="utf-8").casefold()
        if any(term in text for term in forbidden_terms) or "affordance_runtime.benchmarks.browsergym" in text:
            violations.append(relative.as_posix())
    assert violations == []


def test_extracted_core_collaborators_do_not_create_authoritative_state() -> None:
    for filename in EXTRACTED_CORE_COLLABORATORS:
        text = (SOURCE_ROOT / filename).read_text(encoding="utf-8")
        assert "StateKernel(" not in text, filename

    constructors = {
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in SOURCE_ROOT.rglob("*.py")
        if "StateKernel(" in path.read_text(encoding="utf-8")
    }
    assert constructors == {"runtime_loop_phase.py"}


def test_task_plan_flow_has_no_state_or_trace_commit_authority() -> None:
    source = (SOURCE_ROOT / "task_plan_flow.py").read_text(encoding="utf-8")

    assert "install_task_plan(" not in source
    assert "replace_task_plan(" not in source
    assert "TraceDag" not in source
    assert ".transition(" not in source


def test_planner_implementations_depend_on_neutral_contract_not_coordinator() -> None:
    violations: list[str] = []
    for filename in PLANNER_IMPLEMENTATION_MODULES:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.ImportFrom) and node.module == "affordance_runtime.coordinator"
            for node in ast.walk(tree)
        ):
            violations.append(filename)
    assert violations == []

    from affordance_runtime.planning_contracts import PlannerPort, PlannerResponse

    assert PlannerPort is not None
    assert PlannerResponse is not None


def test_approval_sources_depend_on_neutral_contract_not_coordinator() -> None:
    approval_contract_path = SOURCE_ROOT / "approval_contracts.py"
    assert approval_contract_path.exists()
    approval_contract_tree = ast.parse(approval_contract_path.read_text(encoding="utf-8"))
    assert not any(
        (isinstance(node, ast.ImportFrom) and node.module == "affordance_runtime.coordinator")
        or (
            isinstance(node, ast.Import) and any(alias.name == "affordance_runtime.coordinator" for alias in node.names)
        )
        for node in ast.walk(approval_contract_tree)
    )

    coordinator_tree = ast.parse((SOURCE_ROOT / "coordinator.py").read_text(encoding="utf-8"))
    coordinator_classes = {node.name for node in coordinator_tree.body if isinstance(node, ast.ClassDef)}
    assert coordinator_classes.isdisjoint({"ApprovalProvider", "ConfiguredApprovalProvider"})

    violations: list[str] = []
    for filename in APPROVAL_ENTRYPOINT_MODULES:
        tree = ast.parse((SOURCE_ROOT / filename).read_text(encoding="utf-8"))
        assert any(
            isinstance(node, ast.ImportFrom)
            and node.module == "affordance_runtime.approval_contracts"
            and any(alias.name == "ConfiguredApprovalProvider" for alias in node.names)
            for node in ast.walk(tree)
        ), filename
        if any(
            isinstance(node, ast.ImportFrom)
            and node.module == "affordance_runtime.coordinator"
            and any(alias.name in {"ApprovalProvider", "ConfiguredApprovalProvider"} for alias in node.names)
            for node in ast.walk(tree)
        ):
            violations.append(filename)
    assert violations == []

    coordinator_source = (SOURCE_ROOT / "coordinator.py").read_text(encoding="utf-8")
    assert "ApprovalProvider" not in coordinator_source
    assert "ConfiguredApprovalProvider" not in coordinator_source


def test_strict_planners_are_physically_separate_from_compatibility_grammar() -> None:
    for filename in ("task_planner.py", "step_choice_planner.py"):
        source = (SOURCE_ROOT / filename).read_text(encoding="utf-8")
        definitions = {
            node.name for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        assert definitions.isdisjoint(COMPATIBILITY_TASK_GRAMMAR_DEFINITIONS)
        assert "compatibility_planner_algorithms" not in source
        assert "generalist_planner" not in source


def test_strict_planner_import_and_construction_do_not_load_compatibility_algorithms() -> None:
    module_name = "affordance_runtime.compatibility_planner_algorithms"
    script = f"""
import sys
from affordance_runtime.step_choice_planner import StrictStepChoicePlanner
from affordance_runtime.task_planner import StrictTaskPlanner
assert {module_name!r} not in sys.modules
StrictStepChoicePlanner(object())
StrictTaskPlanner(object())
assert {module_name!r} not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(SOURCE_ROOT.parent),
        },
    )
    assert completed.returncode == 0, completed.stderr


def test_legacy_three_argument_planner_signatures_are_deleted() -> None:
    generalist = (SOURCE_ROOT / "generalist_planner.py").read_text(encoding="utf-8")
    context = (SOURCE_ROOT / "planner_context.py").read_text(encoding="utf-8")
    adapters = (SOURCE_ROOT / "planner_adapters.py").read_text(encoding="utf-8")

    assert "propose_legacy" not in generalist + adapters
    assert "build_planner_context" not in generalist + context
    assert "StateKernel" not in context + adapters
    assert "BrowserSnapshot" not in context + adapters
    assert not (SOURCE_ROOT / "planner_compatibility.py").exists()


def test_task_planning_and_step_choice_flows_do_not_share_authority_objects() -> None:
    task_flow = (SOURCE_ROOT / "task_plan_flow.py").read_text(encoding="utf-8")
    choice_flow = (SOURCE_ROOT / "step_choice_flow.py").read_text(encoding="utf-8")

    assert "ChoicePlanningRequest" not in task_flow
    assert "ActionChoiceCatalog" not in task_flow
    assert "TaskPlanAuthority" not in choice_flow
    assert "TaskPlanningRequest" not in choice_flow


def test_historical_profile_loads_quarantined_compatibility_algorithms() -> None:
    module_name = "affordance_runtime.compatibility_planner_algorithms"
    script = f"""
import sys
from affordance_runtime.generalist_planner import GeneralistLMPlanner, GeneralistPlannerProfile
assert {module_name!r} not in sys.modules
GeneralistLMPlanner(object(), planner_profile=GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY)
assert {module_name!r} in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(SOURCE_ROOT.parent),
        },
    )
    assert completed.returncode == 0, completed.stderr


def test_browsergym_facade_preserves_split_component_identities() -> None:
    assert facade.BrowserGymObserver is observer.BrowserGymObserver
    assert facade.BrowserGymContractBuilder is encoder.BrowserGymContractBuilder
    assert facade.BrowserGymExecutor is episode_runner.BrowserGymExecutor
    assert facade.run_browsergym_generalist_episode is episode_runner.run_browsergym_generalist_episode
    assert facade.browsergym_episode_schedule is protocol.browsergym_episode_schedule
    assert facade.browsergym_failure_envelope is report_adapter.browsergym_failure_envelope
    assert facade.write_browsergym_report is report_adapter.write_browsergym_report
