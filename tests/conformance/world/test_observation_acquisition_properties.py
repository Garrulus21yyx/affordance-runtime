from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.agent.context.acquisition_projection import (
    project_acquisition_offers,
)
from affordance_runtime.benchmarks.support import ScriptedEnvironment
from affordance_runtime.world import (
    AcquisitionOrigin,
    AcquisitionReason,
    AcquisitionReasonKind,
    AcquisitionStage,
    AcquisitionStatus,
    ObservationAcquisition,
    ObservationCapabilities,
    ObservationNeed,
    ObservationOffer,
    ObservationOrchestrator,
    ObservationPurpose,
    ObservationRequestKind,
    ObservationSourceProfile,
    ProviderActivation,
    SelectedObservationResult,
    SurfaceObservation,
    WorldFusion,
    WorldObservationRequest,
    selected_observation_requests,
)


@given(reverse=st.booleans())
def test_capability_projection_unions_equivalent_offers_order_independently(
    reverse: bool,
) -> None:
    offers = (
        ObservationOffer(
            "dom:grounding",
            "structural",
            "structural",
            "low",
            supported_purposes=(ObservationPurpose.WORLD_GROUNDING,),
        ),
        ObservationOffer(
            "dom:verification",
            "structural",
            "structural",
            "low",
            supported_purposes=(ObservationPurpose.EFFECT_VERIFICATION,),
        ),
    )
    ordered = tuple(reversed(offers)) if reverse else offers

    projection = project_acquisition_offers(
        ObservationCapabilities(True, True, ordered)
    )

    assert len(projection) == 1
    assert projection[0].purposes == (
        ObservationPurpose.EFFECT_VERIFICATION.value,
        ObservationPurpose.WORLD_GROUNDING.value,
    )


def test_scripted_fixture_rejects_prefused_multi_source_authority() -> None:
    sources = (
        SurfaceObservation(
            "source:one",
            "one",
            "revision:one",
            ObservationSourceProfile.dom(),
        ),
        SurfaceObservation(
            "source:two",
            "two",
            "revision:two",
            ObservationSourceProfile.dom(),
        ),
    )
    fused = WorldFusion().fuse(sources)
    assert fused.observation is not None

    with pytest.raises(ValueError, match="exactly one original source"):
        ScriptedEnvironment(initial_observation=fused.observation)


@given(
    need_count=st.integers(min_value=1, max_value=6),
    fulfilled_indexes=st.sets(st.integers(min_value=0, max_value=5)),
)
def test_need_outcomes_are_total_unique_and_distinct_from_fusion_success(
    need_count: int,
    fulfilled_indexes: set[int],
) -> None:
    needs = tuple(
        ObservationNeed(f"need:{index}", ObservationPurpose.WORLD_GROUNDING)
        for index in range(need_count)
    )
    request = WorldObservationRequest(
        ObservationRequestKind.POLICY_REQUEST,
        "property acquisition",
        needs,
    )
    offer = ObservationOffer("dom", "structural", "structural", "low")
    plan = ObservationOrchestrator(acquisition_budget=1).select((offer,), request).plan
    assert plan is not None
    selected = selected_observation_requests(
        plan, request, (offer,), "acquisition:property"
    )[0]
    source = SurfaceObservation(
        "source:property",
        "dom",
        "revision:property",
        ObservationSourceProfile.dom(),
    )
    fulfilled = tuple(
        need.need_id for index, need in enumerate(needs) if index in fulfilled_indexes
    )
    result = SelectedObservationResult.acquired(
        selected,
        source,
        fulfilled_need_ids=fulfilled,
    )
    fused = WorldFusion().fuse((source,))
    all_fulfilled = len(fulfilled) == need_count
    stage = (
        AcquisitionStage.ACQUIRED_ALL_NEEDS_FULFILLED
        if all_fulfilled
        else AcquisitionStage.ACQUIRED_WITH_UNRESOLVED_NEEDS
    )
    acquisition = ObservationAcquisition(
        "acquisition:property",
        AcquisitionOrigin.INDEPENDENT_CAPTURE,
        request,
        stage,
        plan,
        (ProviderActivation(selected, result),),
        fused,
        AcquisitionStatus.ACQUIRED,
        AcquisitionReason(
            AcquisitionReasonKind.ALL_NEEDS_FULFILLED
            if all_fulfilled
            else AcquisitionReasonKind.UNRESOLVED_NEEDS,
            "world_acquired" if all_fulfilled else "world_acquired_with_unresolved_need",
            stage,
        ),
    )

    assert acquisition.observation is fused.observation
    assert tuple(item.need_id for item in acquisition.per_need_outcomes) == tuple(
        item.need_id for item in needs
    )
    assert len({item.need_id for item in acquisition.per_need_outcomes}) == need_count
    assert (acquisition.stage is AcquisitionStage.ACQUIRED_ALL_NEEDS_FULFILLED) is all_fulfilled

    with pytest.raises(ValueError, match="conserve acquisition identity"):
        replace(
            acquisition,
            activations=(
                replace(
                    acquisition.activations[0],
                    request=replace(selected, acquisition_id="acquisition:foreign"),
                ),
            ),
        )

    with pytest.raises(ValueError, match="illegal terminal stage shape"):
        replace(
            acquisition,
            stage=AcquisitionStage.CANCELLED,
            activations=(),
            fusion_outcome=None,
            status=AcquisitionStatus.CANCELLED,
            reason=AcquisitionReason(
                AcquisitionReasonKind.CANCELLATION,
                "source_acquisition_cancelled",
                AcquisitionStage.CANCELLED,
            ),
        )
