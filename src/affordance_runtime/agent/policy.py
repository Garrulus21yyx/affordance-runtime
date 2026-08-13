"""Policy and independent evaluation ports for the target short loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeAlias

from affordance_runtime.agent.decision_capability import (
    DecisionCapability,
    normalize_decision_capabilities,
)
from affordance_runtime.agent.decisions import AgentDecision
from affordance_runtime.evaluation.contracts import ActionEvaluation, TaskEvaluation
from affordance_runtime.execution.contracts import ActionResult, BoundActionRequest
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.model_boundary.failures import ModelFailureKind
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import WorldObservation

if TYPE_CHECKING:
    from affordance_runtime.agent.local_objective_proposal import LocalObjectiveProposalPort


@dataclass(frozen=True)
class PolicyFailure:
    kind: ModelFailureKind
    reason: str
    retryable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ModelFailureKind):
            raise TypeError("policy failure kind must be typed")
        if type(self.retryable) is not bool:
            raise TypeError("policy failure retryable flag must be boolean")
        if not self.reason.strip() or len(self.reason) > 240:
            raise ValueError("policy failure requires a bounded public reason")


AgentPolicyOutcome: TypeAlias = AgentDecision | PolicyFailure


class AgentPolicy(Protocol):
    """Choose one current action/control operation; never construct objectives."""

    async def decide(self, context: AgentContext) -> AgentPolicyOutcome: ...


@dataclass(frozen=True)
class AgentDecisionPorts:
    """Explicit model-facing phase composition for one AgentLoop."""

    action_policy: AgentPolicy
    local_objective_proposer: LocalObjectiveProposalPort | None = None

    def __post_init__(self) -> None:
        if not callable(getattr(self.action_policy, "decide", None)):
            raise TypeError("AgentDecisionPorts requires an action policy")
        if self.local_objective_proposer is not None and not callable(
            getattr(self.local_objective_proposer, "propose", None)
        ):
            raise TypeError("AgentDecisionPorts objective proposer is invalid")

    @property
    def supported_decisions(self) -> frozenset[DecisionCapability]:
        return normalize_decision_capabilities(
            getattr(self.action_policy, "supported_decisions", frozenset()),
            field_name="action policy supported_decisions",
        )


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
