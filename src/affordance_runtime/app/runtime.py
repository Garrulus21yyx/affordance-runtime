"""Production composition root for the single core GUI-agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.core_loop import CoreAgentLoop
from affordance_runtime.agent.decision_capability import (
    DecisionCapability,
    UnsupportedComposition,
    UnsupportedCompositionError,
    normalize_decision_capabilities,
)
from affordance_runtime.agent.observability import NullRunTraceSink, RunTraceSink
from affordance_runtime.agent.policy import ActionEvaluator, AgentDecisionPorts, TaskEvaluator
from affordance_runtime.agent.run_state import RunState
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import (
    NaturalLanguageTaskRequest,
    ReadyTask,
    TaskIntake,
    TaskIntakeOutcome,
    ThinTaskIntake,
)
from affordance_runtime.world.environment import WorldEnvironment


@dataclass(frozen=True)
class TargetRuntimeRunOutcome:
    """One intake outcome and, when admitted, its authoritative run state."""

    intake: TaskIntakeOutcome
    state: RunState | None = None

    def __post_init__(self) -> None:
        if isinstance(self.intake, ReadyTask) != (self.state is not None):
            raise ValueError("target runtime run must align intake and state")

    @property
    def started(self) -> bool:
        return self.state is not None


@dataclass(frozen=True)
class TargetRuntime:
    """Own the only product loop; adapters and benchmarks inject ports."""

    decision_ports: AgentDecisionPorts
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    intake: TaskIntake = field(default_factory=ThinTaskIntake)
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    trace_sink: RunTraceSink = field(default_factory=NullRunTraceSink)
    required_decisions: frozenset[DecisionCapability] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.decision_ports, AgentDecisionPorts):
            raise TypeError("TargetRuntime requires explicit AgentDecisionPorts")
        if not callable(getattr(self.action_evaluator, "evaluate", None)):
            raise TypeError("TargetRuntime action evaluator is invalid")
        if not callable(getattr(self.task_evaluator, "evaluate", None)):
            raise TypeError("TargetRuntime task evaluator is invalid")
        if not callable(getattr(self.intake, "compile", None)):
            raise TypeError("TargetRuntime intake is invalid")
        required = normalize_decision_capabilities(
            self.required_decisions,
            field_name="TargetRuntime required_decisions",
        )
        object.__setattr__(self, "required_decisions", required)
        supported = self.decision_ports.supported_decisions
        missing = required - supported
        if missing:
            raise UnsupportedCompositionError(
                UnsupportedComposition(required, supported, missing)
            )

    def build_loop(self) -> CoreAgentLoop:
        return CoreAgentLoop(
            self.decision_ports,
            self.action_evaluator,
            self.task_evaluator,
            action_space_builder=self.action_space_builder,
            binder=self.binder,
            risk_policy=self.risk_policy,
            context_builder=self.context_builder,
            wait_controller=self.wait_controller,
            trace_sink=self.trace_sink,
        )

    async def run_task(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
    ) -> RunState:
        return await self.build_loop().run(environment, task)

    async def initialize_task(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
    ) -> RunState:
        return await self.build_loop().initialize(environment, task)

    async def continue_task(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        return await self.build_loop().continue_run(environment, task, state)

    async def resume_user(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        return await self.build_loop().resume_user(environment, task, state)

    async def resume_confirmation(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        *,
        approved: bool,
    ) -> RunState:
        return await self.build_loop().resume_confirmation(
            environment,
            task,
            state,
            approved=approved,
        )

    def admit(self, request: NaturalLanguageTaskRequest) -> TaskIntakeOutcome:
        """Compile stable task authority before allocating a world session."""

        return self.intake.compile(request)

    async def run_request(
        self,
        environment: WorldEnvironment,
        request: NaturalLanguageTaskRequest,
    ) -> TargetRuntimeRunOutcome:
        admitted = self.admit(request)
        if not isinstance(admitted, ReadyTask):
            return TargetRuntimeRunOutcome(admitted)
        return await self.run_admitted(environment, admitted)

    async def run_admitted(
        self,
        environment: WorldEnvironment,
        admitted: ReadyTask,
    ) -> TargetRuntimeRunOutcome:
        if not isinstance(admitted, ReadyTask):
            raise TypeError("target runtime admitted run requires ReadyTask")
        state = await self.run_task(
            environment,
            admitted.task,
        )
        return TargetRuntimeRunOutcome(admitted, state)

    async def resume_request(
        self,
        environment: WorldEnvironment,
        state: RunState,
        request: NaturalLanguageTaskRequest,
    ) -> TargetRuntimeRunOutcome:
        """Re-admit one consecutive task revision and continue a waiting run."""

        admitted = self.intake.compile(request)
        if not isinstance(admitted, ReadyTask):
            return TargetRuntimeRunOutcome(admitted)
        resumed = await self.resume_user(
            environment,
            admitted.task,
            state,
        )
        return TargetRuntimeRunOutcome(admitted, resumed)
