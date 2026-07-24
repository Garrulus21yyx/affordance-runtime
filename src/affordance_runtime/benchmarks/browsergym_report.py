"""Failure taxonomy and aggregate BrowserGym report publication."""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from affordance_runtime.benchmarks.browsergym_miniwob_source import BROWSERGYM_MINIWOB_COMMIT
from affordance_runtime.benchmarks.browsergym_protocol import (
    BROWSERGYM_RUN_PROTOCOL_VERSION,
    BROWSERGYM_VERSION,
    NIGHTLY_ACTION_FAMILY_MANIFEST,
    NIGHTLY_TASK_MANIFEST_VERSION,
    browsergym_episode_schedule,
)
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult
from affordance_runtime.evaluation_audit import (
    EvaluationBatchStatus,
    EvaluationBatchStop,
    EvaluationRunAudit,
    EvaluationRunIdentity,
    build_evaluation_run_audit,
)
from affordance_runtime.runtime import RuntimeStep


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
        "family": _failure_family(episode, task_family_map or {}),
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


def cluster_browsergym_failures_by_runtime_owner(
    envelopes: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate across task families before selecting an owning-layer repair."""

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for envelope in envelopes:
        key = (str(envelope["root_layer"]), str(envelope["failure_signature"]))
        groups.setdefault(key, []).append(envelope)
    return [
        {
            "root_layer": root_layer,
            "failure_signature": signature,
            "families": sorted({str(item["family"]) for item in items}),
            "task_count": len({str(item["task"]) for item in items}),
            "episode_count": len(items),
            "episode_ids": [f"{item['task']}:seed-{item['seed']}" for item in items],
        }
        for (root_layer, signature), items in sorted(groups.items())
    ]


def write_browsergym_report(
    output_dir: Path,
    *,
    profile: str,
    registered_tasks: Sequence[str],
    selected_tasks: Sequence[str],
    seeds: Sequence[int],
    episodes: Sequence[BrowserGymEpisodeResult],
    evaluation_identity: EvaluationRunIdentity | None = None,
    resumed_episode_ids: Sequence[str] = (),
    batch_stop: EvaluationBatchStop | None = None,
    interrupted: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = tuple(selected_tasks)
    selected_seeds = tuple(seeds)
    if len(set(selected)) != len(selected):
        raise ValueError("BrowserGym report selected tasks must be unique")
    if len(set(selected_seeds)) != len(selected_seeds):
        raise ValueError("BrowserGym report seeds must be unique")
    expected = {(task, seed) for task in selected for seed in selected_seeds}
    for episode in episodes:
        validate_browsergym_episode_result(episode)
    observed = {(episode.task_id, episode.seed) for episode in episodes}
    if len(observed) != len(episodes):
        raise ValueError("BrowserGym report contains duplicate episode results")
    unexpected = sorted(observed - expected)
    if unexpected:
        raise ValueError("BrowserGym report contains episodes outside the selected matrix")
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
        f"policy stopped: {episode.task_id}:seed-{episode.seed}" for episode in episodes if episode.policy_stopped
    )
    statistics = {
        task: _task_statistics([episode for episode in episodes if episode.task_id == task]) for task in selected
    }
    family_map = {task: family for family, tasks in NIGHTLY_ACTION_FAMILY_MANIFEST.items() for task in tasks}
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
    identity = evaluation_identity or EvaluationRunIdentity.from_dimensions(
        {
            "run_protocol_version": BROWSERGYM_RUN_PROTOCOL_VERSION,
            "browsergym_version": BROWSERGYM_VERSION,
            "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
            "profile": profile,
            "selected_task_ids": list(selected),
            "seeds": list(selected_seeds),
        }
    )
    scheduled_case_ids = [
        _case_id(task_id, seed)
        for task_id, seed in browsergym_episode_schedule(selected, selected_seeds)
    ]
    observed_case_ids = [_case_id(episode.task_id, episode.seed) for episode in episodes]
    runtime_failed_case_ids = [
        _case_id(episode.task_id, episode.seed)
        for episode in episodes
        if episode.runtime_status != RuntimeStep.DONE.value or episode.policy_stopped
    ]
    external_failed_case_ids = [
        _case_id(episode.task_id, episode.seed)
        for episode in episodes
        if not episode.official_success
    ]
    failed_case_ids = sorted(set(runtime_failed_case_ids) | set(external_failed_case_ids))
    audit = build_evaluation_run_audit(
        identity=identity,
        scheduled_case_ids=scheduled_case_ids,
        observed_case_ids=observed_case_ids,
        failed_case_ids=failed_case_ids,
        runtime_failed_case_ids=runtime_failed_case_ids,
        external_failed_case_ids=external_failed_case_ids,
        resumed_case_ids=resumed_episode_ids,
        stop=batch_stop,
        interrupted=interrupted,
    )
    browser_versions = sorted(
        {episode.browser_version for episode in episodes if episode.browser_version}
    )
    if len(browser_versions) > 1 and (
        batch_stop is None or batch_stop.reason != "version_drift"
    ):
        raise ValueError("BrowserGym report mixes browser versions without version-drift invalidation")
    clustered = (
        cluster_browsergym_failure_envelopes(failure_envelopes)
        if audit.repair_selection_ready
        else []
    )
    owner_clusters = (
        cluster_browsergym_failures_by_runtime_owner(failure_envelopes)
        if audit.repair_selection_ready
        else []
    )
    report = {
        "schema_version": "browsergym-full-path-v3",
        "run_protocol_version": BROWSERGYM_RUN_PROTOCOL_VERSION,
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
        "profile": profile,
        "task_manifest_version": (
            NIGHTLY_TASK_MANIFEST_VERSION if profile in {"diagnostic", "nightly"} else ""
        ),
        "task_action_families": (
            {family: list(tasks) for family, tasks in NIGHTLY_ACTION_FAMILY_MANIFEST.items()}
            if profile in {"diagnostic", "nightly"}
            else {}
        ),
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
        "seed_count": len(selected_seeds),
        "expected_episode_count": len(expected),
        "observed_episode_count": audit.observed_count,
        "failed_episode_count": audit.failed_count,
        "unrun_episode_count": audit.unrun_count,
        "invalidated_episode_count": audit.invalidated_count,
        "resumed_episode_count": audit.resumed_count,
        "missing_episode_count": len(missing),
        "missing_episode_ids": [item.case_id for item in audit.cases if not item.observed],
        "coverage_rate": len(observed & expected) / len(expected) if expected else 0.0,
        "official_success_rate": sum(episode.official_success for episode in episodes) / len(episodes)
        if episodes
        else 0.0,
        "mean_official_reward": sum(episode.official_reward for episode in episodes) / len(episodes)
        if episodes
        else 0.0,
        "task_statistics": statistics,
        "action_family_coverage": sorted({name for episode in episodes for name in episode.action_families}),
        "execution_order": [
            f"{task_id}:seed-{seed}"
            for task_id, seed in browsergym_episode_schedule(selected, selected_seeds)
        ],
        "failure_envelopes": failure_envelopes,
        "failure_clusters": clustered,
        "runtime_owner_failure_clusters": owner_clusters,
        "unclustered_failure_envelope_count": (
            0 if audit.repair_selection_ready else len(failure_envelopes)
        ),
        "repair_selection_ready": audit.repair_selection_ready,
        "unsupported_actions": sorted({name for episode in episodes for name in episode.unsupported_actions}),
        "runtime_failure_count": sum(
            episode.runtime_status != RuntimeStep.DONE.value or episode.policy_stopped for episode in episodes
        ),
        "runtime_error_counts": dict(sorted(runtime_error_counts.items())),
        "runtime_verification_outcomes": {
            "passed": audit.observed_count - audit.runtime_failed_count,
            "failed": audit.runtime_failed_count,
        },
        "external_evaluator_outcomes": {
            "passed": audit.observed_count - audit.external_failed_count,
            "failed": audit.external_failed_count,
        },
        "external_metrics_scope": "observed_cases_only",
        "score_evidence_eligible": audit.status.value == "complete",
        "official_score_claimed": False,
        "score_promotion_gate": "m8.2b-new-strict-frozen-evaluation-required",
        "evaluation_run_identity": identity.model_dump(mode="json"),
        "evaluation_audit": audit.model_dump(mode="json"),
        "observed_browser_versions": browser_versions,
        "run_complete": audit.status == EvaluationBatchStatus.COMPLETE,
        "batch_status": audit.status.value,
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
            "route_selection_count": sum(episode.route_selection_count for episode in episodes),
            "route_source_counts": dict(
                sorted(Counter(source for episode in episodes for source in episode.route_sources).items())
            ),
            "visual_route_count": sum(episode.visual_route_count for episode in episodes),
            "fallback_route_count": sum(episode.fallback_route_count for episode in episodes),
            "targeted_perception_count": sum(episode.targeted_perception_count for episode in episodes),
            "source_conflict_count": sum(episode.source_conflict_count for episode in episodes),
            "task_skill_activated_count": sum(episode.task_skill_activated_count for episode in episodes),
            "task_skill_completed_count": sum(episode.task_skill_completed_count for episode in episodes),
            "task_skill_fallthrough_count": sum(episode.task_skill_fallthrough_count for episode in episodes),
        },
        "episodes": [asdict(episode) for episode in episodes],
        "acceptance_errors": errors,
    }
    publish_browsergym_report(output_dir, report)
    return report


def validate_browsergym_episode_result(
    episode: BrowserGymEpisodeResult,
    *,
    expected_case: tuple[str, int] | None = None,
) -> None:
    """Reject corrupt or misbound external-evaluator results before checkpointing."""

    if expected_case is not None and (episode.task_id, episode.seed) != expected_case:
        raise ValueError("BrowserGym episode result does not match the scheduled case")
    if not math.isfinite(episode.official_reward):
        raise ValueError("BrowserGym official reward must be finite")
    if episode.action_count < 0 or episode.model_call_count < 0:
        raise ValueError("BrowserGym episode counters must be non-negative")
    if episode.rate_limit_retry_count < 0 or episode.transient_retry_count < 0:
        raise ValueError("BrowserGym retry counters must be non-negative")


def publish_browsergym_report(output_dir: Path, report: dict[str, Any]) -> None:
    """Atomically publish the reconciled report before it becomes evidence."""

    validate_browsergym_report(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "browsergym-report.json"
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory_fd = os.open(output_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def validate_browsergym_report(report: dict[str, Any]) -> None:
    """Fail closed when aggregate claims diverge from the typed case ledger."""

    if report.get("schema_version") != "browsergym-full-path-v3":
        raise ValueError("unsupported BrowserGym G4 report schema")
    try:
        identity = EvaluationRunIdentity.model_validate_json(
            json.dumps(report["evaluation_run_identity"])
        )
        audit = EvaluationRunAudit.model_validate_json(
            json.dumps(report["evaluation_audit"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("BrowserGym report lacks a valid typed evaluation ledger") from exc
    if audit.identity_digest != identity.digest:
        raise ValueError("BrowserGym report identity and audit digest disagree")
    raw_episodes = report.get("episodes")
    if not isinstance(raw_episodes, list):
        raise ValueError("BrowserGym report episodes must be a list")
    try:
        episodes = [
            BrowserGymEpisodeResult(**item)
            for item in raw_episodes
            if isinstance(item, dict)
        ]
    except (TypeError, ValueError) as exc:
        raise ValueError("BrowserGym report contains an invalid episode result") from exc
    if len(episodes) != len(raw_episodes):
        raise ValueError("BrowserGym report contains a non-object episode result")
    for episode in episodes:
        validate_browsergym_episode_result(episode)
    episode_ids = {_case_id(item.task_id, item.seed) for item in episodes}
    if len(episode_ids) != len(episodes):
        raise ValueError("BrowserGym report contains duplicate episode results")
    ledger_observed = {item.case_id for item in audit.cases if item.observed}
    if episode_ids != ledger_observed:
        raise ValueError("BrowserGym episode payloads disagree with the typed case ledger")
    runtime_failed_ids = {
        _case_id(item.task_id, item.seed)
        for item in episodes
        if item.runtime_status != RuntimeStep.DONE.value or item.policy_stopped
    }
    external_failed_ids = {
        _case_id(item.task_id, item.seed)
        for item in episodes
        if not item.official_success
    }
    if runtime_failed_ids != {
        item.case_id for item in audit.cases if item.runtime_failed
    } or external_failed_ids != {
        item.case_id for item in audit.cases if item.external_failed
    }:
        raise ValueError("BrowserGym episode outcomes disagree with the typed case ledger")
    expected_fields = {
        "expected_episode_count": audit.scheduled_count,
        "observed_episode_count": audit.observed_count,
        "failed_episode_count": audit.failed_count,
        "unrun_episode_count": audit.unrun_count,
        "missing_episode_count": audit.unrun_count,
        "invalidated_episode_count": audit.invalidated_count,
        "resumed_episode_count": audit.resumed_count,
        "runtime_failure_count": audit.runtime_failed_count,
        "repair_selection_ready": audit.repair_selection_ready,
        "run_complete": audit.status == EvaluationBatchStatus.COMPLETE,
        "batch_status": audit.status.value,
        "score_evidence_eligible": audit.status == EvaluationBatchStatus.COMPLETE,
    }
    for name, expected in expected_fields.items():
        if report.get(name) != expected:
            raise ValueError(f"BrowserGym report field {name} disagrees with evaluation ledger")
    expected_missing_ids = [item.case_id for item in audit.cases if not item.observed]
    if report.get("missing_episode_ids") != expected_missing_ids:
        raise ValueError("BrowserGym missing case ids disagree with evaluation ledger")
    expected_success_rate = (
        sum(item.official_success for item in episodes) / len(episodes)
        if episodes
        else 0.0
    )
    expected_mean_reward = (
        sum(item.official_reward for item in episodes) / len(episodes)
        if episodes
        else 0.0
    )
    expected_coverage = audit.observed_count / audit.scheduled_count if audit.scheduled_count else 0.0
    if report.get("official_success_rate") != expected_success_rate:
        raise ValueError("BrowserGym success aggregate disagrees with episode results")
    if report.get("mean_official_reward") != expected_mean_reward:
        raise ValueError("BrowserGym reward aggregate disagrees with episode results")
    if report.get("coverage_rate") != expected_coverage:
        raise ValueError("BrowserGym coverage aggregate disagrees with evaluation ledger")
    if report.get("official_score_claimed") is not False:
        raise ValueError("BrowserGym evidence reports cannot claim an official promoted score")
    browser_versions = report.get("observed_browser_versions")
    if not isinstance(browser_versions, list) or not all(
        isinstance(item, str) and item for item in browser_versions
    ):
        if browser_versions != []:
            raise ValueError("BrowserGym observed browser versions must be non-empty strings")
    if len(set(browser_versions)) != len(browser_versions):
        raise ValueError("BrowserGym observed browser versions contain duplicates")
    if len(browser_versions) > 1 and (
        audit.stop is None or audit.stop.reason != "version_drift"
    ):
        raise ValueError("BrowserGym mixed browser versions require version-drift invalidation")
    runtime_outcomes = report.get("runtime_verification_outcomes")
    external_outcomes = report.get("external_evaluator_outcomes")
    if runtime_outcomes != {
        "passed": audit.observed_count - audit.runtime_failed_count,
        "failed": audit.runtime_failed_count,
    }:
        raise ValueError("BrowserGym Runtime outcome counts disagree with evaluation ledger")
    if external_outcomes != {
        "passed": audit.observed_count - audit.external_failed_count,
        "failed": audit.external_failed_count,
    }:
        raise ValueError("BrowserGym external outcome counts disagree with evaluation ledger")
    envelopes = report.get("failure_envelopes")
    if not isinstance(envelopes, list):
        raise ValueError("BrowserGym failure envelopes must be a list")
    family_map = {
        task: family
        for family, tasks in NIGHTLY_ACTION_FAMILY_MANIFEST.items()
        for task in tasks
    }
    expected_envelopes = [
        envelope
        for episode in episodes
        if (
            envelope := browsergym_failure_envelope(
                episode,
                task_family_map=family_map,
            )
        )
        is not None
    ]
    if envelopes != expected_envelopes:
        raise ValueError("BrowserGym failure envelopes disagree with episode evidence")
    if audit.repair_selection_ready:
        if report.get("failure_clusters") != cluster_browsergym_failure_envelopes(envelopes):
            raise ValueError("BrowserGym failure clusters do not match closed collection evidence")
        if report.get("runtime_owner_failure_clusters") != cluster_browsergym_failures_by_runtime_owner(
            envelopes
        ):
            raise ValueError("BrowserGym owner clusters do not match closed collection evidence")
        if report.get("unclustered_failure_envelope_count") != 0:
            raise ValueError("closed BrowserGym collection cannot retain unclustered envelopes")
    elif (
        report.get("failure_clusters")
        or report.get("runtime_owner_failure_clusters")
        or report.get("unclustered_failure_envelope_count") != len(envelopes)
    ):
        raise ValueError("incomplete BrowserGym collection cannot publish formal failure clusters")


def _case_id(task_id: str, seed: int) -> str:
    return f"{task_id}:seed-{seed}"


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


def _failure_family(episode: BrowserGymEpisodeResult, task_family_map: dict[str, str]) -> str:
    """Prefer fixed protocol metadata, then bounded observed action evidence."""

    declared = task_family_map.get(episode.task_id)
    if declared:
        return declared
    semantic_action_families = {
        "click": "activate",
        "click_no_navigation": "activate",
        "dblclick": "activate",
        "mouse_click": "point_activate",
        "fill": "text_entry",
        "type_text_with_events": "text_entry",
        "select_option": "selection",
        "press": "keyboard",
        "scroll": "scroll",
        "drag_and_drop": "drag",
        "mouse_drag_and_drop": "drag",
    }
    for action in reversed(episode.action_families):
        normalized = semantic_action_families.get(action)
        if normalized:
            return f"observed:{normalized}"
    return "unresolved:no_action_evidence"


def _failure_signature(episode: BrowserGymEpisodeResult) -> str:
    details = " ".join([episode.runtime_error, *episode.provider_failures]).casefold()
    if "safety_violation" in details:
        return "safety_violation"
    if any(marker in details for marker in ("namespace", "source server", "miniwob", "oracle")):
        return "source_or_oracle_unavailable"
    if "model call budget exhausted" in details:
        return "model_call_budget_exhausted"
    if "intent compilation " in details:
        return "intent_compilation_rejected"
    if any(marker in details for marker in ("schema", "validation", "structuredmodelerror")):
        return "schema_incompatible"
    if any(marker in details for marker in ("artifact", "checkpoint")):
        return "artifact_checkpoint_failure"
    if any(marker in details for marker in ("version drift", "metadata does not match")):
        return "version_drift"
    if episode.provider_failures or any(
        marker in details for marker in ("provider failure", "429", "quota", "rate_limit")
    ):
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
    if signature in {
        "provider_failure",
        "source_or_oracle_unavailable",
        "artifact_checkpoint_failure",
        "version_drift",
    }:
        return "PROVIDER / INFRA"
    if signature == "schema_incompatible":
        return "CONTRACT / FIELD_BINDING"
    if signature in {"model_call_budget_exhausted", "intent_compilation_rejected"}:
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
