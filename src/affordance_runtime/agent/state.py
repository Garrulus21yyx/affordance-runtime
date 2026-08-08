"""Bounded serial state for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.agent.decisions import AgentDecision
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
    recent_turn_limit: int = 12

    def append_turn(self, turn: Turn) -> None:
        self.recent_turns = (*self.recent_turns, turn)[-self.recent_turn_limit :]
        self.progress_revision += 1
