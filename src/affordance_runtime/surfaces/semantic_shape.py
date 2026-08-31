"""Shared explicit-role conversion used at structural SurfaceAdapter boundaries."""

from __future__ import annotations

from affordance_runtime.world.contracts import SemanticShape, SemanticShapeKind

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
    if has_semantic_target or not has_children:
        return SemanticShape.resolved(SemanticShapeKind.ATOM, complete=complete)
    return SemanticShape.unknown("source_role_has_no_compositional_contract", incomplete=not complete)
