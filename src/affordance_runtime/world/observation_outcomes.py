"""Closed per-query outcomes owned by the observation acquisition boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, TypeAlias

from affordance_runtime.world.observation_needs import ObservationPurpose


class ObservationQueryDisposition(StrEnum):
    OBSERVED = "observed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    FAILED = "failed"


class VisualUnknownReason(StrEnum):
    TARGET_NOT_VISIBLE = "target_not_visible"
    INSUFFICIENT_RESOLUTION = "insufficient_resolution"
    MULTIPLE_PLAUSIBLE_TARGETS = "multiple_plausible_targets"
    PROPERTY_NOT_OBSERVABLE = "property_not_observable"
    RELATION_NOT_OBSERVABLE = "relation_not_observable"
    TEXT_NOT_LEGIBLE = "text_not_legible"
    CHANGE_NOT_DETERMINABLE = "change_not_determinable"


class VisualQueryFailureReason(StrEnum):
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    STRUCTURED_OUTPUT = "structured_output"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class InputLocator:
    kind: ClassVar[str] = "input"
    input_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_indices", tuple(self.input_indices))
        if (
            not 1 <= len(self.input_indices) <= 32
            or len(set(self.input_indices)) != len(self.input_indices)
            or any(type(item) is not int or not 0 <= item < 32 for item in self.input_indices)
        ):
            raise ValueError("input locator requires 1-32 unique indices in [0, 31]")


@dataclass(frozen=True)
class QueryScopeLocator:
    kind: ClassVar[str] = "query_scope"


@dataclass(frozen=True)
class ResultLocator:
    kind: ClassVar[str] = "result"
    result_index: int

    def __post_init__(self) -> None:
        if type(self.result_index) is not int or not 0 <= self.result_index < 32:
            raise ValueError("result locator index must be in [0, 31]")


ObservationResultLocator: TypeAlias = InputLocator | QueryScopeLocator | ResultLocator


@dataclass(frozen=True)
class ObservationObservedItem:
    locator: ObservationResultLocator
    subject_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.locator, InputLocator | QueryScopeLocator | ResultLocator):
            raise TypeError("observed item locator must be typed")
        object.__setattr__(self, "subject_ids", tuple(self.subject_ids))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if any(not item.strip() for item in (*self.subject_ids, *self.evidence_refs)):
            raise ValueError("observed item identities cannot be blank")
        if len(set(self.subject_ids)) != len(self.subject_ids) or len(set(self.evidence_refs)) != len(
            self.evidence_refs
        ):
            raise ValueError("observed item identities cannot repeat")


@dataclass(frozen=True)
class ObservationUnknownItem:
    locator: InputLocator | QueryScopeLocator
    reason: VisualUnknownReason

    def __post_init__(self) -> None:
        if not isinstance(self.locator, InputLocator | QueryScopeLocator):
            raise TypeError("unknown item locator must refer to an input or the query scope")
        if not isinstance(self.reason, VisualUnknownReason):
            raise TypeError("unknown item reason must be typed")


@dataclass(frozen=True)
class ObservationQueryOutcome:
    query_id: str
    purpose: ObservationPurpose
    disposition: ObservationQueryDisposition
    observed_items: tuple[ObservationObservedItem, ...] = ()
    unknown_items: tuple[ObservationUnknownItem, ...] = ()
    failure_reason: VisualQueryFailureReason | None = None

    def __post_init__(self) -> None:
        if not self.query_id.strip() or len(self.query_id) > 240:
            raise ValueError("observation query outcome requires a bounded query identity")
        if not isinstance(self.purpose, ObservationPurpose):
            raise TypeError("observation query outcome purpose must be typed")
        if not isinstance(self.disposition, ObservationQueryDisposition):
            raise TypeError("observation query outcome disposition must be typed")
        object.__setattr__(self, "observed_items", tuple(self.observed_items))
        object.__setattr__(self, "unknown_items", tuple(self.unknown_items))
        if any(not isinstance(item, ObservationObservedItem) for item in self.observed_items):
            raise TypeError("observation query observed items must be typed")
        if any(not isinstance(item, ObservationUnknownItem) for item in self.unknown_items):
            raise TypeError("observation query unknown items must be typed")
        legal = {
            ObservationQueryDisposition.OBSERVED: bool(self.observed_items) and not self.unknown_items,
            ObservationQueryDisposition.PARTIAL: bool(self.observed_items) and bool(self.unknown_items),
            ObservationQueryDisposition.UNKNOWN: bool(self.unknown_items) and not self.observed_items,
            ObservationQueryDisposition.FAILED: (
                not self.observed_items and not self.unknown_items and self.failure_reason is not None
            ),
        }[self.disposition]
        if not legal or ((self.disposition is ObservationQueryDisposition.FAILED) != (self.failure_reason is not None)):
            raise ValueError("observation query outcome disposition and payload disagree")
        self._validate_locators()

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ref for item in self.observed_items for ref in item.evidence_refs))

    @property
    def observed_subject_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(subject for item in self.observed_items for subject in item.subject_ids))

    def _validate_locators(self) -> None:
        locators: tuple[ObservationResultLocator, ...] = (
            tuple(item.locator for item in self.observed_items)
            + tuple(item.locator for item in self.unknown_items)
        )
        if self.purpose is ObservationPurpose.ENTITY_DISCOVERY:
            if any(not isinstance(item.locator, ResultLocator) for item in self.observed_items) or any(
                not isinstance(item.locator, QueryScopeLocator) for item in self.unknown_items
            ):
                raise ValueError("entity discovery requires result locators or a query-scope unknown")
        elif self.purpose is ObservationPurpose.POINT_GROUNDING:
            if any(isinstance(locator, ResultLocator) for locator in locators):
                raise ValueError("point grounding cannot use discovery result locators")
        elif any(not isinstance(locator, InputLocator) for locator in locators):
            raise ValueError("subject/candidate observation outcomes require input locators")
