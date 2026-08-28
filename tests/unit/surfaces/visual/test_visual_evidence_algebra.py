from __future__ import annotations

import pytest

from affordance_runtime.surfaces.visual.evidence import (
    ChangeEvidence,
    DisambiguationEvidence,
    PointEvidence,
    PredicateEvidence,
    RegionEvidence,
    SpatialEvidence,
    TextEvidence,
    VisualEvidenceProvenance,
    VisualQueryCompleted,
    VisualQueryCoverage,
)
from affordance_runtime.world import ObservationPurpose
from affordance_runtime.world.observation_outcomes import (
    InputLocator,
    ObservationUnknownItem,
    VisualUnknownReason,
)


def _provenance() -> VisualEvidenceProvenance:
    return VisualEvidenceProvenance(
        "observation-query:test",
        "fixture",
        "fixture-model",
        "fixture-v1",
        "sha256:frame",
        (200, 100),
        "page:1",
        "episode:1",
        (200, 100, 0, 0, 1, 1),
        12.5,
    )


def test_closed_visual_evidence_variants_share_runtime_provenance() -> None:
    provenance = _provenance()
    evidence = (
        RegionEvidence("e:region", 0.8, provenance, "R1", (1, 2, 3, 4), "target"),
        PredicateEvidence("e:predicate", 0.9, provenance, "subject:1", "red", True),
        DisambiguationEvidence("e:choice", 0.9, provenance, ("subject:1", "subject:2"), "subject:1"),
        TextEvidence("e:text", 0.9, provenance, "subject:1", "Alpha"),
        SpatialEvidence(
            "e:spatial",
            0.9,
            provenance,
            ("subject:1", "subject:2"),
            "left of",
            True,
        ),
        PointEvidence("e:point", 0.7, provenance, "R1", (20, 30)),
        ChangeEvidence("e:change", 0.9, provenance, ("subject:1",), "appearance changed", False),
    )
    result = VisualQueryCompleted(
        "observation-query:test",
        ObservationPurpose.VISUAL_PROPERTY,
        evidence,
    )

    assert result.coverage is VisualQueryCoverage.COMPLETE
    assert all(item.provenance is provenance for item in result.evidence)


def test_visual_query_coverage_is_derived_from_evidence_and_typed_unknowns() -> None:
    evidence = PredicateEvidence("e:predicate", 0.9, _provenance(), "subject:1", "selected", True)
    unknown = ObservationUnknownItem(InputLocator((1,)), VisualUnknownReason.PROPERTY_NOT_OBSERVABLE)

    assert (
        VisualQueryCompleted(
            "observation-query:test",
            ObservationPurpose.VISUAL_PROPERTY,
            (evidence,),
            (unknown,),
        ).coverage
        is VisualQueryCoverage.PARTIAL
    )
    assert (
        VisualQueryCompleted(
            "observation-query:test",
            ObservationPurpose.VISUAL_PROPERTY,
            unknown_items=(unknown,),
        ).coverage
        is VisualQueryCoverage.UNKNOWN
    )
    with pytest.raises(ValueError, match="evidence or a typed unknown"):
        VisualQueryCompleted("observation-query:test", ObservationPurpose.VISUAL_PROPERTY)
