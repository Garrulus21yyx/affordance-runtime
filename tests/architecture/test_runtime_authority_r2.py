from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path("src/affordance_runtime")


def _python_files(root: Path):
    return tuple(root.rglob("*.py"))


def test_legacy_control_schemas_are_physically_absent() -> None:
    forbidden = {
        "ExecutionSummary",
        "AcquisitionSummary",
        "AdmissionSummary",
        "Turn",
    }
    for path in _python_files(PACKAGE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        declared = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        }
        assert not declared & forbidden, path
        assert "as_turn" not in declared, path


def test_execution_outcome_has_one_package_and_one_product_constructor_owner() -> None:
    constructors = []
    for path in _python_files(PACKAGE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (isinstance(node.func, ast.Name) and node.func.id == "ExecutionOutcome"):
                constructors.append(path.relative_to(PACKAGE).as_posix())
    assert set(constructors) == {"world/orchestrator.py"}
    assert "ExecutionOutcome" not in (PACKAGE / "world" / "__init__.py").read_text(encoding="utf-8")
    assert "class ExecutionOutcome" not in (PACKAGE / "world" / "acquisition.py").read_text(encoding="utf-8")


def test_transition_composes_exact_phase_aggregates() -> None:
    tree = ast.parse((PACKAGE / "agent" / "control_transition.py").read_text(encoding="utf-8"))
    transition = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ControlTransition")
    annotations = {
        node.target.id: ast.unparse(node.annotation)
        for node in transition.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert annotations["execution_attempts"] == "tuple[ExecutionOutcome, ...]"
    assert annotations["acquisition_attempts"] == "tuple[ObservationAcquisition, ...]"
    assert "EvaluationOutcome" in annotations["evaluation"]
    assert annotations["before_observation"] == "WorldObservation"
    assert annotations["after_observation"] == "WorldObservation"


def test_evaluation_contract_owns_low_level_construction_and_named_shapes() -> None:
    direct_callers = []
    for path in _python_files(PACKAGE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id
                in {
                    "EvaluationOutcome",
                    "EvaluationInterruption",
                }
            ):
                direct_callers.append(path.relative_to(PACKAGE).as_posix())
    assert not direct_callers
    contracts = (PACKAGE / "evaluation" / "contracts.py").read_text(encoding="utf-8")
    for constructor in (
        "completed_after_execution",
        "completed_after_observation",
        "interrupted_after_execution",
        "interrupted_after_observation",
    ):
        assert f"def {constructor}(" in contracts


def test_reducer_never_constructs_phase_authority() -> None:
    tree = ast.parse((PACKAGE / "agent" / "control_reducer.py").read_text(encoding="utf-8"))
    forbidden = {"ActionResult", "ExecutionOutcome", "ObservationAcquisition", "EvaluationOutcome"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not calls & forbidden


def test_bound_request_finalization_and_continuation_have_one_owner_path() -> None:
    cycle = (PACKAGE / "agent" / "execution_cycle.py").read_text(encoding="utf-8")
    binder = (PACKAGE / "actions" / "binder.py").read_text(encoding="utf-8")
    state = (PACKAGE / "agent" / "state.py").read_text(encoding="utf-8")
    facade = (PACKAGE / "agent" / "__init__.py").read_text(encoding="utf-8")

    assert "replace(request" not in cycle
    assert "bind_for_execution" in binder
    assert "latest_control_continuation" not in state
    assert '"ControlContinuation":' not in facade
