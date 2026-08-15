"""Read-only privacy-safe snapshot of an in-flight AgentRunSession."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.world.contracts import CoverageState

if TYPE_CHECKING:
    from affordance_runtime.agent.run_state import RunState
    from affordance_runtime.agent.session import AgentRunSession


@dataclass(frozen=True)
class PartialEpisodeSnapshot:
    observation_count: int
    execution_count: int
    currentness_probe_count: int
    completed_turn_count: int
    latest_task_status: str
    latest_action_evaluation_status: str
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
    control_feedback_count: int = 0
    control_feedback_delivery_count: int = 0
    control_issue_consumption_count: int = 0
    control_repetition_count: int = 0


def snapshot_partial_episode(session: AgentRunSession) -> PartialEpisodeSnapshot:
    state = session.state
    latest_transition = next(
        (item for item in reversed(state.recent_control_transitions) if item.action_evaluation is not None),
        None,
    )
    latest_action = latest_transition.action_evaluation if latest_transition is not None else None
    key = session.progress_controller.latest_attempt_key
    latest_event = state.recent_progress_events[-1] if state.recent_progress_events else None
    latest_task = state.current_task_evaluation
    if latest_task is not None and latest_task.observation_id != state.current_observation.observation_id:
        latest_task = None
    latest_control = state.recent_control_transitions[-1] if state.recent_control_transitions else None
    latest_receipt = (
        latest_control.attempt_receipts[-1] if latest_control is not None and latest_control.attempt_receipts else None
    )
    return PartialEpisodeSnapshot(
        session.observation_count,
        session.execution_count,
        session.currentness_probe_count,
        state.control_transition_total_count,
        str(latest_task.status) if latest_task else "",
        str(latest_action.status) if latest_action is not None else "",
        key.digest if key else "",
        session.progress_controller.same_attempt_streak,
        session.progress_controller.no_progress_count,
        latest_event.event_type if latest_event else "",
        state.sent_unknown_total_count,
        type(state.recent_control_transitions[-1].decision).__name__ if state.recent_control_transitions else "",
        len(session.current_action_space.options) if session.current_action_space is not None else 0,
        len(state.current_observation.targets),
        _coverage_summary({
            item.source_observation_id: item.coverage
            for item in state.current_observation.source_manifest
        }),
        _pending_kind(session),
        tuple(sorted(state.control_transition_kind_counts.items())),
        str(latest_control.resulting_status)
        if latest_control is not None and latest_control.resulting_status is not None
        else "",
        latest_control.reason_code if latest_control is not None else "",
        str(latest_control.acquisition.request.kind)
        if latest_control is not None and latest_control.acquisition is not None
        else "",
        str(latest_receipt.operation) if latest_receipt is not None else "",
        latest_receipt.reason_code if latest_receipt is not None else "",
        str(latest_task.outcome.kind) if latest_task is not None and latest_task.outcome is not None else "",
        latest_task.outcome.code if latest_task is not None and latest_task.outcome is not None else "",
        state.control_feedback_total_count,
        state.control_feedback_delivery_total_count,
        state.control_issue_consumption_total_count,
        state.control_repetition_total_count,
    )


def snapshot_core_episode(state: RunState) -> PartialEpisodeSnapshot:
    """Project benchmark-safe facts from the thin loop without adding state to it."""

    latest = state.last_step
    task_evaluation = state.current_task_evaluation
    task_outcome = task_evaluation.outcome
    return PartialEpisodeSnapshot(
        state.observation_count,
        state.execution_count,
        0,
        state.step_count,
        str(task_evaluation.status),
        str(latest.action_evaluation.status)
        if latest is not None and latest.action_evaluation is not None
        else "",
        "",
        0,
        0,
        "",
        0,
        type(latest.decision).__name__
        if latest is not None and not isinstance(latest.decision, PolicyFailure)
        else "",
        0,
        len(state.current_world.targets),
        _coverage_summary({
            item.source_observation_id: item.coverage
            for item in state.current_world.source_manifest
        }),
        _core_pending_kind(state),
        (),
        str(state.status),
        latest.feedback if latest is not None else "",
        "",
        "",
        "",
        str(task_outcome.kind) if task_outcome is not None else "",
        task_outcome.code if task_outcome is not None else "",
    )


def _pending_kind(session: AgentRunSession) -> str:
    state = session.state
    if state.pending_unknown_request is not None:
        return "unknown_effect"
    if state.pending_user_question:
        return "user_question"
    if state.pending_confirmation is not None:
        return "confirmation"
    return ""


def _core_pending_kind(state: RunState) -> str:
    from affordance_runtime.agent.run_state import RunStatus

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
