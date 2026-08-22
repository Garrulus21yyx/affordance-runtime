from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_single_action_policy_baseline_has_no_removed_manager_auditor_chain() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src/affordance_runtime").rglob("*.py"))

    assert "MissionSupervisor" not in production
    assert "MissionAuditor" not in production
    assert "MilestonePlanner" not in production


def test_world_transition_projector_is_the_only_public_change_projector() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src/affordance_runtime").rglob("*.py"))

    assert production.count("class WorldTransitionProjector:") == 1
    assert "def _fact_changes(" not in _source("src/affordance_runtime/evaluation/action_outcome_projector.py")
    assert "public_world_delta" in _source("src/affordance_runtime/agent/run_state.py")
    assert "public_world_delta" in _source("src/affordance_runtime/agent/monitor.py")
    assert "public_world_delta" in _source("src/affordance_runtime/agent/context/step_projection.py")
    assert "public_world_delta" in _source("src/affordance_runtime/agent/observability.py")


def test_frozen_contracts_have_one_declared_owner_each() -> None:
    ownership = {
        "PublicWorldDelta": "src/affordance_runtime/agent/context/world_transition.py",
        "RegionVersion": "src/affordance_runtime/agent/context/world_region_index.py",
        "CurrentFinding": "src/affordance_runtime/agent/workspace.py",
        "SemanticEvent": "src/affordance_runtime/agent/workspace.py",
        "ActivitySummary": "src/affordance_runtime/agent/workspace.py",
        "AgentWorkspace": "src/affordance_runtime/agent/workspace.py",
        "AgentLoopProfile": "src/affordance_runtime/agent/profile.py",
    }
    production_files = tuple((ROOT / "src/affordance_runtime").rglob("*.py"))

    for contract, owner in ownership.items():
        declarations = tuple(
            path for path in production_files if f"class {contract}:" in path.read_text(encoding="utf-8")
        )
        assert declarations == (ROOT / owner,)
