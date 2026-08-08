"""Policy and independent evaluation ports for the target short loop."""

from typing import Protocol

from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation


class AgentPolicy(Protocol):
    async def decide(self, context: AgentContext) -> AgentDecision: ...


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
