"""Policy and independent evaluation ports for the target short loop."""

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.failures import ModelFailureKind
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


@dataclass(frozen=True)
class PolicyFailure:
    kind: ModelFailureKind
    reason: str
    retryable: bool = False

    def __post_init__(self) -> None:
        if not self.reason.strip() or len(self.reason) > 240:
            raise ValueError("policy failure requires a bounded public reason")


AgentPolicyOutcome: TypeAlias = AgentDecision | PolicyFailure


class AgentPolicy(Protocol):
    async def decide(self, context: AgentContext) -> AgentPolicyOutcome: ...


class ActionEvaluator(Protocol):
    async def evaluate(
        self,
        task: TaskGoal,
        before: WorldObservation,
        request: BoundActionRequest,
        result: ActionResult,
        after: WorldObservation,
    ) -> ActionEvaluation: ...


class TaskEvaluator(Protocol):
    async def evaluate(self, task: TaskGoal, observation: WorldObservation) -> TaskEvaluation: ...
