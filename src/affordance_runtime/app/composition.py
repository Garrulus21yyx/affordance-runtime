"""Product-owned composition root for the target Runtime."""

from __future__ import annotations

import os
from collections.abc import Mapping

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.decision_capability import (
    GROUNDED_ACTION_DECISION_CAPABILITIES,
    DecisionCapability,
)
from affordance_runtime.agent.monitor import EpisodeMonitor
from affordance_runtime.agent.observability import (
    NullRunTraceSink,
    RunTraceSink,
    trace_recorder_from_environment,
)
from affordance_runtime.agent.policy import (
    ActionOutcomeProjector,
    AgentDecisionPorts,
    AgentPolicy,
    TaskEvaluator,
)
from affordance_runtime.agent.run_control import CooperativeRunControl
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.app.runtime import TargetRuntime
from affordance_runtime.evaluation import ProductionActionOutcomeProjector, ProductionTaskEvaluator
from affordance_runtime.goals.compiler import GoalCompiler, GoalPlanBoundary, UnavailableGoalCompiler
from affordance_runtime.model.policy import model_roles_from_environment
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.intake import TaskIntake, ThinTaskIntake
from affordance_runtime.task.revision import (
    TaskRevisionBoundary,
    TaskRevisionCompiler,
    UnavailableTaskRevisionCompiler,
)


def compose_target_runtime(
    action_policy: AgentPolicy,
    action_outcome_projector: ActionOutcomeProjector,
    task_evaluator: TaskEvaluator,
    *,
    required_decisions: frozenset[DecisionCapability] = frozenset(),
    risk_policy: RiskPolicy | None = None,
    intake: TaskIntake | None = None,
    action_space_builder: ActionSpaceBuilder | None = None,
    binder: ActionBinder | None = None,
    context_builder: ContextBuilder | None = None,
    wait_controller: WaitController | None = None,
    trace_sink: RunTraceSink | None = None,
    goal_compiler: GoalCompiler | None = None,
    goal_plan_boundary: GoalPlanBoundary | None = None,
    task_revision_compiler: TaskRevisionCompiler | None = None,
    task_revision_boundary: TaskRevisionBoundary | None = None,
    runtime_controls: tuple[str, ...] = (),
    episode_monitor: object | None = None,
    official_outcome_sink: object | None = None,
    run_control: CooperativeRunControl | None = None,
) -> TargetRuntime:
    """Compose product and benchmark target runs through one validation boundary."""

    return TargetRuntime(
        AgentDecisionPorts(action_policy),
        action_outcome_projector,
        task_evaluator,
        risk_policy=risk_policy or RiskPolicy(),
        intake=intake or ThinTaskIntake(),
        action_space_builder=action_space_builder or ActionSpaceBuilder(),
        binder=binder or ActionBinder(),
        context_builder=context_builder or ContextBuilder(),
        wait_controller=wait_controller or SystemWaitController(),
        trace_sink=trace_sink if trace_sink is not None else NullRunTraceSink(),
        required_decisions=required_decisions,
        goal_compiler=goal_compiler or UnavailableGoalCompiler(),
        goal_plan_boundary=goal_plan_boundary or GoalPlanBoundary(),
        task_revision_compiler=(
            task_revision_compiler or UnavailableTaskRevisionCompiler()
        ),
        task_revision_boundary=task_revision_boundary or TaskRevisionBoundary(),
        runtime_controls=runtime_controls,
        episode_monitor=episode_monitor if episode_monitor is not None else EpisodeMonitor(),
        official_outcome_sink=official_outcome_sink,
        run_control=run_control or CooperativeRunControl(),
    )


def compose_target_runtime_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    call_timeout_s: float = 90.0,
) -> TargetRuntime:
    """Compose the configured model against the supported product GUI control set."""

    runtime_environment = os.environ if environment is None else environment
    model_roles = model_roles_from_environment(
        runtime_environment,
        call_timeout_s=call_timeout_s,
    )
    return compose_target_runtime(
        model_roles.action_policy,
        ProductionActionOutcomeProjector(),
        ProductionTaskEvaluator(),
        required_decisions=GROUNDED_ACTION_DECISION_CAPABILITIES,
        trace_sink=trace_recorder_from_environment(runtime_environment),
        goal_compiler=model_roles.goal_compiler,
        task_revision_compiler=model_roles.task_revision_compiler,
    )
