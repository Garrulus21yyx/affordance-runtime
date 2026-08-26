"""Production composition root for the single core GUI-agent loop."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

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
from affordance_runtime.agent.policy import ActionOutcomeProjector, AgentDecisionPorts, TaskEvaluator
from affordance_runtime.agent.run_control import (
    CooperativeRunControl,
    RunControlAdmission,
    RunControlBoundary,
    RunControlKind,
    RunControlOutcome,
)
from affordance_runtime.agent.run_state import RunCheckpointFacts, RunState, RunStatus
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.goals.compiler import GoalCompiler, GoalPlanBoundary, UnavailableGoalCompiler
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import (
    NaturalLanguageTaskRequest,
    ReadyTask,
    TaskIntake,
    TaskIntakeOutcome,
    ThinTaskIntake,
)
from affordance_runtime.task.revision import (
    RevisionReady,
    TaskRevisionBoundary,
    TaskRevisionCompiler,
    TaskRevisionCompilerOutcome,
    UnavailableTaskRevisionCompiler,
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
class TargetRuntimeRevisionOutcome:
    compiler: TaskRevisionCompilerOutcome
    intake: TaskIntakeOutcome | None = None

    def __post_init__(self) -> None:
        if isinstance(self.compiler, RevisionReady) != (self.intake is not None):
            raise ValueError("Runtime revision must align compiler and intake outcomes")


@dataclass(frozen=True)
class TargetRuntime:
    """Own the only product loop; adapters and benchmarks inject ports."""

    decision_ports: AgentDecisionPorts
    action_outcome_projector: ActionOutcomeProjector
    task_evaluator: TaskEvaluator
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    intake: TaskIntake = field(default_factory=ThinTaskIntake)
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    trace_sink: RunTraceSink = field(default_factory=NullRunTraceSink)
    required_decisions: frozenset[DecisionCapability] = field(default_factory=frozenset)
    goal_compiler: GoalCompiler = field(default_factory=UnavailableGoalCompiler)
    goal_plan_boundary: GoalPlanBoundary = field(default_factory=GoalPlanBoundary)
    task_revision_compiler: TaskRevisionCompiler = field(
        default_factory=UnavailableTaskRevisionCompiler
    )
    task_revision_boundary: TaskRevisionBoundary = field(
        default_factory=TaskRevisionBoundary
    )
    runtime_controls: tuple[str, ...] = ()
    episode_monitor: object | None = None
    official_outcome_sink: object | None = None
    run_control: CooperativeRunControl = field(
        default_factory=CooperativeRunControl,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.decision_ports, AgentDecisionPorts):
            raise TypeError("TargetRuntime requires explicit AgentDecisionPorts")
        if not callable(getattr(self.action_outcome_projector, "evaluate", None)):
            raise TypeError("TargetRuntime action outcome projector is invalid")
        if not callable(getattr(self.task_evaluator, "evaluate", None)):
            raise TypeError("TargetRuntime task evaluator is invalid")
        if not callable(getattr(self.intake, "compile", None)):
            raise TypeError("TargetRuntime intake is invalid")
        if not callable(getattr(self.goal_compiler, "compile", None)):
            raise TypeError("TargetRuntime goal compiler is invalid")
        if not callable(getattr(self.task_revision_compiler, "compile", None)):
            raise TypeError("TargetRuntime task revision compiler is invalid")
        if not isinstance(self.run_control, CooperativeRunControl):
            raise TypeError("TargetRuntime cooperative control owner is invalid")
        required = normalize_decision_capabilities(
            self.required_decisions,
            field_name="TargetRuntime required_decisions",
        )
        object.__setattr__(self, "required_decisions", required)
        supported = self.decision_ports.supported_decisions
        missing = required - supported
        if missing:
            raise UnsupportedCompositionError(UnsupportedComposition(required, supported, missing))

    def build_loop(self) -> CoreAgentLoop:
        return CoreAgentLoop(
            self.decision_ports,
            self.action_outcome_projector,
            self.task_evaluator,
            action_space_builder=self.action_space_builder,
            binder=self.binder,
            risk_policy=self.risk_policy,
            context_builder=self.context_builder,
            wait_controller=self.wait_controller,
            trace_sink=self.trace_sink,
            goal_compiler=self.goal_compiler,
            goal_plan_boundary=self.goal_plan_boundary,
            runtime_controls=self.runtime_controls,
            episode_monitor=self.episode_monitor,
            official_outcome_sink=self.official_outcome_sink,
            run_control=self.run_control,
        )

    def request_control(
        self,
        command_id: str,
        kind: RunControlKind,
    ) -> RunControlAdmission:
        return self.run_control.request(command_id, kind)

    def export_checkpoint_history(self) -> Mapping[str, object]:
        """Read model history at the policy owner after a closed safe boundary."""

        exporter = getattr(self.decision_ports.action_policy, "export_checkpoint_history", None)
        if not callable(exporter):
            return {"format": "unavailable", "messages": []}
        history = exporter()
        if not isinstance(history, Mapping):
            raise TypeError("Runtime checkpoint history must be a mapping")
        return history

    async def persist_checkpoint_history(self) -> Mapping[str, object]:
        """Durably settle model history before the Runtime checkpoint refers to it."""

        persister = getattr(
            self.decision_ports.action_policy,
            "persist_checkpoint_history",
            None,
        )
        if not callable(persister):
            return self.export_checkpoint_history()
        history = persister()
        if inspect.isawaitable(history):
            history = await history
        if not isinstance(history, Mapping):
            raise TypeError("Runtime persisted checkpoint history must be a mapping")
        return history

    def restore_checkpoint_history(
        self,
        payload: Mapping[str, object],
        *,
        task_id: str,
        task_revision: int,
    ) -> None:
        restorer = getattr(self.decision_ports.action_policy, "restore_checkpoint_history", None)
        if not callable(restorer):
            raise TypeError("Runtime model policy does not support checkpoint restoration")
        restorer(payload, task_id=task_id, task_revision=task_revision)

    async def restore_persisted_checkpoint_history(
        self,
        payload: Mapping[str, object],
        *,
        task_id: str,
        task_revision: int,
    ) -> None:
        restorer = getattr(
            self.decision_ports.action_policy,
            "restore_persisted_checkpoint_history",
            None,
        )
        if not callable(restorer):
            self.restore_checkpoint_history(
                payload,
                task_id=task_id,
                task_revision=task_revision,
            )
            return
        restored = restorer(
            payload,
            task_id=task_id,
            task_revision=task_revision,
        )
        if inspect.isawaitable(restored):
            await restored

    def rebind_checkpoint_history(
        self,
        *,
        task_id: str,
        current_revision: int,
        revised_revision: int,
    ) -> None:
        rebind = getattr(self.decision_ports.action_policy, "rebind_checkpoint_history", None)
        if not callable(rebind):
            raise TypeError("Runtime model policy does not support task revision")
        rebind(
            task_id=task_id,
            current_revision=current_revision,
            revised_revision=revised_revision,
        )

    def apply_waiting_control(
        self,
        state: RunState,
    ) -> RunControlOutcome | None:
        boundary = {
            "waiting_user": RunControlBoundary.WAITING_USER,
            "waiting_confirmation": RunControlBoundary.WAITING_CONFIRMATION,
        }.get(state.status.value)
        if (
            boundary is None
            and state.control_boundary is not None
            and state.control_boundary.kind is RunControlKind.PAUSE
        ):
            boundary = RunControlBoundary.BEFORE_POLICY
        if boundary is None:
            raise ValueError("run is not at a waiting control boundary")
        request = self.run_control.pending
        close = getattr(self.decision_ports.action_policy, "close_deferred_call", None)
        if callable(close) and state.last_step is not None:
            try:
                close(state.last_step)
            except Exception:
                if request is not None and request.kind is RunControlKind.PAUSE:
                    return self.run_control.fail_pending("deferred_history_closure_failed")
        outcome = self.run_control.acknowledge(boundary)
        if outcome is not None:
            state.apply_control_boundary(outcome)
            emit = getattr(self.trace_sink, "control_boundary_reached", None)
            if callable(emit):
                emit(outcome)
            if outcome.kind is RunControlKind.CANCEL:
                self.trace_sink.run_finished(state)
        return outcome

    def resume_control(self, state: RunState, command_id: str) -> RunControlOutcome:
        if (
            state.control_boundary is None
            or state.control_boundary.kind is not RunControlKind.PAUSE
            or self.run_control.paused is None
        ):
            raise ValueError("run has no matching internal pause boundary")
        restored_checkpoint = bool(state.durable_checkpoint_id)
        outcome = self.run_control.resume(command_id)
        state.resume_control_boundary()
        self.trace_sink.run_resumed(
            "control",
            {"command_id": command_id, "outcome": outcome.outcome.value},
        )
        if restored_checkpoint:
            self.build_loop().settle_restored_currentness(state)
        return outcome

    async def recover_pause_persistence_failure(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        command_id: str,
    ) -> RunState:
        """Clear an uncommitted pause and recover a fresh current World."""

        prior_status = state.status
        self.resume_control(state, command_id)
        if prior_status is RunStatus.RUNNING:
            return await self.build_loop().refresh_after_pause_persistence_failure(
                environment,
                task,
                state,
            )
        return state

    async def restore_paused_checkpoint(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        facts: RunCheckpointFacts,
        checkpoint_id: str,
    ) -> RunState:
        """Restore Runtime/model/control owners before exposing a recovered session."""

        self.run_control.restore_paused(facts.pause_boundary)
        try:
            return await self.build_loop().restore_paused(
                environment,
                task,
                facts,
                checkpoint_id,
            )
        except BaseException:
            self.run_control.resume("restore-failed")
            raise

    async def compile_task_revision(
        self,
        admitted: ReadyTask,
        text: str,
    ) -> TargetRuntimeRevisionOutcome:
        """Compile once, then re-admit the complete consecutive TaskGoal."""

        compiled = await self.task_revision_boundary.resolve(
            self.task_revision_compiler,
            admitted.task,
            text,
        )
        if not isinstance(compiled, RevisionReady):
            return TargetRuntimeRevisionOutcome(compiled)
        request = NaturalLanguageTaskRequest(
            admitted.task.task_id,
            compiled.proposal.instruction,
            compiled.proposal.boundary,
            admitted.intent_context,
            admitted.source_ref,
            admitted.task.revision + 1,
        )
        return TargetRuntimeRevisionOutcome(compiled, self.intake.compile(request))

    async def prepare_paused_task_revision(
        self,
        environment: WorldEnvironment,
        current_task: TaskGoal,
        revised_task: TaskGoal,
        state: RunState,
    ) -> RunState:
        return await self.build_loop().revise_paused(
            environment,
            current_task,
            revised_task,
            state,
        )

    def with_runtime_controls(
        self,
        runtime_controls: tuple[str, ...],
        *,
        episode_monitor: object | None = None,
    ) -> TargetRuntime:
        return replace(
            self,
            runtime_controls=tuple(runtime_controls),
            episode_monitor=episode_monitor,
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
