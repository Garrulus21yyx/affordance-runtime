"""Readable observe-decide-act-observe-evaluate loop for staged migration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder, BindingError
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.control_transition_projection import (
    project_step_result,
)
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.decisions import (
    Abort,
    AbortCategory,
    AgentDecision,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.evaluation_control import (
    validated_action_evaluation,
    validated_task_evaluation,
)
from affordance_runtime.agent.policy import (
    ActionEvaluator,
    AgentDecisionPorts,
    PolicyFailure,
    TaskEvaluator,
)
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.waiting import MAX_TOTAL_WAIT_MS, SystemWaitController, WaitController
from affordance_runtime.evaluation.contracts import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.world.acquisition import (
    AcquisitionStatus,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.observation_needs import ObservationNeed, ObservationPurpose
from affordance_runtime.world.source_profile import ObservationModality

if TYPE_CHECKING:
    from affordance_runtime.agent.control_feedback import ControlFeedback
    from affordance_runtime.agent.control_transition import ControlTransition
    from affordance_runtime.agent.progress_control import ProgressEvent
    from affordance_runtime.confirmation.contracts import ConfirmationRequest
    from affordance_runtime.execution.contracts import BoundActionRequest


class CoreLoopStartError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class CoreAgentLoop:
    decision_ports: AgentDecisionPorts
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    wait_controller: WaitController = field(default_factory=SystemWaitController)

    async def run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> RunState:
        state = await self.initialize(environment, task)
        return await self.continue_run(environment, task, state, intent_context)

    async def initialize(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
    ) -> RunState:
        """Acquire the first world and create the sole run state."""

        acquisition = await environment.reset(task)
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            raise CoreLoopStartError(acquisition.reason_code)
        initial = acquisition.observation
        evaluation = await validated_task_evaluation(self.task_evaluator, task, initial)
        state = RunState(
            initial,
            evaluation,
            task.loop_budget.max_turns,
            status=_status_for_evaluation(evaluation),
            task_revision=task.revision,
        )
        return state

    async def continue_run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        intent_context: IntentContext | None = None,
    ) -> RunState:
        """Continue an initialized state until it pauses or terminates."""

        return await self._run_until_pause(environment, task, state, intent_context)

    async def _run_until_pause(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        intent_context: IntentContext | None,
    ) -> RunState:
        while state.status is RunStatus.RUNNING:
            result = await self.step(environment, task, state, intent_context)
            state.apply(result)
            if state.status is RunStatus.RUNNING and not isinstance(result.decision, PolicyFailure):
                state.remember_step(project_step_result(result))
        return state

    async def resume_user(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        intent_context: IntentContext | None = None,
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
        evaluation = await validated_task_evaluation(
            self.task_evaluator,
            task,
            state.current_world,
        )
        resumed = replace(
            pending,
            task_evaluation=evaluation,
            status_after=_status_for_evaluation(evaluation),
            feedback="user_input_received",
        )
        state.current_task_evaluation = evaluation
        state.task_revision = task.revision
        state.status = resumed.status_after
        state.last_step = resumed
        state.action_page = None
        if state.status is RunStatus.RUNNING:
            state.remember_step(project_step_result(resumed))
        return await self._run_until_pause(environment, task, state, intent_context)

    async def resume_confirmation(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        *,
        approved: bool,
        intent_context: IntentContext | None = None,
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
        if not approved:
            declined = replace(
                pending,
                status_after=RunStatus.RUNNING,
                confirmation=None,
                feedback="confirmation_declined",
            )
            state.last_step = declined
            state.remember_step(project_step_result(declined))
            return await self._run_until_pause(environment, task, state, intent_context)
        action_space = self.action_space_builder.build(task, state.current_world)
        context_state = _context_state(task, state)
        action_page = self.context_builder.page(action_space, context_state)
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
        state.apply(result, consume_step=False)
        if state.status is RunStatus.RUNNING:
            state.remember_step(project_step_result(result))
        return await self._run_until_pause(environment, task, state, intent_context)

    async def step(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        intent_context: IntentContext | None = None,
    ) -> StepResult:
        if state.status is not RunStatus.RUNNING:
            raise ValueError("core step requires a running state")
        action_space = self.action_space_builder.build(task, state.current_world)
        context_state = _context_state(task, state)
        action_page = (
            state.action_page
            if state.action_page is not None
            and state.action_page.action_space_id == action_space.action_space_id
            else self.context_builder.page(action_space, context_state)
        )
        context = self.context_builder.build(
            task,
            context_state,
            action_space,
            state.current_task_evaluation,
            intent_context,
            action_page=action_page,
            context_generation=state.next_context_generation(),
            observation_count=state.observation_count,
            observation_capabilities=environment.observation_capabilities,
        )
        if state.recent_steps:
            context = replace(
                context,
                history=BoundedSection(
                    state.recent_steps,
                    state.step_count,
                    state.step_count > len(state.recent_steps),
                ),
            )
        try:
            decision = await self.decision_ports.action_policy.decide(context)
        except Exception as exc:
            failure = PolicyFailure(
                ModelFailureKind.INTERNAL_ERROR,
                "policy decision failed",
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
        if isinstance(decision, PolicyFailure):
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.FAILED,
                feedback=f"policy_failure:{decision.kind}",
            )
        if not isinstance(decision, (SelectAction, RequestObservation, RequestActionPage, AskUser, ProposeDone, Wait, Abort)):
            raise TypeError("agent policy returned an unsupported decision")
        if decision.context_id != context.context_id:
            return _same_world_step(state, decision, RunStatus.FAILED, "decision_context_is_stale")
        if isinstance(decision, SelectAction):
            return await self._select(
                environment,
                task,
                state,
                context.context_id,
                action_space,
                action_page,
                decision,
            )
        if isinstance(decision, RequestObservation):
            return await self._observe(environment, task, state, decision)
        if isinstance(decision, RequestActionPage):
            return self._action_page(task, state, action_space, decision)
        if isinstance(decision, Wait):
            return await self._wait(environment, task, state, decision)
        if isinstance(decision, ProposeDone):
            status = _status_for_evaluation(state.current_task_evaluation)
            if status is RunStatus.RUNNING:
                status = RunStatus.RUNNING
            feedback = "task_complete" if status is RunStatus.DONE else "completion_not_verified"
            return _same_world_step(state, decision, status, feedback)
        if isinstance(decision, AskUser):
            return _same_world_step(state, decision, RunStatus.WAITING_USER, "user_input_required")
        if isinstance(decision, Abort):
            status = RunStatus.CANCELLED if decision.category == AbortCategory.USER_REQUEST else RunStatus.BLOCKED
            return _same_world_step(state, decision, status, f"agent_aborted:{decision.category}")
        raise TypeError("core decision dispatch is incomplete")

    def _action_page(self, task, state, action_space, decision: RequestActionPage) -> StepResult:
        try:
            page = self.context_builder.page(
                action_space,
                _context_state(task, state),
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
            _status_for_evaluation(task_evaluation),
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
            _status_for_evaluation(task_evaluation),
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
        action_evaluation = await validated_action_evaluation(
            self.action_evaluator,
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
            _status_for_evaluation(task_evaluation),
            execution,
            action_evaluation,
            feedback=f"action_evaluated:{action_evaluation.status}",
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
            _status_for_evaluation(task_evaluation),
            feedback="binding_refreshed",
        )


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


def _status_for_evaluation(evaluation: TaskEvaluation) -> RunStatus:
    if evaluation.status is TaskEvaluationStatus.COMPLETE:
        return RunStatus.DONE
    if evaluation.status is TaskEvaluationStatus.BLOCKED:
        return RunStatus.BLOCKED
    return RunStatus.RUNNING


@dataclass
class _ContextStateProjection:
    current_observation: WorldObservation
    current_task_evaluation: TaskEvaluation
    remaining_turns: int
    task_revision: int
    progress_revision: int
    context_generation: int
    recent_control_transitions: tuple[ControlTransition, ...] = ()
    control_transition_total_count: int = 0
    pending_revision: int = 0
    pending_user_question: str = ""
    pending_confirmation: ConfirmationRequest | None = None
    pending_unknown_request: BoundActionRequest | None = None
    pending_control_feedback: ControlFeedback | None = None
    observation_cursor: str = ""
    recent_progress_events: tuple[ProgressEvent, ...] = ()
    progress_event_total_count: int = 0


def _context_state(task: TaskGoal, state: RunState) -> _ContextStateProjection:
    return _ContextStateProjection(
        state.current_world,
        state.current_task_evaluation,
        state.remaining_steps,
        task.revision,
        max(0, state.context_generation - 1),
        state.context_generation,
    )
