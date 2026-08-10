"""Bind, execute once, consume typed after acquisition, and evaluate."""

from __future__ import annotations

import asyncio

from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
)
from affordance_runtime.agent.control_outcome import Continue, LoopDirective, Terminate
from affordance_runtime.agent.control_transition import (
    AdmissionStatus,
    ControlContinuationScope,
    ControlTransitionScope,
)
from affordance_runtime.agent.decisions import SelectAction
from affordance_runtime.agent.evaluation_control import (
    validated_action_evaluation,
    validated_task_evaluation,
)
from affordance_runtime.agent.observation_control import (
    capture_for_session,
    no_fresh_after_result,
    post_action_fallback_result,
    validate_fresh_acquisition,
)
from affordance_runtime.agent.policy import ActionEvaluator, TaskEvaluator
from affordance_runtime.agent.post_action_policy import post_action_result
from affordance_runtime.agent.progress_control import record_execution_progress
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import task_evaluation_loop_status
from affordance_runtime.execution.contracts import ActionError, ActionResult, DispatchStatus
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    ExecutionOutcome,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.binder import ActionBinder, BindingError
from affordance_runtime.world.contracts import AdmittedActionSelection


async def execute_cycle(
    session: AgentRunSession,
    selection: AdmittedActionSelection,
    decision: SelectAction,
    binder: ActionBinder,
    action_evaluator: ActionEvaluator,
    task_evaluator: TaskEvaluator,
    scope: ControlTransitionScope | ControlContinuationScope,
) -> LoopDirective:
    task, state = session.task, session.state
    scope.record_admission(AdmissionStatus.ADMITTED, "action_admitted")
    if session.observation_count >= task.loop_budget.max_observations:
        scope.set_reason("observation_budget_exhausted")
        return Terminate(
            AgentLoopStatus.FAILED, "observation_budget_exhausted",
            "agent loop observation budget exhausted",
        )
    before = state.current_observation
    try:
        request = binder.bind(selection, before, decision.context_id)
    except BindingError:
        return await _binding_refresh(session, before.observation_id, scope)
    current = session.current_context_snapshot
    if (
        current is None
        or request.context_id != current.context_id
        or session.consumed_context_id != request.context_id
    ):
        scope.set_reason("stale_bound_request")
        return Terminate(
            AgentLoopStatus.BLOCKED, "stale_bound_request",
            "bound request context is not current",
        )
    outcome = await _execute_boundary(
        session, request, before.observation_id, scope,
    )
    result = outcome.result
    probe_error = False
    try:
        _probe_count(result)
    except ValueError:
        probe_error = True
    primary = validate_fresh_acquisition(
        outcome.post_acquisition,
        before.observation_id,
        expected_origin=AcquisitionOrigin.POST_ACTION,
        post_action=True,
    )
    if probe_error:
        scope.set_reason("invalid_currentness_probe_count")
        return Terminate(
            AgentLoopStatus.FAILED, "invalid_currentness_probe_count",
            "adapter returned invalid currentness probe metadata",
        )
    if result.request_id != request.request_id or result.backend != request.binding.executor_id:
        scope.set_reason("action_result_lineage_mismatch")
        return Terminate(
            AgentLoopStatus.FAILED, "action_result_lineage_mismatch",
            "action result lineage mismatch",
        )
    if result.dispatch_status is DispatchStatus.NOT_SENT:
        return await _not_sent_outcome(session, decision, request, result, scope)
    remaining = task.loop_budget.max_observations - session.observation_count
    acquired = primary
    if (
        acquired.observation is None
        and session.environment.observation_capabilities.independent_capture
        and primary.attempts < remaining
    ):
        fallback_request = WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "post action acquisition fallback",
        )
        fallback = await capture_for_session(
            session, before.observation_id, fallback_request, scope,
        )
        acquired = post_action_fallback_result(primary, fallback)
    if acquired.observation is None:
        return no_fresh_after_result(session, decision, request, result, acquired, scope)
    state.current_observation = acquired.observation
    state.current_task_evaluation = None
    scope.record_after(acquired.observation.observation_id)
    return await _evaluate_after(
        session, selection, decision, request, result, before, acquired.observation,
        action_evaluator, task_evaluator,
        scope,
    )


async def _evaluate_after(
    session, selection, decision, request, result, before, after,
    action_evaluator, task_evaluator,
    scope,
) -> LoopDirective:
    task, state = session.task, session.state
    try:
        action_evaluation = await validated_action_evaluation(
            action_evaluator, task, before, request, result, after,
        )
    except ValueError as exc:
        scope.record_evaluations()
        scope.set_reason("action_evaluation_invalid")
        return Terminate(AgentLoopStatus.FAILED, "action_evaluation_invalid", str(exc))
    scope.record_evaluations(action=action_evaluation)
    try:
        task_evaluation = await validated_task_evaluation(task_evaluator, task, after)
    except ValueError as exc:
        scope.set_reason("task_evaluation_invalid")
        return Terminate(AgentLoopStatus.FAILED, "task_evaluation_invalid", str(exc))
    scope.record_evaluations(task=task_evaluation)
    state.current_task_evaluation = task_evaluation
    record_execution_progress(session, selection, action_evaluation, after, task_evaluation)
    scope.set_reason(f"action_{action_evaluation.status}")
    outcome = post_action_result(
        task, state, request, result, action_evaluation, task_evaluation,
    )
    task_status = task_evaluation_loop_status(task_evaluation)
    if task_status is not None:
        scope.set_reason(f"task_{task_evaluation.status}")
    elif not isinstance(outcome, Continue) and state.pending_unknown_request is not None:
        scope.set_reason("effect_unknown")
    elif not isinstance(outcome, Continue):
        scope.set_reason("action_rejected")
    return outcome


