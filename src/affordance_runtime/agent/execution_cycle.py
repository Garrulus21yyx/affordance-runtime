"""Bind, execute once, consume typed after acquisition, and evaluate."""

from __future__ import annotations

import asyncio

from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
    safe_boundary_identity,
    safe_exception_class,
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
from affordance_runtime.agent.runtime_failure import (
    FailureKind,
    FailureStage,
    RuntimeFailure,
)
from affordance_runtime.agent.session import AgentRunSession
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.agent.task_evaluation_policy import (
    task_evaluation_disposition_for_world,
)
from affordance_runtime.evaluation.contracts import TaskEvaluationStatus
from affordance_runtime.execution.contracts import ActionError, ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    ExecutionOutcome,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.binder import ActionBinder, BindingError
from affordance_runtime.world.contracts import ActionOption, AdmittedActionSelection, WorldObservation


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
            failure_stage=FailureStage.EXECUTION,
            failure_kind=FailureKind.INVALID_OUTPUT,
        )
    if result.request_id != request.request_id or result.backend != request.binding.executor_id:
        scope.set_reason("action_result_lineage_mismatch")
        return Terminate(
            AgentLoopStatus.FAILED, "action_result_lineage_mismatch",
            "action result lineage mismatch",
            failure_stage=FailureStage.EXECUTION,
            failure_kind=FailureKind.INVALID_OUTPUT,
        )
    if result.dispatch_status is DispatchStatus.NOT_SENT:
        rerouted = await _reroute_not_sent(
            session, selection, decision, request, result, binder, scope,
        )
        if isinstance(rerouted, LoopDirective):
            return rerouted
        selection, request, outcome, before = rerouted
        result = outcome.result
        try:
            _probe_count(result)
        except ValueError:
            scope.set_reason("invalid_currentness_probe_count")
            return Terminate(
                AgentLoopStatus.FAILED, "invalid_currentness_probe_count",
                "adapter returned invalid currentness probe metadata",
                failure_stage=FailureStage.EXECUTION,
                failure_kind=FailureKind.INVALID_OUTPUT,
            )
        if result.request_id != request.request_id or result.backend != request.binding.executor_id:
            scope.set_reason("action_result_lineage_mismatch")
            return Terminate(
                AgentLoopStatus.FAILED, "action_result_lineage_mismatch",
                "action result lineage mismatch",
                failure_stage=FailureStage.EXECUTION,
                failure_kind=FailureKind.INVALID_OUTPUT,
            )
        primary = validate_fresh_acquisition(
            outcome.post_acquisition,
            before.observation_id,
            expected_origin=AcquisitionOrigin.POST_ACTION,
            post_action=True,
        )
        if result.dispatch_status is DispatchStatus.NOT_SENT:
            scope.set_reason("route_exhausted")
            return Terminate(
                AgentLoopStatus.FAILED, "route_exhausted",
                "all bounded equivalent routes were not dispatched",
                failure_stage=FailureStage.EXECUTION,
                failure_kind=FailureKind.CALL_FAILED,
            )
    if result.dispatch_status is DispatchStatus.SENT:
        state.clear_control_issue_budget()
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
    state.install_observation(acquired.observation)
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
    prior_task_evaluation = state.current_task_evaluation
    prior_action_space = session.current_action_space
    try:
        action_evaluation = await validated_action_evaluation(
            action_evaluator, task, before, request, result, after,
        )
    except asyncio.CancelledError:
        raise
    except ValueError as exc:
        scope.record_evaluations()
        scope.set_reason("action_evaluation_invalid")
        return Terminate(
            AgentLoopStatus.FAILED, "action_evaluation_invalid", str(exc),
            failure_stage=FailureStage.EVALUATION,
            failure_kind=FailureKind.INVALID_OUTPUT,
        )
    except Exception as exc:
        scope.record_evaluations()
        scope.set_reason("action_evaluation_call_failed")
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.EVALUATION,
            FailureKind.CALL_FAILED,
            "action_evaluation_call_failed",
            exception_class=safe_exception_class(exc),
        )
        raise
    scope.record_evaluations(action=action_evaluation)
    try:
        task_evaluation = await validated_task_evaluation(task_evaluator, task, after)
    except asyncio.CancelledError:
        raise
    except ValueError as exc:
        scope.set_reason("task_evaluation_invalid")
        return Terminate(
            AgentLoopStatus.FAILED, "task_evaluation_invalid", str(exc),
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
    scope.record_evaluations(task=task_evaluation)
    state.current_task_evaluation = task_evaluation
    progress_event = record_execution_progress(
        session, selection, action_evaluation, after, task_evaluation,
    )
    scope.set_reason(f"action_{action_evaluation.status}")
    contextual_disposition = task_evaluation_disposition_for_world(
        task,
        task_evaluation,
        after,
        session.environment.observation_capabilities,
    )
    outcome = post_action_result(
        task, state, request, result, action_evaluation, task_evaluation,
        unknown_recoverable=(
            task_evaluation.status == TaskEvaluationStatus.UNKNOWN
            and contextual_disposition.status is None
        ),
    )
    if isinstance(outcome, Continue) and progress_event is not None and progress_event.strategy_transition_required:
        from affordance_runtime.agent.control_feedback import (
            ControlFeedbackSource,
            RecoveryConstraints,
            SemanticEffectSnapshot,
            route_feedback,
            selection_snapshot,
            strategy_feedback,
        )
        from affordance_runtime.world.public_semantic_digest import (
            public_action_contract_digest,
            public_world_semantic_digest,
            task_progress_fingerprint,
        )

        action_space = session.agent_loop.action_space_builder.build(task, after)
        page = session.agent_loop.context_builder.page(action_space, state)
        session.current_action_space = action_space
        session.current_action_page = page
        feedback = strategy_feedback(
            state,
            action_space,
            page,
            source=ControlFeedbackSource.ACTION_EVALUATION,
            code="action_no_effect_change_strategy",
            public_subject_id=selection.target_id,
            related_decision=selection_snapshot(decision, selection.target_id),
            semantic_effect=SemanticEffectSnapshot(
                result.dispatch_status.value,
                selection.semantic_effects,
                action_evaluation.status.value,
                public_world_semantic_digest(before) != public_world_semantic_digest(after),
                prior_action_space is None
                or public_action_contract_digest(before, prior_action_space)
                != public_action_contract_digest(after, action_space),
                task_progress_fingerprint(prior_task_evaluation)
                != task_progress_fingerprint(task_evaluation),
            ),
            recovery=RecoveryConstraints(
                repeat_previous_decision_allowed=False,
                retry_allowed=False,
                rollback_available=False,
                strategy_change_required=True,
                offered_action_ids=page.visible_action_ids,
            ),
        )
        outcome = route_feedback(state, scope, feedback)
    scope.set_reason(outcome.reason_code)
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
        session.state.install_observation(acquired.observation)
        scope.record_after(acquired.observation.observation_id)
        return Continue("binding_refreshed")
    return Terminate(
        AgentLoopStatus.FAILED,
        acquired.reason_code,
        acquired.reason_code,
        failure_code=acquired.failure_code,
    )


async def _reroute_not_sent(
    session: AgentRunSession,
    selection: AdmittedActionSelection,
    decision: SelectAction,
    request: BoundActionRequest,
    result: ActionResult,
    binder: ActionBinder,
    scope: ControlTransitionScope | ControlContinuationScope,
) -> tuple[AdmittedActionSelection, BoundActionRequest, ExecutionOutcome, WorldObservation] | LoopDirective:
    state = session.state
    before_id = state.current_observation.observation_id
    reroutable = {
        ActionError.STALE_BINDING,
        ActionError.CURRENTNESS_UNAVAILABLE,
        ActionError.RATE_LIMITED,
        ActionError.UNSUPPORTED_ACTION,
    }
    if result.error not in reroutable:
        scope.set_reason("action_not_dispatched")
        return Terminate(
            AgentLoopStatus.FAILED, "action_not_dispatched",
            "action was not dispatched",
            failure_stage=FailureStage.EXECUTION,
            failure_kind=FailureKind.CALL_FAILED,
        )
    before = state.current_observation
    current_selection = selection
    if result.error in {ActionError.STALE_BINDING, ActionError.CURRENTNESS_UNAVAILABLE}:
        acquired = await capture_for_session(
            session,
            before_id,
            WorldObservationRequest(
                ObservationRequestKind.CURRENTNESS_REFRESH,
                "stale route revalidation",
            ),
            scope,
        )
        if acquired.observation is None:
            return Terminate(
                AgentLoopStatus.FAILED, acquired.reason_code, acquired.reason_code,
                failure_code=acquired.failure_code,
            )
        before = acquired.observation
        state.install_observation(before)
        scope.record_after(before.observation_id)
        action_space = session.agent_loop.action_space_builder.build(session.task, before)
        option = _equivalent_option(action_space.options, selection)
        if option is None:
            scope.set_reason("route_revalidation_failed")
            return Terminate(
                AgentLoopStatus.FAILED, "route_revalidation_failed",
                "fresh ActionSpace has no equivalent semantic action",
                failure_stage=FailureStage.EXECUTION,
                failure_kind=FailureKind.INVALID_OUTPUT,
            )
        admission = session.agent_loop.action_space_builder.try_admit(
            option, dict(selection.parameters), selection.destination_id,
        )
        if admission.admitted is None:
            scope.set_reason("route_readmission_rejected")
            return Terminate(
                AgentLoopStatus.FAILED, "route_readmission_rejected",
                "fresh equivalent action failed normal admission",
                failure_stage=FailureStage.CONTROL,
                failure_kind=FailureKind.REJECTED,
            )
        current_selection = admission.admitted
    excluded_binding_ids = {request.binding.binding_id}
    if before.observation_id != before_id:
        different_surface = any(
            binding.binding_id in current_selection.eligible_binding_ids
            and binding.surface != request.binding.surface
            for binding in before.bindings
        )
        excluded_binding_ids = {
            binding.binding_id
            for binding in before.bindings
            if different_surface and binding.surface == request.binding.surface
        }
    try:
        alternate_request = binder.bind(
            current_selection,
            before,
            decision.context_id,
            excluded_binding_ids=frozenset(excluded_binding_ids),
        )
    except BindingError:
        scope.set_reason("no_equivalent_alternate_route")
        return Terminate(
            AgentLoopStatus.FAILED, "no_equivalent_alternate_route",
            "no current equivalent alternate route was available",
            failure_stage=FailureStage.EXECUTION,
            failure_kind=FailureKind.CALL_FAILED,
        )
    alternate_outcome = await _execute_boundary(
        session, alternate_request, before.observation_id, scope,
    )
    return current_selection, alternate_request, alternate_outcome, before


def _equivalent_option(
    options: tuple[ActionOption, ...],
    previous: AdmittedActionSelection,
) -> ActionOption | None:
    return next((
        option for option in options
        if option.semantic_action == previous.semantic_action
        and option.target_id == previous.target_id
        and option.effect_category == previous.effect_category
        and option.semantic_effects == previous.semantic_effects
        and option.schema_digest == previous.schema_digest
        and option.observation_barrier == previous.observation_barrier
        and option.destination_required == previous.destination_required
        and option.eligible_destination_ids == previous.eligible_destination_ids
        and option.verification_contract_digest == previous.verification_contract_digest
        and _risk_rank(option.risk) <= _risk_rank(previous.risk)
    ), None)


def _risk_rank(risk: object) -> int:
    return ("low", "medium", "high", "irreversible").index(str(risk))


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
        exception_class = safe_exception_class(exc)
        _record_execute_exception(
            session, scope, request, attempt_id,
            AttemptDisposition.THREW, "execute_exception", exception_class,
        )
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.EXECUTION,
            FailureKind.CALL_FAILED,
            "execute_exception",
            exception_class=exception_class,
        )
        raise
    if not isinstance(outcome, ExecutionOutcome) or not isinstance(outcome.result, ActionResult):
        _record_execute_exception(
            session, scope, request, attempt_id,
            AttemptDisposition.MALFORMED, "execute_malformed", "",
        )
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.EXECUTION,
            FailureKind.INVALID_OUTPUT,
            "execute_malformed",
        )
        raise TypeError("WorldEnvironment.execute returned a malformed contract")
    result = outcome.result
    request_lineage_valid = (
        result.request_id == request.request_id
        and result.backend == request.binding.executor_id
    )
    public_result = ActionResult(
        safe_boundary_identity(result.request_id, request.request_id, kind="request"),
        result.dispatch_status,
        safe_boundary_identity(result.backend, request.binding.executor_id, kind="backend"),
        result.transport_success,
        result.error,
    )
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
        public_result.request_id,
        request_lineage_valid,
        acquisition_status=primary.status,
    )
    session.accounting.record(receipt)
    scope.record_execution_receipt(receipt, request.request_id, request.intent, public_result)
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
