"""Runtime-owned acquisition admission, freshness validation, and typed mapping."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.agent.result import AgentFailureCode, build_result
from affordance_runtime.agent.state import AgentLoopStatus, Turn
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


async def capture_fresh(
    environment: WorldEnvironment,
    previous_id: str,
    request: WorldObservationRequest,
) -> FreshAcquisition:
    unavailable = capture_admission_failure(environment, request)
    if unavailable is not None:
        return unavailable
    acquisition = await environment.capture(request)
    return validate_fresh_acquisition(
        acquisition,
        previous_id,
        expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
    )


def validate_fresh_acquisition(
    acquisition: ObservationAcquisition,
    previous_id: str,
    *,
    expected_origin: AcquisitionOrigin,
    post_action: bool = False,
) -> FreshAcquisition:
    attempts = acquisition_attempt_count(acquisition)
    if acquisition.origin is not expected_origin:
        return FreshAcquisition(
            None,
            attempts,
            AcquisitionStatus.FAILED,
            "post_action_origin_invalid"
            if post_action else "independent_capture_origin_invalid",
            AgentFailureCode.POST_ACTION_ORIGIN_INVALID
            if post_action else AgentFailureCode.OBSERVATION_ORIGIN_INVALID,
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
            )
        return FreshAcquisition(
            acquisition.observation, attempts, acquisition.status, acquisition.reason_code,
        )
    return FreshAcquisition(
        None,
        attempts,
        acquisition.status,
        acquisition.reason_code,
        _failure_code(acquisition.status, post_action),
    )


async def post_action_observation(
    environment: WorldEnvironment,
    previous_id: str,
    post_acquisition: ObservationAcquisition,
    attempt_budget: int,
) -> FreshAcquisition:
    primary = validate_fresh_acquisition(
        post_acquisition,
        previous_id,
        expected_origin=AcquisitionOrigin.POST_ACTION,
        post_action=True,
    )
    if primary.observation is not None:
        return primary
    if (
        not environment.observation_capabilities.independent_capture
        or primary.attempts >= attempt_budget
    ):
        return primary
    fallback = await capture_fresh(
        environment,
        previous_id,
        WorldObservationRequest(
            ObservationRequestKind.POST_ACTION_FALLBACK,
            "post action acquisition fallback",
        ),
    )
    if fallback.observation is not None:
        return FreshAcquisition(
            fallback.observation,
            primary.attempts + fallback.attempts,
            fallback.status,
            fallback.reason_code,
        )
    return _post_action_fallback_failure(primary, fallback)


def acquisition_attempt_count(acquisition: ObservationAcquisition) -> int:
    return int(acquisition.status in {AcquisitionStatus.ACQUIRED, AcquisitionStatus.FAILED})


def no_fresh_after_result(session, decision, request, result, acquisition: FreshAcquisition):
    state = session.state
    state.append_turn(
        Turn(
            state.current_observation.observation_id,
            decision,
            request.intent,
            request.request_id,
            result,
        )
    )
    state.set_pending_unknown_effect(request)
    return build_result(
        AgentLoopStatus.WAITING_USER,
        session.task,
        state,
        0,
        0,
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
    offered = any(
        offer.modality == request.modality
        and assurance_satisfies(offer.assurance, request.required_assurance)
        for offer in capabilities.offers
    )
    return None if offered else _unavailable("observation_capability_not_offered")


def _unavailable(reason_code: str) -> FreshAcquisition:
    return FreshAcquisition(
        None,
        0,
        AcquisitionStatus.CAPABILITY_UNAVAILABLE,
        reason_code,
        AgentFailureCode.OBSERVATION_CAPABILITY_UNAVAILABLE,
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
    )
