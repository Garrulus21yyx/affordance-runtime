"""Readable observe-decide-act-observe-evaluate loop for every product run."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import assert_never

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder, BindingError
from affordance_runtime.agent.attempt_signature import public_attempt_signature
from affordance_runtime.agent.budgets import EpisodeBudget, StandaloneRunBudget
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.contracts import AgentMilestoneContractView
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.decisions import (
    Abort,
    AbortCategory,
    AgentDecision,
    AskUser,
    DecisionKind,
    FinalResponse,
    LocalToolResult,
    ProtocolFeedback,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    SetFormFields,
    Wait,
    YieldMilestone,
)
from affordance_runtime.agent.evaluation_control import (
    validated_action_outcome,
    validated_task_evaluation,
)
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
from affordance_runtime.agent.run_state import EpisodeYieldReason, RunState, RunStatus, StepResult
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.waiting import MAX_TOTAL_WAIT_MS, SystemWaitController, WaitController
from affordance_runtime.evaluation.contracts import (
    CriterionEvaluationStatus,
    LocalPostconditionStatus,
    ObservedChange,
    TaskEvaluation,
    TaskEvaluationStatus,
)
from affordance_runtime.evaluation.criterion_normalization import normalize_task_criteria
from affordance_runtime.execution.contracts import (
    DispatchStatus,
    ExecutionCancellationPhase,
    ExecutionCancelled,
    ExecutionCompletion,
    ExecutionOutcome,
    ExecutionReceiptBatch,
    FormFieldsExecutionCancelled,
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
from affordance_runtime.world.public_semantic_digest import public_world_semantic_digest
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
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    trace_sink: RunTraceSink = field(default_factory=NullRunTraceSink)
    goal_compiler: GoalCompiler = field(default_factory=UnavailableGoalCompiler)
    goal_plan_boundary: GoalPlanBoundary = field(default_factory=GoalPlanBoundary)
    runtime_controls: tuple[str, ...] = ()
    episode_monitor: object | None = None

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
        state = await self.initialize_from_world(
            task,
            acquisition.observation,
            resolution,
            budget=StandaloneRunBudget(task.loop_budget.max_turns),
            yield_on_budget_exhaustion=False,
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

    async def initialize_from_world(
        self,
        task: TaskGoal,
        initial: WorldObservation,
        goal_resolution: GoalPlanResolution,
        *,
        budget: EpisodeBudget | StandaloneRunBudget,
        yield_on_budget_exhaustion: bool,
        working_facts=(),
        active_milestone: AgentMilestoneContractView | None = None,
    ) -> RunState:
        """Create a fresh executor episode from an already acquired world."""

        if not isinstance(budget, EpisodeBudget | StandaloneRunBudget):
            raise TypeError("CoreLoop requires one validated typed budget")
        if goal_resolution.task_revision != task.revision:
            raise ValueError("episode goal resolution belongs to a previous task revision")
        evaluation = await validated_task_evaluation(self.task_evaluator, task, initial)
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
            yield_on_budget_exhaustion=yield_on_budget_exhaustion,
            working_facts=working_facts,
            active_milestone_contract=active_milestone,
        )
        start_episode = getattr(self.episode_monitor, "start_episode", None)
        if callable(start_episode):
            start_episode(initial, evaluation, working_facts)
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
            result = self._apply_episode_monitor(result, state)
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
        evaluation = await validated_task_evaluation(
            self.task_evaluator,
            task,
            state.current_world,
        )
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
    ) -> StepResult:
        projected = None
        if result.status_after in {RunStatus.RUNNING, RunStatus.YIELDED} and not isinstance(
            result.decision,
            PolicyFailure,
        ):
            projected = project_step_result(result)
            if not state.can_remember_step(
                projected,
                max_bytes=self.context_builder.budget.max_history_serialized_bytes,
            ):
                result = replace(
                    result,
                    status_after=RunStatus.YIELDED,
                    feedback="context_capacity",
                    failure_code=None,
                    runtime_failure=None,
                    yield_reason=EpisodeYieldReason.CONTEXT_CAPACITY,
                )
                projected = None
        state.apply(result, consume_step=consume_step)
        if trace_step:
            self.trace_sink.step_completed(state.step_count, result)
        if projected is not None:
            state.remember_step(
                projected,
                max_bytes=self.context_builder.budget.max_history_serialized_bytes,
            )
        return result

    def _apply_episode_monitor(self, result: StepResult, state: RunState) -> StepResult:
        monitor = self.episode_monitor
        if monitor is None or result.status_after in {
            RunStatus.DONE,
            RunStatus.YIELDED,
            RunStatus.WAITING_USER,
            RunStatus.WAITING_CONFIRMATION,
            RunStatus.CANCELLED,
        }:
            return result
        evaluate = getattr(monitor, "evaluate", None)
        if not callable(evaluate):
            return result
        transition = evaluate(result, state.recent_steps, _world_fingerprint(result.after_world))
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
        if str(recommendation) != "yield":
            return result
        reason = getattr(transition, "reason", "stalled")
        try:
            from affordance_runtime.agent.run_state import EpisodeYieldReason

            yield_reason = EpisodeYieldReason(reason)
        except ValueError:
            yield_reason = None
        if yield_reason is None:
            return result
        return replace(
            result,
            status_after=RunStatus.YIELDED,
            feedback=f"episode_monitor:{yield_reason.value}",
            failure_code=None,
            recovery_signal=getattr(transition, "recovery_signal", None),
            yield_reason=yield_reason,
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
        )
        lens = (
            state.delivery_lens
            if state.delivery_lens is not None
            and state.delivery_lens.world_observation_id == state.current_world.observation_id
            and (
                not state.delivery_lens.selected_region_key
                or region_index.get(state.delivery_lens.selected_region_key) is not None
            )
            else None
        )
        action_page = (
            state.action_page
            if state.action_page is not None and state.action_page.action_space_id == action_space.action_space_id
            else self.context_builder.page(
                action_space,
                state.current_world,
                region_index=region_index,
            )
        )
        context = self.context_builder.build(
            task,
            state.current_world,
            action_space,
            state.current_task_evaluation,
            state.recent_steps,
            max(state.step_count, len(state.recent_steps)),
            action_page=action_page,
            context_generation=state.next_context_generation(),
            observation_capabilities=environment.observation_capabilities,
            goal_resolution=state.goal_resolution,
            working_facts=state.working_facts,
            runtime_controls=self.runtime_controls,
            delivery_lens=lens,
            region_index=region_index,
            control_feedback=_recovery_feedback(state.recovery_signal),
            active_milestone=state.active_milestone_contract,
        )
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
                SetFormFields,
                RequestObservation,
                RequestActionPage,
                AskUser,
                LocalToolResult,
                ProtocolFeedback,
                YieldMilestone,
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
            case DecisionKind.SET_FORM_FIELDS:
                assert isinstance(decision, SetFormFields)
                result = await self._set_form_fields(
                    environment,
                    task,
                    state,
                    context.context_id,
                    action_space,
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
                | DecisionKind.PIN_FACT
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
            case DecisionKind.PROTOCOL_FEEDBACK:
                assert isinstance(decision, ProtocolFeedback)
                result = StepResult(
                    decision,
                    state.current_world,
                    state.current_world,
                    state.current_task_evaluation,
                    RunStatus.RUNNING,
                    feedback=f"protocol_feedback:{decision.feedback_kind.value}",
                )
            case DecisionKind.YIELD_MILESTONE:
                assert isinstance(decision, YieldMilestone)
                result = _same_world_step(
                    state,
                    decision,
                    RunStatus.YIELDED,
                    f"yield_milestone:{decision.yield_kind}",
                    yield_reason=EpisodeYieldReason(decision.yield_kind),
                )
                result = replace(result, runtime_failure=None)
            case DecisionKind.WAIT:
                assert isinstance(decision, Wait)
                result = await self._wait(environment, task, state, decision)
            case DecisionKind.SUBMIT_FINAL_RESPONSE:
                assert isinstance(decision, FinalResponse)
                ready = _final_response_available(state, decision)
                result = _same_world_step(
                    state,
                    decision,
                    RunStatus.YIELDED if ready else RunStatus.FAILED,
                    "final_response" if ready else "final_response_not_available",
                    yield_reason=EpisodeYieldReason.FINAL_RESPONSE if ready else None,
                )
            case DecisionKind.ASK_USER:
                assert isinstance(decision, AskUser)
                result = _same_world_step(state, decision, RunStatus.WAITING_USER, "user_input_required")
            case DecisionKind.ABORT:
                assert isinstance(decision, Abort)
                status = RunStatus.CANCELLED if decision.category == AbortCategory.USER_REQUEST else RunStatus.BLOCKED
                result = _same_world_step(state, decision, status, f"agent_aborted:{decision.category}")
            case unexpected:
                assert_never(unexpected)
        return replace(
            result,
            policy_observation=context.actor_world,
            policy_target_refs=context.grounding.target_refs,
        )

    def _action_page(self, task, state, action_space, decision: RequestActionPage) -> StepResult:
        try:
            page = self.context_builder.page(
                action_space,
                state.current_world,
                query=decision.query,
                target_id=decision.target_id,
                relevance_role=decision.relevance_role,
                cursor=decision.cursor,
            )
        except ValueError:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "action_page_invalid")
        result_payload = _action_page_result_payload(page, decision)
        retained_page = page
        feedback = "action_page_ready"
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
            action_page_result=result_payload,
        )

    async def _wait(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        decision: Wait,
    ) -> StepResult:
        if state.waited_ms + decision.max_wait_ms > MAX_TOTAL_WAIT_MS:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "wait_budget_exhausted")
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
        task_evaluation = await validated_task_evaluation(self.task_evaluator, task, after)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            feedback="wait_completed",
            waited_ms=decision.max_wait_ms,
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
        task_evaluation = await validated_task_evaluation(self.task_evaluator, task, after)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            feedback="observation_acquired",
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
                _interrupted_task_evaluation(state, after, "action_execution_cancelled"),
                RunStatus.CANCELLED,
                execution_receipts=ExecutionReceiptBatch.from_atomic(
                    exc.outcome,
                    after.observation_id,
                    completion=ExecutionCompletion.CANCELLED,
                ),
                feedback="action_execution_cancelled",
            )
        except Exception:
            return _same_world_step(state, decision, RunStatus.FAILED, "execution_failed")
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
        try:
            action_outcome = await validated_action_outcome(
                self.action_outcome_projector,
                task,
                state.current_world,
                request,
                execution.result,
                after,
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
                    task, state, decision, after, batch
                )
                if isinstance(task_evaluation, StepResult):
                    return task_evaluation
                return StepResult(
                    decision,
                    state.current_world,
                    after,
                    task_evaluation,
                    RunStatus.YIELDED,
                    batch,
                    action_outcome,
                    feedback="action_dispatch_uncertain:effect_unresolved",
                    yield_reason=EpisodeYieldReason.UNCERTAIN_EFFECT,
                )
        batch = ExecutionReceiptBatch.from_atomic(execution, after.observation_id)
        task_evaluation = await self._task_evaluation_after_dispatch(
            task, state, decision, after, batch
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
        )

    async def _set_form_fields(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        context_id: str,
        action_space,
        decision: SetFormFields,
    ) -> StepResult:
        """Admit and bind the whole safe compound command before any dispatch."""

        requests = []
        for field_update in decision.fields:
            admission = self.action_space_builder.try_admit_selection(
                action_space,
                field_update.action_id,
                dict(field_update.parameters),
                "",
                "",
            )
            if admission.admitted is None:
                assert admission.issue is not None
                return _same_world_step(
                    state,
                    decision,
                    RunStatus.BLOCKED,
                    f"form_fields_admission_rejected:{admission.issue.code}",
                )
            selection = admission.admitted
            if selection.semantic_action != field_update.operation:
                return _same_world_step(state, decision, RunStatus.BLOCKED, "form_fields_operation_mismatch")
            risk = self.risk_policy.assess(task, selection)
            if risk.decision is not RiskDecisionKind.ALLOW:
                return _same_world_step(state, decision, RunStatus.BLOCKED, "form_fields_not_low_risk")
            try:
                request = self.binder.bind_for_execution(
                    selection,
                    state.current_world,
                    context_id,
                    task,
                    tool_call_id=decision.tool_call_id,
                )
            except BindingError:
                return _same_world_step(state, decision, RunStatus.BLOCKED, "form_fields_binding_unavailable")
            requests.append(request)
        for request in requests:
            state.currentness_probe_count += 1
            if not environment.is_current(request):
                return await self._refresh_stale_binding(environment, task, state, decision)
        try:
            command = self.binder.seal_form_fields(
                decision.form_key,
                tuple(requests),
                tool_call_id=decision.tool_call_id,
            )
        except BindingError:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "form_fields_binding_unavailable")
        try:
            execution = await environment.execute_form_fields(command)
        except FormFieldsExecutionCancelled as exc:
            cancelled_post = exc.outcome.post_acquisition
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
                _interrupted_task_evaluation(state, after, "form_fields_execution_cancelled"),
                RunStatus.CANCELLED,
                execution_receipts=ExecutionReceiptBatch.from_form_fields(
                    exc.outcome,
                    after.observation_id,
                    completion=ExecutionCompletion.CANCELLED,
                ),
                feedback="form_fields_execution_cancelled",
            )
        except Exception:
            return _same_world_step(state, decision, RunStatus.FAILED, "form_fields_execution_failed")
        post = execution.post_acquisition
        if post is None or post.status is not AcquisitionStatus.ACQUIRED or post.observation is None:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                feedback="form_fields_not_sent" if post is None else "form_fields_post_capture_failed",
                execution_receipts=ExecutionReceiptBatch.from_form_fields(
                    execution,
                    state.current_world.observation_id,
                ),
            )
        after = post.observation
        batch = ExecutionReceiptBatch.from_form_fields(execution, after.observation_id)
        task_evaluation = await self._task_evaluation_after_dispatch(
            task, state, decision, after, batch
        )
        if isinstance(task_evaluation, StepResult):
            return task_evaluation
        if any(result.dispatch_status is DispatchStatus.SENT_UNKNOWN for result in execution.results):
            return StepResult(
                decision,
                state.current_world,
                after,
                task_evaluation,
                RunStatus.YIELDED,
                feedback="form_fields_dispatch_uncertain",
                yield_reason=EpisodeYieldReason.UNCERTAIN_EFFECT,
                execution_receipts=replace(batch, completion=ExecutionCompletion.UNKNOWN),
            )
        feedback = (
            "form_fields_completed"
            if execution.failed_field_index is None
            else f"form_fields_partial_failure:{execution.failed_field_index}"
        )
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            feedback=feedback,
            execution_receipts=batch,
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
                RunStatus.YIELDED,
                execution_receipts=ExecutionReceiptBatch.from_atomic(
                    execution,
                    state.current_world.observation_id,
                    completion=ExecutionCompletion.UNKNOWN,
                ),
                feedback="post_action_acquisition_failed:environment_recovery",
                yield_reason=EpisodeYieldReason.ENVIRONMENT_RECOVERY,
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
        task_evaluation = await validated_task_evaluation(self.task_evaluator, task, after)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            feedback="binding_refreshed",
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
        decision: SelectAction | SetFormFields,
        after: WorldObservation,
        batch: ExecutionReceiptBatch,
    ) -> TaskEvaluation | StepResult:
        """Close evaluator failure without losing already-crossed dispatch truth."""

        try:
            return await validated_task_evaluation(self.task_evaluator, task, after)
        except asyncio.CancelledError:
            return _post_dispatch_evaluation_failure(
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
        except Exception as exc:
            return _post_dispatch_evaluation_failure(
                state,
                decision,
                after,
                batch,
                cancelled=False,
                code="task_evaluation_failed",
                exception_class=type(exc).__name__,
            )

    def _status_for_task(self, task: TaskGoal, evaluation: TaskEvaluation) -> RunStatus:
        return _status_for_evaluation(evaluation)


def _post_dispatch_evaluation_failure(
    state: RunState,
    decision: SelectAction | SetFormFields,
    after: WorldObservation,
    batch: ExecutionReceiptBatch,
    *,
    cancelled: bool,
    code: str,
    exception_class: str = "",
) -> StepResult:
    """Materialize the reached dispatch prefix before evaluation terminates."""

    evaluation = _interrupted_task_evaluation(state, after, code)
    return StepResult(
        decision,
        state.current_world,
        after,
        evaluation,
        RunStatus.CANCELLED if cancelled else RunStatus.FAILED,
        execution_receipts=batch,
        feedback=code,
        runtime_failure=(
            None
            if cancelled
            else RuntimeFailure(
                FailureStage.EVALUATION,
                FailureKind.CALL_FAILED,
                code,
                exception_class=exception_class,
            )
        ),
    )


def _interrupted_task_evaluation(
    state: RunState,
    after: WorldObservation,
    code: str,
) -> TaskEvaluation:
    return TaskEvaluation(
        state.current_task_evaluation.task_id,
        after.observation_id,
        TaskEvaluationStatus.UNKNOWN,
        code,
    )


def _same_world_step(
    state: RunState,
    decision: AgentDecision,
    status: RunStatus,
    feedback: str,
    *,
    yield_reason: EpisodeYieldReason | None = None,
) -> StepResult:
    return StepResult(
        decision,
        state.current_world,
        state.current_world,
        state.current_task_evaluation,
        status,
        feedback=feedback,
        yield_reason=yield_reason,
    )


def _action_page_result_payload(page, decision: RequestActionPage) -> dict[str, object]:
    applied = {
        "query": decision.query,
        "exact_target": decision.exact_target_ref,
        "cursor": decision.cursor,
    }
    if decision.relevance_role:
        applied["relevance_role"] = decision.relevance_role
    relaxations = []
    if decision.exact_target_ref:
        relaxations.append("remove_exact_target")
    if decision.relevance_role:
        relaxations.append("remove_relevance_role")
    if decision.query:
        relaxations.append("shorten_query")
    return {
        "kind": "Empty" if page.total_count == 0 else "Page",
        "matches": () if page.total_count == 0 else page.visible_action_ids,
        "searched_domain": "executable_controls",
        "base_action_page_preserved": page.total_count == 0,
        "does_not_search": "readable_content",
        "suggested_next": "search_page_content" if page.total_count == 0 else "",
        "applied_filters": applied,
        "coverage": "complete_current_action_space",
        "total_count": page.total_count,
        "visible_count": len(page.visible_action_ids),
        "why_empty": (
            "filters_matched_no_actions"
            if page.total_count == 0 and any(value for value in applied.values())
            else "action_space_empty"
            if page.total_count == 0
            else ""
        ),
        "safe_relaxations": tuple(relaxations) if page.total_count == 0 else (),
        "authority_changed": False if page.total_count == 0 else True,
    }


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


def _final_response_available(
    state: RunState,
    response: FinalResponse,
) -> bool:
    if state.current_task_evaluation.status is TaskEvaluationStatus.COMPLETE and response.evidence_refs:
        return True
    milestone = state.active_milestone_contract
    if milestone is None or not milestone.final:
        return False
    retained = {item.key for item in state.working_facts}
    return bool(response.evidence_refs) and all(key in retained for key, _ in milestone.required_evidence)


def _world_fingerprint(world: WorldObservation) -> str:
    return public_world_semantic_digest(world)


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
