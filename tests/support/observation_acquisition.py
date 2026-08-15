from typing import Any

from affordance_runtime.world import (
    ObservationNeed,
    ObservationOffer,
    ObservationOrchestrator,
    ObservationPurpose,
    ObservationRequestKind,
    SelectedObservationRequest,
    WorldObservationRequest,
    selected_observation_requests,
)


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
    return selected_observation_requests(
        outcome.plan, request, (offer,), "test:acquisition"
    )[0]


async def acquire_observation(adapter: Any, reason: str):
    request = selected_request(adapter.observation_offers[0], reason)
    result = await adapter.acquire(request)
    assert result.observation is not None
    return result.observation
