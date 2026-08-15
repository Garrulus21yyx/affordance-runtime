"""Product-owned composition root for the target Runtime."""

from __future__ import annotations

from collections.abc import Mapping

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.agent.policy import (
    ActionEvaluator,
    AgentDecisionPorts,
    AgentPolicy,
    TaskEvaluator,
)
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.evaluation import ProductionActionEvaluator, ProductionTaskEvaluator
from affordance_runtime.model.policy import model_policy_from_environment
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.intake import TaskIntake, ThinTaskIntake


def compose_target_runtime(
    action_policy: AgentPolicy,
    action_evaluator: ActionEvaluator,
    task_evaluator: TaskEvaluator,
    *,
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
        AgentDecisionPorts(action_policy),
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


def compose_target_runtime_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
) -> TargetRuntime:
    """Compose the configured model against the supported product GUI control set."""

    policy = model_policy_from_environment(
        environment,
        call_timeout_s=call_timeout_s,
    )
    return compose_target_runtime(
        policy,
        ProductionActionEvaluator(),
        ProductionTaskEvaluator(),
        required_decisions=GROUNDED_ACTION_DECISION_CAPABILITIES,
    )
