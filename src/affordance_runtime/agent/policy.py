"""Policy protocols and the deliberately small post-action loop policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from affordance_runtime.agent.types import (
    ActionEvaluation,
    AgentTurn,
    LoopDecision,
    LoopDecisionKind,
    TaskGoal,
)
from affordance_runtime.contracts import ExecutionReceipt, Observation, TransportState


class AgentPolicy(Protocol):
    async def decide(
        self,
        goal: TaskGoal,
        observation: Observation,
        recent_turns: tuple[AgentTurn, ...],
    ) -> LoopDecision: ...


class TaskEvaluator(Protocol):
    async def evaluate(
        self,
        goal: TaskGoal,
        observation_before: Observation,
        receipt: ExecutionReceipt,
        observation_after: Observation,
    ) -> ActionEvaluation: ...


@dataclass(frozen=True)
class LoopPolicy:
    max_unverified_actions: int = 2

    def __post_init__(self) -> None:
        if self.max_unverified_actions < 1:
            raise ValueError("loop policy requires a positive unverified-action bound")

    def after_action(
        self,
        receipt: ExecutionReceipt,
        evaluation: ActionEvaluation,
        *,
        consecutive_unverified: int,
    ) -> LoopDecisionKind:
        if evaluation.task_complete:
            return LoopDecisionKind.DONE
        if evaluation.requires_user:
            return LoopDecisionKind.ASK_USER
        if consecutive_unverified >= self.max_unverified_actions:
            return LoopDecisionKind.STOP
        if receipt.transport_state == TransportState.SENT_UNKNOWN:
            # A fresh observation has already happened. Replan from that fact;
            # never convert transport uncertainty into an implicit retry.
            return LoopDecisionKind.REPLAN
        if not receipt.success or not evaluation.action_verified:
            return LoopDecisionKind.REPLAN
        return LoopDecisionKind.REOBSERVE
