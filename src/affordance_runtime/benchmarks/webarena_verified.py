"""Dataset-manifest preparation for the official WebArena-Verified evaluator.

The scored evaluator remains the upstream ``webarena-verified eval-tasks``
command.  This module only selects a reproducible 30--50 task stratified
subset and records the exact source-data digest needed for a later official
offline trace evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class WebArenaVerifiedTaskRef:
    task_id: int
    sites: tuple[str, ...]
    intent_template_id: int
    revision: int


def load_webarena_verified_tasks(dataset_path: Path) -> list[WebArenaVerifiedTaskRef]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("WebArena-Verified dataset must be a JSON array")
    tasks: list[WebArenaVerifiedTaskRef] = []
    ids: set[int] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"dataset[{index}] must be an object")
        task_id = item.get("task_id")
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 0:
            raise ValueError(f"dataset[{index}].task_id must be a non-negative integer")
        if task_id in ids:
            raise ValueError(f"duplicate WebArena-Verified task id: {task_id}")
        ids.add(task_id)
        sites = item.get("sites")
        if not isinstance(sites, list) or not sites or any(not isinstance(site, str) or not site for site in sites):
            raise ValueError(f"dataset[{index}].sites must be a non-empty string array")
        template_id = item.get("intent_template_id")
        revision = item.get("revision")
        if isinstance(template_id, bool) or not isinstance(template_id, int):
            raise ValueError(f"dataset[{index}].intent_template_id must be an integer")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError(f"dataset[{index}].revision must be an integer")
        tasks.append(WebArenaVerifiedTaskRef(task_id, tuple(sites), template_id, revision))
    return tasks


def select_stratified_webarena_subset(
    tasks: Iterable[WebArenaVerifiedTaskRef], *, count: int = 30
) -> list[WebArenaVerifiedTaskRef]:
    """Select a deterministic round-robin sample across primary benchmark sites."""

    if not 30 <= count <= 50:
        raise ValueError("WebArena-Verified subset count must be between 30 and 50")
    groups: dict[str, list[WebArenaVerifiedTaskRef]] = defaultdict(list)
    for task in sorted(tasks, key=lambda item: item.task_id):
        groups[task.sites[0]].append(task)
    if not groups:
        raise ValueError("WebArena-Verified dataset contains no tasks")
    selected: list[WebArenaVerifiedTaskRef] = []
    cursors = {site: 0 for site in sorted(groups)}
    while len(selected) < count:
        progressed = False
        for site in sorted(groups):
            cursor = cursors[site]
            if cursor >= len(groups[site]):
                continue
            selected.append(groups[site][cursor])
            cursors[site] += 1
            progressed = True
            if len(selected) == count:
                break
        if not progressed:
            raise ValueError(f"WebArena-Verified dataset has fewer than {count} tasks")
    return selected


def write_webarena_verified_subset(
    dataset_path: Path, output_path: Path, *, count: int = 30
) -> dict[str, Any]:
    tasks = load_webarena_verified_tasks(dataset_path)
    selected = select_stratified_webarena_subset(tasks, count=count)
    source_digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    site_distribution = Counter(task.sites[0] for task in selected)
    manifest = {
        "schema_version": "webarena-verified-subset-v1",
        "official_evaluator": "webarena-verified eval-tasks",
        "source_dataset_sha256": f"sha256:{source_digest}",
        "source_task_count": len(tasks),
        "selection_policy": "sorted-primary-site-round-robin-v1",
        "selected_task_count": len(selected),
        "task_ids": [task.task_id for task in selected],
        "site_distribution": dict(sorted(site_distribution.items())),
        "tasks": [asdict(task) for task in selected],
        "official_score_claimed": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def evaluate_webarena_verified_manifest(
    manifest_path: Path,
    agent_logs_dir: Path,
    *,
    config_path: Path | None = None,
    executable: str = "webarena-verified",
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Delegate scoring to upstream's deterministic evaluator without a shell."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "webarena-verified-subset-v1":
        raise ValueError("invalid WebArena-Verified subset manifest")
    task_ids = manifest.get("task_ids")
    if (
        not isinstance(task_ids, list)
        or not task_ids
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in task_ids)
    ):
        raise ValueError("WebArena-Verified manifest task_ids must be a non-empty non-negative integer array")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("WebArena-Verified manifest task_ids must be unique")
    selected_count = manifest.get("selected_task_count")
    if selected_count is not None and selected_count != len(task_ids):
        raise ValueError("WebArena-Verified manifest selected_task_count does not match task_ids")
    source_digest = manifest.get("source_dataset_sha256")
    if not _is_sha256(source_digest):
        raise ValueError("WebArena-Verified manifest requires a valid source dataset SHA-256")
    command = [
        executable,
        "eval-tasks",
        "--task-ids",
        ",".join(str(task_id) for task_id in task_ids),
        "--output-dir",
        str(agent_logs_dir),
    ]
    if config_path is not None:
        command.extend(["--config", str(config_path)])
    try:
        completed = runner(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return _evaluation_report(
            manifest,
            manifest_path,
            command,
            task_ids,
            {},
            {},
            {},
            f"official evaluator unavailable: {type(exc).__name__}",
        )
    if completed.returncode != 0:
        return _evaluation_report(
            manifest,
            manifest_path,
            command,
            task_ids,
            {},
            {},
            {},
            f"official evaluator failed: exit_{completed.returncode}",
        )
    results: dict[int, dict[str, Any]] = {}
    result_digests: dict[int, str] = {}
    invalid_results: dict[int, str] = {}
    resolved_logs = agent_logs_dir.resolve()
    for task_id in task_ids:
        path = agent_logs_dir / str(task_id) / "eval_result.json"
        if not path.exists():
            continue
        try:
            resolved_path = path.resolve()
            resolved_path.relative_to(resolved_logs)
        except (OSError, ValueError):
            invalid_results[task_id] = "result_path_escape"
            continue
        try:
            raw_result = resolved_path.read_bytes()
            value = json.loads(raw_result.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            invalid_results[task_id] = f"unreadable_result:{type(exc).__name__}"
            continue
        error = _validate_upstream_result(value, task_id)
        if error:
            invalid_results[task_id] = error
            continue
        results[task_id] = value
        result_digests[task_id] = f"sha256:{hashlib.sha256(raw_result).hexdigest()}"
    return _evaluation_report(
        manifest,
        manifest_path,
        command,
        task_ids,
        results,
        result_digests,
        invalid_results,
        "",
    )


def _evaluation_report(
    manifest: dict[str, Any],
    manifest_path: Path,
    command: list[str],
    task_ids: list[int],
    results: dict[int, dict[str, Any]],
    result_digests: dict[int, str],
    invalid_results: dict[int, str],
    evaluator_error: str,
) -> dict[str, Any]:
    missing = [
        task_id
        for task_id in task_ids
        if task_id not in results and task_id not in invalid_results
    ]
    scores = [float(result["score"]) for result in results.values()]
    report = {
        "schema_version": "webarena-verified-evaluation-v2",
        "official_evaluator": "webarena-verified eval-tasks",
        "source_dataset_sha256": manifest.get("source_dataset_sha256", ""),
        "manifest_sha256": f"sha256:{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}",
        "manifest_task_ids": task_ids,
        "evaluated_task_count": len(results),
        "missing_result_ids": missing,
        "invalid_results": {str(task_id): invalid_results[task_id] for task_id in sorted(invalid_results)},
        "upstream_result_sha256": {
            str(task_id): result_digests[task_id] for task_id in sorted(result_digests)
        },
        # Absence of an upstream result is not an official zero.  Keeping this
        # nullable makes fail-closed preflight reports impossible to misread as
        # a scored run.
        "mean_official_score": sum(scores) / len(scores) if scores else None,
        "upstream_results": {str(task_id): results[task_id] for task_id in sorted(results)},
        "command": command,
        "official_score_claimed": False,
        "acceptance_errors": [],
    }
    if evaluator_error:
        report["acceptance_errors"].append(evaluator_error)
    if missing:
        report["acceptance_errors"].append(f"missing official results: {len(missing)}")
    if invalid_results:
        report["acceptance_errors"].append(f"invalid official results: {len(invalid_results)}")
    return report


def _validate_upstream_result(value: Any, expected_task_id: int) -> str:
    if not isinstance(value, dict):
        return "result_not_object"
    task_id = value.get("task_id")
    if task_id != expected_task_id:
        return "task_id_mismatch"
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return "score_not_numeric"
    if not math.isfinite(float(score)) or not 0.0 <= float(score) <= 1.0:
        return "score_out_of_range"
    return ""


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)
