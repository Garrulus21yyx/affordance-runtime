"""Typed values for the target world's observation acquisition lifecycle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.world.contracts import SurfaceObservation, WorldObservation

_REASON_CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_PRIVATE_MARKERS = (
    "credential", "password", "payload", "secret", "selector", "token", "url",
)


class AcquisitionStatus(StrEnum):
    ACQUIRED = "acquired"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    FAILED = "failed"


class SourceAcquisitionStatus(StrEnum):
    NOT_ACQUIRED = "not_acquired"
    ACQUIRED = "acquired"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    FAILED = "failed"


class SourceRequirement(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    UNSELECTED = "unselected"


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
    acquisition_group: str = ""

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (
            self.source, self.modality, self.assurance, self.acquisition_cost,
        )):
            raise ValueError("observation offer fields cannot be blank")


@dataclass(frozen=True)
class SourceSelection:
    source: str
    requirement: SourceRequirement
    reason_code: str

    def __post_init__(self) -> None:
        if not self.source.strip() or not isinstance(self.requirement, SourceRequirement):
            raise ValueError("source selection requires typed source identity")
        _validate_reason_code(self.reason_code)


@dataclass(frozen=True)
class ObservationSelectionPlan:
    selections: tuple[SourceSelection, ...]
    max_source_calls: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "selections", tuple(self.selections))
        if self.max_source_calls < 1 or len(self.selections) > self.max_source_calls:
            raise ValueError("source selection exceeds its bounded call budget")
        if len({item.source for item in self.selections}) != len(self.selections):
            raise ValueError("source selection cannot repeat a source")


@dataclass(frozen=True)
class SourceAcquisitionResult:
    source: str
    requirement: SourceRequirement
    status: SourceAcquisitionStatus
    reason_code: str
    observation: SurfaceObservation | None = None

    def __post_init__(self) -> None:
        if not self.source.strip() or not isinstance(self.requirement, SourceRequirement):
            raise ValueError("source acquisition requires typed source identity")
        if not isinstance(self.status, SourceAcquisitionStatus):
            raise TypeError("source acquisition status must be typed")
        acquired = self.status is SourceAcquisitionStatus.ACQUIRED
        if acquired != isinstance(self.observation, SurfaceObservation):
            raise ValueError("source ACQUIRED requires exactly one observation")
        if (self.requirement is SourceRequirement.UNSELECTED) != (
            self.status is SourceAcquisitionStatus.NOT_ACQUIRED
        ):
            raise ValueError("only unselected sources may be NOT_ACQUIRED")
        _validate_reason_code(self.reason_code)


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
    selection_plan: ObservationSelectionPlan | None = None
    source_results: tuple[SourceAcquisitionResult, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, AcquisitionStatus):
            raise TypeError("acquisition status must be typed")
        if not isinstance(self.origin, AcquisitionOrigin):
            raise TypeError("acquisition origin must be typed")
        acquired = self.status is AcquisitionStatus.ACQUIRED
        if acquired != isinstance(self.observation, WorldObservation):
            raise ValueError(
                "ACQUIRED requires a WorldObservation and other statuses forbid one"
            )
        _validate_reason_code(self.reason_code)
        object.__setattr__(self, "source_results", tuple(self.source_results))
        if self.selection_plan is not None and not isinstance(
            self.selection_plan, ObservationSelectionPlan
        ):
            raise TypeError("acquisition selection plan must be typed")


@dataclass(frozen=True)
class ExecutionOutcome:
    result: ActionResult
    post_acquisition: ObservationAcquisition

    def __post_init__(self) -> None:
        if not isinstance(self.result, ActionResult):
            raise TypeError("execution outcome result must be typed")
        if not isinstance(self.post_acquisition, ObservationAcquisition):
            raise TypeError("execution post acquisition must be typed")
        if self.post_acquisition.origin is not AcquisitionOrigin.POST_ACTION:
            raise ValueError("execution post acquisition must have POST_ACTION origin")


def _validate_reason_code(value: str) -> None:
    if len(value) > 64 or _REASON_CODE.fullmatch(value) is None:
        raise ValueError("reason_code must be a bounded stable snake-case code")
    if any(marker in value for marker in _PRIVATE_MARKERS):
        raise ValueError("reason_code must not name private or secret-bearing data")
