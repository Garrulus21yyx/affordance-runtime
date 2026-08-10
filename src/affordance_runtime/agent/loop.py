"""Observe/select/bind/execute/reobserve/evaluate target AgentLoop."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import affordance_runtime.agent.progress_control as progress_control
from affordance_runtime.agent.control_transition import (
    AdmissionStatus,
    ControlContinuationScope,
    ControlTransitionScope,
)
from affordance_runtime.agent.decision_control import ensure_current_action_page, run_policy_turn
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.evaluation_control import validated_task_evaluation
from affordance_runtime.agent.execution_cycle import execute_cycle
from affordance_runtime.agent.observation_control import capture_for_session
from affordance_runtime.agent.policy import ActionEvaluator, AgentPolicy, TaskEvaluator
from affordance_runtime.agent.result import (
    AgentResult,
    add_counts,
    build_result,
    refresh_control_projection,
)
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.start_error import require_initial_observation
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.confirmation.contracts import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.confirmation.summary import build_confirmation_request
from affordance_runtime.execution.contracts import ActionIntent
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.world.acquisition import (
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.binder import ActionBinder
from affordance_runtime.world.contracts import ActionSpace, AdmittedActionSelection
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.view import build_agent_world_view


@dataclass
class AgentLoop:
    policy: AgentPolicy
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    recent_turn_limit: int = 12

    async def start(
        self,
        task: TaskGoal,
        environment: WorldEnvironment,
        intent_context: IntentContext | None = None,
    ) -> AgentRunSession:
        current = require_initial_observation(await environment.reset(task))
        state = AgentLoopState(
            current, remaining_turns=task.loop_budget.max_turns, recent_turn_limit=self.recent_turn_limit
        )
        return AgentRunSession(self, task, environment, state, intent_context)

    async def run(
        self,
        task: TaskGoal,
        environment: WorldEnvironment,
        intent_context: IntentContext | None = None,
    ) -> AgentResult:
        return await (await self.start(task, environment, intent_context)).run_until_pause()

    async def _run_session(self, session: AgentRunSession) -> AgentResult:
        task, state = session.task, session.state
        while True:
            try:
                current = state.current_task_evaluation
                task_evaluation = (
                    current
                    if current is not None
                    and current.observation_id == state.current_observation.observation_id
                    else await validated_task_evaluation(
                        self.task_evaluator, task, state.current_observation
                    )
                )
            except ValueError as exc:
                result = self._result(
                    session,
                    AgentLoopStatus.FAILED,
                    str(exc),
                    "task_evaluation_invalid",
                )
                return self._close_confirmation(
                    session, result, "task_evaluation_invalid"
                )
            state.current_task_evaluation = task_evaluation
            task_status = task_evaluation_loop_status(task_evaluation)
            if task_status is not None:
                if session.confirmation_continuation_scope is not None:
                    session.confirmation_continuation_scope.record_evaluations(
                        task=task_evaluation
                    )
                result = self._result(
                    session,
                    task_status,
                    task_evaluation.reason,
                    f"task_{task_evaluation.status}",
                )
                return self._close_confirmation(
                    session, result, f"task_{task_evaluation.status}"
                )
            if (
                session.approved_confirmation is None
                and state.remaining_turns <= 0
            ):
                result = self._result(
                    session,
                    AgentLoopStatus.FAILED,
                    "agent loop turn budget exhausted",
                    "turn_budget_exhausted",
                )
                return self._close_confirmation(
                    session, result, "turn_budget_exhausted"
                )
            action_space = self.action_space_builder.build(task, state.current_observation)
            ensure_current_action_page(session, action_space, self.context_builder)
            if session.approved_confirmation is not None:
                outcome = await self._execute_confirmed(session, action_space, task_evaluation)
            else:
                outcome = await run_policy_turn(
                    session,
                    action_space,
                    task_evaluation,
                    self.policy,
                    self.context_builder,
                    self.task_evaluator,
                    self.wait_controller,
                    self._execute_selection,
                )
            applied_result = self._apply_outcome(session, outcome)
            if applied_result is not None:
                return applied_result

    async def _execute_selection(
        self,
        session: AgentRunSession,
        action_space: ActionSpace,
        decision: SelectAction,
        scope: ControlTransitionScope,
    ):
        admitted = self._admit_selection(
            session.task,
            session.state,
            action_space,
            decision,
            scope,
        )
        if isinstance(admitted, AgentResult):
            return admitted
        return (await self._execute_admitted(session, admitted, decision, scope)).routed

    async def _execute_confirmed(self, session: AgentRunSession, action_space: ActionSpace, task_evaluation):
        confirmed = session.approved_confirmation
        assert confirmed is not None
        candidates = []
        for option in action_space.options:
            if option.semantic_action != confirmed.intent.semantic_action or option.target_id != confirmed.intent.target_id:
                continue
            try:
                selection = self.action_space_builder.admit(
                    option,
                    dict(confirmed.intent.parameters),
                    confirmed.intent.destination_id,
                )
            except ValueError:
                continue
            candidates.append((selection, self.risk_policy.assess(session.task, selection)))
        exact = next((item for item in candidates if item[1].subject_id == confirmed.subject_id), None)
        if exact is not None:
            selection = exact[0]
            execution_page = self.context_builder.execution_page(
                action_space,
                session.state,
                selection.action_id,
                selection.destination_id,
            )
            session.current_action_space = action_space
            session.current_action_page = execution_page
            context = self.context_builder.build(
                session.task,
                session.state,
                action_space,
                task_evaluation,
                session.intent_context,
                execution_page,
                observation_count=session.observation_count,
                waited_ms=session.waited_ms,
                context_generation=session.next_context_generation(),
                observation_capabilities=session.environment.observation_capabilities,
            )
            session.current_context_snapshot = context
            session.consumed_context_id = context.context_id
            decision = SelectAction(
                context.context_id,
                selection.action_id,
                dict(selection.parameters),
                selection.destination_id,
            )
            scope = session.confirmation_continuation_scope
            assert scope is not None
            admitted_outcome = await self._execute_admitted(
                session, selection, decision, scope
            )
            outcome = admitted_outcome.routed
            if (
                admitted_outcome.disposition
                is progress_control.SelectionProgressDisposition.ALREADY_SATISFIED
            ):
                scope.record_evaluations(task=task_evaluation)
                return self._close_confirmation(
                    session, outcome, "already_satisfied"
                )
            if scope.has_effectful_execution or _terminal_from_outcome(outcome) is not None:
                return self._close_confirmation(
                    session,
                    outcome,
                    scope.reason_code,
                )
            return outcome
        self._close_confirmation(
            session,
            None,
            "confirmation_subject_unavailable",
        )
        return None

    async def _execute_admitted(
        self,
        session: AgentRunSession,
        selection: AdmittedActionSelection,
        decision: SelectAction,
        scope: ControlTransitionScope | ControlContinuationScope,
    ):
        progress = progress_control.apply_selection_progress(session, selection)
        if progress.disposition != progress_control.SelectionProgressDisposition.EXECUTE:
            scope.set_reason(
                "already_satisfied"
                if progress.disposition
                is progress_control.SelectionProgressDisposition.ALREADY_SATISFIED
                else "no_progress_repetition"
            )
            return _AdmittedOutcome(progress.terminal_result, progress.disposition)
        routed = await execute_cycle(
            session,
            selection,
            decision,
            self.binder,
            self.action_evaluator,
            self.task_evaluator,
            scope,
        )
        return _AdmittedOutcome(routed, progress.disposition)

    def _admit_selection(
        self,
        task: TaskGoal,
        state: AgentLoopState,
        action_space: ActionSpace,
        decision: SelectAction,
        scope: ControlTransitionScope,
    ) -> AdmittedActionSelection | AgentResult:
        option = action_space.find(decision.action_id)
        if option is None:
            scope.record_admission(AdmissionStatus.REJECTED, "action_outside_action_space")
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "policy selected outside ActionSpace")
        try:
            selection = self.action_space_builder.admit(
                option,
                dict(decision.parameters),
                decision.destination_id,
            )
        except ValueError as exc:
            scope.record_admission(AdmissionStatus.REJECTED, "invalid_action_parameters")
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, str(exc))
        assessment = self.risk_policy.assess(task, selection)
        if assessment.decision == RiskDecisionKind.BLOCK:
            scope.record_admission(AdmissionStatus.REJECTED, "risk_blocked")
            return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, assessment.reason)
        if assessment.decision == RiskDecisionKind.NEEDS_CONFIRMATION:
            scope.record_admission(
                AdmissionStatus.CONFIRMATION_REQUIRED,
                "confirmation_required",
            )
            intent = ActionIntent(
                selection.semantic_action,
                selection.target_id,
                dict(selection.parameters),
                selection.destination_id,
            )
            state.set_pending_confirmation(build_confirmation_request(
                intent,
                assessment,
                build_agent_world_view(state.current_observation),
            ))
            return build_result(AgentLoopStatus.WAITING_CONFIRMATION, task, state, 0, 0, assessment.reason)
        scope.record_admission(AdmissionStatus.ADMITTED, "action_admitted")
        return selection

    async def _resolve_confirmation(
        self,
        session: AgentRunSession,
        decision: ConfirmationDecision,
    ) -> AgentResult:
        pending = session.state.pending_confirmation
        if session.is_terminal or pending is None or decision.confirmation_id in session.resolved_confirmation_ids:
            return self._result(
                session,
                AgentLoopStatus.WAITING_CONFIRMATION,
                "confirmation decision is stale or already resolved",
                "invalid_confirmation_decision",
            )
        if not decision.matches(pending):
            return self._result(
                session,
                AgentLoopStatus.WAITING_CONFIRMATION,
                "confirmation decision identity mismatch",
                "invalid_confirmation_decision",
            )
        session.resolved_confirmation_ids.add(decision.confirmation_id)
        source_transition_id = session.state.pending_confirmation_transition_id
        root = next(
            item
            for item in session.state.recent_control_transitions
            if item.transition_id == source_transition_id
        )
        scope = ControlContinuationScope(
            session.state, root.decision, source_transition_id
        )
        session.confirmation_continuation_scope = scope
        session.state.clear_pending_confirmation()
        try:
            return await self._continue_confirmation(
                session, decision, pending, source_transition_id, scope
            )
        except asyncio.CancelledError as exc:
            self._close_confirmation_exception(session, exc)
            raise
        except Exception as exc:
            self._close_confirmation_exception(session, exc)
            raise

    async def _continue_confirmation(
        self, session, decision, pending, source_transition_id, scope
    ) -> AgentResult:
        if decision.decision == ConfirmationDecisionKind.DENY:
            session.approved_confirmation = None
            result = self._result(
                session,
                AgentLoopStatus.CANCELLED,
                "user denied the semantic action",
                "confirmation_denied",
            )
            return self._close_confirmation(session, result, "confirmation_denied")
        if session.observation_count >= session.task.loop_budget.max_observations:
            result = self._result(
                session,
                AgentLoopStatus.FAILED,
                "agent loop observation budget exhausted",
                "observation_budget_exhausted",
            )
            return self._close_confirmation(
                session, result, "observation_budget_exhausted"
            )
        session.approved_confirmation = pending
        session.approved_confirmation_transition_id = source_transition_id
        previous_id = session.state.current_observation.observation_id
        acquired = await capture_for_session(
            session,
            previous_id,
            WorldObservationRequest(
                ObservationRequestKind.CONFIRMATION_REFRESH,
                "fresh observation after confirmation",
            ),
            scope,
        )
        if acquired.observation is None:
            result = build_result(
                AgentLoopStatus.FAILED,
                session.task,
                session.state,
                session.observation_count,
                session.execution_count,
                acquired.reason_code,
                session.currentness_probe_count,
                failure_code=acquired.failure_code,
                reason_code=acquired.reason_code,
            )
            return self._close_confirmation(session, result, acquired.reason_code)
        session.state.current_observation = acquired.observation
        session.state.current_task_evaluation = None
        scope.record_after(acquired.observation.observation_id)
        session.last_result = None
        return await self._run_session(session)

    def _apply_outcome(self, session: AgentRunSession, outcome) -> AgentResult | None:
        if outcome is None:
            return None
        if isinstance(outcome, AgentResult):
            return add_counts(
                outcome,
                session.observation_count + outcome.observation_count,
                session.execution_count + outcome.execution_count,
                session.currentness_probe_count + outcome.currentness_probe_count,
            )
        _, observed, executed, probed, terminal = outcome
        session.observation_count += observed
        session.execution_count += executed
        session.currentness_probe_count += probed
        if executed:
            session.approved_confirmation = None
            session.approved_confirmation_transition_id = ""
        if terminal is not None:
            return add_counts(
                terminal,
                session.observation_count,
                session.execution_count,
                session.currentness_probe_count,
            )
        return None

    def _close_confirmation(self, session, outcome, reason_code):
        scope = session.confirmation_continuation_scope
        if scope is None:
            return outcome
        scope.set_reason(reason_code)
        continuation = scope.finalize(session.state, outcome)
        session.approved_confirmation = None
        session.approved_confirmation_transition_id = ""
        session.confirmation_continuation_scope = None
        return self._refresh_continuation_outcome(
            outcome, session.state, continuation.reason_code
        )

    def _close_confirmation_exception(self, session, exc: Exception | asyncio.CancelledError) -> None:
        scope = session.confirmation_continuation_scope
        if scope is None:
            return
        cancelled = isinstance(exc, asyncio.CancelledError)
        scope.set_reason("runtime_cancelled" if cancelled else "runtime_exception")
        scope.set_resulting_status(
            AgentLoopStatus.CANCELLED if cancelled else AgentLoopStatus.FAILED
        )
        scope.finalize(session.state, None)
        session.approved_confirmation = None
        session.approved_confirmation_transition_id = ""
        session.confirmation_continuation_scope = None

    @staticmethod
    def _result(
        session: AgentRunSession,
        status: AgentLoopStatus,
        message: str,
        reason_code: str = "",
    ) -> AgentResult:
        return build_result(
            status,
            session.task,
            session.state,
            session.observation_count,
            session.execution_count,
            message,
            session.currentness_probe_count,
            reason_code=reason_code,
        )

    @staticmethod
    def _refresh_continuation_outcome(outcome, state, reason_code):
        if isinstance(outcome, AgentResult):
            return refresh_control_projection(outcome, state, reason_code)
        if isinstance(outcome, tuple) and outcome and isinstance(outcome[-1], AgentResult):
            return (*outcome[:-1], refresh_control_projection(outcome[-1], state, reason_code))
        return outcome


def _terminal_from_outcome(outcome):
    if isinstance(outcome, AgentResult):
        return outcome
    if isinstance(outcome, tuple) and outcome:
        return outcome[-1]
    return None


@dataclass(frozen=True)
class _AdmittedOutcome:
    routed: object
    disposition: progress_control.SelectionProgressDisposition
