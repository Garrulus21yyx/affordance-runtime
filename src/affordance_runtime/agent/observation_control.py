"""Runtime-owned acquisition admission, freshness validation, and typed mapping."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

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
    AcquisitionCancelled,
    AcquisitionOrigin,
    AcquisitionStage,
    AcquisitionStatus,
    ObservationAcquisition,
    ObservationRequestKind,
    WorldObservationRequest,
)
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.environment import WorldEnvironment


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    REUSED = "reused"
    NOT_ACQUIRED = "not_acquired"
    ORIGIN_MISMATCH = "origin_mismatch"


class AcquisitionRelationship(StrEnum):
    POST_ACTION_FALLBACK = "post_action_fallback"


@dataclass(frozen=True)
class LinkedAcquisition:
    relationship: AcquisitionRelationship
    primary_acquisition_id: str
    acquisition: ObservationAcquisition

    def __post_init__(self) -> None:
        if self.relationship is not AcquisitionRelationship.POST_ACTION_FALLBACK:
            raise ValueError("linked acquisition relationship is unsupported")
        if not isinstance(self.acquisition, ObservationAcquisition):
            raise TypeError("linked acquisition must retain the exact aggregate")
        if not self.primary_acquisition_id.strip():
            raise ValueError("linked fallback requires its primary acquisition identity")
        if self.primary_acquisition_id == self.acquisition.acquisition_id:
            raise ValueError("linked fallback requires a distinct acquisition identity")


@dataclass(frozen=True)
class FreshObservationOutcome:
    acquisition: ObservationAcquisition
    expected_origin: AcquisitionOrigin
    freshness: FreshnessStatus
    failure_code: AgentFailureCode | None = None
    linked_fallback: LinkedAcquisition | None = None
    consumed_acquisition_id: str = ""

    @property
    def consumed_acquisition(self) -> ObservationAcquisition:
        if self.linked_fallback is not None and (
            self.consumed_acquisition_id == self.linked_fallback.acquisition.acquisition_id
        ):
            return self.linked_fallback.acquisition
        return self.acquisition

    @property
    def observation(self) -> WorldObservation | None:
        if self.freshness is not FreshnessStatus.FRESH:
            return None
        return self.consumed_acquisition.observation

    @property
    def attempts(self) -> int:
        return _physical_attempt_count(self.acquisition) + (
            0 if self.linked_fallback is None else _physical_attempt_count(self.linked_fallback.acquisition)
        )

    @property
    def status(self) -> AcquisitionStatus:
        if self.freshness in {FreshnessStatus.REUSED, FreshnessStatus.ORIGIN_MISMATCH}:
            return AcquisitionStatus.FAILED
        return self.consumed_acquisition.status

    @property
    def reason_code(self) -> str:
        if self.freshness is FreshnessStatus.REUSED:
            return "observation_identity_reused"
        if self.freshness is FreshnessStatus.ORIGIN_MISMATCH:
            return (
                "post_action_origin_invalid"
                if self.expected_origin is AcquisitionOrigin.POST_ACTION
                else "independent_capture_origin_invalid"
            )
        return self.consumed_acquisition.reason_code

    @property
    def used_fallback(self) -> bool:
        return self.linked_fallback is not None

    @property
    def actual_origin(self) -> AcquisitionOrigin:
        return self.consumed_acquisition.origin

    @property
    def request_kind(self) -> ObservationRequestKind:
        return self.consumed_acquisition.request.kind


async def capture_fresh(
    environment: WorldEnvironment,
    previous_id: str,
    request: WorldObservationRequest,
) -> FreshObservationOutcome:
    acquisition = await environment.capture(request)
    fresh = validate_fresh_acquisition(
        acquisition,
        previous_id,
        expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
        attempts_override=1,
    )
    return fresh


def validate_fresh_acquisition(
    acquisition: ObservationAcquisition,
    previous_id: str,
    *,
    expected_origin: AcquisitionOrigin,
    post_action: bool = False,
    attempts_override: int | None = None,
) -> FreshObservationOutcome:
    del attempts_override
    if acquisition.origin is not expected_origin:
        return FreshObservationOutcome(
            acquisition,
            expected_origin,
            FreshnessStatus.ORIGIN_MISMATCH,
            AgentFailureCode.POST_ACTION_ORIGIN_INVALID if post_action else AgentFailureCode.OBSERVATION_ORIGIN_INVALID,
        )
    if acquisition.status is AcquisitionStatus.ACQUIRED:
        assert acquisition.observation is not None
        if acquisition.observation.observation_id == previous_id:
            return FreshObservationOutcome(
                acquisition,
                expected_origin,
                FreshnessStatus.REUSED,
                _failure_code(AcquisitionStatus.ACQUIRED, post_action, freshness=True),
            )
        return FreshObservationOutcome(
            acquisition,
            expected_origin,
            FreshnessStatus.FRESH,
        )
    return FreshObservationOutcome(
        acquisition,
        expected_origin,
        FreshnessStatus.NOT_ACQUIRED,
        _failure_code(acquisition.status, post_action),
    )


def acquisition_attempt_count(acquisition: ObservationAcquisition) -> int:
    return _physical_attempt_count(acquisition)


def no_fresh_after_result(
    session,
    decision,
    request,
    result,
    acquisition: FreshObservationOutcome,
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


def _failure_code(
    status: AcquisitionStatus,
    post_action: bool,
    *,
    freshness: bool = False,
) -> AgentFailureCode:
    if freshness:
        return (
            AgentFailureCode.POST_ACTION_FRESHNESS_INVALID
            if post_action
            else AgentFailureCode.OBSERVATION_FRESHNESS_INVALID
        )
    if status is AcquisitionStatus.CAPABILITY_UNAVAILABLE:
        return (
            AgentFailureCode.POST_ACTION_CAPABILITY_UNAVAILABLE
            if post_action
            else AgentFailureCode.OBSERVATION_CAPABILITY_UNAVAILABLE
        )
    return (
        AgentFailureCode.POST_ACTION_ACQUISITION_FAILED
        if post_action
        else AgentFailureCode.OBSERVATION_ACQUISITION_FAILED
    )


def _post_action_fallback_failure(
    primary: FreshObservationOutcome,
    fallback: FreshObservationOutcome,
) -> FreshObservationOutcome:
    if fallback.failure_code is AgentFailureCode.OBSERVATION_FRESHNESS_INVALID:
        failure_code = AgentFailureCode.POST_ACTION_FRESHNESS_INVALID
    elif fallback.failure_code is AgentFailureCode.OBSERVATION_ORIGIN_INVALID:
        failure_code = AgentFailureCode.POST_ACTION_ORIGIN_INVALID
    else:
        failure_code = _failure_code(fallback.status, True)
    linked = LinkedAcquisition(
        AcquisitionRelationship.POST_ACTION_FALLBACK,
        primary.acquisition.acquisition_id,
        fallback.acquisition,
    )
    return FreshObservationOutcome(
        primary.acquisition,
        primary.expected_origin,
        fallback.freshness,
        failure_code,
        linked,
        fallback.acquisition.acquisition_id,
    )


def post_action_fallback_result(
    primary: FreshObservationOutcome,
    fallback: FreshObservationOutcome,
) -> FreshObservationOutcome:
    if fallback.observation is not None:
        linked = LinkedAcquisition(
            AcquisitionRelationship.POST_ACTION_FALLBACK,
            primary.acquisition.acquisition_id,
            fallback.acquisition,
        )
        return FreshObservationOutcome(
            primary.acquisition,
            primary.expected_origin,
            FreshnessStatus.FRESH,
            linked_fallback=linked,
            consumed_acquisition_id=fallback.acquisition.acquisition_id,
        )
    return _post_action_fallback_failure(primary, fallback)


async def capture_for_session(
    session,
    previous_id: str,
    request: WorldObservationRequest,
    scope: ControlTransitionScope | ControlContinuationScope,
) -> FreshObservationOutcome:
    """Perform and monotonically account one Runtime-owned capture boundary."""
    attempt_id = session.accounting.next_attempt_id()
    try:
        acquisition = await session.environment.capture(request)
    except asyncio.CancelledError as exc:
        acquisition = exc.acquisition if isinstance(exc, AcquisitionCancelled) else None
        if acquisition is not None and acquisition.request is not request:
            _record_capture_exception(
                session,
                scope,
                request,
                attempt_id,
                "capture_malformed",
                AttemptDisposition.MALFORMED,
                "",
            )
            session.pending_runtime_failure = RuntimeFailure(
                FailureStage.ACQUISITION,
                FailureKind.INVALID_OUTPUT,
                "capture_malformed",
            )
            raise TypeError("WorldEnvironment.capture returned a foreign request authority") from exc
        if acquisition is not None:
            scope.record_acquisition(acquisition)
        _record_capture_exception(
            session,
            scope,
            request,
            attempt_id,
            "capture_cancelled",
            AttemptDisposition.CANCELLED,
            "CancelledError",
            acquisition,
        )
        raise
    except Exception as exc:
        exception_class = safe_exception_class(exc)
        _record_capture_exception(
            session,
            scope,
            request,
            attempt_id,
            "capture_exception",
            AttemptDisposition.THREW,
            exception_class,
        )
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.ACQUISITION,
            FailureKind.CALL_FAILED,
            "capture_exception",
            exception_class=exception_class,
        )
        raise
    if not isinstance(acquisition, ObservationAcquisition) or acquisition.request is not request:
        _record_capture_exception(
            session,
            scope,
            request,
            attempt_id,
            "capture_malformed",
            AttemptDisposition.MALFORMED,
            "",
        )
        session.pending_runtime_failure = RuntimeFailure(
            FailureStage.ACQUISITION,
            FailureKind.INVALID_OUTPUT,
            "capture_malformed",
        )
        raise TypeError("WorldEnvironment.capture returned a malformed contract")
    acquired = validate_fresh_acquisition(
        acquisition,
        previous_id,
        expected_origin=AcquisitionOrigin.INDEPENDENT_CAPTURE,
        attempts_override=1,
    )
    receipt = AttemptReceipt(
        attempt_id,
        AttemptOperation.CAPTURE,
        str(request.kind),
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        (
            None
            if acquired.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE and not acquired.attempts
            else acquired.actual_origin
        ),
        AttemptDisposition.RETURNED,
        acquired.reason_code,
        acquired.attempts,
        0,
        0,
        0,
        acquisition_status=(
            AcquisitionStatus.FAILED
            if acquired.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE and acquired.attempts
            else acquired.status
        ),
    )
    session.accounting.record(receipt)
    scope.record_attempt(receipt, acquisition)
    return acquired


def _record_capture_exception(
    session,
    scope,
    request,
    attempt_id: str,
    reason_code: str,
    disposition: AttemptDisposition,
    exception_class: str,
    acquisition: ObservationAcquisition | None = None,
) -> None:
    receipt = AttemptReceipt(
        attempt_id,
        AttemptOperation.CAPTURE,
        str(request.kind),
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        acquisition.origin if acquisition is not None else None,
        disposition,
        reason_code,
        acquisition_attempt_count(acquisition) if acquisition is not None else 1,
        0,
        0,
        0,
        exception_class=exception_class,
        acquisition_status=(acquisition.status if acquisition is not None else AcquisitionStatus.FAILED),
    )
    session.accounting.record(receipt)
    scope.record_attempt(receipt)


def _physical_attempt_count(acquisition: ObservationAcquisition) -> int:
    return int(acquisition.stage is not AcquisitionStage.PRE_SELECTION_UNAVAILABLE)
