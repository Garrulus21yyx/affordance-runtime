from affordance_runtime.benchmarks.task_planning import run_task_planning_ablation
from affordance_runtime.cli import main


def test_controlled_task_planning_ablation_preserves_short_path_and_improves_long_path(tmp_path) -> None:
    report = run_task_planning_ablation(tmp_path)

    assert report["acceptance_errors"] == []
    assert report["profiles"]["flat"]["short_success"] is True
    assert report["profiles"]["flat"]["long_success"] is False
    assert report["profiles"]["always_plan"]["short_success"] is False
    assert report["profiles"]["adaptive"]["short_success"] is True
    assert report["profiles"]["adaptive"]["long_success"] is True
    assert report["profiles"]["adaptive"]["model_calls"] == 1
    adaptive_long = next(item for item in report["runs"] if item["profile"] == "adaptive" and item["case_id"] == "long")
    assert adaptive_long["action_count"] == 3
    assert (tmp_path / "task-planning-ablation.json").exists()


def test_task_planning_ablation_cli_returns_success(tmp_path) -> None:
    assert main(["benchmark-task-planning", "--output", str(tmp_path)]) == 0
    assert (tmp_path / "task-planning-ablation.json").exists()
