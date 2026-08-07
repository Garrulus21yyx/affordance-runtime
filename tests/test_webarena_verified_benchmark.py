import json
from pathlib import Path

import pytest

from affordance_runtime.benchmarks.webarena_verified import (
    evaluate_webarena_verified_manifest,
    load_webarena_verified_tasks,
    select_stratified_webarena_subset,
    write_webarena_verified_subset,
)


def _dataset(path: Path, *, count: int = 36) -> Path:
    sites = ("shopping", "reddit", "gitlab")
    payload = [
        {
            "task_id": index,
            "sites": [sites[index % len(sites)]],
            "intent_template_id": 100 + index,
            "revision": 1,
        }
        for index in range(count)
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_webarena_manifest_is_stratified_and_digest_bound(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "dataset.json")

    manifest = write_webarena_verified_subset(dataset, tmp_path / "subset.json", count=30)

    assert manifest["selected_task_count"] == 30
    assert manifest["site_distribution"] == {"gitlab": 10, "reddit": 10, "shopping": 10}
    assert manifest["task_ids"][:6] == [2, 1, 0, 5, 4, 3]
    assert manifest["source_dataset_sha256"].startswith("sha256:")
    assert manifest["official_score_claimed"] is False


def test_webarena_subset_requires_planned_range_and_enough_tasks(tmp_path: Path) -> None:
    tasks = load_webarena_verified_tasks(_dataset(tmp_path / "dataset.json", count=30))

    with pytest.raises(ValueError, match="between 30 and 50"):
        select_stratified_webarena_subset(tasks, count=29)
    with pytest.raises(ValueError, match="fewer than 31"):
        select_stratified_webarena_subset(tasks, count=31)


def test_webarena_dataset_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            [
                {"task_id": 1, "sites": ["shopping"], "intent_template_id": 1, "revision": 1},
                {"task_id": 1, "sites": ["reddit"], "intent_template_id": 2, "revision": 1},
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate WebArena-Verified task id"):
        load_webarena_verified_tasks(path)


def test_webarena_evaluation_delegates_to_upstream_and_preserves_results(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'a' * 64}",
                "selected_task_count": 2,
                "task_ids": [1, 2],
            }
        ),
        encoding="utf-8",
    )
    logs = tmp_path / "logs"
    for task_id, score in ((1, 1.0), (2, 0.0)):
        task_dir = logs / str(task_id)
        task_dir.mkdir(parents=True)
        (task_dir / "eval_result.json").write_text(
            json.dumps({"task_id": task_id, "score": score, "status": "success"}), encoding="utf-8"
        )
    commands: list[list[str]] = []

    class Completed:
        returncode = 0

    def runner(command: list[str], **kwargs: object) -> Completed:
        commands.append(command)
        assert kwargs == {"check": False, "capture_output": True, "text": True}
        return Completed()

    report = evaluate_webarena_verified_manifest(
        manifest, logs, config_path=tmp_path / "config.json", runner=runner
    )

    assert commands == [
        [
            "webarena-verified", "eval-tasks", "--task-ids", "1,2", "--output-dir", str(logs),
            "--config", str(tmp_path / "config.json"),
        ]
    ]
    assert report["mean_official_score"] == 0.5
    assert report["upstream_results"]["1"]["score"] == 1.0
    assert report["upstream_result_sha256"]["1"].startswith("sha256:")
    assert report["manifest_sha256"].startswith("sha256:")
    assert report["official_score_claimed"] is False
    assert report["acceptance_errors"] == []


def test_webarena_evaluation_fails_closed_when_upstream_results_are_missing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'b' * 64}",
                "task_ids": [1],
            }
        )
    )

    class Completed:
        returncode = 0

    report = evaluate_webarena_verified_manifest(
        manifest, tmp_path / "logs", runner=lambda *_args, **_kwargs: Completed()
    )

    assert report["missing_result_ids"] == [1]
    assert report["mean_official_score"] is None
    assert report["acceptance_errors"] == ["missing official results: 1"]


def test_webarena_evaluation_rejects_duplicate_or_count_mismatched_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    common = {
        "schema_version": "webarena-verified-subset-v1",
        "source_dataset_sha256": f"sha256:{'c' * 64}",
    }
    manifest.write_text(json.dumps({**common, "task_ids": [1, 1]}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be unique"):
        evaluate_webarena_verified_manifest(manifest, tmp_path / "logs")

    manifest.write_text(
        json.dumps({**common, "selected_task_count": 3, "task_ids": [1, 2]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match"):
        evaluate_webarena_verified_manifest(manifest, tmp_path / "logs")


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"task_id": 99, "score": 1.0}, "task_id_mismatch"),
        ({"task_id": 1, "score": True}, "score_not_numeric"),
        ({"task_id": 1, "score": 1.5}, "score_out_of_range"),
    ],
)
def test_webarena_evaluation_fails_closed_for_invalid_upstream_result(
    tmp_path: Path, payload: dict[str, object], reason: str
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'d' * 64}",
                "task_ids": [1],
            }
        ),
        encoding="utf-8",
    )
    result_dir = tmp_path / "logs" / "1"
    result_dir.mkdir(parents=True)
    (result_dir / "eval_result.json").write_text(json.dumps(payload), encoding="utf-8")

    class Completed:
        returncode = 0

    report = evaluate_webarena_verified_manifest(
        manifest,
        tmp_path / "logs",
        runner=lambda *_args, **_kwargs: Completed(),
    )

    assert report["evaluated_task_count"] == 0
    assert report["invalid_results"] == {"1": reason}
    assert report["mean_official_score"] is None
    assert report["acceptance_errors"] == ["invalid official results: 1"]


def test_webarena_evaluation_rejects_result_symlink_outside_log_root(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "webarena-verified-subset-v1",
                "source_dataset_sha256": f"sha256:{'e' * 64}",
                "task_ids": [1],
            }
        ),
        encoding="utf-8",
    )
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"task_id": 1, "score": 1.0}), encoding="utf-8")
    result_dir = tmp_path / "logs" / "1"
    result_dir.mkdir(parents=True)
    (result_dir / "eval_result.json").symlink_to(outside)

    class Completed:
        returncode = 0

    report = evaluate_webarena_verified_manifest(
        manifest,
        tmp_path / "logs",
        runner=lambda *_args, **_kwargs: Completed(),
    )

    assert report["invalid_results"] == {"1": "result_path_escape"}
    assert report["acceptance_errors"] == ["invalid official results: 1"]
