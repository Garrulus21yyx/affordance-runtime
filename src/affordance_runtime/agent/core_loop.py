"""Readable observe-decide-act-observe-evaluate loop for every product run."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import assert_never

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder, BindingError
from affordance_runtime.agent.attempt_signature import public_attempt_signature
from affordance_runtime.agent.budgets import StandaloneRunBudget
from affordance_runtime.agent.context.canonical_world_projection import (
    CanonicalPublicWorldProjection,
    PublicGroundingAmbiguousError,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.context.observation_delivery import (
    DeliveryTransition,
    current_findings_digest,
)
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import WorldTransitionProjector
from affordance_runtime.agent.decisions import (
    Abort,
    AbortCategory,
    AgentDecision,
    AskUser,
    DecisionKind,
    FinalResponse,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.evaluation_control import (
    validated_action_outcome,
    validated_task_evaluation_attempt,
)
from affordance_runtime.agent.finalization import FinalizationProtocolResult, admit_final_response
from affordance_runtime.agent.observability import (
    NullRunTraceSink,
    RunTraceSink,
    goal_compiler_trace_diagnostic,
    goal_guidance_trace_payload,
)
from affordance_runtime.agent.policy import (
    ActionOutcomeProjector,
    AgentDecisionPorts,
    PolicyFailure,
    TaskEvaluator,
)
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.run_state import (
    ControlTermination,
    ControlTerminationKind,
    RunState,
    RunStatus,
    StepResult,
)
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.waiting import MAX_TOTAL_WAIT_MS, SystemWaitController, WaitController
from affordance_runtime.agent.workspace import (
    DefaultWorkspaceReducer,
    WorkspaceReducer,
)
from affordance_runtime.evaluation.contracts import (
    CriterionEvaluationStatus,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.evaluation.invocation import (
    Evaluated,
    InternalFailure,
    TaskEvaluationInternalError,
    TaskEvaluationUnavailableError,
    Unavailable,
)
from affordance_runtime.execution.contracts import (
    DispatchStatus,
    ExecutionCancellationPhase,
    ExecutionCancelled,
    ExecutionCompletion,
    ExecutionOutcome,
    ExecutionReceiptBatch,
    SessionHealth,
    SessionHealthStatus,
)
from affordance_runtime.goals.compiler import (
    GoalCompiler,
    GoalCompileTrigger,
    GoalPlanBoundary,
    UnavailableGoalCompiler,
)
from affordance_runtime.goals.plan import GoalPlanResolution, NeedsInput, Ready
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    AcquisitionStatus,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.observation_needs import ObservationNeed, ObservationPurpose
from affordance_runtime.world.source_profile import ObservationAssurance, ObservationModality

_ASSURANCE_RANK = {
    ObservationAssurance.WEAK: 0,
    ObservationAssurance.STRUCTURAL: 1,
    ObservationAssurance.AUTHORITATIVE: 2,
}


def _action_feedback(effect: ObservedChange, postcondition: LocalPostconditionStatus) -> str:
    if postcondition is LocalPostconditionStatus.SATISFIED:
        return "action_postcondition_satisfied"
    if postcondition is LocalPostconditionStatus.UNSATISFIED:
        return "action_postcondition_unsatisfied_change_strategy"
    if effect is ObservedChange.UNCHANGED:
        return "action_unchanged_change_strategy"
    return "action_outcome_unknown"


class CoreLoopStartError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class CoreAgentLoop:
    decision_ports: AgentDecisionPorts
    action_outcome_projector: ActionOutcomeProjector
    task_evaluator: TaskEvaluator
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    workspace_reducer: WorkspaceReducer = field(default_factory=DefaultWorkspaceReducer)
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    trace_sink: RunTraceSink = field(default_factory=NullRunTraceSink)
    goal_compiler: GoalCompiler = field(default_factory=UnavailableGoalCompiler)
    goal_plan_boundary: GoalPlanBoundary = field(default_factory=GoalPlanBoundary)
    runtime_controls: tuple[str, ...] = ()
    episode_monitor: object | None = None
    official_outcome_sink: object | None = None

    async def run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
    ) -> RunState:
        state = await self.initialize(environment, task)
        return await self.continue_run(environment, task, state)

    async def initialize(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
    ) -> RunState:
        """Acquire the first world and create the sole run state."""

        acquisition = await environment.reset(task)
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            self.trace_sink.run_start_failed(task, acquisition)
            raise CoreLoopStartError(acquisition.reason_code)
        resolution = await self.goal_plan_boundary.resolve(
            self.goal_compiler,
            task,
            acquisition.observation,
            next_plan_version=1,
            trigger=GoalCompileTrigger.TASK_START,
        )
        state = await self._initialize_from_world(
            task,
            acquisition.observation,
            resolution,
            budget=StandaloneRunBudget(
                min(
                    task.loop_budget.max_turns,
                    getattr(
                        getattr(self.episode_monitor, "profile", None),
                        "max_policy_decisions",
                        task.loop_budget.max_turns,
                    ),
                )
            ),
        )
        self.trace_sink.run_started(task, state)
        self.trace_sink.goal_compiler_completed(
            goal_compiler_trace_diagnostic(
                self.goal_compiler,
                resolution,
                task_revision=task.revision,
                trigger=GoalCompileTrigger.TASK_START,
                initial_evidence=acquisition.observation,
            )
        )
        return state

    async def _initialize_from_world(
        self,
        task: TaskGoal,
        initial: WorldObservation,
        goal_resolution: GoalPlanResolution,
        *,
        budget: StandaloneRunBudget,
    ) -> RunState:
        """Create the sole run state from an already acquired initial World."""

        if not isinstance(budget, StandaloneRunBudget):
            raise TypeError("CoreLoop requires one validated typed budget")
        if goal_resolution.task_revision != task.revision:
            raise ValueError("episode goal resolution belongs to a previous task revision")
        initial_projection, initial_index = self._canonical_world_for(task, initial)
        evaluation = await self._validated_task_evaluation(task, initial, initial_projection)
        initial_status = self._status_for_goal_resolution(task, evaluation, goal_resolution)
        state = RunState(
            initial,
            evaluation,
            budget.turns,
            status=(
                RunStatus.RUNNING
                if isinstance(goal_resolution, NeedsInput) and initial_status is RunStatus.WAITING_USER
                else initial_status
            ),
            task_revision=task.revision,
            goal_resolution=goal_resolution,
            goal_plan_version_counter=(
                goal_resolution.accepted_plan.plan_version if isinstance(goal_resolution, Ready) else 0
            ),
        )
        state.install_delivery_index(initial_index)
        state.install_canonical_world(initial_projection)
        start_episode = getattr(self.episode_monitor, "start_episode", None)
        if callable(start_episode):
            start_episode(initial, evaluation)
        if isinstance(goal_resolution, NeedsInput) and initial_status is RunStatus.WAITING_USER:
            state.apply(
                StepResult(
                    AskUser(
                        f"context:goal-compiler:{task.revision}",
                        goal_resolution.question,
                        goal_resolution.fields,
                    ),
                    initial,
                    initial,
                    evaluation,
                    RunStatus.WAITING_USER,
                    feedback="goal_compiler_needs_input",
                ),
                consume_step=False,
            )
        elif evaluation.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}:
            self._record_official_outcome(evaluation)
        return state

    async def continue_run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        """Continue an initialized state until it pauses or terminates."""

        return await self._run_until_pause(environment, task, state)

    async def _run_until_pause(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        while state.status is RunStatus.RUNNING:
            try:
                result = await self.step(environment, task, state)
            except BaseException as exc:
                self.trace_sink.run_error(exc, state)
                raise
            result = self._attach_canonical_worlds(task, state, result)
            delivery = state.delivery_store.reduce(result, step_index=max(1, state.step_count + 1))
            result = self._apply_episode_monitor(result, state, delivery)
            self._commit_step(state, result)
        if state.terminal:
            self.trace_sink.run_finished(state)
        else:
            self.trace_sink.run_paused(state)
        return state

    async def resume_user(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        pending = state.last_step
        if state.status is not RunStatus.WAITING_USER or pending is None or not isinstance(pending.decision, AskUser):
            raise ValueError("core run has no pending user request")
        if task.task_id != state.current_task_evaluation.task_id or task.revision != state.task_revision + 1:
            raise ValueError("core user resume requires one consecutive task revision")
        await environment.revise_task(task)
        state.goal_resolution = None
        state.canonical_world = None
        projection, region_index = self._canonical_world_for(task, state.current_world)
        evaluation = await self._validated_task_evaluation(task, state.current_world, projection)
        resolution = await self.goal_plan_boundary.resolve(
            self.goal_compiler,
            task,
            state.current_world,
            next_plan_version=state.goal_plan_version_counter + 1,
            trigger=GoalCompileTrigger.TASK_REVISION,
        )
        status = self._status_for_goal_resolution(task, evaluation, resolution)
        decision = (
            AskUser(
                f"context:goal-compiler:{task.revision}",
                resolution.question,
                resolution.fields,
            )
            if isinstance(resolution, NeedsInput) and status is RunStatus.WAITING_USER
            else pending.decision
        )
        resumed = replace(
            pending,
            decision=decision,
            task_evaluation=evaluation,
            status_after=status,
            feedback=(
                "goal_compiler_needs_input"
                if isinstance(resolution, NeedsInput) and status is RunStatus.WAITING_USER
                else "user_input_received"
            ),
        )
        state.task_revision = task.revision
        state.install_delivery_index(region_index)
        state.install_canonical_world(projection)
        state.goal_resolution = resolution
        if isinstance(resolution, Ready):
            state.goal_plan_version_counter = resolution.accepted_plan.plan_version
        state.resume(RunStatus.WAITING_USER)
        resumed = self._commit_step(
            state,
            resumed,
            consume_step=False,
            trace_step=False,
        )
        self.trace_sink.run_resumed(
            "user",
            {
                "task_revision": task.revision,
                "goal_guidance": goal_guidance_trace_payload(resolution),
            },
        )
        self.trace_sink.goal_compiler_completed(
            goal_compiler_trace_diagnostic(
                self.goal_compiler,
                resolution,
                task_revision=task.revision,
                trigger=GoalCompileTrigger.TASK_REVISION,
                initial_evidence=state.current_world,
            )
        )
        return await self._run_until_pause(environment, task, state)

    def _commit_step(
        self,
        state: RunState,
        result: StepResult,
        *,
        consume_step: bool = True,
        trace_step: bool = True,
        delivery_transition: DeliveryTransition | None = None,
    ) -> StepResult:
        if consume_step and state.remaining_steps == 1 and result.status_after is RunStatus.RUNNING:
            result = replace(
                result,
                status_after=RunStatus.BLOCKED,
                feedback="turn_budget_exhausted",
                control_termination=ControlTermination(
                    ControlTerminationKind.TURN_BUDGET_EXHAUSTED
                ),
            )
        if delivery_transition is None:
            delivery_transition = state.delivery_store.reduce(
                result,
                step_index=max(1, state.step_count + int(consume_step)),
            )
        information_delta = delivery_transition.information_delta
        projected = (
            None
            if isinstance(result.decision, PolicyFailure)
            else project_step_result(result, information_delta=information_delta)
        )
        workspace = self.workspace_reducer.reduce(
            state.workspace,
            result,
            projected,
            max(1, state.step_count + int(consume_step)),
            information_delta=information_delta,
        )
        state.apply(
            result,
            consume_step=consume_step,
            delivery_transition=delivery_transition,
        )
        state.workspace = workspace
        if result.task_evaluation is not None and (
            (
                result.finalization is not None
                and result.finalization.native_evaluation_status is not None
            )
            or result.task_evaluation.status
            in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}
        ):
            self._record_official_outcome(result.task_evaluation)
        if trace_step:
            self.trace_sink.step_completed(state.step_count, result)
        return result

    def _attach_canonical_worlds(
        self,
        task: TaskGoal,
        state: RunState,
        result: StepResult,
    ) -> StepResult:
        """Orchestrate the World owner value; do not interpret its order or refs."""

        if result.before_public_world is not None or result.feedback == PublicGroundingAmbiguousError.code:
            return result
        before = state.canonical_world
        if before is None:
            before_actions = self.action_space_builder.build(task, result.before_world)
            before_index = state.delivery_index or WorldDeliveryIndex.from_observation(
                result.before_world, before_actions.options
            )
            before = CanonicalPublicWorldProjection.build(
                result.before_world, before_index, before_actions
            )
        if result.after_world is result.before_world or (
            result.after_world.observation_id == result.before_world.observation_id
        ):
            after = before
        else:
            after_actions = self.action_space_builder.build(task, result.after_world)
            after_index = WorldDeliveryIndex.from_observation(
                result.after_world,
                after_actions.options,
                public_world_delta=result.public_world_delta,
                previous_index=state.delivery_index or state.prior_delivery_index,
            )
            after = CanonicalPublicWorldProjection.build(
                result.after_world, after_index, after_actions
            )
        return replace(result, before_public_world=before, after_public_world=after)

    def _record_official_outcome(self, evaluation: TaskEvaluation) -> None:
        recorder = getattr(self.official_outcome_sink, "native_evaluator_returned", None)
        if not callable(recorder):
            recorder = getattr(self.trace_sink, "native_evaluator_returned", None)
        if callable(recorder):
            recorder(evaluation)

    def _apply_episode_monitor(
        self,
        result: StepResult,
        state: RunState,
        delivery_transition: DeliveryTransition,
    ) -> StepResult:
        monitor = self.episode_monitor
        if monitor is None or result.task_evaluation is None or result.status_after in {
            RunStatus.DONE,
            RunStatus.WAITING_USER,
            RunStatus.WAITING_CONFIRMATION,
            RunStatus.CANCELLED,
        }:
            return result
        evaluate = getattr(monitor, "evaluate", None)
        if not callable(evaluate):
            return result
        transition = evaluate(
            result,
            current_findings_digest(result.after_world),
            delivery_transition.information_delta,
        )
        recommendation = getattr(transition, "recommendation", "")
        if str(recommendation) == "recover":
            signal = getattr(transition, "recovery_signal", None)
            return replace(
                result,
                status_after=RunStatus.RUNNING,
                feedback=(
                    f"episode_monitor_recover:{getattr(signal.kind, 'value', 'strategy_stall')}"
                    if signal is not None
                    else "episode_monitor_recover:strategy_stall"
                ),
                recovery_signal=signal,
            )
        if str(recommendation) != "block":
            return result
        return replace(
            result,
            status_after=RunStatus.BLOCKED,
            feedback=f"episode_monitor_blocked:{getattr(transition, 'reason', 'stalled')}",
            recovery_signal=getattr(transition, "recovery_signal", None),
            control_termination=ControlTermination(
                ControlTerminationKind.CONTROL_STALLED,
                "episode_monitor",
            ),
        )

    async def resume_confirmation(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        *,
        approved: bool,
    ) -> RunState:
        pending = state.last_step
        if (
            state.status is not RunStatus.WAITING_CONFIRMATION
            or pending is None
            or pending.confirmation is None
            or not isinstance(pending.decision, SelectAction)
        ):
            raise ValueError("core run has no pending confirmation")
        if task.task_id != state.current_task_evaluation.task_id or task.revision != state.task_revision:
            raise ValueError("core confirmation task is stale")
        state.resume(RunStatus.WAITING_CONFIRMATION)
        self.trace_sink.run_resumed("confirmation", {"approved": approved})
        if not approved:
            declined = replace(
                pending,
                status_after=RunStatus.RUNNING,
                confirmation=None,
                feedback="confirmation_declined",
            )
            self._commit_step(state, declined, consume_step=False)
            return await self._run_until_pause(environment, task, state)
        action_space = self.action_space_builder.build(task, state.current_world)
        action_page = self.context_builder.page(action_space, state.current_world)
        result = await self._select(
            environment,
            task,
            state,
            pending.decision.context_id,
            action_space,
            action_page,
            pending.decision,
            confirmed_subject_id=pending.confirmation.subject_id,
        )
        result = self._attach_canonical_worlds(task, state, result)
        self._commit_step(state, result, consume_step=False)
        return await self._run_until_pause(environment, task, state)

    async def step(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> StepResult:
        if state.status is not RunStatus.RUNNING:
            raise ValueError("core step requires a running state")
        action_space = self.action_space_builder.build(task, state.current_world)
        region_index = WorldDeliveryIndex.from_observation(
            state.current_world,
            action_space.options,
            public_world_delta=(
                state.last_step.public_world_delta
                if state.last_step is not None and state.last_step.after_world is state.current_world
                else None
            ),
            previous_index=state.delivery_index or state.prior_delivery_index,
        )
        state.install_delivery_index(region_index)
        action_page = (
            state.action_page
            if state.action_page is not None and state.action_page.action_space_id == action_space.action_space_id
            else self.context_builder.page(
                action_space,
                state.current_world,
                region_index=region_index,
            )
        )
        try:
            context = self.context_builder.build(
                task,
                state.current_world,
                action_space,
                state.current_task_evaluation,
                state.workspace,
                action_page=action_page,
                context_generation=state.next_context_generation(),
                current_step_index=state.step_count,
                observation_capabilities=environment.observation_capabilities,
                goal_resolution=state.goal_resolution,
                runtime_controls=self.runtime_controls,
                region_index=region_index,
                canonical_world=state.canonical_world,
                control_feedback=_recovery_feedback(state.recovery_signal),
                action_discovery=state.action_discovery,
                last_step=state.last_step,
            )
        except PublicGroundingAmbiguousError:
            return StepResult(
                PolicyFailure(
                    ModelFailureKind.SCHEMA_ERROR,
                    PublicGroundingAmbiguousError.code,
                ),
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.FAILED,
                feedback=PublicGroundingAmbiguousError.code,
            )
        state.install_canonical_world(context.canonical_world)
        try:
            decision = await self.decision_ports.action_policy.decide(context)
        except asyncio.CancelledError as exc:
            failure = PolicyFailure(
                ModelFailureKind.TIMEOUT,
                "policy decision was cancelled by its enclosing deadline",
            )
            self.trace_sink.model_turn(
                context,
                failure,
                self.decision_ports.action_policy,
                exception=type(exc).__name__,
            )
            return StepResult(
                failure,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.CANCELLED,
                feedback="policy_cancelled:enclosing_deadline",
            )
        except Exception as exc:
            failure = PolicyFailure(
                ModelFailureKind.INTERNAL_ERROR,
                "policy decision failed",
            )
            self.trace_sink.model_turn(
                context,
                failure,
                self.decision_ports.action_policy,
                exception=type(exc).__name__,
            )
            return StepResult(
                failure,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.FAILED,
                feedback="policy_failure:internal_error",
                runtime_failure=RuntimeFailure(
                    FailureStage.POLICY,
                    FailureKind.CALL_FAILED,
                    "internal_error",
                    exception_class=type(exc).__name__,
                ),
            )
        self.trace_sink.model_turn(
            context,
            decision,
            self.decision_ports.action_policy,
        )
        if isinstance(decision, PolicyFailure):
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.FAILED,
                feedback=f"policy_failure:{decision.kind}",
            )
        if not isinstance(
            decision,
            (
                SelectAction,
                RequestObservation,
                RequestActionPage,
                AskUser,
                LocalToolResult,
                FinalResponse,
                Wait,
                Abort,
            ),
        ):
            raise TypeError("agent policy returned an unsupported decision")
        if decision.context_id != context.context_id:
            return _same_world_step(state, decision, RunStatus.FAILED, "decision_context_is_stale")
        match decision.kind:
            case DecisionKind.SELECT_ACTION:
                assert isinstance(decision, SelectAction)
                result = await self._select(
                    environment,
                    task,
                    state,
                    context.context_id,
                    action_space,
                    action_page,
                    decision,
                )
            case DecisionKind.REQUEST_OBSERVATION:
                assert isinstance(decision, RequestObservation)
                result = await self._observe(environment, task, state, decision)
            case DecisionKind.FIND_CONTROLS:
                assert isinstance(decision, RequestActionPage)
                result = self._action_page(task, state, action_space, decision)
            case (
                DecisionKind.READ_REGION
                | DecisionKind.SEARCH_PAGE_CONTENT
                | DecisionKind.TOOL_REJECTED
            ):
                assert isinstance(decision, LocalToolResult)
                result = StepResult(
                    decision,
                    state.current_world,
                    state.current_world,
                    state.current_task_evaluation,
                    RunStatus.RUNNING,
                    feedback="local_tool_result",
                )
            case DecisionKind.WAIT:
                assert isinstance(decision, Wait)
                result = await self._wait(environment, task, state, decision)
            case DecisionKind.SUBMIT_FINAL_RESPONSE:
                assert isinstance(decision, FinalResponse)
                result = await self._finalize(environment, task, state, decision)
            case DecisionKind.ASK_USER:
                assert isinstance(decision, AskUser)
                result = _same_world_step(state, decision, RunStatus.WAITING_USER, "user_input_required")
            case DecisionKind.ABORT:
                assert isinstance(decision, Abort)
                status = RunStatus.CANCELLED if decision.category == AbortCategory.USER_REQUEST else RunStatus.BLOCKED
                result = _same_world_step(
                    state,
                    decision,
                    status,
                    f"agent_aborted:{decision.category}",
                    control_termination=ControlTermination(
                        ControlTerminationKind.AGENT_ABORTED
                    ),
                )
            case unexpected:
                assert_never(unexpected)
        return replace(
            result,
            policy_observation=context.actor_world,
            policy_target_refs=context.grounding.target_refs,
            model_delivery=getattr(
                getattr(self.decision_ports.action_policy, "port", None),
                "last_model_delivery",
                None,
            ),
        )

    async def _finalize(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        decision: FinalResponse,
    ) -> StepResult:
        admission = admit_final_response(state.current_world, decision)
        if not admission.admitted:
            return _same_world_step(
                state,
                decision,
                RunStatus.FAILED,
                admission.rejection_code,
            )
        if not environment.supports_finalization:
            return _same_world_step(
                state,
                decision,
                RunStatus.BLOCKED,
                "finalization_unsupported",
            )
        try:
            normalized_content = environment.final_response_codec.normalize(decision.content)
        except (TypeError, ValueError):
            return _same_world_step(
                state,
                decision,
                RunStatus.FAILED,
                "final_response_invalid",
            )
        try:
            finalization = await environment.finalize(normalized_content)
        except asyncio.CancelledError:
            facts = FinalizationProtocolResult(DispatchStatus.NOT_SENT)
            self._trace_finalization(facts)
            return _same_world_step(
                state,
                decision,
                RunStatus.CANCELLED,
                "final_response_cancelled",
                finalization=facts,
            )
        except Exception:
            facts = FinalizationProtocolResult(DispatchStatus.NOT_SENT)
            self._trace_finalization(facts)
            return _same_world_step(
                state,
                decision,
                RunStatus.FAILED,
                "final_response_send_failed",
                finalization=facts,
            )
        delivered = finalization.result.dispatch_status is not DispatchStatus.NOT_SENT
        post = finalization.post_acquisition
        captured = bool(
            delivered
            and post is not None
            and post.status is AcquisitionStatus.ACQUIRED
            and post.observation is not None
        )
        evaluation = None
        after_projection = None
        native_evaluator_invoked = False
        if captured:
            assert post is not None and post.observation is not None
            native_evaluator_invoked = True
            final_delta = WorldTransitionProjector().project(
                state.current_world, post.observation
            )
            after_projection, _after_index = self._canonical_world_for(
                task,
                post.observation,
                previous_index=state.delivery_index,
                delta=final_delta,
            )
            try:
                attempt = await validated_task_evaluation_attempt(
                    self.task_evaluator,
                    task,
                    post.observation,
                    after_projection,
                )
            except asyncio.CancelledError:
                facts = FinalizationProtocolResult(
                    finalization.result.dispatch_status,
                    post.observation.observation_id,
                    native_evaluator_invoked=True,
                )
                self._trace_finalization(facts)
                return StepResult(
                    decision,
                    state.current_world,
                    post.observation,
                    None,
                    RunStatus.CANCELLED,
                    feedback="final_response_evaluation_cancelled",
                    finalization=facts,
                    public_world_delta=final_delta,
                    before_public_world=state.canonical_world,
                    after_public_world=after_projection,
                )
            if isinstance(attempt, Evaluated):
                evaluation = attempt.evaluation
            else:
                assert isinstance(attempt, Unavailable | InternalFailure)
                facts = FinalizationProtocolResult(
                    finalization.result.dispatch_status,
                    post.observation.observation_id,
                    native_evaluator_invoked=True,
                )
                self._trace_finalization(facts)
                self._trace_native_evaluator_failure(attempt)
                return StepResult(
                    decision,
                    state.current_world,
                    post.observation,
                    None,
                    RunStatus.FAILED,
                    feedback=attempt.code,
                    runtime_failure=RuntimeFailure(
                        FailureStage.EVALUATION,
                        FailureKind.CAPABILITY_UNAVAILABLE if isinstance(attempt, Unavailable) else FailureKind.INTERNAL,
                        attempt.code,
                        exception_class=attempt.diagnostic.exception_type,
                    ),
                    finalization=facts,
                    public_world_delta=final_delta,
                    before_public_world=state.canonical_world,
                    after_public_world=after_projection,
                )
        facts = FinalizationProtocolResult(
            finalization.result.dispatch_status,
            post.observation.observation_id if captured and post is not None and post.observation is not None else "",
            native_evaluator_invoked=native_evaluator_invoked,
            native_evaluation_status=evaluation.status if evaluation is not None else None,
        )
        self._trace_finalization(facts)
        if not delivered:
            return _same_world_step(
                state,
                decision,
                RunStatus.FAILED,
                "final_response_not_sent",
                finalization=facts,
            )
        if evaluation is None or post is None or post.observation is None:
            return _same_world_step(
                state,
                decision,
                RunStatus.FAILED,
                "final_response_post_capture_failed",
                finalization=facts,
            )
        return StepResult(
            decision,
            state.current_world,
            post.observation,
            evaluation,
            _status_for_final_evaluation(evaluation),
            feedback="final_response_evaluated",
            finalization=facts,
            public_world_delta=final_delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
        )

    def _trace_finalization(self, facts: FinalizationProtocolResult) -> None:
        protocol = getattr(self.trace_sink, "finalization_protocol", None)
        if callable(protocol):
            protocol(
                stop_send_count=facts.stop_send_count,
                post_stop_capture_count=facts.post_stop_capture_count,
                native_evaluator_count=facts.native_evaluator_count,
                dispatch_status=facts.dispatch_status.value,
            )

    def _trace_native_evaluator_failure(self, outcome: Unavailable | InternalFailure) -> None:
        emit = getattr(self.trace_sink, "native_evaluator_failed", None)
        if callable(emit):
            emit(
                outcome="unavailable" if isinstance(outcome, Unavailable) else "internal_failure",
                code=outcome.code,
                diagnostic=outcome.diagnostic,
            )

    def _action_page(self, task, state, action_space, decision: RequestActionPage) -> StepResult:
        query = decision.query
        try:
            page = self.context_builder.page(
                action_space,
                state.current_world,
                query=query,
            )
        except ValueError:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "action_page_invalid")
        discovery = self.context_builder.discovery_result(
            action_space,
            state.current_world,
            page,
            canonical_world=state.canonical_world,
        )
        retained_page = page
        feedback = "action_page_ready"
        if query:
            retained_page = (
                state.action_page
                if state.action_page is not None
                and state.action_page.action_space_id == action_space.action_space_id
                and not state.action_page.query
                else self.context_builder.page(action_space, state.current_world)
            )
        if page.total_count == 0:
            retained_page = (
                state.action_page
                if state.action_page is not None and state.action_page.action_space_id == action_space.action_space_id
                else self.context_builder.page(action_space, state.current_world)
            )
            feedback = "action_page_empty"
        return StepResult(
            decision,
            state.current_world,
            state.current_world,
            state.current_task_evaluation,
            RunStatus.RUNNING,
            feedback=feedback,
            action_page=retained_page,
            action_page_result=discovery,
        )

    async def _wait(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        decision: Wait,
    ) -> StepResult:
        if state.waited_ms + decision.max_wait_ms > MAX_TOTAL_WAIT_MS:
            return _same_world_step(
                state,
                decision,
                RunStatus.BLOCKED,
                "wait_budget_exhausted",
                control_termination=ControlTermination(
                    ControlTerminationKind.WAIT_BUDGET_EXHAUSTED
                ),
            )
        await self.wait_controller.wait(decision.max_wait_ms)
        acquisition = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.WAIT_REFRESH,
                "fresh observation after wait",
            )
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                feedback=f"wait_observation_unavailable:{acquisition.reason_code}",
                waited_ms=decision.max_wait_ms,
            )
        after = acquisition.observation
        delta = WorldTransitionProjector().project(state.current_world, after)
        after_projection, _after_index = self._canonical_world_for(
            task, after, previous_index=state.delivery_index, delta=delta
        )
        task_evaluation = await self._validated_task_evaluation(task, after, after_projection)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            feedback="wait_completed",
            waited_ms=decision.max_wait_ms,
            public_world_delta=delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
        )

    async def _observe(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        decision: RequestObservation,
    ) -> StepResult:
        purpose = ObservationPurpose(decision.purpose)
        modality = (
            ObservationModality.VISUAL
            if purpose in {ObservationPurpose.VISUAL_PROPERTY, ObservationPurpose.TEXT_IN_IMAGE}
            else None
        )
        need = ObservationNeed(
            f"agent:{state.context_generation}",
            purpose,
            (decision.subject_id,),
            modality,
            _criterion_assurance(
                task,
                state.current_task_evaluation,
                purpose,
                decision.subject_id,
            ),
            evidence_property=decision.evidence_property,
        )
        acquisition = await environment.capture(
            WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, decision.reason, (need,))
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return _same_world_step(
                state,
                decision,
                RunStatus.BLOCKED,
                f"observation_unavailable:{acquisition.reason_code}",
            )
        after = acquisition.observation
        delta = WorldTransitionProjector().project(state.current_world, after)
        after_projection, _after_index = self._canonical_world_for(
            task, after, previous_index=state.delivery_index, delta=delta
        )
        task_evaluation = await self._validated_task_evaluation(task, after, after_projection)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            feedback="observation_acquired",
            public_world_delta=delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
        )

    async def _select(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        context_id: str,
        action_space,
        action_page,
        decision: SelectAction,
        *,
        confirmed_subject_id: str = "",
    ) -> StepResult:
        admission = self.action_space_builder.try_admit_selection(
            action_space,
            decision.action_id,
            dict(decision.parameters),
            decision.destination_id,
            decision.expected_outcome,
        )
        if admission.admitted is None:
            assert admission.issue is not None
            return _same_world_step(state, decision, RunStatus.BLOCKED, f"admission_rejected:{admission.issue.code}")
        selection = admission.admitted
        if _repeats_recovery_signature(state.recovery_signal, selection, state.current_world):
            return _same_world_step(
                state,
                decision,
                RunStatus.RUNNING,
                "recovery_repeat_rejected",
            )
        # Model-visible selection authority is the current DeliveryManifest,
        # enforced by the grounded catalog before this private action_id is
        # created. The ActionPage is a retrieval projection, not a second
        # legality gate; canonical ActionSpace admission above remains strict.
        risk = self.risk_policy.assess(task, selection)
        if risk.decision is RiskDecisionKind.BLOCK:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "risk_blocked")
        if risk.decision is RiskDecisionKind.NEEDS_CONFIRMATION:
            if not confirmed_subject_id:
                return StepResult(
                    decision,
                    state.current_world,
                    state.current_world,
                    state.current_task_evaluation,
                    RunStatus.WAITING_CONFIRMATION,
                    confirmation=risk,
                    feedback="confirmation_required",
                )
            if confirmed_subject_id != risk.subject_id:
                return _same_world_step(
                    state,
                    decision,
                    RunStatus.RUNNING,
                    "confirmation_subject_changed",
                )
        try:
            request = self.binder.bind_for_execution(
                selection,
                state.current_world,
                context_id,
                task,
                tool_call_id=decision.tool_call_id,
            )
        except BindingError:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "binding_unavailable")
        state.currentness_probe_count += 1
        if not environment.is_current(request):
            return await self._refresh_stale_binding(environment, task, state, decision)
        try:
            execution = await environment.execute(request)
        except ExecutionCancelled as exc:
            cancelled_post = (
                exc.outcome.recovery_acquisitions[-1]
                if exc.outcome.recovery_acquisitions
                else exc.outcome.post_acquisition
            )
            after = (
                cancelled_post.observation
                if cancelled_post is not None
                and cancelled_post.status is AcquisitionStatus.ACQUIRED
                and cancelled_post.observation is not None
                else state.current_world
            )
            return StepResult(
                decision,
                state.current_world,
                after,
                None,
                RunStatus.CANCELLED,
                execution_receipts=ExecutionReceiptBatch.from_atomic(
                    exc.outcome,
                    after.observation_id,
                    completion=ExecutionCompletion.CANCELLED,
                ),
                feedback="action_execution_cancelled",
            )
        if execution.result.dispatch_status is DispatchStatus.NOT_SENT:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                execution_receipts=ExecutionReceiptBatch.from_atomic(
                    execution,
                    state.current_world.observation_id,
                ),
                feedback=f"action_not_sent:{execution.result.error or 'unknown'}",
            )
        execution = await self._recover_post_dispatch_observation(environment, execution)
        post = execution.recovery_acquisitions[-1] if execution.recovery_acquisitions else execution.post_acquisition
        if post is None or post.status is not AcquisitionStatus.ACQUIRED or post.observation is None:
            if execution.result.dispatch_status is DispatchStatus.SENT_UNKNOWN:
                return await self._unresolved_dispatch_step(
                    environment,
                    state,
                    decision,
                    execution,
                )
            failure_code = (
                AgentFailureCode.POST_ACTION_CAPABILITY_UNAVAILABLE
                if post is not None and post.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
                else AgentFailureCode.POST_ACTION_ACQUISITION_FAILED
            )
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                execution_receipts=ExecutionReceiptBatch.from_atomic(
                    execution,
                    state.current_world.observation_id,
                ),
                feedback=str(failure_code),
                failure_code=failure_code,
            )
        after = post.observation
        public_world_delta = WorldTransitionProjector().project(state.current_world, after)
        after_projection, _after_index = self._canonical_world_for(
            task,
            after,
            previous_index=state.delivery_index,
            delta=public_world_delta,
        )
        try:
            action_outcome = await validated_action_outcome(
                self.action_outcome_projector,
                task,
                state.current_world,
                request,
                execution.result,
                after,
                public_world_delta,
            )
        except asyncio.CancelledError:
            return _post_dispatch_evaluation_failure(
                state,
                decision,
                after,
                ExecutionReceiptBatch.from_atomic(
                    execution,
                    after.observation_id,
                    completion=ExecutionCompletion.CANCELLED,
                    cancellation_phase=ExecutionCancellationPhase.EVALUATION,
                ),
                cancelled=True,
                code="action_outcome_cancelled",
            )
        except Exception as exc:
            return _post_dispatch_evaluation_failure(
                state,
                decision,
                after,
                ExecutionReceiptBatch.from_atomic(execution, after.observation_id),
                cancelled=False,
                code="action_outcome_failed",
                exception_class=type(exc).__name__,
            )
        if execution.result.dispatch_status is DispatchStatus.SENT_UNKNOWN:
            if action_outcome.local_postcondition is LocalPostconditionStatus.UNKNOWN:
                batch = ExecutionReceiptBatch.from_atomic(execution, after.observation_id)
                task_evaluation = await self._task_evaluation_after_dispatch(
                    task, state, decision, after, batch, after_projection
                )
                if isinstance(task_evaluation, StepResult):
                    return task_evaluation
                return StepResult(
                    decision,
                    state.current_world,
                    after,
                    task_evaluation,
                    RunStatus.BLOCKED,
                    batch,
                    action_outcome,
                    feedback="action_dispatch_uncertain:effect_unresolved",
                    public_world_delta=public_world_delta,
                    before_public_world=state.canonical_world,
                    after_public_world=after_projection,
                )
        batch = ExecutionReceiptBatch.from_atomic(execution, after.observation_id)
        task_evaluation = await self._task_evaluation_after_dispatch(
            task, state, decision, after, batch, after_projection
        )
        if isinstance(task_evaluation, StepResult):
            return task_evaluation
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            batch,
            action_outcome,
            feedback=_action_feedback(
                action_outcome.observed_change,
                action_outcome.local_postcondition,
            ),
            public_world_delta=public_world_delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
        )

    async def _recover_post_dispatch_observation(
        self,
        environment: WorldEnvironment,
        execution: ExecutionOutcome,
    ) -> ExecutionOutcome:
        """Allow at most two fresh captures total for one dispatch attempt."""

        post = execution.post_acquisition
        if (
            execution.result.dispatch_status is not DispatchStatus.SENT_UNKNOWN
            or post is None
            or post.status is AcquisitionStatus.ACQUIRED
            or execution.recovery_acquisitions
        ):
            return execution
        observation_request = WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "recover uncertain dispatch observation",
            execution.request.verification_needs,
        )
        recover = getattr(environment, "recover_execution_observation", None)
        if callable(recover):
            recovered = await recover(execution.request, observation_request)
            result = replace(
                execution.result,
                diagnostics=(*execution.result.diagnostics, *recovered.diagnostics),
            )
            return replace(
                execution,
                result=result,
                recovery_acquisitions=(recovered.acquisition,),
            )
        recovery = await environment.capture(observation_request)
        return replace(execution, recovery_acquisitions=(recovery,))

    async def _unresolved_dispatch_step(
        self,
        environment: WorldEnvironment,
        state: RunState,
        decision: SelectAction,
        execution: ExecutionOutcome,
    ) -> StepResult:
        probe = getattr(environment, "session_health", None)
        try:
            health = await probe(execution.request) if callable(probe) else SessionHealth(SessionHealthStatus.UNKNOWN)
        except Exception:
            health = SessionHealth(SessionHealthStatus.UNKNOWN)
        if execution.result.diagnostics:
            last = execution.result.diagnostics[-1]
            execution = replace(
                execution,
                result=replace(
                    execution.result,
                    diagnostics=(
                        *execution.result.diagnostics[:-1],
                        replace(
                            last,
                            page_closed=health.page_closed,
                            browser_connected=health.browser_connected,
                        ),
                    ),
                ),
            )
        if health.status is SessionHealthStatus.ALIVE:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                execution_receipts=ExecutionReceiptBatch.from_atomic(
                    execution,
                    state.current_world.observation_id,
                    completion=ExecutionCompletion.UNKNOWN,
                ),
                feedback="post_action_acquisition_failed:environment_recovery",
            )
        exception_class = next(
            (item.exception_type for item in execution.all_diagnostics if item.exception_type),
            "EnvironmentUnavailable",
        )
        return StepResult(
            decision,
            state.current_world,
            state.current_world,
            state.current_task_evaluation,
            RunStatus.FAILED,
            execution_receipts=ExecutionReceiptBatch.from_atomic(
                execution,
                state.current_world.observation_id,
                completion=ExecutionCompletion.UNKNOWN,
            ),
            feedback="environment_unresponsive:unresolved_action_effect",
            runtime_failure=RuntimeFailure(
                FailureStage.SESSION,
                FailureKind.CALL_FAILED,
                "environment_unresponsive",
                exception_class=exception_class,
            ),
        )

    async def _refresh_stale_binding(self, environment, task, state, decision) -> StepResult:
        acquisition = await environment.capture(
            WorldObservationRequest(ObservationRequestKind.BINDING_REFRESH, "selected binding is stale")
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "binding_refresh_unavailable")
        after = acquisition.observation
        delta = WorldTransitionProjector().project(state.current_world, after)
        after_projection, _after_index = self._canonical_world_for(
            task, after, previous_index=state.delivery_index, delta=delta
        )
        task_evaluation = await self._validated_task_evaluation(task, after, after_projection)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            feedback="binding_refreshed",
            public_world_delta=delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
        )

    def _status_for_goal_resolution(self, task, evaluation, resolution) -> RunStatus:
        task_status = self._status_for_task(task, evaluation)
        if task_status is not RunStatus.RUNNING:
            return task_status
        return RunStatus.WAITING_USER if isinstance(resolution, NeedsInput) else task_status

    async def _task_evaluation_after_dispatch(
        self,
        task: TaskGoal,
        state: RunState,
        decision: SelectAction,
        after: WorldObservation,
        batch: ExecutionReceiptBatch,
        after_projection: CanonicalPublicWorldProjection,
    ) -> TaskEvaluation | StepResult:
        """Close evaluator failure without losing already-crossed dispatch truth."""

        try:
            return await self._validated_task_evaluation(task, after, after_projection)
        except asyncio.CancelledError:
            failure = _post_dispatch_evaluation_failure(
                state,
                decision,
                after,
                replace(
                    batch,
                    completion=ExecutionCompletion.CANCELLED,
                    cancellation_phase=ExecutionCancellationPhase.EVALUATION,
                ),
                cancelled=True,
                code="task_evaluation_cancelled",
            )
            return replace(
                failure,
                before_public_world=state.canonical_world,
                after_public_world=after_projection,
            )
        except (TaskEvaluationUnavailableError, TaskEvaluationInternalError) as exc:
            outcome = exc.outcome
            failure = _post_dispatch_evaluation_failure(
                state,
                decision,
                after,
                batch,
                cancelled=False,
                code=outcome.code,
                failure_kind=(
                    FailureKind.CAPABILITY_UNAVAILABLE
                    if isinstance(outcome, Unavailable)
                    else FailureKind.INTERNAL
                ),
                exception_class=outcome.diagnostic.exception_type,
            )
            return replace(
                failure,
                before_public_world=state.canonical_world,
                after_public_world=after_projection,
            )

    async def _validated_task_evaluation(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        canonical_world: CanonicalPublicWorldProjection,
    ) -> TaskEvaluation:
        attempt = await validated_task_evaluation_attempt(
            self.task_evaluator, task, observation, canonical_world
        )
        if isinstance(attempt, Evaluated):
            return attempt.evaluation
        self._trace_native_evaluator_failure(attempt)
        if isinstance(attempt, Unavailable):
            raise TaskEvaluationUnavailableError(attempt)
        raise TaskEvaluationInternalError(attempt)

    def _canonical_world_for(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        *,
        previous_index: WorldDeliveryIndex | None = None,
        delta: object | None = None,
    ) -> tuple[CanonicalPublicWorldProjection, WorldDeliveryIndex]:
        action_space = self.action_space_builder.build(task, observation)
        index = WorldDeliveryIndex.from_observation(
            observation,
            action_space.options,
            public_world_delta=delta,
            previous_index=previous_index,
        )
        return CanonicalPublicWorldProjection.build(observation, index, action_space), index

    def _status_for_task(self, task: TaskGoal, evaluation: TaskEvaluation) -> RunStatus:
        return _status_for_evaluation(evaluation)


def _post_dispatch_evaluation_failure(
    state: RunState,
    decision: SelectAction,
    after: WorldObservation,
    batch: ExecutionReceiptBatch,
    *,
    cancelled: bool,
    code: str,
    failure_kind: FailureKind = FailureKind.INTERNAL,
    exception_class: str = "",
) -> StepResult:
    """Materialize the reached dispatch prefix before evaluation terminates."""

    return StepResult(
        decision,
        state.current_world,
        after,
        None,
        RunStatus.CANCELLED if cancelled else RunStatus.FAILED,
        execution_receipts=batch,
        feedback=code,
        runtime_failure=(
            None
            if cancelled
            else RuntimeFailure(
                FailureStage.EVALUATION,
                failure_kind,
                code,
                exception_class=exception_class,
            )
        ),
    )


def _same_world_step(
    state: RunState,
    decision: AgentDecision,
    status: RunStatus,
    feedback: str,
    *,
    finalization: FinalizationProtocolResult | None = None,
    control_termination: ControlTermination | None = None,
) -> StepResult:
    return StepResult(
        decision,
        state.current_world,
        state.current_world,
        state.current_task_evaluation,
        status,
        feedback=feedback,
        finalization=finalization,
        control_termination=control_termination,
    )


def _recovery_feedback(signal) -> dict[str, object]:
    if signal is None:
        return {}
    return {
        "kind": signal.kind.value,
        "stable_signature": signal.stable_signature,
        "observed_evidence": signal.observed_evidence,
        "attempted_modes": signal.attempted_modes,
        "prohibited_attempt_signature": (
            to_json_compatible(signal.prohibited_attempt_signature)
            if signal.prohibited_attempt_signature is not None
            else None
        ),
        "human_instruction": signal.human_instruction,
        "recovery_attempt": signal.recovery_attempt,
        "instruction": (
            "Do not repeat the prohibited typed attempt. Use the fresh World and current tools "
            "to choose a materially different route, or yield if no supported route exists."
        ),
    }


def _repeats_recovery_signature(signal, selection, world) -> bool:
    if signal is None or signal.prohibited_attempt_signature is None:
        return False
    current = public_attempt_signature(
        selection.semantic_action,
        selection.target_id,
        selection.destination_id,
        selection.parameters,
        world,
    )
    return current == signal.prohibited_attempt_signature


def _criterion_assurance(
    task: TaskGoal,
    evaluation: TaskEvaluation,
    purpose: ObservationPurpose,
    subject_id: str,
) -> ObservationAssurance:
    if purpose is not ObservationPurpose.CRITERION_VERIFICATION:
        return ObservationAssurance.WEAK
    statuses = {item.criterion_id: item.status for item in evaluation.criteria}
    required = ObservationAssurance.WEAK
    for criterion in normalize_task_criteria(task):
        if statuses.get(criterion.criterion_id) is CriterionEvaluationStatus.SATISFIED:
            continue
        applies_to_subject = criterion.subject_id == subject_id or subject_id in criterion.evidence_scope_target_ids
        if not applies_to_subject or not criterion.required_assurance:
            continue
        candidate = ObservationAssurance(criterion.required_assurance)
        if _ASSURANCE_RANK[candidate] > _ASSURANCE_RANK[required]:
            required = candidate
    return required


def _status_for_evaluation(evaluation: TaskEvaluation) -> RunStatus:
    if evaluation.status is TaskEvaluationStatus.COMPLETE:
        return RunStatus.DONE
    if evaluation.status is TaskEvaluationStatus.BLOCKED:
        return RunStatus.BLOCKED
    return RunStatus.RUNNING


def _status_for_final_evaluation(evaluation: TaskEvaluation) -> RunStatus:
    """STOP is terminal even when the native evaluator reports non-success."""

    status = _status_for_evaluation(evaluation)
    return RunStatus.FAILED if status is RunStatus.RUNNING else status
