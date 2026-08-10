"""Read-only privacy-safe snapshot of an in-flight AgentRunSession."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def snapshot_partial_episode(session: AgentRunSession) -> PartialEpisodeSnapshot:
    state = session.state
    latest_transition = next(
        (
            item
            for item in reversed(state.recent_control_transitions)
            if item.action_evaluation is not None
        ),
        None,
    )
    latest_action = (
        latest_transition.action_evaluation if latest_transition is not None else None
    )
    key = session.progress_controller.latest_attempt_key
    latest_event = state.recent_progress_events[-1] if state.recent_progress_events else None
    latest_task = state.current_task_evaluation
    if (
        latest_task is not None
        and latest_task.observation_id != state.current_observation.observation_id
    ):
        latest_task = None
    latest_control = (
        state.recent_control_transitions[-1]
        if state.recent_control_transitions
        else None
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
        type(state.recent_control_transitions[-1].decision).__name__
        if state.recent_control_transitions
        else "",
        len(session.current_action_space.options) if session.current_action_space is not None else 0,
        len(state.current_observation.targets),
        str(state.current_observation.coverage),
        _pending_kind(session),
        tuple(sorted(state.control_transition_kind_counts.items())),
        str(latest_control.resulting_status)
        if latest_control is not None and latest_control.resulting_status is not None
        else "",
        latest_control.reason_code if latest_control is not None else "",
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
