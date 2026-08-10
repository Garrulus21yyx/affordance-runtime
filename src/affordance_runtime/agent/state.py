"""Bounded serial state for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.agent.progress_control import ProgressEvent
from affordance_runtime.confirmation.contracts import ConfirmationRequest
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.execution.contracts import ActionIntent, ActionResult, BoundActionRequest
from affordance_runtime.task.planning_contracts import LocalObjective, TaskPlan
from affordance_runtime.world.contracts import WorldObservation


class AgentLoopStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class Turn:
    before_observation_id: str
    decision: AgentDecision
    intent: ActionIntent | None = None
    request_id: str = ""
    result: ActionResult | None = None
    after_observation_id: str = ""
    action_evaluation: ActionEvaluation | None = None
    task_evaluation: TaskEvaluation | None = None
    decision_result: str = ""


@dataclass
class AgentLoopState:
    current_observation: WorldObservation
    recent_turns: tuple[Turn, ...] = ()
    plan: TaskPlan | None = None
    active_objective: LocalObjective | None = None
    task_revision: int = 1
    progress_revision: int = 0
    pending_revision: int = 0
    pending_user_question: str = ""
    pending_confirmation: ConfirmationRequest | None = None
    pending_unknown_request: BoundActionRequest | None = None
    remaining_turns: int = 20
    final_result: dict[str, object] = field(default_factory=dict)
    recent_progress_events: tuple[ProgressEvent, ...] = ()
    recent_turn_limit: int = 12
    progress_event_limit: int = 3

    def append_turn(self, turn: Turn) -> None:
        self.recent_turns = (*self.recent_turns, turn)[-self.recent_turn_limit :]
        self.progress_revision += 1

    def _append_progress_event(self, event: ProgressEvent) -> None:
        self.recent_progress_events = (
            *self.recent_progress_events,
            event,
        )[-self.progress_event_limit :]
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
            self.pending_revision += 1

    def set_pending_unknown_effect(self, request: BoundActionRequest) -> None:
        if self.pending_unknown_request != request:
            self.pending_unknown_request = request
            self.pending_revision += 1

    def clear_pending_unknown_effect(self) -> None:
        if self.pending_unknown_request is not None:
            self.pending_unknown_request = None
            self.pending_revision += 1
