from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "affordance_runtime"


def _production() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.rglob("*.py"))


def _production_contract_assets() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in SOURCE.rglob("*")
        if path.is_file() and path.suffix in {".py", ".yaml", ".yml"}
    )


def test_superseded_control_owners_are_physically_absent() -> None:
    assert not tuple((SOURCE / "mission").glob("*.py"))
    assert not (SOURCE / "model" / "mission_roles.py").exists()
    assert not (SOURCE / "model" / "pydantic_ai_role_invoker.py").exists()
    assert not (SOURCE / "model" / "prompts" / "milestone_planner.yaml").exists()
    assert not (SOURCE / "model" / "prompts" / "mission_auditor.yaml").exists()

    production = _production()
    for displaced in (
        "MissionSupervisor",
        "MilestoneRoadmap",
        "MissionState",
        "YieldMilestone",
        "yield_milestone",
        "active_milestone",
        "mission_role_invocation",
        "planner_proposal_rejected",
        "planner_failed",
        '"yield_kind"',
        '"milestone_id"',
        "ProtocolFeedback",
        "protocol_feedback",
        "pin_fact",
        "EpisodeBudget",
        "EpisodeYieldReason",
        'YIELDED = "yielded"',
    ):
        assert displaced not in production


def test_production_prompts_cannot_advertise_deleted_control_protocols() -> None:
    assets = _production_contract_assets()
    prompt = (SOURCE / "model" / "policy" / "prompts" / "grounded_agent.yaml").read_text(
        encoding="utf-8"
    )

    for displaced in (
        "active_milestone",
        "yield_milestone",
        "MissionState",
        "prior pinning",
        "Pin an offered",
    ):
        assert displaced not in assets
    assert "required_evidence" not in prompt
    assert "remember_fact" in prompt
    assert "submit_final_response" in prompt


def test_target_runner_has_exactly_one_core_loop_path() -> None:
    runner = (SOURCE / "benchmarks" / "target_loop" / "runner.py").read_text(encoding="utf-8")
    composition = (SOURCE / "benchmarks" / "target_loop" / "contracts.py").read_text(
        encoding="utf-8"
    )

    assert "_run_mission" not in runner
    assert "ExecutionMode" not in runner + composition
    assert "run = _run_episode(" in runner
    assert "mission_planner" not in composition
    assert "mission_auditor" not in composition
    assert "trace_recorder.events" not in runner
    assert "finalization = result.finalization" in runner


def test_decision_and_repair_algebra_is_closed() -> None:
    decisions = (SOURCE / "agent" / "decisions.py").read_text(encoding="utf-8")
    bridge = (SOURCE / "model" / "policy" / "pydantic_ai_bridge.py").read_text(
        encoding="utf-8"
    )

    assert 'SUBMIT_FINAL_RESPONSE = "submit_final_response"' in decisions
    assert 'REMEMBER_FACT = "remember_fact"' in decisions
    assert "PROTOCOL_FEEDBACK" not in decisions
    assert 'phase="representation_repair"' not in bridge
    assert "repair_profile.phase.value" in bridge
    assert bridge.count("_representation_repair_prompt(") == 2  # one call and one definition
    assert "_protocol_feedback_invocation" not in bridge


def test_single_control_and_state_owner_remain() -> None:
    production = _production()

    assert production.count("class CoreAgentLoop") == 1
    assert production.count("class RunState") == 1
    assert production.count("class EpisodeMonitor:") == 1
    assert "class ManagerAgent" not in production
    assert "class WorkerAgent" not in production


def test_product_composition_installs_the_same_monitor_as_benchmark() -> None:
    composition = (SOURCE / "app" / "composition.py").read_text(encoding="utf-8")
    runner = (SOURCE / "benchmarks" / "target_loop" / "runner.py").read_text(encoding="utf-8")

    assert "else EpisodeMonitor()" in composition
    assert "episode_monitor=EpisodeMonitor()" in runner
