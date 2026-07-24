"""BrowserGym profile selection, matrix checkpoints, and official reporting."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from affordance_runtime.benchmarks import browsergym_protocol as _browsergym_protocol
from affordance_runtime.benchmarks import browsergym_report as _browsergym_report
from affordance_runtime.benchmarks.browsergym_protocol import (
    NIGHTLY_TASKS,
    PR_SMOKE_TASKS,
    BrowserGymProfile,
)
from affordance_runtime.benchmarks.browsergym_types import BrowserGymEpisodeResult
from affordance_runtime.evaluation_audit import (
    EvaluationBatchStop,
    EvaluationRunAudit,
    EvaluationRunIdentity,
    EvaluationStopCategory,
    select_unobserved_cases_for_resume,
)
from affordance_runtime.runtime import RuntimeStep

BROWSERGYM_RUN_PROTOCOL_VERSION = _browsergym_protocol.BROWSERGYM_RUN_PROTOCOL_VERSION
BROWSERGYM_VERSION = _browsergym_protocol.BROWSERGYM_VERSION
NIGHTLY_ACTION_FAMILY_MANIFEST = _browsergym_protocol.NIGHTLY_ACTION_FAMILY_MANIFEST
NIGHTLY_TASK_MANIFEST_VERSION = _browsergym_protocol.NIGHTLY_TASK_MANIFEST_VERSION
browsergym_episode_schedule = _browsergym_protocol.browsergym_episode_schedule
browsergym_failure_envelope = _browsergym_report.browsergym_failure_envelope
cluster_browsergym_failure_envelopes = _browsergym_report.cluster_browsergym_failure_envelopes
cluster_browsergym_failures_by_runtime_owner = (
    _browsergym_report.cluster_browsergym_failures_by_runtime_owner
)
write_browsergym_report = _browsergym_report.write_browsergym_report
publish_browsergym_report = _browsergym_report.publish_browsergym_report
validate_browsergym_episode_result = _browsergym_report.validate_browsergym_episode_result


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


def browsergym_batch_stop(reason: str) -> EvaluationBatchStop | None:
    """Translate an adapter stop reason into the generic validity boundary."""

    if not reason:
        return None
    if reason == "safety_violation":
        return EvaluationBatchStop(
            category=EvaluationStopCategory.SAFETY_AUTHORITY,
            reason=reason,
            invalidates_observed_results=False,
            resume_allowed=False,
        )
    if reason == "version_drift":
        return EvaluationBatchStop(
            category=EvaluationStopCategory.COMPARABILITY,
            reason=reason,
            invalidates_observed_results=True,
            resume_allowed=False,
        )
    if reason == "provider_unavailable_or_continuous_rate_limit":
        return EvaluationBatchStop(
            category=EvaluationStopCategory.PROVIDER_INFRASTRUCTURE,
            reason=reason,
            invalidates_observed_results=False,
            resume_allowed=True,
        )
    if reason in {
        "source_or_oracle_unavailable",
        "artifact_checkpoint_failure",
        "schema_incompatible",
        "result_accounting_failure",
    }:
        return EvaluationBatchStop(
            category=EvaluationStopCategory.RESULT_INTEGRITY,
            reason=reason,
            invalidates_observed_results=True,
            resume_allowed=False,
        )
    raise ValueError(f"unsupported BrowserGym batch stop reason: {reason}")


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
        consecutive_failures.clear()
        return True, ""
    consecutive_failures.append(envelope)
    return schema_compatible_episode_observed, browsergym_batch_circuit_breaker(consecutive_failures)


def restore_browsergym_batch_circuit_state(
    episodes: Sequence[BrowserGymEpisodeResult],
    *,
    task_family_map: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], bool, str]:
    """Rebuild batch-wide suffix state from checkpointed cases in run order."""

    consecutive: list[dict[str, Any]] = []
    schema_compatible = False
    reason = ""
    for episode in episodes:
        envelope = browsergym_failure_envelope(
            episode,
            task_family_map=task_family_map or {},
        )
        schema_compatible, reason = update_browsergym_batch_circuit_state(
            consecutive,
            episode,
            envelope,
            schema_compatible_episode_observed=schema_compatible,
        )
    return consecutive, schema_compatible, reason


def browsergym_model_timeout_s(episode_timeout_s: float) -> float:
    """Reserve time for several planning turns inside a bounded episode."""

    return min(30.0, max(5.0, episode_timeout_s / 5.0))


def checkpoint_filename(task_id: str, seed: int) -> str:
    safe_task = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in task_id)
    task_digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:12]
    return f"{safe_task}-{task_digest}-seed-{seed}.json"


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
    _write_json_atomic(path, metadata)


def write_browsergym_checkpoint(directory: Path, episode: BrowserGymEpisodeResult) -> None:
    validate_browsergym_episode_result(episode)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / checkpoint_filename(episode.task_id, episode.seed)
    _write_json_atomic(path, asdict(episode))


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
        validate_browsergym_episode_result(episode)
        key = (episode.task_id, episode.seed)
        if key not in expected:
            raise ValueError(f"BrowserGym checkpoint is outside the requested matrix: {key[0]}:seed-{key[1]}")
        if path.name != checkpoint_filename(episode.task_id, episode.seed):
            raise ValueError(f"BrowserGym checkpoint filename does not match its payload: {path}")
        if key in results:
            raise ValueError(f"duplicate BrowserGym checkpoint: {key[0]}:seed-{key[1]}")
        results[key] = episode
    return results


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def validate_browsergym_resume(
    report_path: Path,
    *,
    identity: EvaluationRunIdentity,
    expected_schedule: Sequence[tuple[str, int]],
    checkpoints: Mapping[tuple[str, int], BrowserGymEpisodeResult],
) -> set[tuple[str, int]]:
    """Return only unobserved cases after proving same-run resume eligibility.

    No report means the process stopped before publishing collection closure;
    exact checkpoint metadata has already established identity, so this is the
    machine-interruption case. A published report is authoritative for whether
    the evidence set remains resumable.
    """

    schedule = tuple(expected_schedule)
    expected = set(schedule)
    if len(schedule) != len(expected):
        raise ValueError("BrowserGym resume schedule contains duplicate cases")
    checkpoint_keys = set(checkpoints)
    if not checkpoint_keys <= expected:
        raise ValueError("BrowserGym checkpoints contain cases outside the requested matrix")
    gap_observed = False
    for key in schedule:
        if key not in checkpoint_keys:
            gap_observed = True
        elif gap_observed:
            raise ValueError("BrowserGym checkpoints do not form the scheduler's observed prefix")
    if not report_path.exists():
        ordered = [checkpoints[key] for key in schedule if key in checkpoints]
        _, _, restored_reason = restore_browsergym_batch_circuit_state(ordered)
        restored_stop = browsergym_batch_stop(restored_reason)
        if restored_stop is not None and not restored_stop.resume_allowed:
            raise ValueError("BrowserGym checkpoint prefix ended in a nonresumable batch stop")
        return expected - checkpoint_keys
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid BrowserGym report; cannot safely resume")
    try:
        stored_identity = EvaluationRunIdentity.model_validate_json(
            json.dumps(payload["evaluation_run_identity"])
        )
        audit = EvaluationRunAudit.model_validate_json(json.dumps(payload["evaluation_audit"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("BrowserGym report lacks valid G4 resume accounting") from exc
    unobserved_ids = select_unobserved_cases_for_resume(
        stored_identity=stored_identity,
        requested_identity=identity,
        audit=audit,
    )
    ledger_observed = {item.case_id for item in audit.cases if item.observed}
    checkpoint_ids = {browsergym_case_id(task_id, seed) for task_id, seed in checkpoint_keys}
    if ledger_observed != checkpoint_ids:
        raise ValueError("BrowserGym report/checkpoint ledger mismatch; cannot safely resume")
    unobserved = {_parse_browsergym_case_id(value) for value in unobserved_ids}
    if unobserved != expected - checkpoint_keys:
        raise ValueError("BrowserGym resume ledger does not match the requested matrix")
    return unobserved


def browsergym_case_id(task_id: str, seed: int) -> str:
    return f"{task_id}:seed-{seed}"


def _parse_browsergym_case_id(value: str) -> tuple[str, int]:
    task_id, marker, raw_seed = value.rpartition(":seed-")
    if not marker or not task_id:
        raise ValueError("invalid BrowserGym case id in evaluation ledger")
    try:
        seed = int(raw_seed)
    except ValueError as exc:
        raise ValueError("invalid BrowserGym seed in evaluation ledger") from exc
    return task_id, seed
