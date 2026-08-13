import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "affordance_runtime"
TARGET_CORE = (
    PACKAGE / "agent",
    PACKAGE / "task" / "contracts.py",
    PACKAGE / "task" / "local_objective.py",
    PACKAGE / "world",
    PACKAGE / "execution" / "contracts.py",
    PACKAGE / "evaluation",
    PACKAGE / "risk",
    PACKAGE / "confirmation",
    PACKAGE / "model_boundary",
    PACKAGE / "model_policy",
    PACKAGE / "model_evaluator",
)
FORBIDDEN = {
    "affordance_runtime.contracts",
    "affordance_runtime.environment_port",
    "affordance_runtime.runtime_committer",
    "affordance_runtime.state_kernel",
    "affordance_runtime.task.legacy_projection",
}
POLICY_FORBIDDEN_PREFIXES = (
    "affordance_runtime.executors",
    "affordance_runtime.grounding",
    "affordance_runtime.surfaces",
)


def _files(root: Path) -> tuple[Path, ...]:
    return (root,) if root.is_file() else tuple(root.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.add(node.module or "")
    return result


def test_target_core_does_not_import_legacy_contract_or_transaction_owners() -> None:
    violations = []
    for root in TARGET_CORE:
        for path in _files(root):
            imported = _imports(path)
            matches = imported.intersection(FORBIDDEN)
            if matches:
                violations.append(f"{path.relative_to(ROOT)}: {sorted(matches)}")
    assert violations == []


def test_agent_and_surface_dependency_directions_are_one_way() -> None:
    agent_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "agent")))
    surface_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "surfaces")))

    assert "affordance_runtime.browser_session" not in agent_imports
    assert not any(name.startswith("affordance_runtime.surfaces") for name in agent_imports)
    assert "affordance_runtime.agent.loop" not in surface_imports


def test_risk_and_confirmation_keep_surface_private_dependencies_out() -> None:
    risk_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "risk")))
    confirmation_imports = set().union(*(_imports(path) for path in _files(PACKAGE / "confirmation")))

    assert not any(name.startswith("affordance_runtime.surfaces") for name in risk_imports)
    assert not any(name.startswith("affordance_runtime.surfaces") for name in confirmation_imports)
    assert "affordance_runtime.browser_session" not in confirmation_imports


def test_policy_and_evaluators_do_not_import_concrete_execution_owners() -> None:
    policy_imports = _imports(PACKAGE / "agent" / "policy.py")
    policy_text = (PACKAGE / "agent" / "policy.py").read_text(encoding="utf-8")

    assert not any(name.startswith(POLICY_FORBIDDEN_PREFIXES) for name in policy_imports)
    assert "affordance_runtime.world.binder" not in policy_imports
    assert "affordance_runtime.world.orchestrator" not in policy_imports
    assert "ActionSpace" not in policy_text.replace("AgentActionSpaceView", "")
    assert "Turn" not in policy_text.replace("AgentTurnView", "")


def test_model_boundary_has_no_concrete_surface_execution_or_fixture_dependencies() -> None:
    imports = set().union(*(_imports(path) for path in _files(PACKAGE / "model_boundary")))

    assert not any(name.startswith("affordance_runtime.surfaces") for name in imports)
    assert not any(name.startswith("affordance_runtime.executors") for name in imports)
    assert not any(name.startswith("affordance_runtime.benchmarks") for name in imports)
    assert "affordance_runtime.world.binder" not in imports


def test_model_policy_has_no_surface_binding_execution_or_loop_state_dependencies() -> None:
    imports = set().union(*(_imports(path) for path in _files(PACKAGE / "model_policy")))
    loop_imports = _imports(PACKAGE / "agent" / "loop.py")

    assert not any(name.startswith("affordance_runtime.surfaces") for name in imports)
    assert not any(name.startswith("affordance_runtime.executors") for name in imports)
    assert "affordance_runtime.world.binder" not in imports
    assert "affordance_runtime.agent.state" not in imports
    assert not any(name.startswith("affordance_runtime.model_policy") for name in loop_imports)


