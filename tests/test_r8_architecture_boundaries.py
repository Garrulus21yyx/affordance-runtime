from __future__ import annotations

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
    "compatibility_semantic_compilers.py",
    "perception_session.py",
    "planner_context.py",
    "planner_model_orchestrator.py",
    "recovery_handler.py",
    "task_plan_lifecycle.py",
)


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


def test_browsergym_facade_preserves_split_component_identities() -> None:
    assert facade.BrowserGymObserver is observer.BrowserGymObserver
    assert facade.BrowserGymContractBuilder is encoder.BrowserGymContractBuilder
    assert facade.BrowserGymExecutor is episode_runner.BrowserGymExecutor
    assert facade.run_browsergym_generalist_episode is episode_runner.run_browsergym_generalist_episode
    assert facade.browsergym_episode_schedule is protocol.browsergym_episode_schedule
    assert facade.browsergym_failure_envelope is report_adapter.browsergym_failure_envelope
    assert facade.write_browsergym_report is report_adapter.write_browsergym_report
