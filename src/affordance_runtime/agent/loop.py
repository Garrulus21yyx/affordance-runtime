"""Observe/select/bind/execute/reobserve/evaluate target AgentLoop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TypeVar

import affordance_runtime.agent.progress_control as progress_control
from affordance_runtime.actions.action_space import ActionSpaceBuilder
from affordance_runtime.actions.binder import ActionBinder
from affordance_runtime.actions.space_contracts import (
    ActionSpace,
    AdmittedActionSelection,
)
from affordance_runtime.agent.accounting import RunAccounting
from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
    safe_exception_class,
)
from affordance_runtime.agent.context.context_builder import ContextBuilder
from affordance_runtime.agent.control_outcome import (
    Continue,
    LoopDirective,
    Pause,
    Terminate,
    directive,
)
from affordance_runtime.agent.control_transition import (
    AdmissionStatus,
    ControlContinuationScope,
    ControlTransitionScope,
)
from affordance_runtime.agent.decision_control import (
    ensure_current_action_page,
    run_policy_turn,
)
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.evaluation_control import validated_task_evaluation
from affordance_runtime.agent.execution_cycle import execute_cycle
from affordance_runtime.agent.observation_control import capture_for_session
from affordance_runtime.agent.policy import ActionEvaluator, AgentDecisionPorts, AgentPolicy, TaskEvaluator
from affordance_runtime.agent.result import AgentResult, project_result
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.start_error import (
    AgentSessionStartCancelledError,
    AgentSessionStartError,
    StartBoundaryEvidence,
    require_initial_observation,
)
from affordance_runtime.agent.state import AgentLoopState, AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_disposition_for_world
from affordance_runtime.agent.waiting import SystemWaitController, WaitController
from affordance_runtime.confirmation.contracts import ConfirmationDecision, ConfirmationDecisionKind
from affordance_runtime.confirmation.summary import build_confirmation_request
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus
from affordance_runtime.execution.contracts import ActionIntent
from affordance_runtime.risk.contracts import RiskDecisionKind
from affordance_runtime.risk.policy import RiskPolicy
from affordance_runtime.risk.validation import validate_risk_assessment
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intent_context import IntentContext
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ObservationAcquisition,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.view import build_agent_world_view

_DirectiveT = TypeVar("_DirectiveT", bound=LoopDirective)


@dataclass
class AgentLoop:
    decision_ports: AgentDecisionPorts | AgentPolicy
    action_evaluator: ActionEvaluator
    task_evaluator: TaskEvaluator
    action_space_builder: ActionSpaceBuilder = field(default_factory=ActionSpaceBuilder)
    binder: ActionBinder = field(default_factory=ActionBinder)
    risk_policy: RiskPolicy = field(default_factory=RiskPolicy)
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)
    wait_controller: WaitController = field(default_factory=SystemWaitController)
    recent_turn_limit: int = 12

    def __post_init__(self) -> None:
        if not isinstance(self.decision_ports, AgentDecisionPorts):
            self.decision_ports = AgentDecisionPorts(self.decision_ports)

    @property
    def _ports(self) -> AgentDecisionPorts:
        if not isinstance(self.decision_ports, AgentDecisionPorts):
            raise TypeError("AgentLoop decision ports were not normalized")
        return self.decision_ports

    async def start(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> AgentRunSession:
        accounting = RunAccounting()
        attempt_id = accounting.next_attempt_id()
        try:
            acquisition = await environment.reset(task)
        except asyncio.CancelledError as exc:
            receipt = _reset_exception_receipt(
                attempt_id,
                AttemptDisposition.CANCELLED,
                "reset_cancelled",
                "CancelledError",
            )
            accounting.record(receipt)
            raise AgentSessionStartCancelledError(StartBoundaryEvidence(receipt, accounting.snapshot())) from exc
        except Exception as exc:
            exception_class = safe_exception_class(exc)
            receipt = _reset_exception_receipt(
                attempt_id,
                AttemptDisposition.THREW,
                "reset_exception",
                exception_class,
            )
            accounting.record(receipt)
            raise AgentSessionStartError(
                AcquisitionStatus.FAILED,
                AcquisitionOrigin.RESET,
                "reset_exception",
                StartBoundaryEvidence(receipt, accounting.snapshot()),
                exception_class,
            ) from exc
        if not isinstance(acquisition, ObservationAcquisition):
            receipt = _reset_exception_receipt(
                attempt_id,
                AttemptDisposition.MALFORMED,
                "reset_malformed",
                "",
            )
            accounting.record(receipt)
            raise AgentSessionStartError(
                AcquisitionStatus.FAILED,
                AcquisitionOrigin.RESET,
                "reset_malformed",
                StartBoundaryEvidence(receipt, accounting.snapshot()),
                "TypeError",
            )
        receipt = AttemptReceipt(
            attempt_id,
            AttemptOperation.RESET,
            "reset",
            AcquisitionOrigin.RESET,
            acquisition.origin,
            AttemptDisposition.RETURNED,
            acquisition.reason_code,
            1,
            0,
            0,
            0,
            acquisition_status=acquisition.status,
        )
        accounting.record(receipt)
        evidence = StartBoundaryEvidence(receipt, accounting.snapshot())
        current = require_initial_observation(acquisition, evidence)
        state = AgentLoopState(
            current,
            task_revision=task.revision,
            remaining_turns=task.loop_budget.max_turns,
            recent_turn_limit=self.recent_turn_limit,
        )
        session = AgentRunSession(
            self,
            task,
            environment,
            state,
            intent_context,
            accounting,
        )
        return session

    async def run(
        self,
        environment: WorldEnvironment,
        task: TaskGoal,
        intent_context: IntentContext | None = None,
    ) -> AgentResult:
        return await (await self.start(environment, task, intent_context)).run_until_pause()

    async def _run_session(self, session: AgentRunSession) -> AgentResult:
        return project_result(session, await self._run_control(session))

    async def _run_control(self, session: AgentRunSession) -> Pause | Terminate:
        task, state = session.task, session.state
        while True:
            outcome: LoopDirective
            try:
                current = state.current_task_evaluation
                task_evaluation = (
                    current
                    if current is not None and current.observation_id == state.current_observation.observation_id
                    else await validated_task_evaluation(self.task_evaluator, task, state.current_observation)
                )
            except ValueError as exc:
                outcome = Terminate(
                    AgentLoopStatus.FAILED,
                    "task_evaluation_invalid",
                    str(exc),
                    failure_stage=FailureStage.EVALUATION,
                    failure_kind=FailureKind.INVALID_OUTPUT,
                )
                return self._close_confirmation(session, outcome, "task_evaluation_invalid")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                session.pending_runtime_failure = RuntimeFailure(
                    FailureStage.EVALUATION,
                    FailureKind.CALL_FAILED,
                    "task_evaluation_call_failed",
                    exception_class=safe_exception_class(exc),
                )
                raise
            state.current_task_evaluation = task_evaluation
            if (
                state.unresolved_observable_request is not None
                and task_evaluation.status is not TaskEvaluationStatus.UNKNOWN
            ):
                state.clear_unknown_effect_observation()
            if session.confirmation_continuation_scope is not None:
                session.confirmation_continuation_scope.record_evaluations(task=task_evaluation)
            task_disposition = task_evaluation_disposition_for_world(
                task,
                task_evaluation,
                state.current_observation,
                session.environment.observation_capabilities,
            )
            if task_disposition.status is not None:
                task_outcome = directive(
                    task_disposition.status,
                    task_disposition.reason_code,
                    task_evaluation.reason,
                    task_terminal=task_disposition.task_terminal,
                )
                assert not isinstance(task_outcome, Continue)
                return self._close_confirmation(session, task_outcome, task_disposition.reason_code)
            if session.approved_confirmation is None and state.remaining_turns <= 0:
                outcome = Terminate(
                    AgentLoopStatus.FAILED,
                    "turn_budget_exhausted",
                    "agent loop turn budget exhausted",
                )
                return self._close_confirmation(session, outcome, "turn_budget_exhausted")
            action_space = self.action_space_builder.build(task, state.current_observation)
            ensure_current_action_page(session, action_space, self.context_builder)
            from affordance_runtime.agent.control_feedback import current_semantic_scope
            from affordance_runtime.world.public_semantic_digest import (
                public_action_page_result_digest,
            )

            assert session.current_action_page is not None
            state.begin_control_epoch(
                current_semantic_scope(state, action_space),
                public_action_page_result_digest(
                    state.current_observation,
                    action_space,
                    session.current_action_page,
                ),
            )
            if session.approved_confirmation is not None:
                outcome = await self._execute_confirmed(session, action_space, task_evaluation)
            else:
                outcome = await run_policy_turn(
                    session,
                    action_space,
                    task_evaluation,
                    self._ports.action_policy,
                    self.context_builder,
                    self.task_evaluator,
                    self.wait_controller,
                    self._execute_selection,
                    self.action_space_builder,
                )
            scope = session.confirmation_continuation_scope
            if scope is not None and (scope.has_effectful_execution or not isinstance(outcome, Continue)):
                outcome = self._close_confirmation(session, outcome, scope.reason_code)
            if isinstance(outcome, Continue):
                continue
            return outcome

    async def _execute_selection(
        self,
        session: AgentRunSession,
        action_space: ActionSpace,
        decision: SelectAction,
        scope: ControlTransitionScope,
    ) -> LoopDirective:
        admitted = self._admit_selection(
            session,
            action_space,
            decision,
            scope,
        )
        if isinstance(admitted, Continue | Pause | Terminate):
            return admitted
        return (await self._execute_admitted(session, admitted, decision, scope)).routed

    async def _execute_confirmed(
        self,
        session: AgentRunSession,
        action_space: ActionSpace,
        task_evaluation,
    ) -> LoopDirective:
        confirmed = session.approved_confirmation
        assert confirmed is not None
        candidates = []
        for option in action_space.options:
            if (
                option.semantic_action != confirmed.intent.semantic_action
                or option.target_id != confirmed.intent.target_id
            ):
                continue
            try:
                selection = self.action_space_builder.admit(
                    option,
                    dict(confirmed.intent.parameters),
                    confirmed.intent.destination_id,
                )
            except (TypeError, ValueError):
                continue
            try:
                assessment = validate_risk_assessment(
                    session.task,
                    selection,
                    self.risk_policy.assess(session.task, selection),
                )
            except (TypeError, ValueError):
                return self._close_confirmation(
                    session,
                    Terminate(
                        AgentLoopStatus.BLOCKED,
                        "risk_assessment_invalid",
                        "fresh risk assessment is invalid",
                    ),
                    "risk_assessment_invalid",
                )
            candidates.append((selection, assessment))
        exact = next(
            (
                item
                for item in candidates
                if item[1].subject == confirmed.subject and item[1].subject_id == confirmed.subject_id
            ),
            None,
        )
        if exact is not None:
            selection, assessment = exact
            if assessment.decision is RiskDecisionKind.BLOCK:
                outcome = Terminate(
                    AgentLoopStatus.BLOCKED,
                    "risk_blocked_after_confirmation",
                    assessment.reason,
                )
                return self._close_confirmation(session, outcome, "risk_blocked_after_confirmation")
            if assessment.decision not in {
                RiskDecisionKind.ALLOW,
                RiskDecisionKind.NEEDS_CONFIRMATION,
            }:
                outcome = Terminate(
                    AgentLoopStatus.BLOCKED,
                    "risk_invalid_after_confirmation",
                    "fresh risk decision is invalid",
                )
                return self._close_confirmation(session, outcome, "risk_invalid_after_confirmation")
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
            scope.record_continuation_decision(decision)
            scope.record_admission(
                AdmissionStatus.CONFIRMED,
                "confirmation_revalidated",
                selection=selection,
                risk_assessment=assessment,
                confirmation_request=confirmed,
            )
            admitted_outcome = await self._execute_admitted(session, selection, decision, scope)
            routed = admitted_outcome.routed
            if admitted_outcome.disposition is progress_control.SelectionProgressDisposition.ALREADY_SATISFIED:
                scope.record_evaluations(task=task_evaluation)
                return self._close_confirmation(session, routed, "already_satisfied")
            return routed
        self._close_confirmation(
            session,
            Continue("confirmation_subject_unavailable"),
            "confirmation_subject_unavailable",
        )
        return Continue("confirmation_subject_unavailable")

    async def _execute_admitted(
        self,
        session: AgentRunSession,
        selection: AdmittedActionSelection,
        decision: SelectAction,
        scope: ControlTransitionScope | ControlContinuationScope,
    ) -> _AdmittedOutcome:
        progress = progress_control.apply_selection_progress(session, selection)
        if progress.disposition != progress_control.SelectionProgressDisposition.EXECUTE:
            scope.set_reason(
                "already_satisfied"
                if progress.disposition is progress_control.SelectionProgressDisposition.ALREADY_SATISFIED
                else "no_progress_repetition"
            )
            assert progress.terminal_result is not None
            if progress.disposition is progress_control.SelectionProgressDisposition.ALREADY_SATISFIED:
                from affordance_runtime.agent.control_feedback import (
                    ControlFeedbackSource,
                    route_feedback,
                    strategy_feedback,
                )

                action_space = session.current_action_space
                page = session.current_action_page
                assert action_space is not None and page is not None
                feedback = strategy_feedback(
                    session.state,
                    action_space,
                    page,
                    source=ControlFeedbackSource.PROGRESS_EVENT,
                    code="already_satisfied_change_strategy",
                    public_subject_id=selection.target_id,
                )
                return _AdmittedOutcome(
                    route_feedback(session.state, scope, feedback),
                    progress.disposition,
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
        session: AgentRunSession,
        action_space: ActionSpace,
        decision: SelectAction,
        scope: ControlTransitionScope,
    ) -> AdmittedActionSelection | Continue | Pause | Terminate:
        task = session.task
        state = session.state
        page = session.current_action_page or self.context_builder.page(action_space, state)
        option = action_space.find(decision.action_id)
        admission = self.action_space_builder.try_admit_selection(
            action_space,
            decision.action_id,
            dict(decision.parameters),
            decision.destination_id,
        )
        if admission.issue is not None:
            from affordance_runtime.agent.control_feedback import repair_feedback, route_feedback

            issue = admission.issue
            scope.record_admission(AdmissionStatus.REJECTED, issue.code.value, issue=issue)
            feedback = repair_feedback(
                state,
                action_space,
                page,
                decision=decision,
                issue=issue,
                public_subject_id=option.target_id if option is not None else None,
            )
            return route_feedback(state, scope, feedback)
        assert admission.admitted is not None
        selection = admission.admitted
        try:
            assessment = validate_risk_assessment(
                task,
                selection,
                self.risk_policy.assess(task, selection),
            )
        except (TypeError, ValueError):
            scope.record_admission(
                AdmissionStatus.REJECTED,
                "risk_assessment_invalid",
                selection=selection,
            )
            return Terminate(
                AgentLoopStatus.BLOCKED,
                "risk_assessment_invalid",
                "risk assessment is invalid",
            )
        if assessment.decision is RiskDecisionKind.BLOCK:
            scope.record_admission(
                AdmissionStatus.REJECTED,
                "risk_blocked",
                selection=selection,
                risk_assessment=assessment,
            )
            return Terminate(AgentLoopStatus.BLOCKED, "risk_blocked", assessment.reason)
        if assessment.decision is RiskDecisionKind.NEEDS_CONFIRMATION:
            intent = ActionIntent(
                selection.semantic_action,
                selection.target_id,
                dict(selection.parameters),
                selection.destination_id,
            )
            confirmation = build_confirmation_request(
                intent,
                assessment,
                build_agent_world_view(state.current_observation),
            )
            scope.record_admission(
                AdmissionStatus.CONFIRMATION_REQUIRED,
                "confirmation_required",
                selection=selection,
                risk_assessment=assessment,
                confirmation_request=confirmation,
            )
            state.set_pending_confirmation(confirmation)
            return Pause(AgentLoopStatus.WAITING_CONFIRMATION, "confirmation_required", assessment.reason)
        if assessment.decision is RiskDecisionKind.ALLOW:
            scope.record_admission(
                AdmissionStatus.ADMITTED,
                "action_admitted",
                selection=selection,
                risk_assessment=assessment,
            )
            return selection
        scope.record_admission(
            AdmissionStatus.REJECTED,
            "risk_decision_invalid",
            selection=selection,
            risk_assessment=assessment,
        )
        return Terminate(
            AgentLoopStatus.BLOCKED,
            "risk_decision_invalid",
            "risk decision is invalid",
        )

    async def _resolve_confirmation(
        self,
        session: AgentRunSession,
        decision: ConfirmationDecision,
    ) -> AgentResult:
        pending = session.state.pending_confirmation
        if session.is_terminal:
            assert session.last_result is not None
            return session.last_result
        if pending is None:
            return project_result(
                session,
                Terminate(
                    AgentLoopStatus.BLOCKED,
                    "invalid_confirmation_decision",
                    "no confirmation is pending",
                ),
            )
        if not isinstance(decision.decision, ConfirmationDecisionKind):
            return project_result(
                session,
                Pause(
                    AgentLoopStatus.WAITING_CONFIRMATION,
                    "invalid_confirmation_decision",
                    "confirmation decision kind is invalid",
                ),
            )
        if decision.confirmation_id in session.resolved_confirmation_ids:
            return project_result(
                session,
                Pause(
                    AgentLoopStatus.WAITING_CONFIRMATION,
                    "invalid_confirmation_decision",
                    "confirmation decision is stale or already resolved",
                ),
            )
        if not decision.matches(pending):
            return project_result(
                session,
                Pause(
                    AgentLoopStatus.WAITING_CONFIRMATION,
                    "invalid_confirmation_decision",
                    "confirmation decision identity mismatch",
                ),
            )
        session.resolved_confirmation_ids.add(decision.confirmation_id)
        source_transition_id = session.state.pending_confirmation_transition_id
        root = next(
            item for item in session.state.recent_control_transitions if item.transition_id == source_transition_id
        )
        scope = ControlContinuationScope(session.state, root.decision, source_transition_id)
        session.confirmation_continuation_scope = scope
        session.state.clear_pending_confirmation()
        try:
            outcome = await self._continue_confirmation(session, decision, pending, source_transition_id, scope)
            return project_result(session, outcome)
        except asyncio.CancelledError as exc:
            self._close_confirmation_exception(session, exc)
            raise
        except Exception as exc:
            self._close_confirmation_exception(session, exc)
            raise

    async def _continue_confirmation(
        self, session, decision, pending, source_transition_id, scope
    ) -> Pause | Terminate:
        if decision.decision == ConfirmationDecisionKind.DENY:
            session.approved_confirmation = None
            outcome = Terminate(
                AgentLoopStatus.CANCELLED,
                "confirmation_denied",
                "user denied the semantic action",
            )
            return self._close_confirmation(session, outcome, "confirmation_denied")
        if session.observation_count >= session.task.loop_budget.max_observations:
            outcome = Terminate(
                AgentLoopStatus.FAILED,
                "observation_budget_exhausted",
                "agent loop observation budget exhausted",
            )
            return self._close_confirmation(session, outcome, "observation_budget_exhausted")
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
            outcome = Terminate(
                AgentLoopStatus.FAILED,
                acquired.reason_code,
                acquired.reason_code,
                failure_code=acquired.failure_code,
            )
            return self._close_confirmation(session, outcome, acquired.reason_code)
        session.state.install_observation(acquired.observation)
        scope.record_after(acquired.observation)
        session.last_result = None
        return await self._run_control(session)

    def _close_confirmation(
        self,
        session: AgentRunSession,
        outcome: _DirectiveT,
        reason_code: str,
    ) -> _DirectiveT:
        scope = session.confirmation_continuation_scope
        if scope is None:
            return outcome
        scope.set_reason(reason_code)
        continuation = scope.finalize(session.state, outcome)
        session.approved_confirmation = None
        session.approved_confirmation_transition_id = ""
        session.confirmation_continuation_scope = None
        del continuation
        return outcome

    def _close_confirmation_exception(self, session, exc: Exception | asyncio.CancelledError) -> None:
        scope = session.confirmation_continuation_scope
        if scope is None:
            return
        cancelled = isinstance(exc, asyncio.CancelledError)
        scope.set_reason("runtime_cancelled" if cancelled else "runtime_exception")
        scope.set_resulting_status(AgentLoopStatus.CANCELLED if cancelled else AgentLoopStatus.FAILED)
        outcome = Terminate(
            AgentLoopStatus.CANCELLED if cancelled else AgentLoopStatus.FAILED,
            "runtime_cancelled" if cancelled else "runtime_exception",
        )
        scope.finalize(session.state, outcome)
        session.approved_confirmation = None
        session.approved_confirmation_transition_id = ""
        session.confirmation_continuation_scope = None


@dataclass(frozen=True)
class _AdmittedOutcome:
    routed: LoopDirective
    disposition: progress_control.SelectionProgressDisposition


def _reset_exception_receipt(
    attempt_id: str,
    disposition: AttemptDisposition,
    reason_code: str,
    exception_class: str,
) -> AttemptReceipt:
    return AttemptReceipt(
        attempt_id,
        AttemptOperation.RESET,
        "reset",
        AcquisitionOrigin.RESET,
        None,
        disposition,
        reason_code,
        1,
        0,
        0,
        0,
        exception_class=exception_class,
    )
