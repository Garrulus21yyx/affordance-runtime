import json
from pathlib import Path

import pytest

from affordance_runtime.benchmarks.webarena_verified import (
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
