from affordance_runtime.benchmarks.adaptive_routing import (
    ABLATION_CASES,
    ABLATION_PROFILES,
    run_adaptive_routing_ablation,
)
from affordance_runtime.cli import main


def test_six_profile_adaptive_routing_ablation_exposes_expected_tradeoffs(tmp_path) -> None:
    report = run_adaptive_routing_ablation(tmp_path)

    assert report["acceptance_errors"] == []
    assert len(report["runs"]) == len(ABLATION_PROFILES) * len(ABLATION_CASES)
    profiles = report["profiles"]
    assert profiles["dom_only"]["task_success_rate"] < 1.0
    assert profiles["visual_only"]["task_success_rate"] == 1.0
    assert profiles["visual_only"]["unnecessary_visual_route_rate"] == 1.0
    assert profiles["visual_only"]["unnecessary_visual_model_call_rate"] == 1.0
    assert profiles["adaptive_unified"]["task_success_rate"] == 1.0
    assert profiles["adaptive_unified"]["unnecessary_visual_route_rate"] == 0.0
    assert profiles["adaptive_unified"]["unnecessary_visual_model_call_rate"] == 0.0
    assert profiles["adaptive_unified"]["fallback_success"] == 1.0
    assert profiles["adaptive_unified"]["stale_block_rate"] == 1.0
    assert profiles["adaptive_unified"]["constraint_violation_rate"] == 0.0
    assert profiles["adaptive_unified"]["mean_cost"] == 0.0
    assert profiles["adaptive_unified"]["regression_delta"] == 0.0
    assert profiles["adaptive_plus_task_skill"]["skill_case_planner_calls"] == 0.0
    assert profiles["always_system2"]["skill_case_planner_calls"] == 2.0
    assert all(
        metrics["unsafe_side_effect_rate"] == 0.0
        and metrics["verifier_false_accept_rate"] == 0.0
        and metrics["duplicate_effect_risk_rate"] == 0.0
        for metrics in profiles.values()
    )
    assert (tmp_path / "adaptive-routing-ablation.json").exists()


def test_adaptive_routing_ablation_cli_returns_success(tmp_path) -> None:
    assert main(["benchmark-adaptive-routing", "--output", str(tmp_path)]) == 0
    assert (tmp_path / "adaptive-routing-ablation.json").exists()
