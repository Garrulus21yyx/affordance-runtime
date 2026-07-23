"""Optional BrowserGym bridge with typed actions and full Coordinator traversal."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from queue import Empty
from typing import Any, Sequence, cast

from affordance_runtime.benchmarks import browsergym_action_schema as _browsergym_action_schema
from affordance_runtime.benchmarks import browsergym_encoder as _browsergym_encoder
from affordance_runtime.benchmarks import browsergym_episode_runner as _browsergym_episode_runner
from affordance_runtime.benchmarks import browsergym_observer as _browsergym_observer
from affordance_runtime.benchmarks import browsergym_types as _browsergym_types
from affordance_runtime.benchmarks.browsergym_action_schema import (
    BROWSERGYM_ACTION_ARGUMENTS as _BROWSERGYM_ACTION_ARGUMENTS,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    BROWSERGYM_VERSION,
    NIGHTLY_ACTION_FAMILY_MANIFEST,
    NIGHTLY_TASK_MANIFEST_VERSION,
    BrowserGymProfile,
    browsergym_episode_schedule,
    browsergym_failure_envelope,
    browsergym_profile,
    write_browsergym_report,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    PR_SMOKE_TASKS as _PR_SMOKE_TASKS,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    browsergym_batch_circuit_breaker as _browsergym_batch_circuit_breaker,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    cluster_browsergym_failure_envelopes as _cluster_browsergym_failure_envelopes,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    load_browsergym_checkpoints as _load_browsergym_checkpoints,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    prepare_browsergym_checkpoint_metadata as _prepare_browsergym_checkpoint_metadata,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    update_browsergym_batch_circuit_state as _update_browsergym_batch_circuit_state,
)
from affordance_runtime.benchmarks.browsergym_matrix import (
    write_browsergym_checkpoint as _write_browsergym_checkpoint,
)
from affordance_runtime.benchmarks.browsergym_miniwob_source import (
    BROWSERGYM_MINIWOB_COMMIT,
    ensure_browsergym_miniwob,
    registered_miniwob_tasks,
)
from affordance_runtime.benchmarks.browsergym_types import (
    BrowserGymEnvironment,
    BrowserGymEpisodeResult,
)
from affordance_runtime.generalist_planner import (
    GENERALIST_PLANNER_CONTEXT_POLICY_VERSION,
    GeneralistPlannerProfile,
    PlannerProposalCandidate,
    historical_compatibility_semantic_compiler_registry,
    planner_prompt_version,
)
from affordance_runtime.model_port import ModelPort
from affordance_runtime.runtime import RuntimeStep
from affordance_runtime.semantic_compilers import SemanticCompilerRegistry
from affordance_runtime.visual_grounding import (
    VisualGrounderPort,
    VisualRegionProposerPort,
)

# Compatibility export for callers that used the original bridge module.
BROWSERGYM_ACTION_ARGUMENTS = _BROWSERGYM_ACTION_ARGUMENTS
# Nightly selection metadata remains available from the public bridge facade.
# Keeping this here avoids coupling benchmark callers to the matrix module split.
NIGHTLY_MANIFEST_VERSION = NIGHTLY_TASK_MANIFEST_VERSION
NIGHTLY_ACTION_FAMILIES = NIGHTLY_ACTION_FAMILY_MANIFEST
PR_SMOKE_TASKS = _PR_SMOKE_TASKS
cluster_browsergym_failure_envelopes = _cluster_browsergym_failure_envelopes
browsergym_batch_circuit_breaker = _browsergym_batch_circuit_breaker
update_browsergym_batch_circuit_state = _update_browsergym_batch_circuit_state
_fuse_visual_candidates = _browsergym_observer.fuse_visual_candidates
_json_safe = _browsergym_observer.json_safe
_refresh_dom_grounding_candidates = _browsergym_observer.refresh_dom_grounding_candidates
_visual_fallback_affordance = _browsergym_observer.visual_fallback_affordance
BrowserGymGestureEncoder = _browsergym_encoder.BrowserGymGestureEncoder
BrowserGymPointEncoder = _browsergym_encoder.BrowserGymPointEncoder
BrowserGymContractBuilder = _browsergym_encoder.BrowserGymContractBuilder
GeneralistBrowserGymContractBuilder = _browsergym_encoder.GeneralistBrowserGymContractBuilder
_browsergym_action_verifiers = _browsergym_encoder.browsergym_action_verifiers
_browsergym_fill_value = _browsergym_encoder.browsergym_fill_value
_browsergym_requires_keyboard_events = _browsergym_encoder.browsergym_requires_keyboard_events
_is_sortable_list_binding = _browsergym_encoder.is_sortable_list_binding
_viewport_box = _browsergym_encoder.viewport_box
BrowserGymAction = _browsergym_action_schema.BrowserGymAction
BrowserGymEpisodeState = _browsergym_types.BrowserGymEpisodeState
BrowserGymPolicyRequest = _browsergym_types.BrowserGymPolicyRequest
BrowserGymObserver = _browsergym_observer.BrowserGymObserver
BROWSERGYM_PAGE_ACTION_TIMEOUT_MS = _browsergym_episode_runner.BROWSERGYM_PAGE_ACTION_TIMEOUT_MS
BROWSERGYM_PLANNER_MAX_TOKENS = _browsergym_episode_runner.BROWSERGYM_PLANNER_MAX_TOKENS
BROWSERGYM_TERMINAL_COMPLETION_POLICY = _browsergym_episode_runner.BROWSERGYM_TERMINAL_COMPLETION_POLICY
AgentLabPlannerAdapter = _browsergym_episode_runner.AgentLabPlannerAdapter
BrowserGymExecutor = _browsergym_episode_runner.BrowserGymExecutor
BrowserGymGeneralistPlanner = _browsergym_episode_runner.BrowserGymGeneralistPlanner
BrowserGymPlanner = _browsergym_episode_runner.BrowserGymPlanner
JsonLinePolicy = _browsergym_episode_runner.JsonLinePolicy
_accessibility_tree_text = _browsergym_episode_runner._accessibility_tree_text
_browser_snapshot_evidence = _browsergym_episode_runner._browser_snapshot_evidence
_browsergym_adaptive_runtime_stats = _browsergym_episode_runner._browsergym_adaptive_runtime_stats
_browsergym_context_stats = _browsergym_episode_runner._browsergym_context_stats
_browsergym_model_stats = _browsergym_episode_runner._browsergym_model_stats
_browsergym_source_server_worker = _browsergym_episode_runner._browsergym_source_server_worker
_close_quietly = _browsergym_episode_runner._close_quietly
_generalist_episode_worker = _browsergym_episode_runner._generalist_episode_worker
_goal_text = _browsergym_episode_runner._goal_text
_quiet_handler = _browsergym_episode_runner._quiet_handler
run_browsergym_episode = _browsergym_episode_runner.run_browsergym_episode
run_browsergym_generalist_episode = _browsergym_episode_runner.run_browsergym_generalist_episode
run_browsergym_generalist_episode_isolated = _browsergym_episode_runner.run_browsergym_generalist_episode_isolated


def run_browsergym_miniwob_suite(
    output_dir: Path,
    *,
    profile: BrowserGymProfile,
    policy_command: str | Sequence[str],
    headless: bool = True,
) -> dict[str, Any]:
    """Run an official, unmodified BrowserGym track with an external policy."""

    try:
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
        import gymnasium as gym  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "BrowserGym is not installed; use an isolated affordance-runtime[browsergym] environment"
        ) from exc

    html_root = ensure_browsergym_miniwob(output_dir / "source")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _quiet_handler(html_root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    registered = registered_miniwob_tasks()
    selected, seeds = browsergym_profile(registered, profile)
    missing_tasks = sorted(set(selected) - set(registered))
    episodes: list[BrowserGymEpisodeResult] = []
    try:
        base_url = f"http://{server.server_name}:{server.server_port}/miniwob/"
        for task_id, seed in browsergym_episode_schedule(selected, seeds):
            if task_id in missing_tasks:
                continue
            environment = gym.make(
                f"browsergym/miniwob.{task_id}",
                task_kwargs={"base_url": base_url},
                headless=headless,
            )
            episodes.append(
                run_browsergym_episode(
                    cast(BrowserGymEnvironment, environment),
                    JsonLinePolicy(policy_command),
                    task_id=task_id,
                    seed=seed,
                    artifact_root=output_dir / "artifacts",
                )
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    report = write_browsergym_report(
        output_dir,
        profile=profile,
        registered_tasks=registered,
        selected_tasks=selected,
        seeds=seeds,
        episodes=episodes,
    )
    report["acceptance_errors"] = [
        *(f"registered task missing: {task}" for task in missing_tasks),
        *report["acceptance_errors"],
    ]
    (output_dir / "browsergym-report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def run_browsergym_miniwob_generalist_suite(
    output_dir: Path,
    *,
    profile: BrowserGymProfile,
    model: ModelPort,
    visual_grounder: VisualGrounderPort | None = None,
    visual_region_proposer: VisualRegionProposerPort | None = None,
    task_ids: Sequence[str] | None = None,
    seed_count: int | None = None,
    headless: bool = True,
    resume: bool = False,
    episode_timeout_s: float = 165.0,
    model_call_timeout_s: float = 10.0,
    max_model_calls: int = 15,
    execution_reserve_s: float = 15.0,
    planner_profile: GeneralistPlannerProfile = GeneralistPlannerProfile.STRICT_GENERALIST,
) -> dict[str, Any]:
    """Run the standard MiniWoB matrix through the common GeneralistLMPlanner.

    This is intentionally separate from the external-policy suite: official
    score, unsupported action coverage, and runtime diagnostics remain in the
    same report schema, while no task-specific JSON-lines policy is involved.
    """

    _validate_browsergym_time_budgets(
        episode_timeout_s=episode_timeout_s,
        model_call_timeout_s=model_call_timeout_s,
        max_model_calls=max_model_calls,
        execution_reserve_s=execution_reserve_s,
    )
    run_identity = _frozen_run_identity()
    _require_frozen_profile_identity(profile, run_identity)
    try:
        import browsergym.miniwob  # type: ignore[import-not-found]  # noqa: F401
        import gymnasium  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "BrowserGym is not installed; use an isolated affordance-runtime[browsergym] environment"
        ) from exc

    html_root = ensure_browsergym_miniwob(output_dir / "source")
    server_context = mp.get_context("fork")
    server_ready = server_context.Queue()
    source_server = server_context.Process(
        target=_browsergym_source_server_worker,
        args=(server_ready, str(html_root)),
    )
    source_server.start()
    try:
        server_name, server_port = server_ready.get(timeout=10)
    except Empty as exc:
        source_server.terminate()
        source_server.join(timeout=5)
        server_ready.close()
        raise RuntimeError("BrowserGym source server failed to start") from exc
    server_ready.close()
    registered = registered_miniwob_tasks()
    profile_tasks, profile_seeds = browsergym_profile(registered, profile)
    selected = tuple(task_ids) if task_ids else profile_tasks
    if len(set(selected)) != len(selected):
        raise ValueError("targeted BrowserGym task ids must be unique")
    if seed_count is not None and seed_count <= 0:
        raise ValueError("targeted BrowserGym seed count must be positive")
    seeds = tuple(range(seed_count)) if seed_count is not None else profile_seeds
    missing_tasks = sorted(set(selected) - set(registered))
    episodes: list[BrowserGymEpisodeResult] = []
    expected = {(task_id, seed) for task_id in selected if task_id not in missing_tasks for seed in seeds}
    checkpoint_dir = output_dir / "episodes"
    checkpoint_metadata = {
        "schema_version": "browsergym-generalist-checkpoint-v5",
        "run_identity": run_identity,
        "profile": profile,
        "planner_profile": planner_profile.value,
        "semantic_compiler_registry_digest": (
            historical_compatibility_semantic_compiler_registry().digest
            if planner_profile == GeneralistPlannerProfile.HISTORICAL_COMPATIBILITY
            else SemanticCompilerRegistry.disabled().digest
        ),
        "selected_task_ids": list(selected),
        "seeds": list(seeds),
        "model_provider": model.provider,
        "model_name": model.model,
        "model_endpoint_class": model.endpoint_class,
        "visual_grounder_provider": visual_grounder.provider if visual_grounder is not None else "disabled",
        "visual_grounder_model": visual_grounder.model if visual_grounder is not None else "",
        "visual_grounder_prompt_version": visual_grounder.prompt_version if visual_grounder is not None else "",
        "visual_region_proposer_provider": visual_region_proposer.provider
        if visual_region_proposer is not None
        else "disabled",
        "visual_region_proposer_model": visual_region_proposer.model if visual_region_proposer is not None else "",
        "visual_region_proposer_prompt_version": visual_region_proposer.prompt_version
        if visual_region_proposer is not None
        else "",
        "planner_prompt_version": planner_prompt_version(planner_profile),
        "planner_context_policy_version": GENERALIST_PLANNER_CONTEXT_POLICY_VERSION,
        "planner_schema_sha256": _planner_schema_sha256(),
        "model_max_tokens": BROWSERGYM_PLANNER_MAX_TOKENS,
        "episode_timeout_s": episode_timeout_s,
        "model_call_timeout_s": model_call_timeout_s,
        "max_model_calls": max_model_calls,
        "execution_reserve_s": execution_reserve_s,
        "terminal_completion_policy": BROWSERGYM_TERMINAL_COMPLETION_POLICY,
        "browsergym_version": BROWSERGYM_VERSION,
        "miniwob_commit": BROWSERGYM_MINIWOB_COMMIT,
    }
    _prepare_browsergym_checkpoint_metadata(checkpoint_dir, checkpoint_metadata, resume=resume)
    reused = _load_browsergym_checkpoints(checkpoint_dir, expected) if resume else {}
    episodes.extend(reused.values())
    newly_completed = 0
    interrupted = False
    circuit_break_reason = ""
    try:
        base_url = f"http://{server_name}:{server_port}/miniwob/"
        family_map = {task: family for family, tasks in NIGHTLY_ACTION_FAMILY_MANIFEST.items() for task in tasks}
        failure_envelopes = [
            envelope
            for episode in episodes
            if (envelope := browsergym_failure_envelope(episode, task_family_map=family_map)) is not None
        ]
        consecutive_batch_failures: list[dict[str, Any]] = []
        schema_compatible_episode_observed = any(
            episode.runtime_status == RuntimeStep.DONE.value and not episode.policy_stopped for episode in episodes
        )
        for task_id, seed in browsergym_episode_schedule(selected, seeds):
            if task_id in missing_tasks or (task_id, seed) in reused:
                continue
            episode = run_browsergym_generalist_episode_isolated(
                model,
                task_id=task_id,
                seed=seed,
                base_url=base_url,
                headless=headless,
                artifact_root=output_dir / "artifacts",
                timeout_s=episode_timeout_s,
                model_timeout_s=model_call_timeout_s,
                max_model_calls=max_model_calls,
                planner_profile=planner_profile,
                visual_grounder=visual_grounder,
                visual_region_proposer=visual_region_proposer,
            )
            episodes.append(episode)
            _write_browsergym_checkpoint(checkpoint_dir, episode)
            newly_completed += 1
            envelope = browsergym_failure_envelope(episode, task_family_map=family_map)
            if envelope is not None:
                failure_envelopes.append(envelope)
            schema_compatible_episode_observed, circuit_break_reason = update_browsergym_batch_circuit_state(
                consecutive_batch_failures,
                episode,
                envelope,
                schema_compatible_episode_observed=schema_compatible_episode_observed,
            )
            if circuit_break_reason:
                break
    except KeyboardInterrupt:
        interrupted = True
    finally:
        if source_server.is_alive():
            source_server.terminate()
        source_server.join(timeout=5)
    episodes.sort(key=lambda item: (item.task_id, item.seed))
    report = write_browsergym_report(
        output_dir,
        profile=profile,
        registered_tasks=registered,
        selected_tasks=selected,
        seeds=seeds,
        episodes=episodes,
    )
    report.update(
        {
            "planner_boundary": "GeneralistLMPlanner",
            "planner_profile": planner_profile.value,
            "model_provider": model.provider,
            "model_name": model.model,
            "model_endpoint_class": model.endpoint_class,
            "checkpoint_reused_episode_count": len(reused),
            "checkpoint_new_episode_count": newly_completed,
            "checkpoint_metadata": checkpoint_metadata,
            "batch_circuit_break_reason": circuit_break_reason,
            "run_complete": (
                not interrupted
                and not circuit_break_reason
                and len({(item.task_id, item.seed) for item in episodes}) == len(expected)
            ),
        }
    )
    # M8.2B score promotion is paused behind M8.6. Keep the external reward in
    # the report, but do not turn even a complete strict nightly into a product
    # capability claim while governance/generalization gates remain open.
    report["official_score_claimed"] = False
    report["score_promotion_gate"] = "m8.6-open"
    report["batch_status"] = (
        "complete" if report["run_complete"] else ("incomplete_diagnostic" if profile == "diagnostic" else "incomplete")
    )
    report["acceptance_errors"] = [
        *(f"registered task missing: {task}" for task in missing_tasks),
        *(["run interrupted; resume with --resume"] if interrupted else []),
        *([f"batch circuit breaker: {circuit_break_reason}"] if circuit_break_reason else []),
        *report["acceptance_errors"],
    ]
    (output_dir / "browsergym-report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _validate_browsergym_time_budgets(
    *,
    episode_timeout_s: float,
    model_call_timeout_s: float,
    max_model_calls: int,
    execution_reserve_s: float,
) -> None:
    if min(episode_timeout_s, model_call_timeout_s) <= 0 or max_model_calls <= 0 or execution_reserve_s < 0:
        raise ValueError("BrowserGym time budgets must be positive")
    if model_call_timeout_s * max_model_calls + execution_reserve_s > episode_timeout_s:
        raise ValueError("model-call budget plus execution reserve exceeds episode timeout")


def _planner_schema_sha256() -> str:
    payload = PlannerProposalCandidate.model_json_schema()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _frozen_run_identity() -> dict[str, str | bool]:
    """Bind a matrix to its revision and exact runtime-source contents."""

    repository = Path(__file__).resolve().parents[3]
    source_tree_sha256 = _runtime_source_sha256(repository)
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {
            "git_sha": "unavailable",
            "working_tree_clean": False,
            "source_tree_sha256": source_tree_sha256,
        }
    return {
        "git_sha": revision,
        "working_tree_clean": not dirty,
        "source_tree_sha256": source_tree_sha256,
    }


def _runtime_source_sha256(repository: Path) -> str:
    """Hash runtime inputs while deliberately excluding local secrets and outputs."""

    candidates = list((repository / "src").rglob("*.py"))
    candidates.extend(
        path
        for path in (
            repository / "scripts" / "run_browsergym_generalist.py",
            repository / "pyproject.toml",
        )
        if path.is_file()
    )
    requirements = repository / "requirements"
    if requirements.is_dir():
        candidates.extend(path for path in requirements.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(set(candidates)):
        relative = path.relative_to(repository).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _require_frozen_profile_identity(
    profile: BrowserGymProfile,
    run_identity: dict[str, str | bool],
) -> None:
    if profile in {"nightly", "release"} and not run_identity["working_tree_clean"]:
        raise ValueError(
            f"Frozen {profile} requires a clean committed worktree; choose a new output directory after committing"
        )
