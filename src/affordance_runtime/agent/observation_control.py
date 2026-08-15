"""Runtime-owned acquisition admission, freshness validation, and typed mapping."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from affordance_runtime.agent.attempt_receipt import (
    AttemptDisposition,
    AttemptOperation,
    AttemptReceipt,
    safe_exception_class,
)
from affordance_runtime.agent.control_outcome import Pause
from affordance_runtime.agent.control_transition import (
    ControlContinuationScope,
    ControlTransitionScope,
)
from affordance_runtime.agent.result_code import AgentFailureCode
from affordance_runtime.agent.runtime_failure import (
    FailureKind,
    FailureStage,
    RuntimeFailure,
)
from affordance_runtime.agent.state import AgentLoopStatus
from affordance_runtime.world.acquisition import (
    AcquisitionOrigin,
    AcquisitionStatus,
    ObservationAcquisition,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.source_profile import assurance_satisfies


@dataclass(frozen=True)
class FreshAcquisition:
    observation: WorldObservation | None
    attempts: int
    status: AcquisitionStatus
    reason_code: str
    failure_code: AgentFailureCode | None = None
    used_fallback: bool = False
    expected_origin: AcquisitionOrigin | None = None
    actual_origin: AcquisitionOrigin | None = None
    request_kind: ObservationRequestKind | None = None


async def capture_fresh(
    environment: WorldEnvironment,
    previous_id: str,
    request: WorldObservationRequest,
) -> FreshAcquisition:
    unavailable = capture_admission_failure(environment, request)
    if unavailable is not None:
        return unavailable
    acquisition = await environment.capture(request)
    fresh = validate_fresh_acquisition(
        acquisition,
        previous_id,
        expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
        attempts_override=1,
    )
    return _with_request(fresh, request.kind)


def validate_fresh_acquisition(
    acquisition: ObservationAcquisition,
    previous_id: str,
    *,
    expected_origin: AcquisitionOrigin,
    post_action: bool = False,
    attempts_override: int | None = None,
) -> FreshAcquisition:
    attempts = (
        acquisition_attempt_count(acquisition)
        if attempts_override is None else attempts_override
    )
    if acquisition.origin is not expected_origin:
        return FreshAcquisition(
            None,
            attempts,
            AcquisitionStatus.FAILED,
            "post_action_origin_invalid"
            if post_action else "independent_capture_origin_invalid",
            AgentFailureCode.POST_ACTION_ORIGIN_INVALID
            if post_action else AgentFailureCode.OBSERVATION_ORIGIN_INVALID,
            expected_origin=expected_origin,
            actual_origin=acquisition.origin,
        )
    if acquisition.status is AcquisitionStatus.ACQUIRED:
        assert acquisition.observation is not None
        if acquisition.observation.observation_id == previous_id:
            return FreshAcquisition(
                None,
                attempts,
                AcquisitionStatus.FAILED,
                "observation_identity_reused",
                _failure_code(AcquisitionStatus.ACQUIRED, post_action, freshness=True),
                expected_origin=expected_origin,
                actual_origin=acquisition.origin,
            )
        return FreshAcquisition(
            acquisition.observation, attempts, acquisition.status, acquisition.reason_code,
            expected_origin=expected_origin,
            actual_origin=acquisition.origin,
        )
    return FreshAcquisition(
        None,
        attempts,
        acquisition.status,
        acquisition.reason_code,
        _failure_code(acquisition.status, post_action),
        expected_origin=expected_origin,
        actual_origin=acquisition.origin,
    )


def acquisition_attempt_count(acquisition: ObservationAcquisition) -> int:
    return int(acquisition.status in {AcquisitionStatus.ACQUIRED, AcquisitionStatus.FAILED})


def no_fresh_after_result(
    session,
    decision,
    request,
    result,
    acquisition: FreshAcquisition,
    scope: ControlTransitionScope | ControlContinuationScope,
):
    state = session.state
    state.set_pending_unknown_effect(request)
    return Pause(
        AgentLoopStatus.WAITING_USER,
        acquisition.reason_code,
        acquisition.reason_code,
        failure_code=acquisition.failure_code,
    )


def capture_admission_failure(
    environment: WorldEnvironment,
    request: WorldObservationRequest,
) -> FreshAcquisition | None:
    capabilities = environment.observation_capabilities
    if not capabilities.independent_capture:
        return _unavailable("independent_capture_unsupported")
    if request.kind is not ObservationRequestKind.POLICY_REQUEST:
        return None
    if not request.needs:
        return None
    offered = all(
        any(
            (need.required_modality is None or offer.modality is need.required_modality)
            and need.purpose in offer.supported_purposes
            and assurance_satisfies(offer.assurance, need.required_assurance)
            for offer in capabilities.offers
        )
        for need in request.needs
    )
    return None if offered else _unavailable("observation_capability_not_offered")


def _unavailable(reason_code: str) -> FreshAcquisition:
    return FreshAcquisition(
        None,
        0,
        AcquisitionStatus.CAPABILITY_UNAVAILABLE,
        reason_code,
        AgentFailureCode.OBSERVATION_CAPABILITY_UNAVAILABLE,
        expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
    )


def _failure_code(
    status: AcquisitionStatus,
    post_action: bool,
    *,
    freshness: bool = False,
) -> AgentFailureCode:
    if freshness:
        return (
            AgentFailureCode.POST_ACTION_FRESHNESS_INVALID
            if post_action else AgentFailureCode.OBSERVATION_FRESHNESS_INVALID
        )
    if status is AcquisitionStatus.CAPABILITY_UNAVAILABLE:
        return (
            AgentFailureCode.POST_ACTION_CAPABILITY_UNAVAILABLE
            if post_action else AgentFailureCode.OBSERVATION_CAPABILITY_UNAVAILABLE
        )
    return (
        AgentFailureCode.POST_ACTION_ACQUISITION_FAILED
        if post_action else AgentFailureCode.OBSERVATION_ACQUISITION_FAILED
    )


def _post_action_fallback_failure(
    primary: FreshAcquisition,
    fallback: FreshAcquisition,
) -> FreshAcquisition:
    if fallback.failure_code is AgentFailureCode.OBSERVATION_FRESHNESS_INVALID:
        failure_code = AgentFailureCode.POST_ACTION_FRESHNESS_INVALID
    elif fallback.failure_code is AgentFailureCode.OBSERVATION_ORIGIN_INVALID:
        failure_code = AgentFailureCode.POST_ACTION_ORIGIN_INVALID
    else:
        failure_code = _failure_code(fallback.status, True)
    return FreshAcquisition(
        None,
        primary.attempts + fallback.attempts,
        fallback.status,
        fallback.reason_code,
        failure_code,
        True,
        fallback.expected_origin,
        fallback.actual_origin,
        fallback.request_kind,
    )


def post_action_fallback_result(
    primary: FreshAcquisition,
    fallback: FreshAcquisition,
) -> FreshAcquisition:
    if fallback.observation is not None:
        return FreshAcquisition(
            fallback.observation,
            primary.attempts + fallback.attempts,
            fallback.status,
            fallback.reason_code,
            used_fallback=True,
            expected_origin=fallback.expected_origin,
            actual_origin=fallback.actual_origin,
            request_kind=fallback.request_kind,
        )
    return _post_action_fallback_failure(primary, fallback)


async def capture_for_session(
    session,
    previous_id: str,
    request: WorldObservationRequest,
    scope: ControlTransitionScope | ControlContinuationScope,
) -> FreshAcquisition:
    """Perform and monotonically account one Runtime-owned capture boundary."""
    unavailable = capture_admission_failure(session.environment, request)
    if unavailable is not None:
        scope.record_acquisition(
            unavailable.status,
            unavailable.actual_origin,
            unavailable.reason_code,
            0,
            request.kind,
            expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
        )
        return _with_request(unavailable, request.kind)
    attempt_id = session.accounting.next_attempt_id()
    try:
        acquisition = await session.environment.capture(request)
    except asyncio.CancelledError:
        _record_capture_exception(
            session, scope, request, attempt_id, "capture_cancelled",
            AttemptDisposition.CANCELLED, "CancelledError",
        )
        raise
    except Exception as exc:
        exception_class = safe_exception_class(exc)
        _record_capture_exception(
            session, scope, request, attempt_id, "capture_exception",
            AttemptDisposition.THREW, exception_class,
        )
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.ACQUISITION,
            FailureKind.CALL_FAILED,
            "capture_exception",
            exception_class=exception_class,
        )
        raise
    if not isinstance(acquisition, ObservationAcquisition):
        _record_capture_exception(
            session, scope, request, attempt_id, "capture_malformed",
            AttemptDisposition.MALFORMED, "",
        )
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.ACQUISITION,
            FailureKind.INVALID_OUTPUT,
            "capture_malformed",
        )
        raise TypeError("WorldEnvironment.capture returned a malformed contract")
    acquired = _with_request(
        validate_fresh_acquisition(
            acquisition,
            previous_id,
            expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
            attempts_override=1,
        ),
        request.kind,
    )
    receipt = AttemptReceipt(
        attempt_id,
        AttemptOperation.CAPTURE,
        str(request.kind),
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        acquired.actual_origin,
        AttemptDisposition.RETURNED,
        acquired.reason_code,
        1,
        0,
        0,
        0,
        acquisition_status=acquired.status,
    )
    session.accounting.record(receipt)
    scope.record_attempt(receipt)
    return acquired


def _record_capture_exception(
    session, scope, request, attempt_id: str, reason_code: str,
    disposition: AttemptDisposition, exception_class: str,
) -> None:
    receipt = AttemptReceipt(
        attempt_id,
        AttemptOperation.CAPTURE,
        str(request.kind),
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        None,
        disposition,
        reason_code,
        1,
        0,
        0,
        0,
        exception_class=exception_class,
        acquisition_status=AcquisitionStatus.FAILED,
    )
    session.accounting.record(receipt)
    scope.record_attempt(receipt)


def _with_request(
    acquisition: FreshAcquisition,
    request_kind: ObservationRequestKind,
) -> FreshAcquisition:
    return FreshAcquisition(
        acquisition.observation,
        acquisition.attempts,
        acquisition.status,
        acquisition.reason_code,
        acquisition.failure_code,
        acquisition.used_fallback,
        acquisition.expected_origin,
        acquisition.actual_origin,
        request_kind,
    )
