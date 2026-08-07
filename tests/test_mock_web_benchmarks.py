from pathlib import Path

import pytest

from affordance_runtime.benchmarks.mock_web import load_mock_web_tasks, mock_web_benchmark_tasks


def test_load_mock_web_tasks_and_project_to_current_benchmark_contract() -> None:
    tasks = load_mock_web_tasks()
    projected = mock_web_benchmark_tasks("http://127.0.0.1:8123")

    assert len(tasks) == len(projected) == 3
    assert projected[0].suite == "mock-web-v1"
    assert projected[0].start_url.startswith("http://127.0.0.1:8123/")
    assert projected[0].oracle["selector"].startswith("#")
    assert projected[0].oracle["forbidden_side_effects"]


def test_mock_web_loader_rejects_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "tasks.json").write_text(
        '[{"task_id":"bad","page":"../bad.html","goal":"bad",'
        '"success":{"selector":"#done","text":"done"},'
        '"forbidden_side_effects":["anything"],"seeded_layout_variants":["default"]}]',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local HTML filename"):
        load_mock_web_tasks(tmp_path)
