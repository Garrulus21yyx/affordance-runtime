from __future__ import annotations

import pytest

from affordance_runtime.world import (
    ObservationSourceProfile,
    ObservationStructureNode,
    SemanticShape,
    SemanticShapeCompleteness,
    SemanticShapeKind,
    SemanticShapeStatus,
    SemanticTarget,
    SurfaceObservation,
    WorldFusion,
)


def test_semantic_shape_algebra_rejects_ambiguous_resolution() -> None:
    with pytest.raises(ValueError, match="requires a typed kind"):
        SemanticShape(SemanticShapeStatus.RESOLVED)
    with pytest.raises(ValueError, match="requires no kind and a reason"):
        SemanticShape(SemanticShapeStatus.UNKNOWN, SemanticShapeKind.RECORD)


def test_world_fusion_projects_source_shape_with_lineage_and_canonical_target() -> None:
    source = SurfaceObservation(
        "source:topology",
        "browser",
        "revision:topology",
        ObservationSourceProfile.dom(),
        targets=(SemanticTarget("local:field", "StaticText", "Notebook"),),
        structure=(
            ObservationStructureNode(
                "local:collection",
                "table",
                "Orders",
                child_structure_ids=("local:record",),
                semantic_shape=SemanticShape.resolved(SemanticShapeKind.COLLECTION),
            ),
            ObservationStructureNode(
                "local:record",
                "row",
                "",
                parent_structure_id="local:collection",
                child_structure_ids=("local:field-node",),
                semantic_shape=SemanticShape.resolved(SemanticShapeKind.RECORD, complete=False),
            ),
            ObservationStructureNode(
                "local:field-node",
                "StaticText",
                "Notebook",
                parent_structure_id="local:record",
                semantic_target_id="local:field",
                semantic_shape=SemanticShape.resolved(SemanticShapeKind.ATOM),
            ),
        ),
        structure_total_count=3,
    )

    result = WorldFusion().fuse((source,))

    assert result.observation is not None
    topology = {item.source_structure_id: item for item in result.observation.semantic_topology}
    assert topology["local:record"].semantic_shape.kind is SemanticShapeKind.RECORD
    assert (
        topology["local:record"].semantic_shape.completeness
        is SemanticShapeCompleteness.INCOMPLETE
    )
    assert topology["local:field-node"].semantic_target_id == result.observation.targets[0].target_id
    assert topology["local:record"].child_structure_ids == (
        topology["local:field-node"].structure_id,
    )


def test_unknown_source_shape_survives_fusion_without_downstream_guess() -> None:
    source = SurfaceObservation(
        "source:unknown-topology",
        "browser",
        "revision:unknown-topology",
        ObservationSourceProfile.dom(),
        structure=(
            ObservationStructureNode(
                "local:opaque",
                "group",
                "Opaque content",
                semantic_shape=SemanticShape.unknown("provider_could_not_resolve_group"),
            ),
        ),
        structure_total_count=1,
    )

    result = WorldFusion().fuse((source,))

    assert result.observation is not None
    shape = result.observation.semantic_topology[0].semantic_shape
    assert shape.status is SemanticShapeStatus.UNKNOWN
    assert shape.kind is None
    assert shape.reason == "provider_could_not_resolve_group"
