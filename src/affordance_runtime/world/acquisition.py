"""Typed values for the target world's observation acquisition lifecycle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.world.contracts import WorldObservation

_REASON_CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_PRIVATE_MARKERS = (
    "credential", "password", "payload", "secret", "selector", "token", "url",
)


class AcquisitionStatus(StrEnum):
    ACQUIRED = "acquired"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    FAILED = "failed"


class AcquisitionOrigin(StrEnum):
    RESET = "reset"
    INDEPENDENT_CAPTURE = "independent_capture"
    POST_ACTION = "post_action"


class ObservationRequestKind(StrEnum):
    POLICY_REQUEST = "policy_request"
    WAIT_REFRESH = "wait_refresh"
    BINDING_REFRESH = "binding_refresh"
    CURRENTNESS_REFRESH = "currentness_refresh"
    CONFIRMATION_REFRESH = "confirmation_refresh"
    POST_ACTION_FALLBACK = "post_action_fallback"


@dataclass(frozen=True)
class WorldObservationRequest:
    kind: ObservationRequestKind
    reason: str
    subject_id: str = ""
    modality: str = ""
    required_assurance: str = ""


@dataclass(frozen=True, order=True)
class ObservationOffer:
    source: str
    modality: str
    assurance: str
    acquisition_cost: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (
            self.source, self.modality, self.assurance, self.acquisition_cost,
        )):
            raise ValueError("observation offer fields cannot be blank")


@dataclass(frozen=True)
class ObservationCapabilities:
    independent_capture: bool
    post_action_observation: bool
    offers: tuple[ObservationOffer, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "offers", tuple(self.offers))


@dataclass(frozen=True)
class ObservationAcquisition:
    status: AcquisitionStatus
    origin: AcquisitionOrigin
    observation: WorldObservation | None
    reason_code: str

    def __post_init__(self) -> None:
        acquired = self.status is AcquisitionStatus.ACQUIRED
        if acquired != (self.observation is not None):
            raise ValueError("ACQUIRED requires an observation and other statuses forbid one")
        _validate_reason_code(self.reason_code)


@dataclass(frozen=True)
class ExecutionOutcome:
    result: ActionResult
    post_acquisition: ObservationAcquisition

    def __post_init__(self) -> None:
        if self.post_acquisition.origin is not AcquisitionOrigin.POST_ACTION:
            raise ValueError("execution post acquisition must have POST_ACTION origin")


def _validate_reason_code(value: str) -> None:
    if len(value) > 64 or _REASON_CODE.fullmatch(value) is None:
        raise ValueError("reason_code must be a bounded stable snake-case code")
    if any(marker in value for marker in _PRIVATE_MARKERS):
        raise ValueError("reason_code must not name private or secret-bearing data")
