import pytest

from affordance_runtime.contracts import Observation
from affordance_runtime.grounding import (
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    PerceptionRequirements,
    RoutePlan,
    SvgGroundingPayload,
    SvgTransform,
    UnifiedAffordance,
)


def _candidate(candidate_id: str = "dom-save") -> GroundingCandidate:
    return GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id="save",
        source=GroundingSource.DOM,
        payload=DomGroundingPayload(bid="save"),
        compatible_executor="browsergym",
        observation_epoch_id="snap-1",
        environment_revision="rev-1",
        page_revision="page-1",
        target_fingerprint="fingerprint-1",
        supported_actions=frozenset({"activate"}),
        evidence_kinds=frozenset({EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}),
    )


def test_grounding_candidate_is_bound_to_current_epoch_and_target() -> None:
    candidate = _candidate()
    observation = Observation(
        "rev-1", snapshot_id="snap-1", page_revision="page-1", target_fingerprints={"dom-save": "fingerprint-1"}
    )

    assert candidate.is_current(observation)
    assert not candidate.is_current(Observation("rev-1", snapshot_id="snap-2", page_revision="page-1"))


def test_unified_affordance_and_route_reject_cross_target_candidates() -> None:
    other = GroundingCandidate(
        **{
            **_candidate("dom-other").__dict__,
            "semantic_target_id": "other",
        }
    )

    with pytest.raises(ValueError, match="unified semantic target"):
        UnifiedAffordance("save", "button", "Save", frozenset({"activate"}), grounding_candidates=(other,))
    with pytest.raises(ValueError, match="active semantic target"):
        RoutePlan("save", selected_candidate=other)


def test_svg_payload_applies_current_svg_transform() -> None:
    payload = SvgGroundingPayload(
        element_id="dot-1",
        tag="circle",
        view_box=(0, 0, 100, 50),
        geometry_bbox_xywh=(10, 5, 20, 10),
        viewport_bbox_xywh=(120, 70, 40, 20),
        transform=SvgTransform(2, 0, 0, 2, 100, 60),
    )

    assert payload.transform.apply((20, 10)) == (140, 80)
    assert payload.viewport_center == (140, 80)


def test_perception_requirement_bounds_are_validated() -> None:
    with pytest.raises(ValueError, match="confidence"):
        PerceptionRequirements(minimum_confidence=1.1)
