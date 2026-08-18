"""Readable observe-decide-act-observe-evaluate loop for every product run."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder, BindingError
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.decisions import (
    Abort,
    AbortCategory,
    AgentDecision,
    AskUser,
    FinalResponse,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
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
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
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
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.goals.compiler import (
    GoalCompiler,
    GoalCompileTrigger,
    GoalPlanBoundary,
    UnavailableGoalCompiler,
)
from affordance_runtime.goals.plan import GoalPlanResolution, NeedsInput, Ready
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
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    trace_sink: RunTraceSink = field(default_factory=NullRunTraceSink)
    goal_compiler: GoalCompiler = field(default_factory=UnavailableGoalCompiler)
    goal_plan_boundary: GoalPlanBoundary = field(default_factory=GoalPlanBoundary)

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
            max_turns=task.loop_budget.max_turns,
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
        max_turns: int,
        yield_on_budget_exhaustion: bool,
    ) -> RunState:
        """Create a fresh executor episode from an already acquired world."""

        if goal_resolution.task_revision != task.revision:
            raise ValueError("episode goal resolution belongs to a previous task revision")
        evaluation = await validated_task_evaluation(self.task_evaluator, task, initial)
        state = RunState(
            initial,
            evaluation,
            max_turns,
            status=self._status_for_goal_resolution(task, evaluation, goal_resolution),
            task_revision=task.revision,
            goal_resolution=goal_resolution,
            goal_plan_version_counter=(
                goal_resolution.accepted_plan.plan_version if isinstance(goal_resolution, Ready) else 0
            ),
            yield_on_budget_exhaustion=yield_on_budget_exhaustion,
        )
        if isinstance(goal_resolution, NeedsInput) and state.status is RunStatus.WAITING_USER:
            state.last_step = StepResult(
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
            self.trace_sink.step_completed(state.step_count + 1, result)
            state.apply(result)
            if state.status in {RunStatus.RUNNING, RunStatus.YIELDED} and not isinstance(
                result.decision,
                PolicyFailure,
            ):
                state.remember_step(
                    project_step_result(result),
                    max_bytes=self.context_builder.budget.max_history_serialized_bytes,
                )
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
        if (
            state.status is not RunStatus.WAITING_USER
            or pending is None
            or not isinstance(pending.decision, AskUser)
        ):
            raise ValueError("core run has no pending user request")
        if (
            task.task_id != state.current_task_evaluation.task_id
            or task.revision != state.task_revision + 1
        ):
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
        state.current_task_evaluation = evaluation
        state.task_revision = task.revision
        state.goal_resolution = resolution
        if isinstance(resolution, Ready):
            state.goal_plan_version_counter = resolution.accepted_plan.plan_version
        state.status = resumed.status_after
        state.last_step = resumed
        state.action_page = None
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
        if state.status is RunStatus.RUNNING:
            state.remember_step(
                project_step_result(resumed),
                max_bytes=self.context_builder.budget.max_history_serialized_bytes,
            )
        return await self._run_until_pause(environment, task, state)

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
        if (
            task.task_id != state.current_task_evaluation.task_id
            or task.revision != state.task_revision
        ):
            raise ValueError("core confirmation task is stale")
        state.status = RunStatus.RUNNING
        self.trace_sink.run_resumed("confirmation", {"approved": approved})
        if not approved:
            declined = replace(
                pending,
                status_after=RunStatus.RUNNING,
                confirmation=None,
                feedback="confirmation_declined",
            )
            state.last_step = declined
            self.trace_sink.step_completed(state.step_count, declined)
            state.remember_step(
                project_step_result(declined),
                max_bytes=self.context_builder.budget.max_history_serialized_bytes,
            )
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
        self.trace_sink.step_completed(state.step_count, result)
        state.apply(result, consume_step=False)
        if state.status is RunStatus.RUNNING:
            state.remember_step(
                project_step_result(result),
                max_bytes=self.context_builder.budget.max_history_serialized_bytes,
            )
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
        action_page = (
            state.action_page
            if state.action_page is not None
            and state.action_page.action_space_id == action_space.action_space_id
            else self.context_builder.page(action_space, state.current_world)
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
        )
        try:
            decision = await self.decision_ports.action_policy.decide(context)
        except asyncio.CancelledError as exc:
            # Preserve provider attempts already captured by the adapter before
            # propagating an orchestrator/watchdog cancellation unchanged.
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
            raise
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
        if isinstance(decision, SelectAction):
            result = await self._select(
                environment,
                task,
                state,
                context.context_id,
                action_space,
                action_page,
                decision,
            )
        elif isinstance(decision, RequestObservation):
            result = await self._observe(environment, task, state, decision)
        elif isinstance(decision, RequestActionPage):
            result = self._action_page(task, state, action_space, decision)
        elif isinstance(decision, LocalToolResult):
            result = StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.RUNNING,
                feedback="local_tool_result",
            )
        elif isinstance(decision, Wait):
            result = await self._wait(environment, task, state, decision)
        elif isinstance(decision, FinalResponse):
            ready = bool(task.requested_outputs) and (
                state.current_task_evaluation.status is TaskEvaluationStatus.COMPLETE
            )
            result = _same_world_step(
                state,
                decision,
                RunStatus.DONE if ready else RunStatus.RUNNING,
                "final_response" if ready else "final_response_not_ready",
            )
        elif isinstance(decision, AskUser):
            result = _same_world_step(state, decision, RunStatus.WAITING_USER, "user_input_required")
        elif isinstance(decision, Abort):
            status = RunStatus.CANCELLED if decision.category == AbortCategory.USER_REQUEST else RunStatus.BLOCKED
            result = _same_world_step(state, decision, status, f"agent_aborted:{decision.category}")
        else:
            raise TypeError("core decision dispatch is incomplete")
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
        return StepResult(
            decision,
            state.current_world,
            state.current_world,
            state.current_task_evaluation,
            RunStatus.RUNNING,
            feedback="action_page_ready",
            action_page=page,
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
        page_issue = action_page.selection_issue(selection.action_id, selection.destination_id)
        if page_issue is not None:
            return _same_world_step(state, decision, RunStatus.BLOCKED, f"admission_rejected:{page_issue.code}")
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
        if not environment.is_current(request):
            return await self._refresh_stale_binding(environment, task, state, decision)
        try:
            execution = await environment.execute(request)
        except Exception:
            return _same_world_step(state, decision, RunStatus.FAILED, "execution_failed")
        if execution.result.dispatch_status is DispatchStatus.NOT_SENT:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                execution=execution,
                feedback=f"action_not_sent:{execution.result.error or 'unknown'}",
            )
        if execution.result.dispatch_status is DispatchStatus.SENT_UNKNOWN:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.WAITING_USER,
                execution=execution,
                feedback="action_effect_unknown",
            )
        post = execution.post_acquisition
        if post is None or post.status is not AcquisitionStatus.ACQUIRED or post.observation is None:
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
                RunStatus.WAITING_USER,
                execution=execution,
                feedback=str(failure_code),
                failure_code=failure_code,
            )
        after = post.observation
        action_outcome = await validated_action_outcome(
            self.action_outcome_projector,
            task,
            state.current_world,
            request,
            execution.result,
            after,
        )
        task_evaluation = await validated_task_evaluation(self.task_evaluator, task, after)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            execution,
            action_outcome,
            feedback=_action_feedback(
                action_outcome.observed_change,
                action_outcome.local_postcondition,
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

    def _status_for_task(self, task: TaskGoal, evaluation: TaskEvaluation) -> RunStatus:
        if (
            evaluation.status is TaskEvaluationStatus.COMPLETE
            and task.requested_outputs
            and bool(getattr(self.decision_ports.action_policy, "supports_final_response", False))
        ):
            return RunStatus.RUNNING
        return _status_for_evaluation(evaluation)


def _same_world_step(
    state: RunState,
    decision: AgentDecision,
    status: RunStatus,
    feedback: str,
) -> StepResult:
    return StepResult(
        decision,
        state.current_world,
        state.current_world,
        state.current_task_evaluation,
        status,
        feedback=feedback,
    )


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
        applies_to_subject = (
            criterion.subject_id == subject_id
            or subject_id in criterion.evidence_scope_target_ids
        )
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
