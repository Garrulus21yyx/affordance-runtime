"""BrowserGym profile selection, matrix checkpoints, and official reporting."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, Sequence

from affordance_runtime.benchmarks.browsergym_miniwob_source import BROWSERGYM_MINIWOB_COMMIT
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult
from affordance_runtime.runtime import RuntimeStep

BROWSERGYM_VERSION = "0.14.3"
BROWSERGYM_RUN_PROTOCOL_VERSION = "three-layer-breadth-first-v1"
BrowserGymProfile = Literal["smoke", "pr", "diagnostic", "nightly", "release"]

PR_SMOKE_TASKS = (
    "click-button",
    "enter-text",
    "choose-list",
    "click-dialog",
    "click-button-sequence",
    "form-sequence",
)

# A versioned, action-family-stratified nightly manifest.  This is deliberately
# independent of Gym's registration iteration order; suite runners still report
# every missing manifest task rather than silently shrinking coverage.
NIGHTLY_TASK_MANIFEST_VERSION = "miniwob-action-family-v1"
NIGHTLY_ACTION_FAMILY_MANIFEST: dict[str, tuple[str, ...]] = {
    "activate": ("click-button", "click-checkboxes", "click-dialog"),
    "form": ("form-sequence", "form-sequence-2", "form-sequence-3"),
    "text_entry": ("enter-text", "enter-text-2", "enter-date"),
    "selection": ("choose-list", "click-option", "use-autocomplete"),
    "keyboard": ("focus-text", "copy-paste", "text-transform"),
    "scroll": ("scroll-text", "scroll-text-2", "click-scroll-list"),
    "drag": ("drag-box", "drag-items", "drag-sort-numbers"),
    "navigation": ("navigate-tree", "search-engine", "click-link"),
    "read": ("read-table", "email-inbox", "phone-book"),
    "spatial_value": ("use-slider", "grid-coordinate", "circle-center"),
}
NIGHTLY_TASKS = tuple(task for family in NIGHTLY_ACTION_FAMILY_MANIFEST.values() for task in family)


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


def browsergym_episode_schedule(
    task_ids: Sequence[str], seeds: Sequence[int]
) -> tuple[tuple[str, int], ...]:
    """Return the protocol's seed-major (breadth-first) episode order."""

    return tuple((task_id, seed) for seed in seeds for task_id in task_ids)


