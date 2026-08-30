"""Readable observe-decide-act-observe-evaluate loop for every product run."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import assert_never

from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder, BindingError
from affordance_runtime.actions.reconciliation import (
    EffectReconciliationReason,
    EffectReconciliationStatus,
)
from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.attempt_signature import (
    PublicAttemptSignature,
    public_attempt_signature,
    public_local_result_attempt_signature,
    public_observation_attempt_signature,
)
from affordance_runtime.agent.budgets import StandaloneRunBudget
from affordance_runtime.agent.context.canonical_world_projection import (
    CanonicalPublicWorldProjection,
    PublicGroundingAmbiguousError,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.context.failures import ModelFailureKind
from affordance_runtime.agent.context.observation_delivery import (
    DeliveryTransition,
    ObservationDeliveryStore,
    current_findings_digest,
)
from affordance_runtime.agent.context.step_projection import project_step_result
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import PublicWorldDelta, WorldTransitionProjector
from affordance_runtime.agent.decisions import (
    Abort,
    AbortCategory,
    AgentDecision,
    DecisionKind,
    FinalResponse,
    InteractionRequestDraft,
    InteractionResponseKind,
    LocalToolResult,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    TextFieldDraft,
    ToolRejectedResult,
    Wait,
)
from affordance_runtime.agent.evaluation_control import (
    validated_action_outcome,
    validated_task_evaluation_attempt,
)
from affordance_runtime.agent.finalization import FinalizationProtocolResult, admit_final_response
from affordance_runtime.agent.interactions import (
    InteractionRequest,
    admit_interaction_request,
    materialize_public_artifact,
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
from affordance_runtime.agent.run_control import (
    CooperativeRunControl,
    RunControlAdmissionKind,
    RunControlBoundary,
    RunControlKind,
    RunControlOutcome,
)
from affordance_runtime.agent.run_state import (
    ControlTermination,
    ControlTerminationKind,
    RunCheckpointFacts,
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
    ActionError,
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
from affordance_runtime.risk.contracts import ConfirmationSubject, RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.acquisition import (
    AcquisitionStatus,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.finalization import final_response_model_guidance, final_response_tool_contract
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
    run_control: CooperativeRunControl = field(default_factory=CooperativeRunControl)

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
            budget=StandaloneRunBudget(task.loop_budget.max_turns),
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
        self._start_episode(initial, evaluation)
        if isinstance(goal_resolution, NeedsInput) and initial_status is RunStatus.WAITING_USER:
            request = _admit_goal_input_request(initial, task.revision, goal_resolution)
            state.apply(
                StepResult(
                    request,
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

    async def restore_paused(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        facts: RunCheckpointFacts,
        checkpoint_id: str,
    ) -> RunState:
        """Hydrate one committed boundary against a newly captured current World."""

        if task.revision != facts.task_revision:
            raise ValueError("checkpoint task revision is stale")
        acquisition = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "fresh World after checkpoint environment reconnect",
            )
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            raise CoreLoopStartError("checkpoint_fresh_world_unavailable")
        current = acquisition.observation
        projection, region_index = self._canonical_world_for(task, current)
        evaluation = await self._validated_task_evaluation(task, current, projection)
        last_decision = facts.last_decision
        if (
            facts.status_before_pause is RunStatus.WAITING_CONFIRMATION
            and isinstance(last_decision, SelectAction)
            and facts.last_confirmation is not None
        ):
            last_decision = self._rebase_checkpoint_confirmation(
                task,
                current,
                last_decision,
                facts.last_confirmation.subject,
            )
        last_step = (
            StepResult(
                last_decision,
                current,
                current,
                evaluation,
                facts.status_before_pause,
                confirmation=facts.last_confirmation,
                feedback=facts.last_feedback,
            )
            if last_decision is not None
            else None
        )
        state = RunState(
            current,
            evaluation,
            facts.remaining_steps,
            status=facts.status_before_pause,
            last_step=last_step,
            observation_count=facts.observation_count + 1,
            execution_count=facts.execution_count,
            step_count=facts.step_count,
            context_generation=facts.context_generation,
            workspace=facts.workspace,
            delivery_store=facts.delivery_store,
            waited_ms=facts.waited_ms,
            task_revision=facts.task_revision,
            goal_resolution=facts.goal_resolution,
            goal_plan_version_counter=facts.goal_plan_version_counter,
            recovery_signal=facts.recovery_signal,
            committed_sent_unknown_count=facts.committed_sent_unknown_count,
            decision_counts=dict(facts.decision_counts),
            currentness_probe_count=facts.currentness_probe_count,
            control_boundary=facts.pause_boundary,
            latest_effect=facts.latest_effect,
            effect_reconciliation=facts.effect_reconciliation,
        )
        state.install_delivery_index(region_index)
        state.install_canonical_world(projection)
        restore_episode = getattr(self.episode_monitor, "restore_episode", None)
        if callable(restore_episode):
            restore_episode(current, evaluation, facts.recovery_signal)
        state.commit_durable_pause(checkpoint_id)
        return state

    async def revise_paused(
        self,
        environment: WorldEnvironment,
        current_task: TaskGoal,
        revised_task: TaskGoal,
        state: RunState,
    ) -> RunState:
        """Build a fresh revision candidate without resuming the policy loop."""

        if (
            state.status is not RunStatus.PAUSED
            or state.control_boundary is None
            or state.paused_from_status is None
            or current_task.task_id != revised_task.task_id
            or current_task.revision != state.task_revision
            or revised_task.revision != current_task.revision + 1
        ):
            raise ValueError("task revision requires one durable consecutive pause")
        await environment.revise_task(revised_task)
        acquisition = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.POLICY_REQUEST,
                "fresh World after task revision",
            )
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            raise CoreLoopStartError("task_revision_fresh_world_unavailable")
        current = acquisition.observation
        projection, region_index = self._canonical_world_for(revised_task, current)
        evaluation = await self._validated_task_evaluation(
            revised_task,
            current,
            projection,
        )
        resolution = await self.goal_plan_boundary.resolve(
            self.goal_compiler,
            revised_task,
            current,
            next_plan_version=state.goal_plan_version_counter + 1,
            trigger=GoalCompileTrigger.TASK_REVISION,
        )
        status = self._status_for_goal_resolution(
            revised_task,
            evaluation,
            resolution,
        )
        if status in {RunStatus.DONE, RunStatus.BLOCKED}:
            status = RunStatus.RUNNING
        pending = (
            StepResult(
                _admit_goal_input_request(current, revised_task.revision, resolution),
                current,
                current,
                evaluation,
                RunStatus.WAITING_USER,
                feedback="goal_compiler_needs_input",
            )
            if isinstance(resolution, NeedsInput) and status is RunStatus.WAITING_USER
            else None
        )
        candidate = RunState(
            current,
            evaluation,
            max(0, revised_task.loop_budget.max_turns - state.step_count),
            status=status,
            last_step=pending,
            observation_count=state.observation_count + 1,
            execution_count=state.execution_count,
            step_count=state.step_count,
            context_generation=state.context_generation,
            workspace=state.workspace,
            waited_ms=state.waited_ms,
            task_revision=revised_task.revision,
            goal_resolution=resolution,
            goal_plan_version_counter=(
                resolution.accepted_plan.plan_version
                if isinstance(resolution, Ready)
                else state.goal_plan_version_counter
            ),
            committed_sent_unknown_count=state.committed_sent_unknown_count,
            decision_counts=dict(state.decision_counts),
            currentness_probe_count=state.currentness_probe_count,
            control_boundary=state.control_boundary,
            latest_effect=state.latest_effect,
        )
        candidate.install_delivery_index(region_index)
        candidate.install_canonical_world(projection)
        self._start_episode(current, evaluation)
        self.trace_sink.goal_compiler_completed(
            goal_compiler_trace_diagnostic(
                self.goal_compiler,
                resolution,
                task_revision=revised_task.revision,
                trigger=GoalCompileTrigger.TASK_REVISION,
                initial_evidence=current,
            )
        )
        return candidate

    def _rebase_checkpoint_confirmation(
        self,
        task: TaskGoal,
        current: WorldObservation,
        decision: SelectAction,
        subject: ConfirmationSubject,
    ) -> SelectAction:
        """Map confirmed semantics to one fresh action ID without dispatching it."""

        action_space = self.action_space_builder.build(task, current)
        candidates = tuple(
            option
            for option in action_space.options
            if option.semantic_action == subject.semantic_action
            and option.target_id == subject.target_id
            and option.effect_category == subject.effect_category
            and tuple(sorted(option.semantic_effects)) == subject.selection_effects
            and (
                subject.destination_id in option.eligible_destination_ids
                if subject.destination_id
                else not option.destination_required
            )
        )
        if len(candidates) != 1 or dict(decision.parameters) != dict(subject.parameters):
            raise CoreLoopStartError("checkpoint_confirmation_not_current")
        return replace(decision, action_id=candidates[0].action_id)

    async def continue_run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        """Continue an initialized state until it pauses or terminates."""

        return await self._run_until_pause(environment, task, state)

    def settle_restored_currentness(self, state: RunState) -> None:
        """Honor a terminal fresh evaluation before any post-restart policy call."""

        evaluation = state.current_task_evaluation
        if evaluation is None:
            raise ValueError("restored state requires a fresh task evaluation")
        status = _status_for_evaluation(evaluation)
        if status not in {RunStatus.DONE, RunStatus.BLOCKED}:
            return
        state.status = status
        self._settle_terminal_episode(state)
        self._record_official_outcome(evaluation)
        self.trace_sink.run_finished(state)

    async def refresh_after_pause_persistence_failure(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        """Re-establish currentness before continuing after a failed pause commit."""

        if state.status is not RunStatus.RUNNING or state.control_boundary is not None:
            raise ValueError("pause persistence recovery requires a running unpaused state")
        acquisition = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "fresh currentness after pause persistence failure",
            )
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            raise CoreLoopStartError("pause_persistence_currentness_unavailable")
        after = acquisition.observation
        delta = WorldTransitionProjector().project(state.current_world, after)
        after_projection, _after_index = self._canonical_world_for(
            task,
            after,
            previous_index=state.delivery_index,
            delta=delta,
        )
        evaluation = await self._validated_task_evaluation(task, after, after_projection)
        decision = RequestObservation(
            context_id="context:runtime:pause-persistence-recovery",
            query_id="observation-query:pause-persistence-recovery",
            purpose=ObservationPurpose.CRITERION_VERIFICATION,
            subject_ids=(task.task_id,),
            public_intent="refresh currentness after pause persistence failure",
        )
        result = StepResult(
            decision,
            state.current_world,
            after,
            evaluation,
            self._status_for_task(task, evaluation),
            feedback="pause_persistence_failed_currentness_refreshed",
            public_world_delta=delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
        )
        result = self._attach_canonical_worlds(task, state, result)
        delivery = state.delivery_store.reduce(result, step_index=max(1, state.step_count))
        self._commit_step(
            state,
            result,
            consume_step=False,
            delivery_transition=delivery,
        )
        return state

    async def refresh_after_user_control(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        """Re-establish Runtime currentness after an exclusive external control lease."""

        state.begin_external_currentness_refresh()
        acquisition = await environment.capture(
            WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "fresh currentness after user control",
            )
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            raise CoreLoopStartError("user_control_currentness_unavailable")
        after = acquisition.observation
        delta = WorldTransitionProjector().project(state.current_world, after)
        after_projection, _after_index = self._canonical_world_for(
            task,
            after,
            previous_index=state.delivery_index,
            delta=delta,
        )
        evaluation = await self._validated_task_evaluation(task, after, after_projection)
        decision = RequestObservation(
            context_id="context:runtime:user-control-return",
            query_id="observation-query:user-control-return",
            purpose=ObservationPurpose.CRITERION_VERIFICATION,
            subject_ids=(task.task_id,),
            public_intent="refresh currentness after user control",
        )
        result = StepResult(
            decision,
            state.current_world,
            after,
            evaluation,
            self._status_for_task(task, evaluation),
            feedback="user_control_currentness_refreshed",
            public_world_delta=delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
        )
        result = self._attach_canonical_worlds(task, state, result)
        delivery = state.delivery_store.reduce(result, step_index=max(1, state.step_count))
        self._commit_step(
            state,
            result,
            consume_step=False,
            delivery_transition=delivery,
        )
        if state.terminal:
            self.trace_sink.run_finished(state)
        return state

    async def _run_until_pause(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
    ) -> RunState:
        while state.status is RunStatus.RUNNING and state.control_boundary is None:
            if self._pause_unavailable_reconciliation(state, task):
                break
            if self._apply_control_before_policy(state):
                break
            try:
                result = await self.step(environment, task, state)
            except BaseException as exc:
                self.trace_sink.run_error(exc, state)
                raise
            result = self._apply_control_after_closed_step(state, result)
            result = self._attach_canonical_worlds(task, state, result)
            delivery = state.delivery_store.reduce(result, step_index=max(1, state.step_count + 1))
            self._commit_step(state, result, delivery_transition=delivery)
        if state.terminal:
            self.run_control.resolve_terminal()
            self.trace_sink.run_finished(state)
        elif state.control_boundary is not None:
            self._trace_control_boundary(state.control_boundary)
        else:
            self.trace_sink.run_paused(state)
        return state

    def _apply_control_before_policy(self, state: RunState) -> bool:
        request = self.run_control.pending
        if request is None:
            return False
        if not self._close_deferred_call(state.last_step) and request.kind is RunControlKind.PAUSE:
            self.run_control.fail_pending("deferred_history_closure_failed")
            return False
        outcome = self.run_control.acknowledge(RunControlBoundary.BEFORE_POLICY)
        if outcome is None:
            return False
        self.commit_control_boundary(state, outcome)
        return True

    def _pause_unavailable_reconciliation(
        self,
        state: RunState,
        task: TaskGoal,
    ) -> bool:
        reconciliation = state.effect_reconciliation
        if reconciliation is None:
            return False
        if reconciliation.status is EffectReconciliationStatus.PENDING:
            action_space = self.action_space_builder.build(task, state.current_world)
            if any(
                option.resource_ref == reconciliation.original_effect.resource_ref for option in action_space.options
            ):
                return False
            state.require_reconciliation_input(EffectReconciliationReason.COMPENSATION_UNAVAILABLE)
        elif reconciliation.status is not EffectReconciliationStatus.NEEDS_INPUT:
            return False
        self._request_reconciliation_pause(state, "needs-input")
        if not self._apply_control_before_policy(state):
            raise RuntimeError("effect reconciliation pause boundary was not admitted")
        return True

    def _request_reconciliation_pause(self, state: RunState, suffix: str) -> None:
        reconciliation = state.effect_reconciliation
        if reconciliation is None:
            raise ValueError("run has no effect reconciliation to pause")
        command_id = (
            f"runtime-reconcile:{state.task_revision}:"
            f"{reconciliation.original_effect.effect_ref[-24:]}:"
            f"{state.execution_count}:{suffix}"
        )
        admission = self.run_control.request(command_id, RunControlKind.PAUSE)
        if admission.outcome is not RunControlAdmissionKind.ACCEPTED:
            raise RuntimeError("effect reconciliation pause command was not admitted")

    def _apply_control_after_closed_step(
        self,
        state: RunState,
        result: StepResult,
    ) -> StepResult:
        request = self.run_control.pending
        if request is None:
            return result
        dispatch_status = _last_dispatch_status(result)
        pause_uncertain_dispatch = (
            request.kind is RunControlKind.PAUSE
            and dispatch_status is DispatchStatus.SENT_UNKNOWN
            and result.status_after is RunStatus.BLOCKED
            and result.runtime_failure is None
            and result.failure_code is None
        )
        if (
            result.status_after
            in {
                RunStatus.DONE,
                RunStatus.BLOCKED,
                RunStatus.CANCELLED,
                RunStatus.FAILED,
            }
            and not pause_uncertain_dispatch
        ):
            self.run_control.resolve_terminal()
            return result
        boundary = {
            RunStatus.WAITING_USER: RunControlBoundary.WAITING_USER,
            RunStatus.WAITING_CONFIRMATION: RunControlBoundary.WAITING_CONFIRMATION,
        }.get(result.status_after, RunControlBoundary.AFTER_EVALUATION)
        preview = self.run_control.preview(
            boundary,
            dispatch_status=dispatch_status,
        )
        if preview is None:
            return result
        controlled = replace(
            result,
            status_after=(
                RunStatus.CANCELLED
                if preview.kind is RunControlKind.CANCEL
                else (RunStatus.RUNNING if pause_uncertain_dispatch else result.status_after)
            ),
            feedback=f"{result.feedback}:control_{preview.outcome.value}",
            control_boundary=preview,
        )
        if not self._close_deferred_call(controlled) and request.kind is RunControlKind.PAUSE:
            self.run_control.fail_pending("deferred_history_closure_failed")
            return result
        outcome = self.run_control.acknowledge(
            boundary,
            dispatch_status=dispatch_status,
        )
        assert outcome is not None
        return replace(controlled, control_boundary=outcome)

    def _control_after_policy(
        self,
        state: RunState,
        decision: AgentDecision,
    ) -> StepResult | None:
        request = self.run_control.pending
        if request is None:
            return None
        preview = self.run_control.preview(
            RunControlBoundary.AFTER_POLICY,
            dispatch_status=DispatchStatus.NOT_SENT,
        )
        if preview is None:
            return None
        result = _same_world_step(
            state,
            decision,
            (RunStatus.CANCELLED if preview.kind is RunControlKind.CANCEL else RunStatus.RUNNING),
            f"action_not_dispatched:control_{preview.outcome.value}",
            control_boundary=preview,
        )
        if not self._close_deferred_call(result) and request.kind is RunControlKind.PAUSE:
            self.run_control.fail_pending("deferred_history_closure_failed")
            return _same_world_step(
                state,
                decision,
                RunStatus.RUNNING,
                "action_not_dispatched:control_boundary_failed",
            )
        outcome = self.run_control.acknowledge(
            RunControlBoundary.AFTER_POLICY,
            dispatch_status=DispatchStatus.NOT_SENT,
        )
        assert outcome is not None
        return replace(result, control_boundary=outcome)

    def _close_deferred_call(self, result: StepResult | None) -> bool:
        if result is None:
            return True
        close = getattr(self.decision_ports.action_policy, "close_deferred_call", None)
        if callable(close):
            try:
                close(result)
            except Exception:
                return False
        return True

    def _trace_control_boundary(self, outcome: RunControlOutcome) -> None:
        emit = getattr(self.trace_sink, "control_boundary_reached", None)
        if callable(emit):
            emit(outcome)

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
            or not isinstance(pending.decision, InteractionRequest)
        ):
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
            _admit_goal_input_request(state.current_world, task.revision, resolution)
            if isinstance(resolution, NeedsInput) and status is RunStatus.WAITING_USER
            else pending.decision
        )
        resumed = replace(
            pending,
            decision=decision,
            task_evaluation=evaluation,
            status_after=status,
            recovery_signal=None,
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
        state.recovery_signal = None
        state.delivery_store = ObservationDeliveryStore()
        self._start_episode(state.current_world, evaluation)
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
                control_termination=ControlTermination(ControlTerminationKind.TURN_BUDGET_EXHAUSTED),
            )
        if delivery_transition is None:
            delivery_transition = state.delivery_store.reduce(
                result,
                step_index=max(1, state.step_count + int(consume_step)),
            )
        result = self._apply_episode_monitor(
            result,
            state,
            delivery_transition,
            advance=(
                consume_step
                or result.execution_receipts is not None
                or result.action_outcome is not None
                or isinstance(result.decision, ToolRejectedResult)
            ),
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
            (result.finalization is not None and result.finalization.native_evaluation_status is not None)
            or result.task_evaluation.status in {TaskEvaluationStatus.COMPLETE, TaskEvaluationStatus.BLOCKED}
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

        if result.feedback == PublicGroundingAmbiguousError.code:
            return result
        if result.before_public_world is not None:
            if (
                result.after_delivery_index is not None
                or result.after_world.observation_id == result.before_world.observation_id
            ):
                return result
            after_actions = self.action_space_builder.build(task, result.after_world)
            after_index = WorldDeliveryIndex.from_observation(
                result.after_world,
                after_actions.options,
                public_world_delta=result.public_world_delta,
                previous_index=state.delivery_index or state.prior_delivery_index,
            )
            return replace(result, after_delivery_index=after_index)
        before = state.canonical_world
        if before is None:
            before_actions = self.action_space_builder.build(task, result.before_world)
            before_index = state.delivery_index or WorldDeliveryIndex.from_observation(
                result.before_world, before_actions.options
            )
            before = CanonicalPublicWorldProjection.build(result.before_world, before_index, before_actions)
        else:
            before_index = state.delivery_index
        if result.after_world is result.before_world or (
            result.after_world.observation_id == result.before_world.observation_id
        ):
            after = before
            after_index = before_index
        else:
            after_actions = self.action_space_builder.build(task, result.after_world)
            after_index = WorldDeliveryIndex.from_observation(
                result.after_world,
                after_actions.options,
                public_world_delta=result.public_world_delta,
                previous_index=state.delivery_index or state.prior_delivery_index,
            )
            after = CanonicalPublicWorldProjection.build(result.after_world, after_index, after_actions)
        return replace(
            result,
            before_public_world=before,
            after_public_world=after,
            after_delivery_index=after_index,
        )

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
        *,
        advance: bool,
    ) -> StepResult:
        if result.status_after in {
            RunStatus.DONE,
            RunStatus.BLOCKED,
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }:
            self._end_episode()
            return replace(result, recovery_signal=None)
        monitor = self.episode_monitor
        if monitor is None:
            return replace(result, recovery_signal=state.recovery_signal)
        if not advance:
            return replace(result, recovery_signal=state.recovery_signal)
        if result.task_evaluation is None:
            return replace(result, recovery_signal=state.recovery_signal)
        if (
            result.status_after in {RunStatus.WAITING_USER, RunStatus.WAITING_CONFIRMATION}
            or result.control_boundary is not None
        ):
            return replace(result, recovery_signal=state.recovery_signal)
        evaluate = getattr(monitor, "evaluate", None)
        if not callable(evaluate):
            return replace(result, recovery_signal=state.recovery_signal)
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
                    f"episode_monitor_recover:{getattr(signal.kind, 'value', 'control_stall')}"
                    if signal is not None
                    else "episode_monitor_recover:control_stall"
                ),
                recovery_signal=signal,
            )
        if str(recommendation) != "block":
            return replace(
                result,
                recovery_signal=getattr(transition, "recovery_signal", None),
            )
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

    def _start_episode(self, world: WorldObservation, evaluation: TaskEvaluation) -> None:
        start_episode = getattr(self.episode_monitor, "start_episode", None)
        if callable(start_episode):
            start_episode(world, evaluation)

    def _end_episode(self) -> None:
        end_episode = getattr(self.episode_monitor, "end_episode", None)
        if callable(end_episode):
            end_episode()

    def _settle_terminal_episode(self, state: RunState) -> None:
        if not state.terminal:
            raise ValueError("episode terminal settlement requires a terminal run")
        state.recovery_signal = None
        self._end_episode()

    def commit_control_boundary(self, state: RunState, outcome: RunControlOutcome) -> None:
        """Commit one non-StepResult control transition without splitting recovery truth."""

        state.apply_control_boundary(outcome)
        if state.terminal:
            self._settle_terminal_episode(state)

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
        complete_action_space = self.action_space_builder.build(
            task,
            state.current_world,
        )
        action_space = self._reconciliation_action_space(
            state,
            complete_action_space,
        )
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
        result = self._close_reconciliation_attempt(state, result)
        result = self._apply_control_after_closed_step(state, result)
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
        complete_action_space = self.action_space_builder.build(
            task,
            state.current_world,
        )
        action_space = self._reconciliation_action_space(
            state,
            complete_action_space,
        )
        canonical_world = (
            state.canonical_world if action_space.action_space_id == complete_action_space.action_space_id else None
        )
        region_index = state.delivery_index
        if (
            region_index is None
            or region_index.world_observation_id != state.current_world.observation_id
            or set(region_index.action_region_keys) != {item.action_id for item in action_space.options}
        ):
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
        if canonical_world is None:
            canonical_world = CanonicalPublicWorldProjection.build(
                state.current_world,
                region_index,
                action_space,
            )
            state.install_canonical_world(canonical_world)
        observation_projection = state.observation_projection
        if observation_projection is None:
            observation_projection = self.context_builder.project_observation(
                state.current_world,
                action_space,
                observation_capabilities=environment.observation_capabilities,
                runtime_controls=self.runtime_controls,
                region_index=region_index,
                canonical_world=canonical_world,
            )
            state.install_observation_projection(observation_projection)
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
                canonical_world=canonical_world,
                control_feedback=_control_feedback(state),
                action_discovery=state.action_discovery,
                last_step=state.last_step,
                observation_projection=observation_projection,
                final_response_guidance=final_response_model_guidance(environment.final_response_codec),
                final_response_contract=final_response_tool_contract(environment.final_response_codec),
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
                InteractionRequestDraft,
                LocalToolResult,
                FinalResponse,
                Wait,
                Abort,
            ),
        ):
            raise TypeError("agent policy returned an unsupported decision")
        if decision.context_id != context.context_id:
            return _same_world_step(state, decision, RunStatus.FAILED, "decision_context_is_stale")
        controlled = self._control_after_policy(state, decision)
        if controlled is not None:
            return replace(
                controlled,
                policy_observation=context.actor_world,
                policy_target_refs=context.grounding.target_refs,
                model_delivery=getattr(
                    getattr(self.decision_ports.action_policy, "port", None),
                    "last_model_delivery",
                    None,
                ),
            )
        if state.reconciliation_pending and isinstance(decision, (FinalResponse, Abort)):
            state.require_reconciliation_input(EffectReconciliationReason.COMPENSATION_ACTION_NOT_ALLOWED)
            self._request_reconciliation_pause(state, "action-not-allowed")
            return _same_world_step(
                state,
                decision,
                RunStatus.RUNNING,
                "effect_reconciliation:compensation_action_required",
            )
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
                rejection = _prohibited_observation_attempt_replay_rejection(
                    state.recovery_signal,
                    decision,
                    state.current_world,
                )
                result = (
                    _same_world_step(
                        state,
                        rejection,
                        RunStatus.RUNNING,
                        "recovery_repeat_rejected",
                    )
                    if rejection is not None
                    else await self._observe(environment, task, state, decision)
                )
            case DecisionKind.FIND_CONTROLS:
                assert isinstance(decision, RequestActionPage)
                result = self._action_page(task, state, action_space, context, decision)
                rejection = _prohibited_local_attempt_replay_rejection(state.recovery_signal, result)
                if rejection is not None:
                    result = _same_world_step(
                        state,
                        rejection,
                        RunStatus.RUNNING,
                        "recovery_repeat_rejected",
                    )
            case DecisionKind.READ_REGION | DecisionKind.SEARCH_PAGE_CONTENT | DecisionKind.TOOL_REJECTED:
                assert isinstance(decision, LocalToolResult)
                result = StepResult(
                    decision,
                    state.current_world,
                    state.current_world,
                    state.current_task_evaluation,
                    RunStatus.RUNNING,
                    feedback="local_tool_result",
                )
                rejection = _prohibited_local_attempt_replay_rejection(state.recovery_signal, result)
                if rejection is not None:
                    result = _same_world_step(
                        state,
                        rejection,
                        RunStatus.RUNNING,
                        "recovery_repeat_rejected",
                    )
            case DecisionKind.WAIT:
                assert isinstance(decision, Wait)
                result = await self._wait(environment, task, state, decision)
            case DecisionKind.SUBMIT_FINAL_RESPONSE:
                assert isinstance(decision, FinalResponse)
                result = await self._finalize(environment, task, state, decision)
            case DecisionKind.ASK_USER:
                assert isinstance(decision, InteractionRequestDraft)
                admission = admit_interaction_request(state.current_world, decision)
                if admission.request is None:
                    result = _same_world_step(
                        state,
                        decision,
                        RunStatus.FAILED,
                        admission.rejection_code.value
                        if admission.rejection_code is not None
                        else "interaction_invalid",
                    )
                else:
                    result = _same_world_step(
                        state,
                        admission.request,
                        RunStatus.WAITING_USER,
                        "user_input_required",
                    )
            case DecisionKind.ABORT:
                assert isinstance(decision, Abort)
                status = RunStatus.CANCELLED if decision.category == AbortCategory.USER_REQUEST else RunStatus.BLOCKED
                result = _same_world_step(
                    state,
                    decision,
                    status,
                    f"agent_aborted:{decision.category}",
                    control_termination=ControlTermination(ControlTerminationKind.AGENT_ABORTED),
                )
            case unexpected:
                assert_never(unexpected)
        result = self._close_reconciliation_attempt(state, result)
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

    def _reconciliation_action_space(
        self,
        state: RunState,
        action_space: ActionSpace,
    ) -> ActionSpace:
        reconciliation = state.effect_reconciliation
        if reconciliation is None or reconciliation.status is not EffectReconciliationStatus.PENDING:
            return action_space
        resource_ref = reconciliation.original_effect.resource_ref
        return ActionSpace(
            action_space.observation_id,
            tuple(option for option in action_space.options if option.resource_ref == resource_ref),
            action_space.issues,
        )

    def _close_reconciliation_attempt(
        self,
        state: RunState,
        result: StepResult,
    ) -> StepResult:
        if not state.reconciliation_pending or self.run_control.pending is not None:
            return result
        receipts = () if result.execution_receipts is None else result.execution_receipts.receipts
        if receipts:
            if result.task_evaluation is None:
                return result
            self._request_reconciliation_pause(state, "attempt-closed")
            return replace(
                result,
                status_after=RunStatus.RUNNING,
                failure_code=None,
                runtime_failure=None,
                control_termination=None,
            )
        if not isinstance(result.decision, SelectAction):
            return result
        if result.status_after not in {RunStatus.BLOCKED, RunStatus.FAILED}:
            return result
        if result.runtime_failure is not None or result.task_evaluation is None:
            return result
        reason = (
            EffectReconciliationReason.COMPENSATION_NOT_SENT
            if result.execution_receipts is not None
            else EffectReconciliationReason.COMPENSATION_ACTION_NOT_ALLOWED
            if result.feedback.startswith(("risk_blocked", "admission_rejected"))
            else EffectReconciliationReason.COMPENSATION_UNAVAILABLE
        )
        state.require_reconciliation_input(reason)
        self._request_reconciliation_pause(state, "attempt-rejected")
        return replace(
            result,
            status_after=RunStatus.RUNNING,
            failure_code=None,
            runtime_failure=None,
            control_termination=None,
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
        try:
            public_artifact = materialize_public_artifact(
                state.current_world,
                decision.artifact,
                response_identity=decision.context_id,
            )
        except ValueError:
            return _same_world_step(
                state,
                decision,
                RunStatus.FAILED,
                "public_artifact_evidence_not_current",
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
            final_delta, after_projection, after_index = self._canonical_transition_for(
                task,
                state.current_world,
                post.observation,
                previous_index=state.delivery_index,
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
                    after_delivery_index=after_index,
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
                        FailureKind.CAPABILITY_UNAVAILABLE
                        if isinstance(attempt, Unavailable)
                        else FailureKind.INTERNAL,
                        attempt.code,
                        exception_class=attempt.diagnostic.exception_type,
                    ),
                    finalization=facts,
                    public_world_delta=final_delta,
                    before_public_world=state.canonical_world,
                    after_public_world=after_projection,
                    after_delivery_index=after_index,
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
        final_status = _status_for_final_evaluation(evaluation)
        return StepResult(
            decision,
            state.current_world,
            post.observation,
            evaluation,
            final_status,
            feedback="final_response_evaluated",
            finalization=facts,
            public_world_delta=final_delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
            after_delivery_index=after_index,
            public_artifact=(public_artifact if final_status is RunStatus.DONE else None),
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

    def _action_page(self, task, state, action_space, context, decision: RequestActionPage) -> StepResult:
        query = decision.query
        region_index = context.region_index
        if region_index is None:
            raise ValueError("action discovery requires the current delivery index")
        try:
            page = self.context_builder.page(
                action_space,
                state.current_world,
                query=query,
                region_index=region_index,
            )
        except ValueError:
            return _same_world_step(state, decision, RunStatus.BLOCKED, "action_page_invalid")
        discovery = self.context_builder.discovery_result(
            action_space,
            state.current_world,
            page,
            region_index=region_index,
            canonical_world=context.canonical_world,
            grounding=context.grounding,
        )
        retained_page = page
        feedback = "action_page_ready"
        if query:
            retained_page = (
                state.action_page
                if state.action_page is not None
                and state.action_page.action_space_id == action_space.action_space_id
                and not state.action_page.query
                else self.context_builder.page(
                    action_space,
                    state.current_world,
                    region_index=region_index,
                )
            )
        if page.total_count == 0:
            retained_page = (
                state.action_page
                if state.action_page is not None and state.action_page.action_space_id == action_space.action_space_id
                else self.context_builder.page(
                    action_space,
                    state.current_world,
                    region_index=region_index,
                )
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
                control_termination=ControlTermination(ControlTerminationKind.WAIT_BUDGET_EXHAUSTED),
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
        delta, after_projection, after_index = self._canonical_transition_for(
            task,
            state.current_world,
            after,
            previous_index=state.delivery_index,
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
            after_delivery_index=after_index,
        )

    async def _observe(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        state: RunState,
        decision: RequestObservation,
    ) -> StepResult:
        purpose = ObservationPurpose(decision.purpose)
        agent_visual_purposes = {
            ObservationPurpose.ENTITY_DISCOVERY,
            ObservationPurpose.TARGET_DISAMBIGUATION,
            ObservationPurpose.VISUAL_PROPERTY,
            ObservationPurpose.POINT_GROUNDING,
            ObservationPurpose.TEXT_IN_IMAGE,
            ObservationPurpose.SPATIAL_RELATIONSHIP,
            ObservationPurpose.VISUAL_CHANGE,
        }
        modality = ObservationModality.VISUAL if purpose in agent_visual_purposes else None
        assurance_subject = (decision.subject_ids or decision.candidate_ids or (task.task_id,))[0]
        need = ObservationNeed(
            need_id=decision.query_id,
            purpose=purpose,
            subject_ids=decision.subject_ids,
            required_modality=modality,
            required_assurance=(
                ObservationAssurance.WEAK
                if purpose in agent_visual_purposes
                else _criterion_assurance(
                    task,
                    state.current_task_evaluation,
                    purpose,
                    assurance_subject,
                )
            ),
            evidence_property=decision.evidence_property,
            candidate_ids=decision.candidate_ids,
            query_text=decision.atomic_query or decision.predicate,
            max_results=decision.max_results,
        )
        acquisition = await environment.capture(
            WorldObservationRequest(ObservationRequestKind.POLICY_REQUEST, decision.reason, (need,))
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            outcome = acquisition.query_outcome(decision.query_id)
            if outcome is not None:
                return StepResult(
                    decision,
                    state.current_world,
                    state.current_world,
                    state.current_task_evaluation,
                    RunStatus.RUNNING,
                    feedback=f"observation_{outcome.disposition.value}",
                    before_public_world=state.canonical_world,
                    after_public_world=state.canonical_world,
                    after_delivery_index=state.delivery_index,
                    observation_outcome=outcome,
                )
            return _same_world_step(
                state,
                decision,
                RunStatus.BLOCKED,
                f"observation_unavailable:{acquisition.reason_code}",
            )
        after = acquisition.observation
        delta, after_projection, after_index = self._canonical_transition_for(
            task,
            state.current_world,
            after,
            previous_index=state.delivery_index,
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
            after_delivery_index=after_index,
            observation_outcome=acquisition.query_outcome(decision.query_id),
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
        reconciliation = state.effect_reconciliation
        if (
            reconciliation is not None
            and reconciliation.status is EffectReconciliationStatus.PENDING
            and selection.resource_ref != reconciliation.original_effect.resource_ref
        ):
            return _same_world_step(
                state,
                decision,
                RunStatus.BLOCKED,
                "effect_reconciliation:resource_mismatch",
            )
        recovery_rejection = _prohibited_gui_attempt_replay_rejection(
            state.recovery_signal,
            decision,
            selection,
            state.current_world,
        )
        if recovery_rejection is not None:
            return _same_world_step(
                state,
                recovery_rejection,
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
            transition_delta: PublicWorldDelta | None = None
            transition_before: CanonicalPublicWorldProjection | None = None
            transition_after: CanonicalPublicWorldProjection | None = None
            transition_index: WorldDeliveryIndex | None = None
            if after.observation_id != state.current_world.observation_id:
                transition_delta, transition_after, transition_index = self._canonical_transition_for(
                    task,
                    state.current_world,
                    after,
                    previous_index=state.delivery_index,
                )
                transition_before = state.canonical_world
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
                public_world_delta=transition_delta,
                before_public_world=transition_before,
                after_public_world=transition_after,
                after_delivery_index=transition_index,
            )
        if (
            execution.result.dispatch_status is DispatchStatus.NOT_SENT
            and execution.result.error is ActionError.STALE_BINDING
        ):
            return await self._refresh_stale_binding(
                environment,
                task,
                state,
                decision,
                execution=execution,
            )
        if execution.result.dispatch_status is DispatchStatus.NOT_SENT:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                (RunStatus.RUNNING if execution.result.permits_reselection else RunStatus.BLOCKED),
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
        public_world_delta, after_projection, after_index = self._canonical_transition_for(
            task,
            state.current_world,
            after,
            previous_index=state.delivery_index,
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
            return replace(
                _post_dispatch_evaluation_failure(
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
                    public_world_delta=public_world_delta,
                ),
                before_public_world=state.canonical_world,
                after_public_world=after_projection,
                after_delivery_index=after_index,
            )
        except Exception as exc:
            return replace(
                _post_dispatch_evaluation_failure(
                    state,
                    decision,
                    after,
                    ExecutionReceiptBatch.from_atomic(execution, after.observation_id),
                    cancelled=False,
                    code="action_outcome_failed",
                    public_world_delta=public_world_delta,
                    exception_class=type(exc).__name__,
                ),
                before_public_world=state.canonical_world,
                after_public_world=after_projection,
                after_delivery_index=after_index,
            )
        if execution.result.dispatch_status is DispatchStatus.SENT_UNKNOWN:
            if action_outcome.local_postcondition is LocalPostconditionStatus.UNKNOWN:
                batch = ExecutionReceiptBatch.from_atomic(execution, after.observation_id)
                task_evaluation = await self._task_evaluation_after_dispatch(
                    task, state, decision, after, batch, after_projection, after_index
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
                    after_delivery_index=after_index,
                )
        batch = ExecutionReceiptBatch.from_atomic(execution, after.observation_id)
        task_evaluation = await self._task_evaluation_after_dispatch(
            task, state, decision, after, batch, after_projection, after_index
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
            after_delivery_index=after_index,
        )

    async def _recover_post_dispatch_observation(
        self,
        environment: WorldEnvironment,
        execution: ExecutionOutcome,
    ) -> ExecutionOutcome:
        """Allow at most two fresh captures total for one dispatch attempt."""

        post = execution.post_acquisition
        if (
            execution.result.dispatch_status is DispatchStatus.NOT_SENT
            or post is None
            or post.status is AcquisitionStatus.ACQUIRED
            or execution.recovery_acquisitions
        ):
            return execution
        observation_request = WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "recover missing post-action observation",
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

    async def _refresh_stale_binding(
        self,
        environment,
        task,
        state,
        decision,
        *,
        execution: ExecutionOutcome | None = None,
    ) -> StepResult:
        acquisition = await environment.capture(
            WorldObservationRequest(ObservationRequestKind.BINDING_REFRESH, "selected binding is stale")
        )
        if acquisition.status is not AcquisitionStatus.ACQUIRED or acquisition.observation is None:
            return StepResult(
                decision,
                state.current_world,
                state.current_world,
                state.current_task_evaluation,
                RunStatus.BLOCKED,
                execution_receipts=(
                    ExecutionReceiptBatch.from_atomic(
                        execution,
                        state.current_world.observation_id,
                    )
                    if execution is not None
                    else None
                ),
                feedback="binding_refresh_unavailable",
            )
        after = acquisition.observation
        delta, after_projection, after_index = self._canonical_transition_for(
            task,
            state.current_world,
            after,
            previous_index=state.delivery_index,
        )
        task_evaluation = await self._validated_task_evaluation(task, after, after_projection)
        return StepResult(
            decision,
            state.current_world,
            after,
            task_evaluation,
            self._status_for_task(task, task_evaluation),
            execution_receipts=(
                ExecutionReceiptBatch.from_atomic(
                    execution,
                    after.observation_id,
                )
                if execution is not None
                else None
            ),
            feedback="binding_refreshed",
            public_world_delta=delta,
            before_public_world=state.canonical_world,
            after_public_world=after_projection,
            after_delivery_index=after_index,
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
        after_index: WorldDeliveryIndex,
    ) -> TaskEvaluation | StepResult:
        """Close evaluator failure without losing already-crossed dispatch truth."""

        public_world_delta = after_index.public_world_delta
        if not isinstance(public_world_delta, PublicWorldDelta):
            raise TypeError("after-World delivery index requires its public transition")
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
                public_world_delta=public_world_delta,
            )
            return replace(
                failure,
                before_public_world=state.canonical_world,
                after_public_world=after_projection,
                after_delivery_index=after_index,
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
                public_world_delta=public_world_delta,
                failure_kind=(
                    FailureKind.CAPABILITY_UNAVAILABLE if isinstance(outcome, Unavailable) else FailureKind.INTERNAL
                ),
                exception_class=outcome.diagnostic.exception_type,
            )
            return replace(
                failure,
                before_public_world=state.canonical_world,
                after_public_world=after_projection,
                after_delivery_index=after_index,
            )

    async def _validated_task_evaluation(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        canonical_world: CanonicalPublicWorldProjection,
    ) -> TaskEvaluation:
        attempt = await validated_task_evaluation_attempt(self.task_evaluator, task, observation, canonical_world)
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

    def _canonical_transition_for(
        self,
        task: TaskGoal,
        before: WorldObservation,
        after: WorldObservation,
        *,
        previous_index: WorldDeliveryIndex | None,
    ) -> tuple[PublicWorldDelta, CanonicalPublicWorldProjection, WorldDeliveryIndex]:
        """Project one fresh World, its regions, and its delta from one shared index."""

        action_space = self.action_space_builder.build(task, after)
        index = WorldDeliveryIndex.from_observation(
            after,
            action_space.options,
            previous_index=previous_index,
        )
        delta = WorldTransitionProjector().project(
            before,
            after,
            before_index=previous_index,
            after_index=index,
        )
        index = replace(index, public_world_delta=delta)
        return delta, CanonicalPublicWorldProjection.build(after, index, action_space), index

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
    public_world_delta: PublicWorldDelta,
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
        public_world_delta=public_world_delta,
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
    decision: AgentDecision | InteractionRequest,
    status: RunStatus,
    feedback: str,
    *,
    finalization: FinalizationProtocolResult | None = None,
    control_termination: ControlTermination | None = None,
    control_boundary: RunControlOutcome | None = None,
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
        control_boundary=control_boundary,
    )


def _admit_goal_input_request(
    world: WorldObservation,
    task_revision: int,
    resolution: NeedsInput,
) -> InteractionRequest:
    fields = tuple(TextFieldDraft(item) for item in resolution.fields)
    draft = InteractionRequestDraft(
        f"context:goal-compiler:{task_revision}",
        resolution.question,
        (InteractionResponseKind.STRUCTURED_FIELDS if fields else InteractionResponseKind.FREE_TEXT),
        fields,
    )
    admission = admit_interaction_request(world, draft)
    if admission.request is None:
        raise TypeError("GoalCompiler input request failed deterministic admission")
    return admission.request


def _last_dispatch_status(result: StepResult) -> DispatchStatus | None:
    batch = result.execution_receipts
    if batch is None:
        return None
    if batch.receipts:
        return batch.receipts[-1].result.dispatch_status
    terminal = batch.terminal_failure
    return terminal.dispatch_status if terminal is not None else None


def _recovery_feedback(signal) -> dict[str, object]:
    if signal is None:
        return {}
    return {
        "kind": signal.kind.value,
        "epoch_id": signal.epoch_id,
        "evidence_revision": signal.evidence_revision,
        "stable_signature": signal.stable_signature,
        "observed_evidence": signal.observed_evidence,
        "attempted_modes": signal.attempted_modes,
        "prohibited_attempt_signatures": tuple(
            to_json_compatible(item) for item in signal.prohibited_attempt_signatures
        ),
        "human_instruction": signal.human_instruction,
        "recovery_attempt": signal.recovery_attempt,
    }


def _control_feedback(state: RunState) -> dict[str, object]:
    feedback = _recovery_feedback(state.recovery_signal)
    reconciliation = state.effect_reconciliation
    if reconciliation is not None and reconciliation.status is EffectReconciliationStatus.PENDING:
        feedback["effect_reconciliation"] = {
            **reconciliation.public_summary(),
            "instruction": (
                "Choose one current ordinary action that compensates the retained effect on "
                "this same resource. Do not blindly replay the original request or continue the "
                "revised goal until compensation is verified; ask the user if no safe action exists."
            ),
        }
    return feedback


def _prohibited_gui_attempt_replay_rejection(signal, decision, selection, world) -> ToolRejectedResult | None:
    if signal is None or not signal.prohibited_attempt_signatures:
        return None
    current = public_attempt_signature(
        selection.semantic_action,
        selection.target_id,
        selection.destination_id,
        selection.parameters,
        world,
    )
    return _prohibited_attempt_replay_rejection(
        signal,
        context_id=decision.context_id,
        tool_call_id=decision.tool_call_id,
        operation=selection.semantic_action,
        signature=current,
    )


def _prohibited_local_attempt_replay_rejection(signal, step: StepResult) -> ToolRejectedResult | None:
    if signal is None or not signal.prohibited_attempt_signatures:
        return None
    decision = step.decision
    if isinstance(decision, ToolRejectedResult):
        return None
    if isinstance(decision, LocalToolResult):
        operation = decision.tool_name
        signature = public_local_result_attempt_signature(
            operation,
            decision.arguments,
            decision.result,
            step.after_world,
        )
        context_id = decision.context_id
        tool_call_id = decision.tool_call_id
    elif isinstance(decision, RequestActionPage) and step.action_page_result is not None:
        operation = "find_controls"
        signature = public_local_result_attempt_signature(
            operation,
            {"query": decision.query},
            step.action_page_result.to_public_value(),
            step.after_world,
        )
        context_id = decision.context_id
        tool_call_id = decision.tool_call_id
    else:
        return None
    return _prohibited_attempt_replay_rejection(
        signal,
        context_id=context_id,
        tool_call_id=tool_call_id,
        operation=operation,
        signature=signature,
    )


def _prohibited_observation_attempt_replay_rejection(
    signal,
    decision: RequestObservation,
    world,
) -> ToolRejectedResult | None:
    if signal is None or not signal.prohibited_attempt_signatures:
        return None
    signature = public_observation_attempt_signature(
        purpose=decision.purpose.value,
        subject_ids=decision.subject_ids,
        candidate_ids=decision.candidate_ids,
        atomic_query=decision.atomic_query,
        predicate=decision.predicate,
        max_results=decision.max_results,
        world=world,
    )
    return _prohibited_attempt_replay_rejection(
        signal,
        context_id=decision.context_id,
        tool_call_id=decision.tool_call_id,
        operation="request_evidence",
        signature=signature,
    )


def _prohibited_attempt_replay_rejection(
    signal,
    *,
    context_id: str,
    tool_call_id: str,
    operation: str,
    signature: PublicAttemptSignature,
) -> ToolRejectedResult | None:
    if signature not in signal.prohibited_attempt_signatures:
        return None
    return ToolRejectedResult(
        context_id,
        operation,
        {
            "operation": operation,
            "attempt_signature": signature.digest,
        },
        {
            "kind": "prohibited_attempt_rejected",
            "failure_kind": "recovery_prohibited_attempt_replay",
            "epoch_id": signal.epoch_id,
            "evidence_revision": signal.evidence_revision,
            "attempted_operation": operation,
            "dispatch": "not_sent",
            "transport_success": False,
            "world_changed": False,
            "must_change": ("attempt",),
        },
        tool_call_id,
        rejected_attempt_signature=signature,
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
