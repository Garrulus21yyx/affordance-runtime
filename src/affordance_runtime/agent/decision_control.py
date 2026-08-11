"""One-shot typed decision admission and surface-neutral routing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from affordance_runtime.agent.attempt_receipt import safe_exception_class
from affordance_runtime.agent.control_feedback import (
    ControlFeedbackSource,
    no_gain_feedback,
    repair_feedback,
    route_feedback,
)
from affordance_runtime.agent.control_outcome import (
    Continue,
    LoopDirective,
    Pause,
    Terminate,
    directive,
)
from affordance_runtime.agent.control_transition import (
    AdmissionStatus,
    ControlTransitionScope,
)
from affordance_runtime.agent.decisions import (
    Abort,
    AgentDecision,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)
from affordance_runtime.agent.evaluation_control import validated_task_evaluation
from affordance_runtime.agent.observation_control import (
    capture_admission_failure,
    capture_for_session,
)
from affordance_runtime.agent.policy import AgentPolicy, PolicyFailure, TaskEvaluator
from affordance_runtime.agent.runtime_failure import FailureKind, FailureStage, RuntimeFailure
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_disposition
from affordance_runtime.agent.waiting import MAX_TOTAL_WAIT_MS, WaitController
from affordance_runtime.evaluation.contracts import TaskEvaluation
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.model_boundary.context_builder import ContextBuilder
from affordance_runtime.task.contracts import criterion_id
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.contracts import ActionSpace
from affordance_runtime.world.public_semantic_digest import (
    action_page_request_digest,
    observation_request_digest,
    policy_observation_result_digest,
    public_action_page_digest,
)

SelectionExecutor = Callable[
    [AgentRunSession, ActionSpace, SelectAction, ControlTransitionScope],
    Awaitable[LoopDirective],
]

_DECISION_TYPES = (
    Abort,
    AskUser,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)


def accept_current_decision(session: AgentRunSession, decision: AgentDecision) -> bool:
    context = session.current_context_snapshot
    if (
        context is None
        or not isinstance(decision, _DECISION_TYPES)
        or decision.context_id != context.context_id
    ):
        return False
    if session.consumed_context_id == context.context_id:
        return False
    session.consumed_context_id = context.context_id
    return True


async def run_policy_turn(
    session: AgentRunSession,
    action_space: ActionSpace,
    task_evaluation: TaskEvaluation,
    policy: AgentPolicy,
    context_builder: ContextBuilder,
    task_evaluator: TaskEvaluator,
    waiter: WaitController,
    execute_selection: SelectionExecutor,
    action_space_builder: ActionSpaceBuilder,
) -> LoopDirective:
    task, state = session.task, session.state
    context = context_builder.build(
        task,
        state,
        action_space,
        task_evaluation,
        session.intent_context,
        session.current_action_page,
        observation_count=session.observation_count,
        waited_ms=session.waited_ms,
        context_generation=session.next_context_generation(),
        observation_capabilities=session.environment.observation_capabilities,
    )
    session.current_context_snapshot = context
    state.consume_control_feedback_for_policy()
    try:
        outcome = await policy.decide(context)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.POLICY,
            FailureKind.CALL_FAILED,
            "policy_call_failed",
            exception_class=safe_exception_class(exc),
        )
        raise
    state.remaining_turns -= 1
    if isinstance(outcome, PolicyFailure):
        return Terminate(
            AgentLoopStatus.FAILED,
            f"policy_{outcome.kind}",
            outcome.reason,
            policy_failure=outcome,
        )
    decision = outcome
    if not accept_current_decision(session, decision):
        return Continue("stale_decision")
    scope = ControlTransitionScope(state, decision)
    try:
        routed = await _route_decision(
            session,
            action_space,
            decision,
            context_builder,
            task_evaluator,
            waiter,
            execute_selection,
            scope,
            action_space_builder,
            task_evaluation,
        )
    except asyncio.CancelledError:
        scope.set_reason("runtime_cancelled")
        scope.set_resulting_status(AgentLoopStatus.CANCELLED)
        scope.finalize(state, Terminate(AgentLoopStatus.CANCELLED, "runtime_cancelled"))
        raise
    except Exception:
        scope.set_reason("runtime_exception")
        scope.set_resulting_status(AgentLoopStatus.FAILED)
        scope.finalize(state, Terminate(AgentLoopStatus.FAILED, "runtime_exception"))
        raise
    scope.finalize(state, routed)
    return routed


async def _route_decision(
    session,
    action_space,
    decision,
    context_builder,
    task_evaluator,
    waiter,
    execute_selection,
    scope,
    action_space_builder,
    task_evaluation,
) -> LoopDirective:
    state = session.state
    if isinstance(decision, AskUser):
        scope.set_reason("user_input_requested")
        state.set_pending_question(decision.question)
        return Pause(AgentLoopStatus.WAITING_USER, "user_input_requested", decision.question)
    if isinstance(decision, Abort):
        scope.set_reason(f"abort_{decision.category}")
        return Terminate(AgentLoopStatus.FAILED, f"abort_{decision.category}", decision.reason)
    if isinstance(decision, ProposeDone):
        return await _propose_done(session, decision, task_evaluator, scope)
    if isinstance(decision, RequestObservation):
        return await _policy_observation(
            session,
            action_space,
            decision,
            scope,
            context_builder,
            task_evaluator,
            action_space_builder,
            task_evaluation,
        )
    if isinstance(decision, Wait):
        return await _wait_refresh(session, decision, waiter, scope)
    if isinstance(decision, RequestActionPage):
        return _request_action_page(session, action_space, context_builder, decision, scope)
    page = session.current_action_page or context_builder.page(action_space, state)
    issue = page.selection_issue(decision.action_id, decision.destination_id)
    if issue is not None:
        scope.record_admission(AdmissionStatus.REJECTED, issue.code.value)
        feedback = repair_feedback(
            state,
            action_space,
            page,
            code=issue.code.value,
            public_field_paths=issue.public_field_paths,
        )
        return route_feedback(state, scope, feedback)
    return await execute_selection(session, action_space, decision, scope)


async def _policy_observation(
    session: AgentRunSession,
    action_space: ActionSpace,
    decision: RequestObservation,
    scope: ControlTransitionScope,
    context_builder: ContextBuilder,
    task_evaluator: TaskEvaluator,
    action_space_builder: ActionSpaceBuilder,
    prior_task_evaluation: TaskEvaluation,
):
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        decision.reason,
        decision.subject_id,
        decision.modality,
        decision.required_assurance,
    )
    state = session.state
    previous_page = session.current_action_page or context_builder.page(action_space, state)
    request_digest = observation_request_digest(
        state.current_observation,
        subject_id=decision.subject_id,
        modality=decision.modality,
        required_assurance=decision.required_assurance,
    )
    before_result = policy_observation_result_digest(
        state.current_observation,
        action_space,
        previous_page,
        prior_task_evaluation,
    )
    acquired = await _fresh_observation(session, decision, request, scope)
    if not isinstance(acquired, Continue):
        return acquired
    try:
        evaluation = await validated_task_evaluation(
            task_evaluator, session.task, state.current_observation,
        )
    except asyncio.CancelledError:
        raise
    except ValueError as exc:
        scope.set_reason("task_evaluation_invalid")
        return Terminate(
            AgentLoopStatus.FAILED,
            "task_evaluation_invalid",
            str(exc),
            failure_stage=FailureStage.EVALUATION,
            failure_kind=FailureKind.INVALID_OUTPUT,
        )
    state.current_task_evaluation = evaluation
    scope.record_evaluations(task=evaluation)
    disposition = task_evaluation_disposition(evaluation)
    if disposition.status is not None:
        return directive(
            disposition.status,
            disposition.reason_code,
            evaluation.reason,
            task_terminal=disposition.task_terminal,
        )
    new_space = action_space_builder.build(session.task, state.current_observation)
    new_page = context_builder.page(new_space, state)
    session.current_action_space = new_space
    session.current_action_page = new_page
    after_result = policy_observation_result_digest(
        state.current_observation, new_space, new_page, evaluation,
    )
    if after_result != before_result:
        state.clear_control_issue_budget()
        return Continue("observation_semantic_gain")
    feedback = no_gain_feedback(
        state,
        new_space,
        new_page,
        source=ControlFeedbackSource.POLICY_OBSERVATION,
        code="observation_no_information_gain",
        request_digest=request_digest,
        result_digest=after_result,
        public_subject_id=decision.subject_id,
        public_field_paths=("observation",),
    )
    return route_feedback(state, scope, feedback)


async def _wait_refresh(
    session: AgentRunSession,
    decision: Wait,
    waiter: WaitController,
    scope: ControlTransitionScope,
) -> LoopDirective:
    if not _can_observe(session):
        scope.set_reason("observation_budget_exhausted")
        return Terminate(
            AgentLoopStatus.FAILED, "observation_budget_exhausted",
            "agent loop observation budget exhausted",
        )
    request = WorldObservationRequest(
        ObservationRequestKind.WAIT_REFRESH, "fresh observation after wait",
    )
    unavailable = capture_admission_failure(session.environment, request)
    if unavailable is not None:
        scope.record_acquisition(
            unavailable.status,
            unavailable.actual_origin,
            unavailable.reason_code,
            unavailable.attempts,
            request.kind,
            expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
        )
        return Terminate(
            AgentLoopStatus.BLOCKED, unavailable.reason_code, unavailable.reason_code,
            failure_code=unavailable.failure_code,
        )
    if session.waited_ms + decision.max_wait_ms > MAX_TOTAL_WAIT_MS:
        scope.record_decision_result("wait_budget_exceeded")
        scope.set_reason("wait_budget_exhausted")
        return Terminate(
            AgentLoopStatus.BLOCKED, "wait_budget_exhausted",
            "total wait budget exhausted",
        )
    await waiter.wait(decision.max_wait_ms)
    session.accounting.record_wait(decision.max_wait_ms)
    return await _fresh_observation(session, decision, request, scope)


def ensure_current_action_page(
    session: AgentRunSession,
    action_space: ActionSpace,
    context_builder: ContextBuilder,
) -> None:
    candidate = context_builder.page(action_space, session.state)
    if (
        session.current_action_space is not None
        and session.current_action_space.action_space_id == action_space.action_space_id
        and session.current_action_page is not None
        and session.current_action_page.objective_digest == candidate.objective_digest
    ):
        return
    session.current_action_space = action_space
    session.current_action_page = candidate


async def _fresh_observation(
    session: AgentRunSession,
    decision: AgentDecision,
    request: WorldObservationRequest,
    scope: ControlTransitionScope,
) -> LoopDirective:
    state = session.state
    if not _can_observe(session):
        scope.set_reason("observation_budget_exhausted")
        return Terminate(
            AgentLoopStatus.FAILED, "observation_budget_exhausted",
            "agent loop observation budget exhausted",
        )
    previous_id = state.current_observation.observation_id
    acquired = await capture_for_session(session, previous_id, request, scope)
    if acquired.observation is None:
        status = (
            AgentLoopStatus.BLOCKED
            if acquired.attempts == 0 else AgentLoopStatus.FAILED
        )
        return directive(
            status,
            acquired.reason_code,
            acquired.reason_code,
            failure_code=acquired.failure_code,
        )
    state.install_observation(acquired.observation)
    return Continue("observation_acquired")


async def _propose_done(
    session: AgentRunSession,
    decision: ProposeDone,
    task_evaluator: TaskEvaluator,
    scope: ControlTransitionScope,
) -> LoopDirective:
    task, state = session.task, session.state
    index = WorldEvidenceIndex.from_observation(state.current_observation)
    known = {criterion_id(item) for item in task.success_criteria}
    if len(set(decision.claimed_criteria)) != len(decision.claimed_criteria) or not set(decision.claimed_criteria).issubset(known):
        scope.set_reason("invalid_completion_claim")
        return Terminate(AgentLoopStatus.BLOCKED, "invalid_completion_claim", "completion claim contains an unknown or duplicate criterion")
    if decision.unresolved_items:
        scope.set_reason("invalid_completion_claim")
        return Terminate(AgentLoopStatus.BLOCKED, "invalid_completion_claim", "completion claim retains unresolved items")
    if any(not index.resolve(item) for item in decision.evidence_refs):
        scope.set_reason("completion_evidence_not_current")
        return Terminate(AgentLoopStatus.BLOCKED, "completion_evidence_not_current", "completion evidence is not current")
    try:
        evaluation = await validated_task_evaluation(
            task_evaluator,
            task,
            state.current_observation,
        )
    except asyncio.CancelledError:
        raise
    except ValueError as exc:
        scope.set_reason("task_evaluation_invalid")
        return Terminate(
            AgentLoopStatus.FAILED,
            "task_evaluation_invalid",
            str(exc),
            failure_stage=FailureStage.EVALUATION,
            failure_kind=FailureKind.INVALID_OUTPUT,
        )
    except Exception as exc:
        scope.set_reason("task_evaluation_call_failed")
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.EVALUATION,
            FailureKind.CALL_FAILED,
            "task_evaluation_call_failed",
            exception_class=safe_exception_class(exc),
        )
        raise
    state.current_task_evaluation = evaluation
    scope.record_evaluations(task=evaluation)
    scope.set_reason(f"task_{evaluation.status}")
    disposition = task_evaluation_disposition(evaluation)
    return Continue("task_incomplete") if disposition.status is None else directive(
        disposition.status,
        disposition.reason_code,
        evaluation.reason,
        task_terminal=disposition.task_terminal,
    )


def _can_observe(session: AgentRunSession) -> bool:
    return session.observation_count < session.task.loop_budget.max_observations


def _valid_page_request(session: AgentRunSession, decision: RequestActionPage) -> bool:
    if not decision.cursor:
        return True
    page = session.current_action_page
    if page is None or decision.cursor != page.next_cursor:
        return False
    role = page.relevance_role.value if page.relevance_role else ""
    return (
        decision.query == page.query
        and decision.target_id == page.target_id
        and decision.relevance_role == role
    )


def _request_action_page(
    session: AgentRunSession,
    action_space: ActionSpace,
    context_builder: ContextBuilder,
    decision: RequestActionPage,
    scope: ControlTransitionScope,
) -> LoopDirective:
    if not _valid_page_request(session, decision):
        scope.set_reason("invalid_action_page_request")
        return Terminate(AgentLoopStatus.BLOCKED, "invalid_action_page_request", "invalid action page request")
    previous_page = session.current_action_page or context_builder.page(action_space, session.state)
    previous_digest = public_action_page_digest(
        session.state.current_observation, action_space, previous_page,
    )
    try:
        session.current_action_page = context_builder.page(
            action_space,
            session.state,
            query=decision.query,
            target_id=decision.target_id,
            relevance_role=decision.relevance_role,
            cursor=decision.cursor,
        )
    except ValueError:
        scope.set_reason("invalid_action_page_request")
        return Terminate(AgentLoopStatus.BLOCKED, "invalid_action_page_request", "invalid action page request")
    result_digest = public_action_page_digest(
        session.state.current_observation, action_space, session.current_action_page,
    )
    request_digest = action_page_request_digest(
        session.state.current_observation,
        query=decision.query,
        target_id=decision.target_id,
        relevance_role=decision.relevance_role,
        semantic_offset=session.current_action_page.offset,
    )
    if result_digest == previous_digest:
        feedback = no_gain_feedback(
            session.state,
            action_space,
            session.current_action_page,
            source=ControlFeedbackSource.ACTION_PAGE,
            code="action_page_no_information_gain",
            request_digest=request_digest,
            result_digest=result_digest,
            public_subject_id=decision.target_id or None,
            public_field_paths=("actions",),
        )
        scope.record_decision_result("page_unchanged")
        return route_feedback(session.state, scope, feedback)
    session.state.clear_control_issue_budget()
    result = "page_changed"
    scope.record_decision_result(result)
    scope.set_reason(result)
    return Continue(result)
