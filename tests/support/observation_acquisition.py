from typing import Any

from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionReason,
    AcquisitionReasonKind,
    AcquisitionStage,
    AcquisitionStatus,
    ObservationAcquisition,
    ObservationNeed,
    ObservationOffer,
    ObservationOrchestrator,
    ObservationPurpose,
    ObservationRequestKind,
    ProviderActivation,
    SelectedObservationRequest,
    SelectedObservationResult,
    SourceAcquisitionStatus,
    WorldObservationRequest,
    selected_observation_requests,
)
from affordance_runtime.world.fusion import WorldFusion


def selected_request(
    offer: ObservationOffer,
    reason: str,
    *,
    purpose: ObservationPurpose = ObservationPurpose.WORLD_GROUNDING,
) -> SelectedObservationRequest:
    """Build the real single-offer provider contract for adapter conformance tests."""

    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        reason,
        (ObservationNeed(f"test:{purpose.value}", purpose),),
    )
    outcome = ObservationOrchestrator(acquisition_budget=1).select((offer,), request)
    assert outcome.plan is not None
    return selected_observation_requests(outcome.plan, request, (offer,), "test:acquisition")[0]


async def acquire_observation(adapter: Any, reason: str):
    request = selected_request(adapter.observation_offers[0], reason)
    result = await adapter.acquire(request)
    assert result.observation is not None
    return result.observation


def acquired_acquisition(
    world,
    origin: AcquisitionOrigin,
    *,
    kind: ObservationRequestKind = ObservationRequestKind.POLICY_REQUEST,
    acquisition_id: str = "test:acquisition",
) -> ObservationAcquisition:
    source = world.sources[0]
    offer = ObservationOffer(
        source.surface,
        source.source_profile.modality,
        source.source_profile.assurance,
        source.source_profile.acquisition_cost,
    )
    request = WorldObservationRequest(kind, "test acquisition")
    plan = ObservationOrchestrator(acquisition_budget=1).select((offer,), request).plan
    assert plan is not None
    selected = selected_observation_requests(plan, request, (offer,), acquisition_id)[0]
    result = SelectedObservationResult.acquired(
        selected,
        source,
        fulfilled_need_ids=tuple(item.need_id for item in selected.needs),
    )
    fused = WorldFusion().fuse((source,))
    stage = AcquisitionStage.ACQUIRED_ALL_NEEDS_FULFILLED
    return ObservationAcquisition(
        acquisition_id,
        origin,
        request,
        stage,
        plan,
        (ProviderActivation(selected, result),),
        fused,
        AcquisitionStatus.ACQUIRED,
        AcquisitionReason(AcquisitionReasonKind.ALL_NEEDS_FULFILLED, "world_acquired", stage),
    )


def failed_acquisition(
    origin: AcquisitionOrigin,
    reason_code: str,
    *,
    kind: ObservationRequestKind = ObservationRequestKind.POLICY_REQUEST,
    acquisition_id: str = "test:failed-acquisition",
) -> ObservationAcquisition:
    offer = ObservationOffer("static", "structural", "structural", "low")
    request = WorldObservationRequest(kind, "test failed acquisition")
    plan = ObservationOrchestrator(acquisition_budget=1).select((offer,), request).plan
    assert plan is not None
    selected = selected_observation_requests(plan, request, (offer,), acquisition_id)[0]
    result = SelectedObservationResult.failed(
        selected,
        SourceAcquisitionStatus.FAILED,
        reason_code,
    )
    stage = AcquisitionStage.SOURCE_ACQUISITION_FAILED
    return ObservationAcquisition(
        acquisition_id,
        origin,
        request,
        stage,
        plan,
        (ProviderActivation(selected, result),),
        None,
        AcquisitionStatus.FAILED,
        AcquisitionReason(AcquisitionReasonKind.SOURCE_FAILURE, reason_code, stage),
    )
