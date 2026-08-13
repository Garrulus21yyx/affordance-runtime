"""Product-owned composition root for the target Runtime."""

from __future__ import annotations

from affordance_runtime.agent.decision_capability import DecisionCapability
from affordance_runtime.agent.local_objective_proposal import LocalObjectiveProposalPort
from affordance_runtime.agent.policy import (
    ActionEvaluator,
    AgentDecisionPorts,
    AgentPolicy,
    LocalObjectiveProposalRequirement,
    TaskEvaluator,
)
from affordance_runtime.agent.runtime import TargetRuntime
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.intake import TaskIntake, ThinTaskIntake
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder


def compose_target_runtime(
    action_policy: AgentPolicy,
    action_evaluator: ActionEvaluator,
    task_evaluator: TaskEvaluator,
    *,
    local_objective_proposer: LocalObjectiveProposalPort | None = None,
    local_objective_requirement: LocalObjectiveProposalRequirement = (
        LocalObjectiveProposalRequirement.NOT_REQUIRED
    ),
    required_decisions: frozenset[DecisionCapability] = frozenset(),
    risk_policy: RiskPolicy | None = None,
    intake: TaskIntake | None = None,
    action_space_builder: ActionSpaceBuilder | None = None,
    binder: ActionBinder | None = None,
    context_builder: ContextBuilder | None = None,
    wait_controller: WaitController | None = None,
    recent_turn_limit: int = 12,
) -> TargetRuntime:
    """Compose product and benchmark target runs through one validation boundary."""

    return TargetRuntime(
        AgentDecisionPorts(
            action_policy,
            local_objective_proposer,
            local_objective_requirement,
        ),
        action_evaluator,
        task_evaluator,
        risk_policy=risk_policy or RiskPolicy(),
        intake=intake or ThinTaskIntake(),
        action_space_builder=action_space_builder or ActionSpaceBuilder(),
        binder=binder or ActionBinder(),
        context_builder=context_builder or ContextBuilder(),
        wait_controller=wait_controller or SystemWaitController(),
        recent_turn_limit=recent_turn_limit,
        required_decisions=required_decisions,
    )
