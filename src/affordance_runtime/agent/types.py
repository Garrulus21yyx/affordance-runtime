"""Small immutable contracts for the short agent loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.contracts import ActionContract, ExecutionReceipt, Observation


class AgentLoopStatus(StrEnum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    FAILED = "failed"


class LoopDecisionKind(StrEnum):
    EXECUTE = "execute"
    REOBSERVE = "reobserve"
    REPLAN = "replan"
    ASK_USER = "ask_user"
    STOP = "stop"
    DONE = "done"


@dataclass(frozen=True)
class TaskGoal:
    goal_id: str
    objective: str
    max_steps: int = 20

    def __post_init__(self) -> None:
        if not self.goal_id or not self.objective.strip():
            raise ValueError("task goal requires identity and objective")
        if not 1 <= self.max_steps <= 100:
            raise ValueError("task goal max_steps must be within [1, 100]")


@dataclass(frozen=True)
class LoopDecision:
    kind: LoopDecisionKind
    reason: str
    contract: ActionContract | None = None
    user_prompt: str = ""

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("loop decision reason cannot be blank")
        if self.kind == LoopDecisionKind.EXECUTE and self.contract is None:
            raise ValueError("execute decision requires an action contract")
        if self.kind != LoopDecisionKind.EXECUTE and self.contract is not None:
            raise ValueError("only execute decisions may carry an action contract")
        if self.kind == LoopDecisionKind.ASK_USER and not self.user_prompt.strip():
            raise ValueError("ask-user decision requires a prompt")


@dataclass(frozen=True)
class ActionEvaluation:
    action_verified: bool
    task_complete: bool
    reason: str
    requires_user: bool = False
    user_prompt: str = ""

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("action evaluation reason cannot be blank")
        if self.requires_user and not self.user_prompt.strip():
            raise ValueError("user-required evaluation needs a prompt")


@dataclass(frozen=True)
class AgentTurn:
    decision: LoopDecision
    observation_before: Observation
    receipt: ExecutionReceipt | None = None
    observation_after: Observation | None = None
    evaluation: ActionEvaluation | None = None


@dataclass(frozen=True)
class AgentResult:
    status: AgentLoopStatus
    goal: TaskGoal
    final_observation: Observation
    turns: tuple[AgentTurn, ...]
    observation_count: int
    execution_count: int
    message: str = ""
