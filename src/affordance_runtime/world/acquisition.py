"""Typed values for the target world's observation acquisition lifecycle."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from enum import StrEnum

from affordance_runtime.world.contracts import SurfaceObservation, WorldObservation
from affordance_runtime.world.fusion import FusionStatus, WorldFusionResult
from affordance_runtime.world.observation_needs import ObservationNeed, ObservationPurpose
from affordance_runtime.world.observation_outcomes import ObservationQueryOutcome
from affordance_runtime.world.source_profile import AcquisitionCost, ObservationAssurance, ObservationModality

_REASON_CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_PRIVATE_MARKERS = (
    "credential",
    "password",
    "payload",
    "secret",
    "selector",
    "token",
    "url",
)


class AcquisitionStatus(StrEnum):
    ACQUIRED = "acquired"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AcquisitionStage(StrEnum):
    PRE_SELECTION_UNAVAILABLE = "pre_selection_unavailable"
    INITIALIZATION_FAILED = "initialization_failed"
    SOURCE_ACQUISITION_FAILED = "source_acquisition_failed"
    FUSION_FAILED = "fusion_failed"
    CANCELLED = "cancelled"
    ACQUIRED_ALL_NEEDS_FULFILLED = "acquired_all_needs_fulfilled"
    ACQUIRED_WITH_UNRESOLVED_NEEDS = "acquired_with_unresolved_needs"


class AcquisitionReasonKind(StrEnum):
    UNAVAILABLE = "unavailable"
    INITIALIZATION_FAILURE = "initialization_failure"
    SOURCE_FAILURE = "source_failure"
    FUSION_FAILURE = "fusion_failure"
    CANCELLATION = "cancellation"
    ALL_NEEDS_FULFILLED = "all_needs_fulfilled"
    UNRESOLVED_NEEDS = "unresolved_needs"


@dataclass(frozen=True)
class AcquisitionReason:
    kind: AcquisitionReasonKind
    code: str
    stage: AcquisitionStage
    source_ids: tuple[str, ...] = ()
    need_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AcquisitionReasonKind):
            raise TypeError("acquisition reason kind must be typed")
        if not isinstance(self.stage, AcquisitionStage):
            raise TypeError("acquisition reason stage must be typed")
        _validate_reason_code(self.code)
        object.__setattr__(self, "source_ids", tuple(self.source_ids))
        object.__setattr__(self, "need_ids", tuple(self.need_ids))
        if any(not item.strip() for item in (*self.source_ids, *self.need_ids)):
            raise ValueError("acquisition reason identities cannot be blank")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("acquisition reason source identities cannot repeat")
        if len(set(self.need_ids)) != len(self.need_ids):
            raise ValueError("acquisition reason need identities cannot repeat")


class SourceAcquisitionStatus(StrEnum):
    NOT_ACQUIRED = "not_acquired"
    ACQUIRED = "acquired"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceRequirement(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    UNSELECTED = "unselected"


class ObservationNeedSatisfactionStatus(StrEnum):
    FULFILLED = "fulfilled"
    UNFULFILLED = "unfulfilled"
    CANCELLED = "cancelled"


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
        if any(item.need_ids for item in self.unselected):
            raise ValueError("unselected sources cannot own observation needs")
        selected_need_ids = tuple(need_id for item in self.selections for need_id in item.need_ids)
        if (
            any(not item.need_ids for item in self.selections)
            or len(set(selected_need_ids)) != len(selected_need_ids)
            or set(selected_need_ids) != known_needs
        ):
            raise ValueError("selected sources must partition all observation needs")
        for reason_code in self.reason_codes:
            _validate_reason_code(reason_code)

    @property
    def need_ids(self) -> tuple[str, ...]:
        return tuple(item.need_id for item in self.needs)


@dataclass(frozen=True)
class SelectedObservationRequest:
    acquisition_id: str
    lifecycle_kind: ObservationRequestKind
    reason: str
    offer: ObservationOffer
    selection: SourceSelection
    needs: tuple[ObservationNeed, ...]

    def __post_init__(self) -> None:
        if not self.acquisition_id.strip() or len(self.acquisition_id) > 200:
            raise ValueError("selected observation request requires a bounded acquisition ID")
        if not isinstance(self.lifecycle_kind, ObservationRequestKind):
            raise TypeError("selected observation lifecycle kind must be typed")
        if not self.reason.strip() or len(self.reason) > 500:
            raise ValueError("selected observation request requires a bounded reason")
        if self.selection.requirement is SourceRequirement.UNSELECTED:
            raise ValueError("selected observation request cannot carry an unselected offer")
        if self.offer.source != self.selection.source:
            raise ValueError("selected observation request source identity must be conserved")
        object.__setattr__(self, "needs", tuple(self.needs))
        need_ids = tuple(item.need_id for item in self.needs)
        if not need_ids or set(need_ids) != set(self.selection.need_ids):
            raise ValueError("selected observation request must carry exactly its selected needs")

    @property
    def source(self) -> str:
        return self.offer.source

    @property
    def acquisition_group(self) -> str:
        return self.offer.acquisition_group


@dataclass(frozen=True)
class ObservationNeedResult:
    need_id: str
    status: ObservationNeedSatisfactionStatus
    reason_code: str
    query_outcome: ObservationQueryOutcome | None = None

    def __post_init__(self) -> None:
        if not self.need_id.strip():
            raise ValueError("observation need result requires a need ID")
        if not isinstance(self.status, ObservationNeedSatisfactionStatus):
            raise TypeError("observation need result status must be typed")
        _validate_reason_code(self.reason_code)
        if self.query_outcome is not None:
            if not isinstance(self.query_outcome, ObservationQueryOutcome):
                raise TypeError("observation need query outcome must be typed")
            if self.query_outcome.query_id != self.need_id:
                raise ValueError("observation need/query outcome identity mismatch")


@dataclass(frozen=True)
class SelectedObservationResult:
    source: str
    status: SourceAcquisitionStatus
    reason_code: str
    observation: SurfaceObservation | None
    need_results: tuple[ObservationNeedResult, ...]

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("selected observation result requires source identity")
        if self.status is SourceAcquisitionStatus.NOT_ACQUIRED:
            raise ValueError("a selected provider cannot report NOT_ACQUIRED")
        acquired = self.status is SourceAcquisitionStatus.ACQUIRED
        if acquired != isinstance(self.observation, SurfaceObservation):
            raise ValueError("selected provider ACQUIRED requires exactly one observation")
        object.__setattr__(self, "need_results", tuple(self.need_results))
        if (
            any(not isinstance(item, ObservationNeedResult) for item in self.need_results)
            or len({item.need_id for item in self.need_results}) != len(self.need_results)
            or (not acquired and self.fulfilled_need_ids)
        ):
            raise ValueError("selected provider need outcome is incoherent")
        _validate_reason_code(self.reason_code)

    @property
    def fulfilled_need_ids(self) -> tuple[str, ...]:
        return tuple(
            item.need_id for item in self.need_results if item.status is ObservationNeedSatisfactionStatus.FULFILLED
        )

    @property
    def unfulfilled_need_ids(self) -> tuple[str, ...]:
        return tuple(
            item.need_id for item in self.need_results if item.status is not ObservationNeedSatisfactionStatus.FULFILLED
        )

    @classmethod
    def acquired(
        cls,
        request: SelectedObservationRequest,
        observation: SurfaceObservation,
        *,
        fulfilled_need_ids: tuple[str, ...],
        unfulfilled_reason_code: str = "need_unresolved",
        query_outcomes: tuple[ObservationQueryOutcome, ...] = (),
    ) -> SelectedObservationResult:
        fulfilled = frozenset(fulfilled_need_ids)
        expected = {item.need_id for item in request.needs}
        if not fulfilled <= expected:
            raise ValueError("fulfilled need IDs must belong to the selected request")
        outcomes = {item.query_id: item for item in query_outcomes}
        if len(outcomes) != len(query_outcomes) or set(outcomes) - expected:
            raise ValueError("query outcomes must uniquely belong to the selected request")
        return cls(
            request.source,
            SourceAcquisitionStatus.ACQUIRED,
            "source_acquired",
            observation,
            tuple(
                ObservationNeedResult(
                    item.need_id,
                    ObservationNeedSatisfactionStatus.FULFILLED
                    if item.need_id in fulfilled
                    else ObservationNeedSatisfactionStatus.UNFULFILLED,
                    "need_fulfilled" if item.need_id in fulfilled else unfulfilled_reason_code,
                    outcomes.get(item.need_id),
                )
                for item in request.needs
            ),
        )

    @classmethod
    def failed(
        cls,
        request: SelectedObservationRequest,
        status: SourceAcquisitionStatus,
        reason_code: str,
        *,
        query_outcomes: tuple[ObservationQueryOutcome, ...] = (),
    ) -> SelectedObservationResult:
        if status not in {
            SourceAcquisitionStatus.CAPABILITY_UNAVAILABLE,
            SourceAcquisitionStatus.FAILED,
            SourceAcquisitionStatus.CANCELLED,
        }:
            raise ValueError("selected observation failure requires a failure status")
        outcomes = {item.query_id: item for item in query_outcomes}
        expected = {item.need_id for item in request.needs}
        if len(outcomes) != len(query_outcomes) or set(outcomes) - expected:
            raise ValueError("failed query outcomes must uniquely belong to the selected request")
        return cls(
            request.source,
            status,
            reason_code,
            None,
            tuple(
                ObservationNeedResult(
                    item.need_id,
                    ObservationNeedSatisfactionStatus.CANCELLED
                    if status is SourceAcquisitionStatus.CANCELLED
                    else ObservationNeedSatisfactionStatus.UNFULFILLED,
                    reason_code,
                    outcomes.get(item.need_id),
                )
                for item in request.needs
            ),
        )


@dataclass(frozen=True)
class SourceAcquisitionResult:
    source: str
    requirement: SourceRequirement
    status: SourceAcquisitionStatus
    reason_code: str
    observation: SurfaceObservation | None = None
    need_results: tuple[ObservationNeedResult, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip() or not isinstance(self.requirement, SourceRequirement):
            raise ValueError("source acquisition requires typed source identity")
        if not isinstance(self.status, SourceAcquisitionStatus):
            raise TypeError("source acquisition status must be typed")
        acquired = self.status is SourceAcquisitionStatus.ACQUIRED
        if acquired != isinstance(self.observation, SurfaceObservation):
            raise ValueError("source ACQUIRED requires exactly one observation")
        if (self.requirement is SourceRequirement.UNSELECTED) != (self.status is SourceAcquisitionStatus.NOT_ACQUIRED):
            raise ValueError("only unselected sources may be NOT_ACQUIRED")
        object.__setattr__(self, "need_results", tuple(self.need_results))
        if any(not isinstance(item, ObservationNeedResult) for item in self.need_results) or len(
            {item.need_id for item in self.need_results}
        ) != len(self.need_results):
            raise ValueError("source acquisition need outcomes must be unique")
        if self.status is not SourceAcquisitionStatus.ACQUIRED and self.fulfilled_need_ids:
            raise ValueError("failed source cannot report fulfilled selected needs")
        _validate_reason_code(self.reason_code)

    @property
    def fulfilled_need_ids(self) -> tuple[str, ...]:
        return tuple(
            item.need_id for item in self.need_results if item.status is ObservationNeedSatisfactionStatus.FULFILLED
        )

    @property
    def unfulfilled_need_ids(self) -> tuple[str, ...]:
        return tuple(
            item.need_id for item in self.need_results if item.status is not ObservationNeedSatisfactionStatus.FULFILLED
        )


@dataclass(frozen=True)
class ObservationCapabilities:
    independent_capture: bool
    post_action_observation: bool
    offers: tuple[ObservationOffer, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "offers", tuple(self.offers))


@dataclass(frozen=True)
class ProviderActivation:
    request: SelectedObservationRequest
    result: SelectedObservationResult

    def __post_init__(self) -> None:
        if self.result.source != self.request.source:
            raise ValueError("provider activation source identity must be conserved")
        expected = {item.need_id for item in self.request.needs}
        actual = {item.need_id for item in self.result.need_results}
        if actual != expected:
            raise ValueError("provider activation must close every selected need exactly once")


@dataclass(frozen=True)
class ObservationAcquisition:
    acquisition_id: str
    origin: AcquisitionOrigin
    request: WorldObservationRequest
    stage: AcquisitionStage
    selection_plan: ObservationSelectionPlan | None
    activations: tuple[ProviderActivation, ...]
    fusion_outcome: WorldFusionResult | None
    status: AcquisitionStatus
    reason: AcquisitionReason

    def __post_init__(self) -> None:
        if not self.acquisition_id.strip() or len(self.acquisition_id) > 200:
            raise ValueError("observation acquisition requires a bounded identity")
        if not isinstance(self.origin, AcquisitionOrigin):
            raise TypeError("acquisition origin must be typed")
        if not isinstance(self.request, WorldObservationRequest):
            raise TypeError("acquisition request must be exact and typed")
        if not isinstance(self.stage, AcquisitionStage):
            raise TypeError("acquisition stage must be typed")
        if not isinstance(self.status, AcquisitionStatus):
            raise TypeError("acquisition status must be typed")
        if self.reason.stage is not self.stage:
            raise ValueError("acquisition reason must name the terminal stage")
        object.__setattr__(self, "activations", tuple(self.activations))
        if self.selection_plan is not None and not isinstance(self.selection_plan, ObservationSelectionPlan):
            raise TypeError("acquisition selection plan must be typed")
        if self.fusion_outcome is not None and not isinstance(self.fusion_outcome, WorldFusionResult):
            raise TypeError("acquisition fusion outcome must be exact and typed")
        self._validate_correlation()
        self._validate_stage_shape()

    @property
    def observation(self) -> WorldObservation | None:
        return None if self.fusion_outcome is None else self.fusion_outcome.observation

    @property
    def reason_code(self) -> str:
        return self.reason.code

    @property
    def per_need_outcomes(self) -> tuple[ObservationNeedResult, ...]:
        by_id = {result.need_id: result for activation in self.activations for result in activation.result.need_results}
        if self.selection_plan is None:
            return ()
        return tuple(by_id[item.need_id] for item in self.selection_plan.needs if item.need_id in by_id)

    def query_outcome(self, query_id: str) -> ObservationQueryOutcome | None:
        outcome = next(
            (
                item.query_outcome
                for item in self.per_need_outcomes
                if item.need_id == query_id and item.query_outcome is not None
            ),
            None,
        )
        if outcome is None or self.observation is None:
            return outcome
        canonical_ids = {item.target_id for item in self.observation.targets}
        by_source_target: dict[str, set[str]] = {}
        for link in self.observation.entity_source_links:
            by_source_target.setdefault(link.source_target_id, set()).add(link.canonical_target_id)

        def current_subject(subject_id: str) -> str | None:
            if subject_id in canonical_ids:
                return subject_id
            candidates = by_source_target.get(subject_id, set())
            return next(iter(candidates)) if len(candidates) == 1 else None

        return replace(
            outcome,
            observed_items=tuple(
                replace(
                    item,
                    subject_ids=tuple(
                        current
                        for subject in item.subject_ids
                        for current in (current_subject(subject),)
                        if current is not None
                    ),
                )
                for item in outcome.observed_items
            ),
        )

    @property
    def source_results(self) -> tuple[SourceAcquisitionResult, ...]:
        if self.selection_plan is None:
            return ()
        by_source = {item.request.source: item for item in self.activations}
        unselected = tuple(
            SourceAcquisitionResult(
                item.source,
                SourceRequirement.UNSELECTED,
                SourceAcquisitionStatus.NOT_ACQUIRED,
                "source_not_selected",
            )
            for item in self.selection_plan.unselected
        )
        selected = tuple(
            SourceAcquisitionResult(
                item.source,
                item.requirement,
                by_source[item.source].result.status,
                by_source[item.source].result.reason_code,
                by_source[item.source].result.observation,
                by_source[item.source].result.need_results,
            )
            for item in self.selection_plan.selections
            if item.source in by_source
        )
        return (*selected, *unselected)

    def _validate_correlation(self) -> None:
        if self.selection_plan is None:
            if self.activations:
                raise ValueError("acquisition without a plan cannot activate providers")
            return
        selected = {item.source: item for item in self.selection_plan.selections}
        activation_sources = tuple(item.request.source for item in self.activations)
        if len(set(activation_sources)) != len(activation_sources):
            raise ValueError("selected provider can have at most one terminal activation")
        if set(activation_sources) - set(selected):
            raise ValueError("provider activation must belong to the final selection plan")
        for activation in self.activations:
            selection = selected[activation.request.source]
            if activation.request.acquisition_id != self.acquisition_id:
                raise ValueError("provider activation must conserve acquisition identity")
            if activation.request.lifecycle_kind is not self.request.kind:
                raise ValueError("provider activation must conserve lifecycle kind")
            if activation.request.selection != selection:
                raise ValueError("provider activation must conserve final source selection")

    def _validate_stage_shape(self) -> None:
        complete = bool(
            self.selection_plan is not None
            and {item.request.source for item in self.activations}
            == {item.source for item in self.selection_plan.selections}
        )
        fused = bool(
            self.fusion_outcome is not None
            and self.fusion_outcome.status is FusionStatus.FUSED
            and self.fusion_outcome.observation is not None
        )
        legal = {
            AcquisitionStage.PRE_SELECTION_UNAVAILABLE: (
                self.status is AcquisitionStatus.CAPABILITY_UNAVAILABLE
                and self.selection_plan is None
                and not self.activations
                and self.fusion_outcome is None
                and self.reason.kind is AcquisitionReasonKind.UNAVAILABLE
            ),
            AcquisitionStage.INITIALIZATION_FAILED: (
                self.status is AcquisitionStatus.FAILED
                and self.selection_plan is not None
                and not self.activations
                and self.fusion_outcome is None
                and self.reason.kind is AcquisitionReasonKind.INITIALIZATION_FAILURE
            ),
            AcquisitionStage.SOURCE_ACQUISITION_FAILED: (
                self.status in {AcquisitionStatus.CAPABILITY_UNAVAILABLE, AcquisitionStatus.FAILED}
                and complete
                and self.fusion_outcome is None
                and self.reason.kind is AcquisitionReasonKind.SOURCE_FAILURE
            ),
            AcquisitionStage.FUSION_FAILED: (
                self.status is AcquisitionStatus.FAILED
                and complete
                and self.fusion_outcome is not None
                and not fused
                and self.reason.kind is AcquisitionReasonKind.FUSION_FAILURE
            ),
            AcquisitionStage.CANCELLED: (
                self.status is AcquisitionStatus.CANCELLED
                and self.selection_plan is not None
                and self.fusion_outcome is None
                and self.reason.kind is AcquisitionReasonKind.CANCELLATION
                and (
                    (
                        self.reason.code == "initialization_cancelled"
                        and not self.activations
                    )
                    or (
                        self.reason.code
                        in {"source_acquisition_cancelled", "fusion_cancelled"}
                        and complete
                    )
                )
            ),
            AcquisitionStage.ACQUIRED_ALL_NEEDS_FULFILLED: (
                self.status is AcquisitionStatus.ACQUIRED
                and complete
                and fused
                and all(item.status is ObservationNeedSatisfactionStatus.FULFILLED for item in self.per_need_outcomes)
                and self.reason.kind is AcquisitionReasonKind.ALL_NEEDS_FULFILLED
            ),
            AcquisitionStage.ACQUIRED_WITH_UNRESOLVED_NEEDS: (
                self.status is AcquisitionStatus.ACQUIRED
                and complete
                and fused
                and any(
                    item.status is not ObservationNeedSatisfactionStatus.FULFILLED for item in self.per_need_outcomes
                )
                and self.reason.kind is AcquisitionReasonKind.UNRESOLVED_NEEDS
            ),
        }[self.stage]
        if not legal:
            raise ValueError("observation acquisition has an illegal terminal stage shape")


class AcquisitionCancelled(asyncio.CancelledError):
    def __init__(self, acquisition: ObservationAcquisition) -> None:
        super().__init__(acquisition.reason_code)
        self.acquisition = acquisition


def selected_observation_requests(
    plan: ObservationSelectionPlan,
    request: WorldObservationRequest,
    offers: tuple[ObservationOffer, ...],
    acquisition_id: str,
) -> tuple[SelectedObservationRequest, ...]:
    offers_by_source = {item.source: item for item in offers}
    if len(offers_by_source) != len(offers):
        raise ValueError("observation offer source identities must be unique")
    needs_by_id = {item.need_id: item for item in plan.needs}
    return tuple(
        SelectedObservationRequest(
            acquisition_id,
            request.kind,
            request.reason,
            offers_by_source[selection.source],
            selection,
            tuple(needs_by_id[need_id] for need_id in selection.need_ids),
        )
        for selection in plan.selections
    )


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
        )
    return (
        ObservationPurpose.WORLD_GROUNDING,
        ObservationPurpose.EFFECT_VERIFICATION,
        ObservationPurpose.CRITERION_VERIFICATION,
        ObservationPurpose.CURRENTNESS_REFRESH,
    )
