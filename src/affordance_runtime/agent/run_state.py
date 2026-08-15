"""Small authoritative state for the simplified GUI-agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.actions.paging import InternalActionPage
from affordance_runtime.agent.context.contracts import AgentTurnView
from affordance_runtime.agent.decisions import AgentDecision, SelectAction
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.runtime_failure import RuntimeFailure
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.execution.contracts import ExecutionOutcome
from affordance_runtime.risk.contracts import RiskAssessment
from affordance_runtime.world.contracts import WorldObservation

MAX_RECENT_STEPS = 8


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
    action_page: InternalActionPage | None = None
    waited_ms: int = 0
    failure_code: AgentFailureCode | None = None
    runtime_failure: RuntimeFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status_after, RunStatus):
            raise TypeError("step status must be typed")
        if self.waited_ms < 0:
            raise ValueError("step wait duration cannot be negative")
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
        if (
            self.execution is not None
            and isinstance(self.decision, SelectAction)
            and self.decision.tool_call_id != self.execution.request.tool_call_id
        ):
            raise ValueError("step decision/execution tool call lineage mismatch")
        if not self.feedback.strip():
            raise ValueError("step feedback must be concise and nonblank")
        if self.failure_code is not None and not isinstance(self.failure_code, AgentFailureCode):
            raise TypeError("step failure code must be typed")
        if self.runtime_failure is not None and not isinstance(self.runtime_failure, RuntimeFailure):
            raise TypeError("step runtime failure must be typed")


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
    step_count: int = 0
    context_generation: int = 0
    recent_steps: tuple[AgentTurnView, ...] = ()
    action_page: InternalActionPage | None = None
    waited_ms: int = 0
    task_revision: int = 1

    def __post_init__(self) -> None:
        if self.current_task_evaluation.observation_id != self.current_world.observation_id:
            raise ValueError("run evaluation must describe the current world")
        if self.remaining_steps < 0:
            raise ValueError("remaining steps cannot be negative")
        if self.observation_count < 1 or self.execution_count < 0 or self.step_count < 0:
            raise ValueError("run counters are invalid")
        if self.waited_ms < 0:
            raise ValueError("run wait duration cannot be negative")
        if self.task_revision < 1:
            raise ValueError("run task revision must be positive")
        self.recent_steps = tuple(self.recent_steps)
        if len(self.recent_steps) > MAX_RECENT_STEPS or any(
            not isinstance(item, AgentTurnView) for item in self.recent_steps
        ):
            raise ValueError("recent step context must be bounded and public")

    @property
    def terminal(self) -> bool:
        return self.status in {
            RunStatus.DONE,
            RunStatus.BLOCKED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }

    @property
    def final_observation(self) -> WorldObservation:
        return self.current_world

    @property
    def policy_failure(self) -> PolicyFailure | None:
        decision = self.last_step.decision if self.last_step is not None else None
        return decision if isinstance(decision, PolicyFailure) else None

    @property
    def failure_code(self) -> AgentFailureCode | None:
        return self.last_step.failure_code if self.last_step is not None else None

    @property
    def task_outcome(self):
        return self.current_task_evaluation.outcome

    @property
    def runtime_failure(self) -> RuntimeFailure | None:
        return self.last_step.runtime_failure if self.last_step is not None else None

    @property
    def sent_unknown_count(self) -> int:
        result = self.last_step.execution.result if self.last_step and self.last_step.execution else None
        return int(result is not None and result.dispatch_status.value == "sent_unknown")

    def next_context_generation(self) -> int:
        self.context_generation += 1
        return self.context_generation

    def remember_step(self, step: AgentTurnView) -> None:
        if not isinstance(step, AgentTurnView):
            raise TypeError("run step memory must be model-safe")
        self.recent_steps = (*self.recent_steps, step)[-MAX_RECENT_STEPS:]

    def apply(self, result: StepResult, *, consume_step: bool = True) -> None:
        if self.status is not RunStatus.RUNNING:
            raise ValueError("only a running state can accept a step")
        if result.before_world.observation_id != self.current_world.observation_id:
            raise ValueError("step starts from a stale world")
        acquired_new_world = result.after_world.observation_id != result.before_world.observation_id
        self.current_world = result.after_world
        self.current_task_evaluation = result.task_evaluation
        self.last_step = result
        self.status = result.status_after
        if consume_step:
            self.remaining_steps = max(0, self.remaining_steps - 1)
        self.observation_count += int(acquired_new_world)
        self.execution_count += int(result.execution is not None)
        self.step_count += int(consume_step)
        self.action_page = result.action_page
        self.waited_ms += result.waited_ms
        if self.status is RunStatus.RUNNING and self.remaining_steps == 0:
            self.status = RunStatus.BLOCKED
