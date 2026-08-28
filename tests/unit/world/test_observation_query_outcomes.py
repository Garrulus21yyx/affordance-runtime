from __future__ import annotations

import pytest

from affordance_runtime.world.observation_needs import ObservationPurpose
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    ObservationObservedItem,
    ObservationQueryDisposition,
    ObservationQueryOutcome,
    ObservationUnknownItem,
    QueryScopeLocator,
    ResultLocator,
    VisualQueryFailureReason,
    VisualUnknownReason,
)


def test_batch_outcome_allows_partial_exact_input_coverage() -> None:
    outcome = ObservationQueryOutcome(
        "observation-query:batch",
        ObservationPurpose.VISUAL_PROPERTY,
        ObservationQueryDisposition.PARTIAL,
        (
            ObservationObservedItem(InputLocator((0,)), ("target:one",), ("fact:one",)),
            ObservationObservedItem(InputLocator((1,)), ("target:two",), ("fact:two",)),
        ),
        (
            ObservationUnknownItem(
                InputLocator((2,)),
                VisualUnknownReason.PROPERTY_NOT_OBSERVABLE,
            ),
        ),
    )

    assert outcome.observed_subject_ids == ("target:one", "target:two")
    assert outcome.evidence_refs == ("fact:one", "fact:two")


def test_scope_unknown_closes_discovery_and_no_candidate_point() -> None:
    discovery = ObservationQueryOutcome(
        "observation-query:discovery",
        ObservationPurpose.ENTITY_DISCOVERY,
        ObservationQueryDisposition.UNKNOWN,
        unknown_items=(
            ObservationUnknownItem(QueryScopeLocator(), VisualUnknownReason.TARGET_NOT_VISIBLE),
        ),
    )
    point = ObservationQueryOutcome(
        "observation-query:point",
        ObservationPurpose.POINT_GROUNDING,
        ObservationQueryDisposition.UNKNOWN,
        unknown_items=(
            ObservationUnknownItem(QueryScopeLocator(), VisualUnknownReason.TARGET_NOT_VISIBLE),
        ),
    )

    assert discovery.unknown_items[0].locator.kind == "query_scope"
    assert point.unknown_items[0].locator.kind == "query_scope"


def test_unknown_cannot_use_result_locator_or_stale_public_ref() -> None:
    with pytest.raises(TypeError, match="input or the query scope"):
        ObservationUnknownItem(  # type: ignore[arg-type]
            ResultLocator(0),
            VisualUnknownReason.TARGET_NOT_VISIBLE,
        )


def test_failed_outcome_is_closed_and_contains_no_observed_items() -> None:
    outcome = ObservationQueryOutcome(
        "observation-query:failed",
        ObservationPurpose.TEXT_IN_IMAGE,
        ObservationQueryDisposition.FAILED,
        failure_reason=VisualQueryFailureReason.STRUCTURED_OUTPUT,
    )

    assert outcome.observed_items == ()
    assert outcome.unknown_items == ()