async def _binding_refresh(
    session: AgentRunSession,
    previous_id: str,
    scope: ControlTransitionScope | ControlContinuationScope,
) -> LoopDirective:
    acquired = await capture_for_session(
        session,
        previous_id,
        WorldObservationRequest(
            ObservationRequestKind.BINDING_REFRESH,
            "binding unavailable refresh",
        ),
        scope,
    )
    if acquired.observation is not None:
        session.state.current_observation = acquired.observation
        session.state.current_task_evaluation = None
        scope.record_after(acquired.observation.observation_id)
        return Continue("binding_refreshed")
    return Terminate(
        AgentLoopStatus.FAILED,
        acquired.reason_code,
        acquired.reason_code,
        failure_code=acquired.failure_code,
    )


async def _not_sent_outcome(
    session,
    decision,
    request,
    result: ActionResult,
    scope: ControlTransitionScope | ControlContinuationScope,
) -> LoopDirective:
    state = session.state
    before_id = state.current_observation.observation_id
    if result.error not in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}:
        scope.set_reason("action_not_dispatched")
        return Terminate(
            AgentLoopStatus.FAILED, "action_not_dispatched",
            "action was not dispatched",
        )
    acquired = await capture_for_session(
        session,
        before_id,
        WorldObservationRequest(
            ObservationRequestKind.CURRENTNESS_REFRESH,
            "currentness unavailable refresh",
        ),
        scope,
    )
    if acquired.observation is not None:
        state.current_observation = acquired.observation
        state.current_task_evaluation = None
        scope.record_after(acquired.observation.observation_id)
        return Continue("currentness_refreshed")
    return Terminate(
        AgentLoopStatus.FAILED, acquired.reason_code, acquired.reason_code,
        failure_code=acquired.failure_code,
    )


def _probe_count(result: ActionResult) -> int:
    value = result.adapter_evidence.get("currentness_probe_count", 0)
    if type(value) is not int or value < 0:
        raise ValueError("currentness probe count must be a non-negative integer")
    return value


async def _execute_boundary(session, request, previous_id, scope) -> ExecutionOutcome:
    attempt_id = session.accounting.next_attempt_id()
    try:
        outcome = await session.environment.execute(request)
    except asyncio.CancelledError:
        _record_execute_exception(
            session, scope, request, attempt_id,
            AttemptDisposition.CANCELLED, "execute_cancelled", "CancelledError",
        )
        raise
    except Exception as exc:
        _record_execute_exception(
            session, scope, request, attempt_id,
            AttemptDisposition.THREW, "execute_exception", type(exc).__name__,
        )
        raise
    if not isinstance(outcome, ExecutionOutcome) or not isinstance(outcome.result, ActionResult):
        _record_execute_exception(
            session, scope, request, attempt_id,
            AttemptDisposition.MALFORMED, "execute_malformed", "",
        )
        raise TypeError("WorldEnvironment.execute returned a malformed contract")
    result = outcome.result
    primary = validate_fresh_acquisition(
        outcome.post_acquisition,
        previous_id,
        expected_origin=AcquisitionOrigin.POST_ACTION,
        post_action=True,
    )
    try:
        probes = _probe_count(result)
    except ValueError:
        probes = 0
    dispatched = int(result.dispatch_status is not DispatchStatus.NOT_SENT)
    receipt = AttemptReceipt(
        attempt_id,
        AttemptOperation.EXECUTE,
        "post_action",
        AcquisitionOrigin.POST_ACTION,
        outcome.post_acquisition.origin,
        AttemptDisposition.RETURNED,
        primary.reason_code,
        primary.attempts,
        1,
        dispatched,
        probes,
        result.dispatch_status,
        request.request_id,
        result.request_id,
        result.request_id == request.request_id,
        acquisition_status=primary.status,
    )
    session.accounting.record(receipt)
    scope.record_execution_receipt(receipt, request.request_id, request.intent, result)
    return outcome


def _record_execute_exception(
    session, scope, request, attempt_id, disposition, reason_code, exception_class,
) -> None:
    receipt = AttemptReceipt(
        attempt_id,
        AttemptOperation.EXECUTE,
        "execute",
        AcquisitionOrigin.POST_ACTION,
        None,
        disposition,
        reason_code,
        0,
        1,
        0,
        0,
        expected_request_id=request.request_id,
        request_lineage_valid=None,
        exception_class=exception_class,
    )
    session.accounting.record(receipt)
    scope.record_attempt(receipt)
