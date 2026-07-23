from __future__ import annotations

import ast
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
    "contract_execution_loop.py",
    "compatibility_planner_algorithms.py",
    "compatibility_semantic_compilers.py",
    "perception_session.py",
    "planner_context.py",
    "planner_model_orchestrator.py",
    "recovery_handler.py",
    "task_plan_lifecycle.py",
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
    # runtime.py is the backwards-compatible one-contract conformance harness;
    # full task execution is owned only by RunCoordinator.
    assert constructors == {"coordinator.py", "runtime.py"}


def test_strict_planner_does_not_define_compatibility_task_grammar() -> None:
    planner_path = SOURCE_ROOT / "generalist_planner.py"
    definitions = {
        node.name
        for node in ast.parse(planner_path.read_text(encoding="utf-8")).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    assert definitions.isdisjoint(COMPATIBILITY_TASK_GRAMMAR_DEFINITIONS)


def test_strict_planner_import_and_construction_do_not_load_compatibility_algorithms() -> None:
    module_name = "affordance_runtime.compatibility_planner_algorithms"
    script = f"""
import sys
from affordance_runtime.generalist_planner import GeneralistLMPlanner
assert {module_name!r} not in sys.modules
GeneralistLMPlanner(object())
assert {module_name!r} not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


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
