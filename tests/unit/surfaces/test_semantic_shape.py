from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from affordance_runtime.surfaces.semantic_shape import (
    close_repeated_source_structure,
    explicit_role_semantic_shape,
)
from affordance_runtime.world import (
    ObservationStructureNode,
    SemanticShapeKind,
    SemanticShapeStatus,
)


def _node(
    structure_id: str,
    role: str,
    *,
    parent: str = "",
    children: tuple[str, ...] = (),
    target: str = "",
    label: str = "",
) -> ObservationStructureNode:
    return ObservationStructureNode(
        structure_id,
        role,
        label,
        parent_structure_id=parent,
        child_structure_ids=children,
        semantic_target_id=target,
        semantic_shape=explicit_role_semantic_shape(
            role,
            has_children=bool(children),
            has_semantic_target=bool(target),
        ),
    )


def test_structural_container_with_target_is_not_flattened_to_atom() -> None:
    shape = explicit_role_semantic_shape(
        "generic",
        has_children=True,
        has_semantic_target=True,
    )

    assert shape.status is SemanticShapeStatus.UNKNOWN
    assert shape.kind is None


def test_exact_repeated_source_subtrees_close_as_collection_records() -> None:
    structure = (
        _node("root", "main", children=("contributors",)),
        _node("contributors", "generic", parent="root", children=("dan", "joe"), target="t-list"),
        _node("dan", "generic", parent="contributors", children=("dan-name", "dan-detail"), target="t-dan"),
        _node("dan-name", "heading", parent="dan", children=("dan-name-text",), target="t-dan-name"),
        _node("dan-name-text", "StaticText", parent="dan-name", target="t-dan-name-text", label="Dan"),
        _node("dan-detail", "paragraph", parent="dan", children=("dan-detail-text",)),
        _node(
            "dan-detail-text",
            "StaticText",
            parent="dan-detail",
            target="t-dan-detail",
            label="634 commits (dan@example.test)",
        ),
        _node("joe", "generic", parent="contributors", children=("joe-name", "joe-detail"), target="t-joe"),
        _node("joe-name", "heading", parent="joe", children=("joe-name-text",), target="t-joe-name"),
        _node("joe-name-text", "StaticText", parent="joe-name", target="t-joe-name-text", label="Joe"),
        _node("joe-detail", "paragraph", parent="joe", children=("joe-detail-text",)),
        _node(
            "joe-detail-text",
            "StaticText",
            parent="joe-detail",
            target="t-joe-detail",
            label="292 commits (joe@example.test)",
        ),
    )

    closed = {item.structure_id: item for item in close_repeated_source_structure(structure)}

    assert closed["contributors"].semantic_shape.kind is SemanticShapeKind.COLLECTION
    assert closed["dan"].semantic_shape.kind is SemanticShapeKind.RECORD
    assert closed["joe"].semantic_shape.kind is SemanticShapeKind.RECORD
    assert closed["dan"].child_structure_ids == ("dan-name", "dan-detail")
    assert closed["joe"].child_structure_ids == ("joe-name", "joe-detail")


def test_non_repeated_unknown_structure_keeps_its_source_tree() -> None:
    structure = (
        _node("root", "main", children=("unknown",)),
        _node("unknown", "generic", parent="root", children=("heading", "paragraph"), target="t-u"),
        _node("heading", "heading", parent="unknown", target="t-h", label="Heading"),
        _node("paragraph", "paragraph", parent="unknown", target="t-p", label="Body"),
    )

    closed = {item.structure_id: item for item in close_repeated_source_structure(structure)}

    assert closed["unknown"].semantic_shape.status is SemanticShapeStatus.UNKNOWN
    assert closed["unknown"].child_structure_ids == ("heading", "paragraph")


@given(
    labels=st.lists(
        st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=30),
        min_size=4,
        max_size=12,
        unique=True,
    ).filter(lambda values: len(values) % 2 == 0),
)
def test_repeated_structure_closure_is_independent_of_open_domain_content(
    labels: list[str],
) -> None:
    record_count = len(labels) // 2
    record_ids = tuple(f"record:{index}" for index in range(record_count))
    nodes = [
        _node("root", "main", children=("collection",)),
        _node("collection", "generic", parent="root", children=record_ids, target="target:collection"),
    ]
    for index, record_id in enumerate(record_ids):
        field_ids = (f"field:{index}:0", f"field:{index}:1")
        nodes.extend((
            _node(record_id, "generic", parent="collection", children=field_ids, target=f"target:{record_id}"),
            _node(
                field_ids[0],
                "StaticText",
                parent=record_id,
                target=f"target:{field_ids[0]}",
                label=labels[index * 2],
            ),
            _node(
                field_ids[1],
                "StaticText",
                parent=record_id,
                target=f"target:{field_ids[1]}",
                label=labels[index * 2 + 1],
            ),
        ))

    original = tuple(nodes)
    closed = close_repeated_source_structure(original)
    by_id = {item.structure_id: item for item in closed}

    assert by_id["collection"].semantic_shape.kind is SemanticShapeKind.COLLECTION
    assert all(by_id[item].semantic_shape.kind is SemanticShapeKind.RECORD for item in record_ids)
    assert tuple((item.structure_id, item.parent_structure_id, item.child_structure_ids, item.label) for item in closed) == tuple(
        (item.structure_id, item.parent_structure_id, item.child_structure_ids, item.label) for item in original
    )
