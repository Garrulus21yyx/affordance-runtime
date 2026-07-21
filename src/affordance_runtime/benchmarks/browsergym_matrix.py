"""BrowserGym profile selection, matrix checkpoints, and official reporting."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from affordance_runtime.benchmarks.browsergym_miniwob_source import BROWSERGYM_MINIWOB_COMMIT
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult
from affordance_runtime.runtime import RuntimeStep

BROWSERGYM_VERSION = "0.14.3"

PR_SMOKE_TASKS = (
    "click-button",
    "enter-text",
    "choose-list",
    "click-dialog",
    "click-button-sequence",
    "form-sequence",
)


def browsergym_profile(task_ids: Sequence[str], profile: str) -> tuple[tuple[str, ...], tuple[int, ...]]:
    available = tuple(sorted(task_ids))
    if profile == "pr":
        return PR_SMOKE_TASKS, (0, 1, 2)
    if profile == "nightly":
        return available[:30], tuple(range(10))
    if profile == "release":
        return available, tuple(range(5))
    raise ValueError(f"unsupported BrowserGym profile: {profile}")


def write_browsergym_report(
    output_dir: Path,
    *,
    profile: str,
    registered_tasks: Sequence[str],
    selected_tasks: Sequence[str],
    seeds: Sequence[int],
    episodes: Sequence[BrowserGymEpisodeResult],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = tuple(selected_tasks)
    expected = {(task, seed) for task in selected for seed in seeds}
    observed = {(episode.task_id, episode.seed) for episode in episodes}
    missing = sorted(expected - observed)
    errors: list[str] = []
    if missing:
        errors.append(f"missing episodes: {len(missing)}")
    errors.extend(
        f"unsupported actions: {episode.task_id}:seed-{episode.seed}:{','.join(episode.unsupported_actions)}"
        for episode in episodes
        if episode.unsupported_actions
    )
    errors.extend(
        f"runtime failure: {episode.task_id}:seed-{episode.seed}:{episode.runtime_error}"
        for episode in episodes
        if episode.runtime_status != RuntimeStep.DONE.value
    )
    errors.extend(
        f"policy stopped: {episode.task_id}:seed-{episode.seed}"
        for episode in episodes
        if episode.policy_stopped
    )
    statistics = {task: _task_statistics([episode for episode in episodes if episode.task_id == task]) for task in selected}
    runtime_error_counts = Counter(
        episode.runtime_error or episode.runtime_status
        for episode in episodes
        if episode.runtime_status != RuntimeStep.DONE.value or episode.policy_stopped
    )
    report = {
        "schema_version": "browsergym-full-path-v1",
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
        "profile": profile,
        "official_track": True,
        "fault_injection": False,
        "registered_task_count": len(set(registered_tasks)),
        "selected_task_count": len(selected),
        "seed_count": len(tuple(seeds)),
        "expected_episode_count": len(expected),
        "observed_episode_count": len(episodes),
        "missing_episode_count": len(missing),
        "missing_episode_ids": [f"{task}:seed-{seed}" for task, seed in missing],
        "coverage_rate": len(observed & expected) / len(expected) if expected else 0.0,
        "official_success_rate": sum(episode.official_success for episode in episodes) / len(episodes) if episodes else 0.0,
        "mean_official_reward": sum(episode.official_reward for episode in episodes) / len(episodes) if episodes else 0.0,
        "task_statistics": statistics,
        "action_family_coverage": sorted({name for episode in episodes for name in episode.action_families}),
        "unsupported_actions": sorted({name for episode in episodes for name in episode.unsupported_actions}),
        "runtime_failure_count": sum(
            episode.runtime_status != RuntimeStep.DONE.value or episode.policy_stopped for episode in episodes
        ),
        "runtime_error_counts": dict(sorted(runtime_error_counts.items())),
        "episodes": [asdict(episode) for episode in episodes],
        "acceptance_errors": errors,
    }
    (output_dir / "browsergym-report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def browsergym_model_timeout_s(episode_timeout_s: float) -> float:
    """Reserve time for several planning turns inside a bounded episode."""

    return min(30.0, max(5.0, episode_timeout_s / 5.0))


def checkpoint_filename(task_id: str, seed: int) -> str:
    safe_task = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in task_id)
    return f"{safe_task}-seed-{seed}.json"


def prepare_browsergym_checkpoint_metadata(directory: Path, metadata: dict[str, Any], *, resume: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "matrix-metadata.json"
    episode_files = list(directory.glob("*-seed-*.json"))
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored != metadata:
            raise ValueError("BrowserGym checkpoint metadata does not match the requested matrix")
        return
    if resume and episode_files:
        raise ValueError("BrowserGym checkpoints lack matrix metadata; cannot safely resume")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def write_browsergym_checkpoint(directory: Path, episode: BrowserGymEpisodeResult) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / checkpoint_filename(episode.task_id, episode.seed)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(episode), indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def load_browsergym_checkpoints(
    directory: Path, expected: set[tuple[str, int]]
) -> dict[tuple[str, int], BrowserGymEpisodeResult]:
    if not directory.exists():
        return {}
    results: dict[tuple[str, int], BrowserGymEpisodeResult] = {}
    for path in directory.glob("*-seed-*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"invalid BrowserGym checkpoint: {path}")
        episode = BrowserGymEpisodeResult(**payload)
        key = (episode.task_id, episode.seed)
        if key in expected:
            if key in results:
                raise ValueError(f"duplicate BrowserGym checkpoint: {key[0]}:seed-{key[1]}")
            results[key] = episode
    return results


def _task_statistics(episodes: Sequence[BrowserGymEpisodeResult]) -> dict[str, float | int]:
    if not episodes:
        return {"episodes": 0, "success_rate": 0.0, "mean_reward": 0.0, "reward_variance": 0.0}
    rewards = [episode.official_reward for episode in episodes]
    mean = sum(rewards) / len(rewards)
    return {
        "episodes": len(episodes),
        "success_rate": sum(episode.official_success for episode in episodes) / len(episodes),
        "mean_reward": mean,
        "reward_variance": sum((reward - mean) ** 2 for reward in rewards) / len(rewards),
    }
