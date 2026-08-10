"""One-shot typed decision admission and surface-neutral routing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

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
    capture_fresh,
)
from affordance_runtime.agent.policy import AgentPolicy, PolicyFailure, TaskEvaluator
from affordance_runtime.agent.result import (
    AgentResult,
    build_result,
    observation_budget_result,
    refresh_control_projection,
)
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
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
from affordance_runtime.world.contracts import ActionSpace

SelectionExecutor = Callable[
    [AgentRunSession, ActionSpace, SelectAction, ControlTransitionScope],
    Awaitable[object],
]


def accept_current_decision(session: AgentRunSession, decision: AgentDecision) -> bool:
    context = session.current_context_snapshot
    if context is None or decision.context_id != context.context_id:
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
) -> object:
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
    outcome = await policy.decide(context)
    state.remaining_turns -= 1
    if isinstance(outcome, PolicyFailure):
        return build_result(
            AgentLoopStatus.FAILED,
            task,
            state,
            0,
            0,
            outcome.reason,
            policy_failure=outcome,
        )
    decision = outcome
    if not accept_current_decision(session, decision):
        return None
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
        )
    except BaseException as exc:
        cancelled = isinstance(exc, asyncio.CancelledError)
        scope.set_reason("runtime_cancelled" if cancelled else "runtime_exception")
        scope.set_resulting_status(
            AgentLoopStatus.CANCELLED if cancelled else AgentLoopStatus.FAILED
        )
        scope.finalize(state, None)
        raise
    transition = scope.finalize(state, routed)
    return _refresh_routed_result(routed, state, transition.reason_code)


async def _route_decision(
    session,
    action_space,
    decision,
    context_builder,
    task_evaluator,
    waiter,
    execute_selection,
    scope,
):
    task, state = session.task, session.state
    if isinstance(decision, AskUser):
        scope.set_reason("user_input_requested")
        state.set_pending_question(decision.question)
        return build_result(AgentLoopStatus.WAITING_USER, task, state, 0, 0, decision.question)
    if isinstance(decision, Abort):
        scope.set_reason(f"abort_{decision.category}")
        return build_result(AgentLoopStatus.FAILED, task, state, 0, 0, decision.reason)
    if isinstance(decision, ProposeDone):
        return await _propose_done(session, decision, task_evaluator, scope)
    if isinstance(decision, RequestObservation):
        return await _policy_observation(session, decision, scope)
    if isinstance(decision, Wait):
        return await _wait_refresh(session, decision, waiter, scope)
    if isinstance(decision, RequestActionPage):
        return _request_action_page(session, action_space, context_builder, decision, scope)
    rejection = _current_page_selection_rejection(session, decision)
    if rejection:
        scope.record_admission(AdmissionStatus.REJECTED, _selection_rejection_code(rejection))
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, rejection)
    return await execute_selection(session, action_space, decision, scope)


async def _policy_observation(
    session: AgentRunSession,
    decision: RequestObservation,
    scope: ControlTransitionScope,
):
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        decision.reason,
        decision.subject_id,
        decision.modality,
        decision.required_assurance,
    )
    return await _fresh_observation(session, decision, request, scope)


async def _wait_refresh(
    session: AgentRunSession,
    decision: Wait,
    waiter: WaitController,
    scope: ControlTransitionScope,
):
    task, state = session.task, session.state
    if not _can_observe(session):
        scope.set_reason("observation_budget_exhausted")
        return observation_budget_result(task, state, 0, 0)
    request = WorldObservationRequest(
        ObservationRequestKind.WAIT_REFRESH, "fresh observation after wait",
    )
    unavailable = capture_admission_failure(session.environment, request)
    if unavailable is not None:
        scope.record_acquisition(
            unavailable.status,
            AcquisitionOrigin.INDEPENDENT_CAPTURE,
            unavailable.reason_code,
            unavailable.attempts,
            request.kind,
        )
        return build_result(
            AgentLoopStatus.BLOCKED, task, state, 0, 0, unavailable.reason_code,
            failure_code=unavailable.failure_code,
        )
    if session.waited_ms + decision.max_wait_ms > MAX_TOTAL_WAIT_MS:
        scope.record_decision_result("wait_budget_exceeded")
        scope.set_reason("wait_budget_exhausted")
        return build_result(
            AgentLoopStatus.BLOCKED, task, state, 0, 0, "total wait budget exhausted",
        )
    await waiter.wait(decision.max_wait_ms)
    session.waited_ms += decision.max_wait_ms
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
) -> None | object:
    state = session.state
    if not _can_observe(session):
        scope.set_reason("observation_budget_exhausted")
        return observation_budget_result(session.task, state, 0, 0)
    previous_id = state.current_observation.observation_id
    acquired = await capture_fresh(session.environment, previous_id, request)
    scope.record_acquisition(
        acquired.status,
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        acquired.reason_code,
        acquired.attempts,
        request.kind,
    )
    session.observation_count += acquired.attempts
    if acquired.observation is None:
        status = (
            AgentLoopStatus.BLOCKED
            if acquired.attempts == 0 else AgentLoopStatus.FAILED
        )
        return build_result(
            status,
            session.task,
            state,
            0,
            0,
            acquired.reason_code,
            failure_code=acquired.failure_code,
        )
    state.current_observation = acquired.observation
    state.current_task_evaluation = None
    return None


async def _propose_done(
    session: AgentRunSession,
    decision: ProposeDone,
    task_evaluator: TaskEvaluator,
    scope: ControlTransitionScope,
) -> None | object:
    task, state = session.task, session.state
    index = WorldEvidenceIndex.from_observation(state.current_observation)
    known = {criterion_id(item) for item in task.success_criteria}
    if len(set(decision.claimed_criteria)) != len(decision.claimed_criteria) or not set(decision.claimed_criteria).issubset(known):
        scope.set_reason("invalid_completion_claim")
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "completion claim contains an unknown or duplicate criterion")
    if decision.unresolved_items:
        scope.set_reason("invalid_completion_claim")
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "completion claim retains unresolved items")
    if any(not index.resolve(item) for item in decision.evidence_refs):
        scope.set_reason("completion_evidence_not_current")
        return build_result(AgentLoopStatus.BLOCKED, task, state, 0, 0, "completion evidence is not current")
    try:
        evaluation = await validated_task_evaluation(
            task_evaluator,
            task,
            state.current_observation,
        )
    except ValueError as exc:
        scope.set_reason("task_evaluation_invalid")
        return build_result(
            AgentLoopStatus.FAILED,
            task,
            state,
            0,
            0,
            str(exc),
            reason_code="task_evaluation_invalid",
        )
    state.current_task_evaluation = evaluation
    scope.record_evaluations(task=evaluation)
    scope.set_reason(f"task_{evaluation.status}")
    status = task_evaluation_loop_status(evaluation)
    return None if status is None else build_result(status, task, state, 0, 0, evaluation.reason)


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
) -> object | None:
    if not _valid_page_request(session, decision):
        scope.set_reason("invalid_action_page_request")
        return build_result(AgentLoopStatus.BLOCKED, session.task, session.state, 0, 0, "invalid action page request")
    previous_page_id = session.current_action_page.page_id if session.current_action_page else ""
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
        return build_result(AgentLoopStatus.BLOCKED, session.task, session.state, 0, 0, "invalid action page request")
    result = "page_unchanged" if session.current_action_page.page_id == previous_page_id else "page_changed"
    scope.record_decision_result(result)
    scope.set_reason(result)
    return None


def _current_page_selection_rejection(session: AgentRunSession, decision: SelectAction) -> str:
    page = session.current_action_page
    if page is None or decision.action_id not in page.visible_action_ids:
        return "policy selected outside the current action page"
    if decision.destination_id and decision.destination_id not in page.visible_destination_ids(decision.action_id):
        return "policy selected a destination outside the current action page"
    return ""


def _selection_rejection_code(message: str) -> str:
    if "destination" in message:
        return "destination_outside_current_page"
    return "action_outside_current_page"


def _refresh_routed_result(outcome, state, reason_code):
    if isinstance(outcome, AgentResult):
        return refresh_control_projection(outcome, state, reason_code)
    if isinstance(outcome, tuple) and outcome and isinstance(outcome[-1], AgentResult):
        return (*outcome[:-1], refresh_control_projection(outcome[-1], state, reason_code))
    return outcome
