"""Read-only benchmark projection of the thin Runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.run_state import RunState, RunStatus
from affordance_runtime.world.contracts import CoverageState


@dataclass(frozen=True)
class PartialEpisodeSnapshot:
    observation_count: int
    execution_count: int
    currentness_probe_count: int
    completed_turn_count: int
    latest_task_status: str
    latest_action_observed_change: str
    latest_action_local_postcondition: str
    latest_action_evidence_method: str
    latest_semantic_attempt_key_digest: str
    same_attempt_streak: int
    no_progress_count: int
    last_progress_event_type: str
    sent_unknown_count: int
    last_decision_type: str
    last_action_space_option_count: int
    last_world_target_count: int
    last_world_coverage: str
    pending_kind: str
    decision_kind_counts: tuple[tuple[str, int], ...] = ()
    latest_control_status: str = ""
    latest_control_reason_code: str = ""
    latest_acquisition_request_kind: str = ""
    latest_attempt_operation: str = ""
    latest_attempt_reason_code: str = ""
    task_outcome_kind: str = ""
    task_outcome_code: str = ""


def snapshot_episode(state: RunState) -> PartialEpisodeSnapshot:
    """Project benchmark-safe facts without adding state to the product loop."""

    latest = state.last_step
    task_evaluation = state.current_task_evaluation
    task_outcome = task_evaluation.outcome
    return PartialEpisodeSnapshot(
        state.observation_count,
        state.execution_count,
        0,
        state.step_count,
        str(task_evaluation.status),
        str(latest.action_outcome.observed_change)
        if latest is not None and latest.action_outcome is not None
        else "",
        str(latest.action_outcome.local_postcondition)
        if latest is not None and latest.action_outcome is not None
        else "",
        str(latest.action_outcome.evidence_method)
        if latest is not None and latest.action_outcome is not None
        else "",
        "",
        0,
        0,
        "",
        state.sent_unknown_count,
        type(latest.decision).__name__
        if latest is not None and not isinstance(latest.decision, PolicyFailure)
        else "",
        len(state.action_page.visible_action_ids) if state.action_page is not None else 0,
        len(state.current_world.targets),
        _coverage_summary({
            item.source_observation_id: item.coverage
            for item in state.current_world.source_manifest
        }),
        _pending_kind(state),
        (),
        str(state.status),
        latest.feedback if latest is not None else "",
        "",
        "",
        "",
        str(task_outcome.kind) if task_outcome is not None else "",
        task_outcome.code if task_outcome is not None else "",
    )


def _pending_kind(state: RunState) -> str:
    if state.status is RunStatus.WAITING_USER:
        return "user_question"
    if state.status is RunStatus.WAITING_CONFIRMATION:
        return "confirmation"
    return ""


def _coverage_summary(coverage: dict[str, CoverageState]) -> str:
    values = set(coverage.values())
    for status in (
        CoverageState.FAILED,
        CoverageState.TRUNCATED,
        CoverageState.STALE,
        CoverageState.NOT_ACQUIRED,
    ):
        if status in values:
            return str(status)
    return str(CoverageState.COMPLETE)