def browsergym_failure_envelope(
    episode: BrowserGymEpisodeResult,
    *,
    task_family_map: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return the redacted, clusterable diagnosis for an ordinary failure."""

    if episode.official_success:
        return None
    signature = _failure_signature(episode)
    root_layer = _failure_root_layer(episode, signature)
    return {
        "task": episode.task_id,
        "family": (task_family_map or {}).get(episode.task_id, "unmapped"),
        "seed": episode.seed,
        "phase": _failure_phase(root_layer),
        "failure_signature": signature,
        "root_layer": root_layer,
        "action_kind": episode.action_families[-1] if episode.action_families else "",
        "context_size": episode.planner_context_size,
        "context_truncation": episode.planner_context_truncation,
        "affordance_count": episode.planner_affordance_count,
        "permitted_action_kinds": list(episode.planner_permitted_action_kinds),
        "required_evidence_present": episode.terminated,
        "last_verified_step": episode.last_verified_step,
        "provider_runtime_status": {
            "runtime_status": episode.runtime_status,
            "provider_failures": list(episode.provider_failures),
            "rate_limit_retry_count": episode.rate_limit_retry_count,
            "transient_retry_count": episode.transient_retry_count,
        },
        "artifact_refs": [episode.trace_path] if episode.trace_path else [],
    }


def cluster_browsergym_failure_envelopes(envelopes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group evidence before deciding which layer, if any, should change."""

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for envelope in envelopes:
        key = (
            str(envelope["root_layer"]),
            str(envelope["failure_signature"]),
            str(envelope["family"]),
        )
        groups.setdefault(key, []).append(envelope)
    return [
        {
            "root_layer": root_layer,
            "failure_signature": signature,
            "family": family,
            "episode_count": len(items),
            "episode_ids": [f"{item['task']}:seed-{item['seed']}" for item in items],
        }
        for (root_layer, signature, family), items in sorted(groups.items())
    ]


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
    return schema_compatible_episode_observed, browsergym_batch_circuit_breaker(
        consecutive_failures
    )


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
    family_map = {
        task: family for family, tasks in NIGHTLY_ACTION_FAMILY_MANIFEST.items() for task in tasks
    }
    failure_envelopes = [
        envelope
        for episode in episodes
        if (envelope := browsergym_failure_envelope(episode, task_family_map=family_map)) is not None
    ]
    runtime_error_counts = Counter(
        episode.runtime_error or episode.runtime_status
        for episode in episodes
        if episode.runtime_status != RuntimeStep.DONE.value or episode.policy_stopped
    )
    report = {
        "schema_version": "browsergym-full-path-v2",
        "run_protocol_version": BROWSERGYM_RUN_PROTOCOL_VERSION,
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
        "profile": profile,
        "nightly_manifest_version": NIGHTLY_TASK_MANIFEST_VERSION if profile == "nightly" else "",
        "nightly_action_families": (
            {family: list(tasks) for family, tasks in NIGHTLY_ACTION_FAMILY_MANIFEST.items()}
            if profile == "nightly"
            else {}
        ),
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
        "execution_order": [
            f"{task_id}:seed-{seed}" for task_id, seed in browsergym_episode_schedule(selected, seeds)
        ],
        "failure_envelopes": failure_envelopes,
        "failure_clusters": cluster_browsergym_failure_envelopes(failure_envelopes),
        "unsupported_actions": sorted({name for episode in episodes for name in episode.unsupported_actions}),
        "runtime_failure_count": sum(
            episode.runtime_status != RuntimeStep.DONE.value or episode.policy_stopped for episode in episodes
        ),
        "runtime_error_counts": dict(sorted(runtime_error_counts.items())),
        "model_call_statistics": {
            "call_count": sum(episode.model_call_count for episode in episodes),
            "latency_ms": round(sum(episode.model_call_latency_ms for episode in episodes), 3),
            "rate_limit_retry_count": sum(episode.rate_limit_retry_count for episode in episodes),
            "transient_retry_count": sum(episode.transient_retry_count for episode in episodes),
            "provider_failure_counts": dict(
                sorted(Counter(failure for episode in episodes for failure in episode.provider_failures).items())
            ),
        },
        "adaptive_runtime_statistics": {
            "route_selection_count": sum(
                episode.route_selection_count for episode in episodes
            ),
            "route_source_counts": dict(
                sorted(
                    Counter(
                        source for episode in episodes for source in episode.route_sources
                    ).items()
                )
            ),
            "visual_route_count": sum(episode.visual_route_count for episode in episodes),
            "fallback_route_count": sum(episode.fallback_route_count for episode in episodes),
            "targeted_perception_count": sum(
                episode.targeted_perception_count for episode in episodes
            ),
            "source_conflict_count": sum(
                episode.source_conflict_count for episode in episodes
            ),
            "task_skill_activated_count": sum(
                episode.task_skill_activated_count for episode in episodes
            ),
            "task_skill_completed_count": sum(
                episode.task_skill_completed_count for episode in episodes
            ),
            "task_skill_fallthrough_count": sum(
                episode.task_skill_fallthrough_count for episode in episodes
            ),
        },
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


def _failure_signature(episode: BrowserGymEpisodeResult) -> str:
    details = " ".join([episode.runtime_error, *episode.provider_failures]).casefold()
    if "safety_violation" in details:
        return "safety_violation"
    if any(marker in details for marker in ("namespace", "source server", "miniwob", "oracle")):
        return "source_or_oracle_unavailable"
    if "model call budget exhausted" in details:
        return "model_call_budget_exhausted"
    if any(marker in details for marker in ("schema", "validation", "structuredmodelerror")):
        return "schema_incompatible"
    if any(marker in details for marker in ("artifact", "checkpoint")):
        return "artifact_checkpoint_failure"
    if any(marker in details for marker in ("version drift", "metadata does not match")):
        return "version_drift"
    if episode.provider_failures or any(marker in details for marker in ("provider failure", "429", "quota", "rate_limit")):
        return "provider_failure"
    if (
        episode.runtime_status == "waiting_clarification"
        and "mouse_click" in episode.action_families
        and episode.action_count > 0
        and not episode.terminated
    ):
        return "grounding_unverified"
    if episode.runtime_status == "waiting_clarification" and episode.planner_affordance_count == 0:
        return "observation_no_affordances"
    if episode.runtime_status == "waiting_clarification":
        return "planner_waiting_clarification"
    if episode.runtime_error == "verification_failed":
        return "verification_failed"
    if episode.runtime_error == "execution_failed":
        return "execution_failed"
    if episode.unsupported_actions:
        return "unsupported_action"
    if episode.policy_stopped:
        return "planner_stopped"
    if episode.runtime_status != RuntimeStep.DONE.value:
        return "runtime_failure"
    if not episode.terminated:
        return "terminal_evidence_missing"
    return "official_reward_zero"


def _failure_root_layer(episode: BrowserGymEpisodeResult, signature: str) -> str:
    del episode
    if signature in {"provider_failure", "source_or_oracle_unavailable", "artifact_checkpoint_failure", "version_drift"}:
        return "PROVIDER / INFRA"
    if signature == "schema_incompatible":
        return "CONTRACT / FIELD_BINDING"
    if signature == "model_call_budget_exhausted":
        return "INTENT / PLANNING"
    if signature == "observation_no_affordances":
        return "OBSERVATION / CONTEXT"
    if signature == "safety_violation":
        return "SAFETY"
    if signature == "unsupported_action":
        return "GROUNDING / ROUTING"
    if signature == "grounding_unverified":
        return "GROUNDING / ROUTING"
    if signature == "planner_stopped":
        return "INTENT / PLANNING"
    if signature == "planner_waiting_clarification":
        return "INTENT / PLANNING"
    if signature == "verification_failed":
        return "VERIFICATION"
    if signature == "execution_failed":
        return "EXECUTION"
    if signature == "terminal_evidence_missing":
        return "VERIFICATION"
    if signature == "official_reward_zero":
        return "EXECUTION"
    return "RECOVERY"


def _failure_phase(root_layer: str) -> str:
    return {
        "PROVIDER / INFRA": "runtime",
        "OBSERVATION / CONTEXT": "observation",
        "CONTRACT / FIELD_BINDING": "binding",
        "GROUNDING / ROUTING": "routing",
        "INTENT / PLANNING": "planning",
        "VERIFICATION": "verification",
        "EXECUTION": "execution",
        "RECOVERY": "recovery",
        "SAFETY": "safety",
    }[root_layer]