def test_model_policy_transport_is_owned_only_by_existing_model_port() -> None:
    imports = set().union(*(_imports(path) for path in _files(PACKAGE / "model_policy")))
    loop_imports = _imports(PACKAGE / "agent" / "loop.py")

    assert not any(name == "requests" or name.startswith(("urllib", "httpx")) for name in imports)
    assert "affordance_runtime.model_policy.model_port_bridge" not in loop_imports


def test_model_evaluator_keeps_transport_and_execution_boundaries() -> None:
    imports = set().union(*(_imports(path) for path in _files(PACKAGE / "model_evaluator")))
    loop_imports = _imports(PACKAGE / "agent" / "loop.py")

    assert not any(name.startswith(("urllib", "httpx", "requests", "affordance_runtime.surfaces")) for name in imports)
    assert "affordance_runtime.world.binder" not in imports
    assert not any(name.startswith("affordance_runtime.executors") for name in imports)
    assert not any(name.startswith("affordance_runtime.model_evaluator") for name in loop_imports)


def test_target_core_does_not_import_benchmark_modules_or_behavioral_recorder() -> None:
    imports = set()
    agent_text = ""
    for root in TARGET_CORE:
        for path in _files(root):
            imports.update(_imports(path))
            if path.parent.name == "agent":
                agent_text += path.read_text(encoding="utf-8")

    assert not any(name.startswith("affordance_runtime.benchmarks") for name in imports)
    assert "TurnRecorder" not in agent_text


def test_agent_loop_injected_collaborator_review_gate_remains_closed() -> None:
    tree = ast.parse((PACKAGE / "agent" / "loop.py").read_text(encoding="utf-8"))
    loop = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AgentLoop")
    collaborators = {
        node.target.id
        for node in loop.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id != "recent_turn_limit"
    }

    assert len(collaborators) <= 8


def test_control_transition_owner_has_one_way_dependencies_and_unique_state_writes() -> None:
    owner = PACKAGE / "agent" / "control_transition.py"
    projection = PACKAGE / "model_boundary" / "control_transition_projection.py"
    owner_imports = _imports(owner)
    projection_imports = _imports(projection)

    assert not any(
        name.startswith(
            (
                "affordance_runtime.benchmarks",
                "affordance_runtime.model_boundary",
                "affordance_runtime.surfaces",
            )
        )
        for name in owner_imports
    )
    assert not any(
        name.startswith(
            (
                "affordance_runtime.benchmarks",
                "affordance_runtime.benchmarks.external_smoke",
                "affordance_runtime.world.environment",
            )
        )
        for name in projection_imports
    )

    writes = []
    for path in _files(PACKAGE / "agent"):
        text = path.read_text(encoding="utf-8")
        if "._append_control_transition(" in text:
            writes.append(path.name)
    assert writes == ["control_transition.py"]


def test_turn_is_only_a_compatibility_projection_not_a_production_fact_writer() -> None:
    for path in _files(PACKAGE / "agent"):
        source = path.read_text(encoding="utf-8")
        assert "record_turn(" not in source
        if path.name in {"control_transition.py", "state.py", "result.py"}:
            continue
        assert "Turn(" not in source


def test_benchmark_case_projection_is_narrow_and_separate_from_model_projection() -> None:
    benchmark = PACKAGE / "benchmarks" / "target_loop" / "case_projection.py"
    runner = PACKAGE / "benchmarks" / "target_loop" / "runner.py"
    model = PACKAGE / "model_boundary" / "control_transition_projection.py"

    assert not any(
        name.startswith("affordance_runtime.model_boundary")
        for name in _imports(benchmark)
    )
    assert not any(
        name.startswith("affordance_runtime.benchmarks")
        for name in _imports(model)
    )
    runner_source = runner.read_text(encoding="utf-8")
    assert "def _case_result(" not in runner_source
    assert "project_case_result(" in runner_source


def test_turn_history_is_read_only_projection_not_a_second_write_api() -> None:
    state_tree = ast.parse((PACKAGE / "agent" / "state.py").read_text(encoding="utf-8"))
    state = next(
        node
        for node in state_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AgentLoopState"
    )
    methods = {
        node.name
        for node in state.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }

    assert "append_turn" not in methods
    assert "recent_turns" in methods
