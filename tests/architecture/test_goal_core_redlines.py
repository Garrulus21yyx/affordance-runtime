from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "src" / "affordance_runtime"


def test_production_goal_guidance_has_no_evaluator_module() -> None:
    assert not (SOURCE / "goals" / "evaluator.py").exists()


def test_phase_one_does_not_introduce_forbidden_goal_or_loop_owners() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.rglob("*.py"))

    for forbidden in (
        "class TaskPlan",
        "class Milestone",
        "class GoalBinding",
        "class CandidateSet",
        "class ArgMin",
        "class StallState",
        "class ManagerAgent",
        "class WorkerAgent",
    ):
        assert forbidden not in production
    assert production.count("class CoreAgentLoop") == 1
    assert production.count("class RunState") == 1


def test_goal_plan_owner_contains_no_benchmark_or_page_specialization() -> None:
    goal_source = "\n".join(path.read_text(encoding="utf-8") for path in (SOURCE / "goals").glob("*.py"))

    for forbidden in ("@nibh", "Like", "Submit", "miniwob"):
        assert forbidden not in goal_source
    assert "witness_target_ids" not in goal_source


def test_goal_plan_is_projected_once_without_symbolic_progress_or_parallel_owner() -> None:
    context = (SOURCE / "agent" / "context" / "context.py").read_text(encoding="utf-8")
    builder = (SOURCE / "agent" / "context" / "context_builder.py").read_text(encoding="utf-8")
    provider = (SOURCE / "model" / "policy" / "grounded_policy_context.py").read_text(
        encoding="utf-8"
    )

    assert "goal_program_identity" not in context
    assert "goal_snapshot_id" not in context
    assert "goal_plan: AgentGoalPlanView" in context
    assert "project_agent_goal_plan" in builder
    assert '"goal_plan": _goal_plan(context)' in provider
    assert '"progress":' not in provider
    production = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.rglob("*.py"))
    assert "goal_evaluator=" not in production
    assert "current_goal_snapshot" not in production
    assert "goal_snapshot_after" not in production


def test_product_composition_fails_closed_without_an_explicit_goal_compiler() -> None:
    runtime = (SOURCE / "app" / "runtime.py").read_text(encoding="utf-8")
    composition = (SOURCE / "app" / "composition.py").read_text(encoding="utf-8")

    assert "default_factory=UnavailableGoalCompiler" in runtime
    assert "goal_compiler or UnavailableGoalCompiler()" in composition
    assert "default_factory=NotRequiredGoalCompiler" not in runtime


def test_g2_context_does_not_expand_the_action_or_loop_contract() -> None:
    production = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.rglob("*.py"))

    assert "GoalActionIntent" not in production
    assert "objective_ref" not in production
    assert "desired_postcondition_ref" not in production
    assert production.count("class CoreAgentLoop") == 1
