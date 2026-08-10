"""Bounded serial state for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from affordance_runtime.agent.control_transition import ControlContinuation, ControlTransition, Turn
from affordance_runtime.agent.progress_control import ProgressEvent
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.execution.contracts import BoundActionRequest
from affordance_runtime.task.planning_contracts import LocalObjective, TaskPlan
from affordance_runtime.world.contracts import WorldObservation


def _current_task_evaluation(continuation, previous, after_observation_id):
    candidate = continuation or previous
    if candidate is None or candidate.observation_id != after_observation_id:
        return None
    return candidate


class AgentLoopStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class AgentLoopState:
    current_observation: WorldObservation
    recent_control_transitions: tuple[ControlTransition, ...] = ()
    control_transition_total_count: int = 0
    sent_unknown_total_count: int = 0
    control_transition_kind_counts: dict[str, int] = field(default_factory=dict)
    plan: TaskPlan | None = None
    active_objective: LocalObjective | None = None
    task_revision: int = 1
    progress_revision: int = 0
    pending_revision: int = 0
    pending_user_question: str = ""
    pending_confirmation: ConfirmationRequest | None = None
    pending_unknown_request: BoundActionRequest | None = None
    pending_confirmation_transition_id: str = ""
    latest_control_continuation: ControlContinuation | None = None
    current_task_evaluation: TaskEvaluation | None = field(default=None, repr=False)
    remaining_turns: int = 20
    final_result: dict[str, object] = field(default_factory=dict)
    recent_progress_events: tuple[ProgressEvent, ...] = ()
    progress_event_total_count: int = 0
    recent_turn_limit: int = 12
    progress_event_limit: int = 3

    @property
    def recent_turns(self) -> tuple[Turn, ...]:
        return tuple(item.as_turn() for item in self.recent_control_transitions)

    def _append_control_transition(self, transition: ControlTransition) -> None:
        if transition.sequence != self.control_transition_total_count + 1:
            raise ValueError("control transition sequence is not contiguous")
        self.recent_control_transitions = (
            *self.recent_control_transitions,
            transition,
        )[-self.recent_turn_limit :]
        self.control_transition_total_count += 1
        kind = type(transition.decision).__name__
        self.control_transition_kind_counts[kind] = (
            self.control_transition_kind_counts.get(kind, 0) + 1
        )
        self.sent_unknown_total_count += sum(
            str(item.dispatch_status) == "sent_unknown"
            for item in transition.execution_attempts
        )
        self.progress_revision += 1

    def _apply_control_continuation(self, continuation: ControlContinuation) -> None:
        for index, transition in enumerate(self.recent_control_transitions):
            if transition.transition_id != continuation.source_transition_id:
                continue
            execution_attempts = (
                *transition.execution_attempts,
                *continuation.execution_attempts,
            )
            attempts = (
                *transition.acquisition_attempts,
                *continuation.acquisition_attempts,
            )
            acquisition = None
            if attempts:
                final = attempts[-1]
                acquisition = replace(
                    final,
                    attempts=sum(item.attempts for item in attempts),
                )
            updated = replace(
                transition,
                execution=continuation.execution or transition.execution,
                execution_attempts=execution_attempts,
                acquisition=acquisition,
                acquisition_attempts=attempts,
                after_observation_id=continuation.after_observation_id,
                action_evaluation=(
                    continuation.action_evaluation or transition.action_evaluation
                ),
                task_evaluation=_current_task_evaluation(
                    continuation.task_evaluation,
                    transition.task_evaluation,
                    continuation.after_observation_id,
                ),
                progress=type(transition.progress)(
                    transition.progress.event_count + continuation.progress.event_count,
                    continuation.progress.latest_event_type
                    or transition.progress.latest_event_type,
                ),
                pending_kind=continuation.pending_kind,
                resulting_status=continuation.resulting_status,
                reason_code=continuation.reason_code,
                intent=continuation.intent or transition.intent,
                request_id=continuation.request_id or transition.request_id,
            )
            values = list(self.recent_control_transitions)
            values[index] = updated
            self.recent_control_transitions = tuple(values)
            self.sent_unknown_total_count += sum(
                str(item.dispatch_status) == "sent_unknown"
                for item in continuation.execution_attempts
            )
            return
        raise ValueError("confirmation continuation root is outside the bounded suffix")

    def _append_progress_event(self, event: ProgressEvent) -> None:
        self.recent_progress_events = (
            *self.recent_progress_events,
            event,
        )[-self.progress_event_limit :]
        self.progress_event_total_count += 1
        self.progress_revision += 1

    def set_active_objective(self, objective: LocalObjective) -> None:
        if self.active_objective != objective:
            self.active_objective = objective
            self.progress_revision += 1

    def clear_active_objective(self) -> None:
        if self.active_objective is not None:
            self.active_objective = None
            self.progress_revision += 1

    def replace_plan(self, plan: TaskPlan | None) -> None:
        if self.plan != plan:
            self.plan = plan
            self.progress_revision += 1

    def set_pending_question(self, question: str) -> None:
        if self.pending_user_question != question:
            self.pending_user_question = question
            self.pending_revision += 1

    def clear_pending_question(self) -> None:
        if self.pending_user_question:
            self.pending_user_question = ""
            self.pending_revision += 1

    def set_pending_confirmation(self, confirmation: ConfirmationRequest) -> None:
        if self.pending_confirmation != confirmation:
            self.pending_confirmation = confirmation
            self.pending_revision += 1

    def clear_pending_confirmation(self) -> None:
        if self.pending_confirmation is not None:
            self.pending_confirmation = None
            self.pending_confirmation_transition_id = ""
            self.pending_revision += 1

    def set_pending_unknown_effect(self, request: BoundActionRequest) -> None:
        if self.pending_unknown_request != request:
            self.pending_unknown_request = request
            self.pending_revision += 1

    def clear_pending_unknown_effect(self) -> None:
        if self.pending_unknown_request is not None:
            self.pending_unknown_request = None
            self.pending_revision += 1
