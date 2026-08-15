"""Readable observe-decide-act-observe-evaluate loop for staged migration."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder, BindingError
from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.control_transition_projection import (
    project_select_action_step,
)
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
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
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

    async def run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> RunState:
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
        )
        while state.status is RunStatus.RUNNING:
            result = await self.step(environment, task, state, intent_context)
            state.apply(result)
            if isinstance(result.decision, SelectAction) and result.execution is not None:
                state.remember_action(project_select_action_step(result))
        return state

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
        context = self.context_builder.build(
            task,
            _context_state(task, state),
            action_space,
            state.current_task_evaluation,
            intent_context,
            context_generation=state.next_context_generation(),
            observation_count=state.observation_count,
            observation_capabilities=environment.observation_capabilities,
        )
        if state.recent_actions:
            context = replace(
                context,
                history=BoundedSection(
                    state.recent_actions,
                    state.execution_count,
                    state.execution_count > len(state.recent_actions),
                ),
            )
        decision = await self.decision_ports.action_policy.decide(context)
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
            return await self._select(environment, task, state, context.context_id, action_space, decision)
        if isinstance(decision, RequestObservation):
            return await self._observe(environment, task, state, decision)
        if isinstance(decision, ProposeDone):
            status = _status_for_evaluation(state.current_task_evaluation)
            if status is RunStatus.RUNNING:
                status = RunStatus.BLOCKED
            feedback = "task_complete" if status is RunStatus.DONE else "completion_not_verified"
            return _same_world_step(state, decision, status, feedback)
        if isinstance(decision, AskUser):
            return _same_world_step(state, decision, RunStatus.WAITING_USER, "user_input_required")
        if isinstance(decision, Abort):
            status = RunStatus.CANCELLED if decision.category == AbortCategory.USER_REQUEST else RunStatus.BLOCKED
            return _same_world_step(state, decision, status, f"agent_aborted:{decision.category}")
        return _same_world_step(state, decision, RunStatus.BLOCKED, "decision_path_not_migrated")

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
        decision: SelectAction,
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
        risk = self.risk_policy.assess(task, selection)
        if risk.decision is RiskDecisionKind.BLOCK:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "risk_blocked")
        if risk.decision is RiskDecisionKind.NEEDS_CONFIRMATION:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.WAITING_CONFIRMATION,
                confirmation=risk,
                feedback="confirmation_required",
            )
        try:
            request = self.binder.bind_for_execution(selection, state.current_world, context_id, task)
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
        post = execution.post_acquisition
        if post is None or post.status is not AcquisitionStatus.ACQUIRED or post.observation is None:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                execution=execution,
                feedback="post_action_observation_unavailable",
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
