"""Small authoritative state for the simplified GUI-agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.execution.contracts import ExecutionOutcome
from affordance_runtime.risk.contracts import RiskAssessment
from affordance_runtime.world.contracts import WorldObservation


class RunStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class StepResult:
    """One policy outcome's concise feedback; never a replay or ledger record."""

    decision: AgentDecision | PolicyFailure
    before_world: WorldObservation
    after_world: WorldObservation
    task_evaluation: TaskEvaluation
    status_after: RunStatus = RunStatus.RUNNING
    execution: ExecutionOutcome | None = None
    action_evaluation: ActionEvaluation | None = None
    confirmation: RiskAssessment | None = None
    feedback: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status_after, RunStatus):
            raise TypeError("step status must be typed")
        if self.task_evaluation.observation_id != self.after_world.observation_id:
            raise ValueError("step task evaluation must describe the after-world")
        if self.action_evaluation is not None:
            if self.execution is None:
                raise ValueError("action evaluation requires an execution")
            if (
                self.action_evaluation.request_id != self.execution.request.request_id
                or self.action_evaluation.before_observation_id != self.before_world.observation_id
                or self.action_evaluation.after_observation_id != self.after_world.observation_id
            ):
                raise ValueError("step action evaluation does not match its worlds and execution")
        if self.confirmation is not None and self.execution is not None:
            raise ValueError("a pending confirmation cannot already contain execution")
        if not self.feedback.strip():
            raise ValueError("step feedback must be concise and nonblank")


@dataclass
class RunState:
    """The sole mutable control value for one simplified run."""

    current_world: WorldObservation
    current_task_evaluation: TaskEvaluation
    remaining_steps: int
    status: RunStatus = RunStatus.RUNNING
    last_step: StepResult | None = None
    observation_count: int = 1
    execution_count: int = 0
    context_generation: int = 0
    recent_actions: tuple[AgentTurnView, ...] = ()

    def __post_init__(self) -> None:
        if self.current_task_evaluation.observation_id != self.current_world.observation_id:
            raise ValueError("run evaluation must describe the current world")
        if self.remaining_steps < 0:
            raise ValueError("remaining steps cannot be negative")
        if self.observation_count < 1 or self.execution_count < 0:
            raise ValueError("run counters are invalid")
        self.recent_actions = tuple(self.recent_actions)
        if len(self.recent_actions) > 4 or any(
            not isinstance(item, AgentTurnView) for item in self.recent_actions
        ):
            raise ValueError("recent action context must be bounded and public")

    @property
    def terminal(self) -> bool:
        return self.status in {
            RunStatus.DONE,
            RunStatus.BLOCKED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }

    def next_context_generation(self) -> int:
        self.context_generation += 1
        return self.context_generation

    def remember_action(self, action: AgentTurnView) -> None:
        if not isinstance(action, AgentTurnView):
            raise TypeError("run action memory must be model-safe")
        self.recent_actions = (*self.recent_actions, action)[-4:]

    def apply(self, result: StepResult) -> None:
        if self.status is not RunStatus.RUNNING:
            raise ValueError("only a running state can accept a step")
        if result.before_world.observation_id != self.current_world.observation_id:
            raise ValueError("step starts from a stale world")
        acquired_new_world = result.after_world.observation_id != result.before_world.observation_id
        self.current_world = result.after_world
        self.current_task_evaluation = result.task_evaluation
        self.last_step = result
        self.status = result.status_after
        self.remaining_steps = max(0, self.remaining_steps - 1)
        self.observation_count += int(acquired_new_world)
        self.execution_count += int(result.execution is not None)
        if self.status is RunStatus.RUNNING and self.remaining_steps == 0:
            self.status = RunStatus.BLOCKED
