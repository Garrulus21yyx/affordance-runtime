"""Typed values for the target world's observation acquisition lifecycle."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.execution.contracts import ActionResult
from affordance_runtime.world.contracts import SurfaceObservation, WorldObservation
from affordance_runtime.world.observation_needs import ObservationNeed, ObservationPurpose
from affordance_runtime.world.source_profile import AcquisitionCost, ObservationAssurance, ObservationModality

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
    needs: tuple[ObservationNeed, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObservationRequestKind):
            raise TypeError("observation request kind must be typed")
        if not self.reason.strip() or len(self.reason) > 500:
            raise ValueError("observation request requires a bounded reason")
        object.__setattr__(self, "needs", tuple(self.needs))
        if any(not isinstance(item, ObservationNeed) for item in self.needs):
            raise TypeError("observation request needs must be typed")
        if len({item.need_id for item in self.needs}) != len(self.needs):
            raise ValueError("observation request need IDs cannot repeat")


@dataclass(frozen=True, order=True)
class ObservationOffer:
    source: str
    modality: ObservationModality | str
    assurance: ObservationAssurance | str
    acquisition_cost: AcquisitionCost | str
    acquisition_group: str = ""
    supported_purposes: tuple[ObservationPurpose, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("observation offer source cannot be blank")
        try:
            modality = ObservationModality(self.modality)
            assurance = ObservationAssurance(self.assurance)
            acquisition_cost = AcquisitionCost(self.acquisition_cost)
        except ValueError as exc:
            raise ValueError("observation offer requires typed quality fields") from exc
        object.__setattr__(self, "modality", modality)
        object.__setattr__(self, "assurance", assurance)
        object.__setattr__(self, "acquisition_cost", acquisition_cost)
        purposes = tuple(self.supported_purposes) or _default_purposes(modality)
        if any(not isinstance(item, ObservationPurpose) for item in purposes):
            raise TypeError("observation offer purposes must be typed")
        object.__setattr__(self, "supported_purposes", purposes)


@dataclass(frozen=True)
class SourceSelection:
    source: str
    requirement: SourceRequirement
    reason_code: str
    need_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip() or not isinstance(self.requirement, SourceRequirement):
            raise ValueError("source selection requires typed source identity")
        _validate_reason_code(self.reason_code)
        object.__setattr__(self, "need_ids", tuple(self.need_ids))
        if any(not item.strip() for item in self.need_ids):
            raise ValueError("selected observation need IDs cannot be blank")


@dataclass(frozen=True)
class ObservationSelectionPlan:
    selections: tuple[SourceSelection, ...]
    unselected: tuple[SourceSelection, ...]
    acquisition_budget: int
    needs: tuple[ObservationNeed, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "selections", tuple(self.selections))
        object.__setattr__(self, "unselected", tuple(self.unselected))
        object.__setattr__(self, "needs", tuple(self.needs))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if self.acquisition_budget < 1 or len(self.selections) > self.acquisition_budget:
            raise ValueError("source selection exceeds its bounded call budget")
        if len({item.source for item in self.selections}) != len(self.selections):
            raise ValueError("source selection cannot repeat a source")
        if any(item.requirement is SourceRequirement.UNSELECTED for item in self.selections):
            raise ValueError("selected sources cannot have UNSELECTED requirement")
        if any(item.requirement is not SourceRequirement.UNSELECTED for item in self.unselected):
            raise ValueError("unselected offers require UNSELECTED requirement")
        all_sources = self.selections + self.unselected
        if len({item.source for item in all_sources}) != len(all_sources):
            raise ValueError("selection plan source disposition must be unique")
        if len({item.need_id for item in self.needs}) != len(self.needs):
            raise ValueError("selection plan need IDs cannot repeat")
        known_needs = {item.need_id for item in self.needs}
        if any(set(item.need_ids) - known_needs for item in all_sources):
            raise ValueError("source selection references an unknown observation need")
        for reason_code in self.reason_codes:
            _validate_reason_code(reason_code)

    @property
    def need_ids(self) -> tuple[str, ...]:
        return tuple(item.need_id for item in self.needs)


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


def _default_purposes(modality: ObservationModality) -> tuple[ObservationPurpose, ...]:
    if modality is ObservationModality.VISUAL:
        return (
            ObservationPurpose.WORLD_GROUNDING,
            ObservationPurpose.ENTITY_DISCOVERY,
            ObservationPurpose.TARGET_DISAMBIGUATION,
            ObservationPurpose.EFFECT_VERIFICATION,
            ObservationPurpose.CRITERION_VERIFICATION,
            ObservationPurpose.CURRENTNESS_REFRESH,
        )
    return (
        ObservationPurpose.WORLD_GROUNDING,
        ObservationPurpose.EFFECT_VERIFICATION,
        ObservationPurpose.CRITERION_VERIFICATION,
        ObservationPurpose.CURRENTNESS_REFRESH,
    )
