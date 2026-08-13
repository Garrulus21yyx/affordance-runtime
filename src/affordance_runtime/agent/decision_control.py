"""One-shot typed decision admission and surface-neutral routing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from affordance_runtime.agent.attempt_receipt import safe_exception_class
from affordance_runtime.agent.control_feedback import (
    ControlFeedbackSource,
    current_semantic_scope,
    no_gain_feedback,
    objective_repair_feedback,
    observation_traversal_feedback,
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
    AgentDecisionPackage,
    AskUser,
    EstablishLocalObjective,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
    package_decision,
)
from affordance_runtime.agent.evaluation_control import validated_task_evaluation
from affordance_runtime.agent.frontier_control import audit_task_frontier
from affordance_runtime.agent.negative_claim_coverage import (
    NegativeClaimCoverageDisposition,
    NegativeClaimCoverageGate,
)
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
from affordance_runtime.task.frontier import (
    PreparedObjectiveOperation,
    prepare_objective_operation,
    synchronize_verified_task_state,
)
from affordance_runtime.task.frontier_contracts import ActiveObjective
from affordance_runtime.task.local_objective import (
    establish_local_objective,
    local_objective_action_parameters,
    local_objective_allowed_action_ids,
    local_objective_complete,
)
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.action_paging import canonical_action_query
from affordance_runtime.world.action_space import ActionSpaceBuilder
from affordance_runtime.world.contracts import ActionSpace
from affordance_runtime.world.public_semantic_digest import (
    action_page_request_digest,
    observation_request_digest,
    policy_observation_result_digest,
    public_action_page_result_digest,
)

SelectionExecutor = Callable[
    [
        AgentRunSession,
        ActionSpace,
        SelectAction,
        PreparedObjectiveOperation,
        ControlTransitionScope,
    ],
    Awaitable[LoopDirective],
]

_DECISION_TYPES = (
    Abort,
    AskUser,
    EstablishLocalObjective,
    ProposeDone,
    RequestActionPage,
    RequestObservation,
    SelectAction,
    Wait,
)


def accept_current_decision(session: AgentRunSession, decision: AgentDecision) -> bool:
    context = session.current_context_snapshot
    if context is None or not isinstance(decision, _DECISION_TYPES) or decision.context_id != context.context_id:
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
    package = outcome if isinstance(outcome, AgentDecisionPackage) else package_decision(outcome)
    decision = package.decision
    if not accept_current_decision(session, decision):
        return Continue("stale_decision")
    scope = ControlTransitionScope(state, decision)
    routed: LoopDirective
    coverage = NegativeClaimCoverageGate().assess(
        package,
        context,
        state.current_observation,
    )
    if coverage.disposition is NegativeClaimCoverageDisposition.UNKNOWN:
        if state.remaining_turns <= 0:
            routed = Terminate(
                AgentLoopStatus.BLOCKED,
                coverage.reason_code,
                "negative claim remains unknown because observation coverage is incomplete",
            )
        else:
            page = session.current_action_page or context_builder.page(action_space, state)
            routed = route_feedback(
                state,
                scope,
                observation_traversal_feedback(
                    state,
                    action_space,
                    page,
                    code=coverage.reason_code,
                ),
            )
        scope.set_reason(coverage.reason_code)
        scope.finalize(state, routed)
        return routed
    if coverage.disposition is NegativeClaimCoverageDisposition.ADVANCE:
        if state.remaining_turns <= 0:
            routed = Terminate(
                AgentLoopStatus.BLOCKED,
                "observation_traversal_budget_exhausted",
                "negative claim remains unknown because policy-call budget is exhausted",
            )
        else:
            state.set_observation_cursor(coverage.next_cursor)
            page = session.current_action_page or context_builder.page(action_space, state)
            routed = route_feedback(
                state,
                scope,
                observation_traversal_feedback(
                    state,
                    action_space,
                    page,
                    code=coverage.reason_code,
                ),
            )
            scope.record_decision_result("observation_page_changed")
        scope.set_reason(routed.reason_code)
        scope.finalize(state, routed)
        return routed
    verified = state.verified_task_state or synchronize_verified_task_state(
        task,
        task_evaluation,
        state.current_observation,
        None,
    )
    state.install_verified_task_state(verified)
    objective_admission = prepare_objective_operation(
        package.objective_operation,
        state=verified,
        active=(state.active_objective if isinstance(state.active_objective, ActiveObjective) else None),
        observation=state.current_observation,
        evaluation=task_evaluation,
        context_id=context.context_id,
        next_sequence=state.objective_sequence + 1,
    )
    if objective_admission.issue is not None:
        if isinstance(decision, SelectAction):
            scope.record_admission(
                AdmissionStatus.REJECTED,
                objective_admission.issue.code.value,
            )
        page = session.current_action_page or context_builder.page(action_space, state)
        feedback = objective_repair_feedback(
            state,
            action_space,
            page,
            decision=decision if isinstance(decision, SelectAction) else None,
            operation=package.objective_operation,
            issue=objective_admission.issue,
        )
        rejected = route_feedback(state, scope, feedback)
        scope.finalize(state, rejected)
        return rejected
    assert objective_admission.prepared is not None
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
            objective_admission.prepared,
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
    prepared_objective,
) -> LoopDirective:
    state = session.state
    if not isinstance(decision, SelectAction):
        state.commit_objective_operation(prepared_objective)
    if isinstance(decision, AskUser):
        scope.set_reason("user_input_requested")
        state.set_pending_question(decision.question)
        return Pause(AgentLoopStatus.WAITING_USER, "user_input_requested", decision.question)
    if isinstance(decision, Abort):
        scope.set_reason(f"abort_{decision.category}")
        return Terminate(AgentLoopStatus.FAILED, f"abort_{decision.category}", decision.reason)
    if isinstance(decision, EstablishLocalObjective):
        if not local_objective_complete(state.local_objective_state):
            scope.set_reason("local_objective_already_active")
            return Continue("local_objective_already_active")
        state.local_objective_state = establish_local_objective(
            decision.objective,
            state.current_observation,
            enumerator=state.scope_enumerator,
        )
        state.progress_revision += 1
        scope.record_decision_result("local_objective_established")
        scope.set_reason("local_objective_established")
        return Continue("local_objective_established")
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
    execution = state.local_objective_state
    if execution is not None and not local_objective_complete(execution):
        allowed = local_objective_allowed_action_ids(execution, action_space)
        parameters = local_objective_action_parameters(execution)
        if decision.action_id not in allowed or dict(decision.parameters) != dict(parameters):
            reason = "action_not_authorized_by_local_objective"
            scope.record_admission(AdmissionStatus.REJECTED, reason)
            scope.record_decision_result(reason)
            scope.set_reason(reason)
            return Terminate(AgentLoopStatus.BLOCKED, reason)
    page = session.current_action_page or context_builder.page(action_space, state)
    issue = page.selection_issue(decision.action_id, decision.destination_id)
    if issue is not None:
        scope.record_admission(AdmissionStatus.REJECTED, issue.code.value)
        feedback = repair_feedback(
            state,
            action_space,
            page,
            decision=decision,
            issue=issue,
        )
        return route_feedback(state, scope, feedback)
    return await execute_selection(
        session,
        action_space,
        decision,
        prepared_objective,
        scope,
    )

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
    if decision.cursor:
        return _policy_observation_page(session, decision, scope)
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        decision.reason,
        decision.subject_id,
        decision.modality,
        decision.required_assurance,
    )
    state = session.state
    request_digest = observation_request_digest(
        state.current_observation,
        subject_id=decision.subject_id,
        modality=decision.modality,
        required_assurance=decision.required_assurance,
    )
    before_result = policy_observation_result_digest(
        state.current_observation,
        action_space,
        prior_task_evaluation,
    )
    acquired = await _fresh_observation(session, decision, request, scope)
    if not isinstance(acquired, Continue):
        return acquired
    try:
        evaluation = await validated_task_evaluation(
            task_evaluator,
            session.task,
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
    state.current_task_evaluation = evaluation
    audit_task_frontier(session, evaluation)
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
        state.current_observation,
        new_space,
        evaluation,
    )
    if after_result != before_result:
        state.begin_control_epoch(current_semantic_scope(state, new_space))
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


def _policy_observation_page(
    session: AgentRunSession,
    decision: RequestObservation,
    scope: ControlTransitionScope,
) -> LoopDirective:
    context = session.current_context_snapshot
    traversal = context.world.traversal if context is not None else None
    if traversal is None or decision.cursor != traversal.next_cursor:
        scope.set_reason("invalid_observation_page_request")
        return Terminate(
            AgentLoopStatus.BLOCKED,
            "invalid_observation_page_request",
            "observation cursor does not continue the current frozen snapshot",
        )
    session.state.set_observation_cursor(decision.cursor)
    scope.record_decision_result("observation_page_changed")
    scope.set_reason("observation_page_changed")
    return Continue("observation_page_changed")


async def _wait_refresh(
    session: AgentRunSession,
    decision: Wait,
    waiter: WaitController,
    scope: ControlTransitionScope,
) -> LoopDirective:
    if not _can_observe(session):
        scope.set_reason("observation_budget_exhausted")
        return Terminate(
            AgentLoopStatus.FAILED,
            "observation_budget_exhausted",
            "agent loop observation budget exhausted",
        )
    request = WorldObservationRequest(
        ObservationRequestKind.WAIT_REFRESH,
        "fresh observation after wait",
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
            AgentLoopStatus.BLOCKED,
            unavailable.reason_code,
            unavailable.reason_code,
            failure_code=unavailable.failure_code,
        )
    if session.waited_ms + decision.max_wait_ms > MAX_TOTAL_WAIT_MS:
        scope.record_decision_result("wait_budget_exceeded")
        scope.set_reason("wait_budget_exhausted")
        return Terminate(
            AgentLoopStatus.BLOCKED,
            "wait_budget_exhausted",
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
            AgentLoopStatus.FAILED,
            "observation_budget_exhausted",
            "agent loop observation budget exhausted",
        )
    previous_id = state.current_observation.observation_id
    acquired = await capture_for_session(session, previous_id, request, scope)
    if acquired.observation is None:
        status = AgentLoopStatus.BLOCKED if acquired.attempts == 0 else AgentLoopStatus.FAILED
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
    if len(set(decision.claimed_criteria)) != len(decision.claimed_criteria) or not set(
        decision.claimed_criteria
    ).issubset(known):
        scope.set_reason("invalid_completion_claim")
        return Terminate(
            AgentLoopStatus.BLOCKED,
            "invalid_completion_claim",
            "completion claim contains an unknown or duplicate criterion",
        )
    if decision.unresolved_items:
        scope.set_reason("invalid_completion_claim")
        return Terminate(
            AgentLoopStatus.BLOCKED, "invalid_completion_claim", "completion claim retains unresolved items"
        )
    if any(not index.resolve(item) for item in decision.evidence_refs):
        scope.set_reason("completion_evidence_not_current")
        return Terminate(
            AgentLoopStatus.BLOCKED, "completion_evidence_not_current", "completion evidence is not current"
        )
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
    return (
        Continue("task_incomplete")
        if disposition.status is None
        else directive(
            disposition.status,
            disposition.reason_code,
            evaluation.reason,
            task_terminal=disposition.task_terminal,
        )
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
        canonical_action_query(decision.query) == page.query
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
    result_digest = public_action_page_result_digest(
        session.state.current_observation,
        action_space,
        session.current_action_page,
    )
    request_digest = action_page_request_digest(
        session.state.current_observation,
        query=decision.query,
        target_id=decision.target_id,
        relevance_role=decision.relevance_role,
        semantic_offset=session.current_action_page.offset,
    )
    if not session.state.record_action_page_result(result_digest):
        recovery_page = session.current_action_page
        if not recovery_page.visible_action_ids:
            recovery_page = context_builder.page(action_space, session.state)
            session.current_action_page = recovery_page
        feedback = no_gain_feedback(
            session.state,
            action_space,
            recovery_page,
            source=ControlFeedbackSource.ACTION_PAGE,
            code="action_page_no_information_gain",
            request_digest=request_digest,
            result_digest=result_digest,
            public_subject_id=decision.target_id or None,
            public_field_paths=("actions",),
        )
        scope.record_decision_result("page_unchanged")
        return route_feedback(session.state, scope, feedback)
    result = "page_changed"
    scope.record_decision_result(result)
    scope.set_reason(result)
    return Continue(result)
