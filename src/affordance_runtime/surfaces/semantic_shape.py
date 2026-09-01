"""Shared explicit-role conversion used at structural SurfaceAdapter boundaries."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import TypeVar

from affordance_runtime.world.contracts import (
    ObservationStructureNode,
    SemanticShape,
    SemanticShapeCompleteness,
    SemanticShapeKind,
    SemanticShapeStatus,
)

COLLECTION_ROLES = frozenset({"feed", "grid", "list", "table", "tree"})
RECORD_ROLES = frozenset({"article", "listitem", "row", "treeitem"})
CONTROL_GROUP_ROLES = frozenset({"listbox", "menu", "menubar", "radiogroup", "tablist", "toolbar"})
REGION_ROLES = frozenset({
    "alertdialog",
    "application",
    "complementary",
    "dialog",
    "document",
    "form",
    "main",
    "navigation",
    "region",
    "rootwebarea",
    "search",
    "webarea",
})


def explicit_role_semantic_shape(
    role: str,
    *,
    has_children: bool,
    has_semantic_target: bool,
    complete: bool = True,
) -> SemanticShape:
    """Convert an explicit structural role without using repetition or domain text."""

    normalized = role.casefold()
    if normalized in COLLECTION_ROLES:
        return SemanticShape.resolved(SemanticShapeKind.COLLECTION, complete=complete)
    if normalized in RECORD_ROLES:
        return SemanticShape.resolved(SemanticShapeKind.RECORD, complete=complete)
    if normalized in CONTROL_GROUP_ROLES:
        return SemanticShape.resolved(SemanticShapeKind.CONTROL_GROUP, complete=complete)
    if normalized in REGION_ROLES:
        return SemanticShape.resolved(SemanticShapeKind.REGION, complete=complete)
    # A structural container cannot be an Atom merely because the same source
    # node also exposes an actionable/readable target.  Doing so discards the
    # only authoritative ownership of its descendants and forces delivery to
    # reconstruct grouping later.  Unknown containers retain their source tree
    # until the source boundary can prove a compositional shape.
    if not has_children:
        return SemanticShape.resolved(SemanticShapeKind.ATOM, complete=complete)
    return SemanticShape.unknown("source_role_has_no_compositional_contract", incomplete=not complete)


_StructureNode = TypeVar("_StructureNode", bound=ObservationStructureNode)


def close_repeated_source_structure(
    structure: tuple[_StructureNode, ...],
) -> tuple[_StructureNode, ...]:
    """Close structurally repeated source siblings before World fusion.

    Explicit roles remain authoritative.  For otherwise unknown containers,
    an exact repeated sibling topology is source-owned evidence for the small
    public algebra ``Collection<Record>``.  Labels, state values, target ids,
    site text, and task terms never participate in the proof.  Unsupported
    non-leaf structure remains unknown and keeps its original child tree.
    """

    if not structure:
        return structure
    nodes = {item.structure_id: item for item in structure}
    signatures: dict[str, tuple[object, ...]] = {}
    visiting: set[str] = set()

    def signature(structure_id: str) -> tuple[object, ...]:
        cached = signatures.get(structure_id)
        if cached is not None:
            return cached
        if structure_id in visiting:
            # ObservationStructureNode validation owns topology legality.  A
            # bounded sentinel keeps this conversion total for malformed input.
            return ("cycle",)
        visiting.add(structure_id)
        node = nodes[structure_id]
        child_signatures = tuple(
            signature(child_id)
            for child_id in node.child_structure_ids
            if child_id in nodes
        )
        visiting.remove(structure_id)
        result = (
            node.role.casefold(),
            bool(node.semantic_target_id),
            child_signatures,
        )
        signatures[structure_id] = result
        return result

    repeated_children: dict[str, tuple[_StructureNode, ...]] = {}
    for parent in structure:
        if (
            parent.semantic_shape.status is not SemanticShapeStatus.UNKNOWN
            or len(parent.child_structure_ids) < 2
        ):
            continue
        children = tuple(
            nodes[child_id]
            for child_id in parent.child_structure_ids
            if child_id in nodes
        )
        if len(children) != len(parent.child_structure_ids) or len(children) < 2:
            continue
        counts = Counter(signature(item.structure_id) for item in children)
        if len(counts) != 1:
            continue
        # Empty representation fragments are not semantic records.  Each
        # repeated subtree must carry at least one public target or label.
        if any(not _subtree_has_public_payload(item.structure_id, nodes) for item in children):
            continue
        repeated_children[parent.structure_id] = children

    replacements: dict[str, SemanticShape] = {}
    for parent in structure:
        children = repeated_children.get(parent.structure_id)
        if children is None:
            continue
        # When this node is itself one of an enclosing exact repeated sibling
        # set, the enclosing source structure owns it as one Record.  Do not
        # reinterpret equal-role fields inside that record as another
        # Collection merely because their labels/values are intentionally
        # absent from the structural signature.
        if parent.parent_structure_id in repeated_children:
            continue
        parent_complete = parent.semantic_shape.completeness is not SemanticShapeCompleteness.INCOMPLETE
        replacements[parent.structure_id] = SemanticShape.resolved(
            SemanticShapeKind.COLLECTION,
            complete=parent_complete,
        )
        for child in children:
            if child.semantic_shape.status is SemanticShapeStatus.UNKNOWN:
                child_complete = (
                    child.semantic_shape.completeness is not SemanticShapeCompleteness.INCOMPLETE
                )
                replacements[child.structure_id] = SemanticShape.resolved(
                    SemanticShapeKind.RECORD,
                    complete=child_complete,
                )

    if not replacements:
        return structure
    return tuple(
        replace(item, semantic_shape=replacements.get(item.structure_id, item.semantic_shape))
        for item in structure
    )


def _subtree_has_public_payload(
    structure_id: str,
    nodes: dict[str, ObservationStructureNode],
) -> bool:
    pending = [structure_id]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current in seen or current not in nodes:
            continue
        seen.add(current)
        node = nodes[current]
        if node.label.strip() or node.semantic_target_id:
            return True
        pending.extend(node.child_structure_ids)
    return False
