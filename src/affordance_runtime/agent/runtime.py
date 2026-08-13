"""Production composition root for the target AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.agent.episode_runner import AgentEpisodeRunner
from affordance_runtime.agent.loop import AgentLoop
from affordance_runtime.agent.policy import ActionEvaluator, AgentDecisionPorts, TaskEvaluator
from affordance_runtime.agent.result import AgentResult
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import (
    NaturalLanguageTaskRequest,
    ReadyTask,
    TaskIntake,
    TaskIntakeOutcome,
    ThinTaskIntake,
)
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder
from affordance_runtime.world.environment import WorldEnvironment


@dataclass(frozen=True)
class TargetRuntimeStartOutcome:
    intake: TaskIntakeOutcome
    session: AgentRunSession | None = None

    def __post_init__(self) -> None:
        if isinstance(self.intake, ReadyTask) != (self.session is not None):
            raise ValueError("target runtime start must align intake admission and session")

    @property
    def started(self) -> bool:
        return self.session is not None


@dataclass(frozen=True)
class TargetRuntime:
    """Own target-loop construction; adapters and benchmarks only inject ports."""

    decision_ports: AgentDecisionPorts
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    intake: TaskIntake = field(default_factory=ThinTaskIntake)
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    recent_turn_limit: int = 12

    def __post_init__(self) -> None:
        if not isinstance(self.decision_ports, AgentDecisionPorts):
            raise TypeError("TargetRuntime requires explicit AgentDecisionPorts")
        if not callable(getattr(self.action_evaluator, "evaluate", None)):
            raise TypeError("TargetRuntime action evaluator is invalid")
        if not callable(getattr(self.task_evaluator, "evaluate", None)):
            raise TypeError("TargetRuntime task evaluator is invalid")
        if not callable(getattr(self.intake, "compile", None)):
            raise TypeError("TargetRuntime intake is invalid")
        if not 1 <= self.recent_turn_limit <= 100:
            raise ValueError("TargetRuntime recent turn limit is invalid")

    def build_loop(self) -> AgentLoop:
        return AgentLoop(
            self.decision_ports,
            self.action_evaluator,
            self.task_evaluator,
            action_space_builder=self.action_space_builder,
            binder=self.binder,
            risk_policy=self.risk_policy,
            context_builder=self.context_builder,
            wait_controller=self.wait_controller,
            recent_turn_limit=self.recent_turn_limit,
        )

    async def start_task(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> AgentRunSession:
        return await AgentEpisodeRunner(self.build_loop()).start(environment, task, intent_context)

    async def run_task(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> AgentResult:
        session = await self.start_task(environment, task, intent_context)
        return await session.run_until_pause()

    async def start_request(
        self,
        environment: WorldEnvironment,
        request: NaturalLanguageTaskRequest,
    ) -> TargetRuntimeStartOutcome:
        admitted = self.intake.compile(request)
        if not isinstance(admitted, ReadyTask):
            return TargetRuntimeStartOutcome(admitted)
        session = await self.start_task(environment, admitted.task, admitted.intent_context)
        return TargetRuntimeStartOutcome(admitted, session)
