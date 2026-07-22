"""BrowserGym profile selection, matrix checkpoints, and official reporting."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from affordance_runtime.benchmarks import browsergym_protocol as _browsergym_protocol
from affordance_runtime.benchmarks import browsergym_report as _browsergym_report
from affordance_runtime.benchmarks.browsergym_protocol import (
    NIGHTLY_TASKS,
    PR_SMOKE_TASKS,
    BrowserGymProfile,
)
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult
from affordance_runtime.runtime import RuntimeStep

BROWSERGYM_RUN_PROTOCOL_VERSION = _browsergym_protocol.BROWSERGYM_RUN_PROTOCOL_VERSION
BROWSERGYM_VERSION = _browsergym_protocol.BROWSERGYM_VERSION
NIGHTLY_ACTION_FAMILY_MANIFEST = _browsergym_protocol.NIGHTLY_ACTION_FAMILY_MANIFEST
NIGHTLY_TASK_MANIFEST_VERSION = _browsergym_protocol.NIGHTLY_TASK_MANIFEST_VERSION
browsergym_episode_schedule = _browsergym_protocol.browsergym_episode_schedule
browsergym_failure_envelope = _browsergym_report.browsergym_failure_envelope
cluster_browsergym_failure_envelopes = _browsergym_report.cluster_browsergym_failure_envelopes
write_browsergym_report = _browsergym_report.write_browsergym_report


def browsergym_profile(task_ids: Sequence[str], profile: BrowserGymProfile) -> tuple[tuple[str, ...], tuple[int, ...]]:
    available = tuple(sorted(task_ids))
    if profile == "smoke":
        return PR_SMOKE_TASKS, (0,)
    if profile == "pr":
        return PR_SMOKE_TASKS, (0, 1, 2)
    if profile == "diagnostic":
        return NIGHTLY_TASKS, (0, 1)
    if profile == "nightly":
        return NIGHTLY_TASKS, tuple(range(10))
    if profile == "release":
        return available, tuple(range(5))
    raise ValueError(f"unsupported BrowserGym profile: {profile}")


def browsergym_batch_circuit_breaker(envelopes: Sequence[dict[str, Any]]) -> str:
    """Return a permitted batch-wide stop reason, otherwise an empty string.

    Single task reward/context/grounding failures deliberately never stop a
    diagnostic or frozen batch.
    """

    immediate = {
        "safety_violation",
        "source_or_oracle_unavailable",
        "artifact_checkpoint_failure",
        "version_drift",
    }
    for envelope in envelopes:
        if envelope["failure_signature"] in immediate:
            return str(envelope["failure_signature"])
    recent = list(envelopes[-2:])
    if len(recent) == 2 and all(item["failure_signature"] == "provider_failure" for item in recent):
        return "provider_unavailable_or_continuous_rate_limit"
    if len(recent) == 2 and all(item["failure_signature"] == "schema_incompatible" for item in recent):
        return "schema_incompatible"
    return ""


def update_browsergym_batch_circuit_state(
    consecutive_failures: list[dict[str, Any]],
    episode: BrowserGymEpisodeResult,
    envelope: dict[str, Any] | None,
    *,
    schema_compatible_episode_observed: bool,
) -> tuple[bool, str]:
    """Update batch-wide failure state without promoting task-local errors.

    Once any ordinary episode completes through the shared schema/runtime
    boundary, later proposal validation errors cannot mean that *all* results
    in the batch are invalid.
    """

    if envelope is None:
        consecutive_failures.clear()
        return True, ""
    if episode.runtime_status == RuntimeStep.DONE.value and not episode.policy_stopped:
        consecutive_failures.clear()
        return True, ""
    if envelope["failure_signature"] == "schema_incompatible" and schema_compatible_episode_observed:
        return True, ""
    consecutive_failures.append(envelope)
    return schema_compatible_episode_observed, browsergym_batch_circuit_breaker(consecutive_failures)


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
        if not resume:
            raise ValueError("BrowserGym output already belongs to an immutable run; use a new output directory")
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
