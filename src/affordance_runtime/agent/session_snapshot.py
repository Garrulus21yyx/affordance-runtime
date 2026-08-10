"""Read-only privacy-safe snapshot of an in-flight AgentRunSession."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from affordance_runtime.execution.contracts import DispatchStatus

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


def snapshot_partial_episode(session: AgentRunSession) -> PartialEpisodeSnapshot:
    state = session.state
    latest_turn = next(
        (item for item in reversed(state.recent_turns) if item.action_evaluation is not None),
        None,
    )
    latest_action = latest_turn.action_evaluation if latest_turn is not None else None
    key = session.progress_controller.latest_attempt_key
    latest_event = state.recent_progress_events[-1] if state.recent_progress_events else None
    sent_unknown = sum(
        item.result is not None and item.result.dispatch_status == DispatchStatus.SENT_UNKNOWN
        for item in state.recent_turns
    )
    return PartialEpisodeSnapshot(
        session.observation_count,
        session.execution_count,
        session.currentness_probe_count,
        session.task.loop_budget.max_turns - state.remaining_turns,
        str(session.latest_task_evaluation.status) if session.latest_task_evaluation else "",
        str(latest_action.status) if latest_action is not None else "",
        key.digest if key else "",
        session.progress_controller.same_attempt_streak,
        session.progress_controller.no_progress_count,
        latest_event.event_type if latest_event else "",
        sent_unknown,
    )
