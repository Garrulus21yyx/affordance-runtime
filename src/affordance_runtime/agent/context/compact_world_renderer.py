"""Compact AX-style delivery of the authoritative ActorWorldSnapshot."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldNodeView,
    ActorWorldSnapshot,
    actor_world_for_delivery,
)
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.immutable import to_json_compatible

_DROPPED_STATE_PREFIXES = ("appearance.",)
_DROPPED_STATE_FIELDS = {
    "grid_coordinate_confidence",
    "grid_membership",
    "semantic.dom.tag",
    "semantic.dom.attribute.id",
    "semantic.name_status",
}
_CLASS_FIELD = "semantic.dom.attribute.class_tokens"


def render_compact_actor_world(
    snapshot: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    *,
    include_images: bool,
) -> str:
    """Render one public World without changing its facts, identity, or binding authority.

    The pruning rules mirror mature accessibility-tree formatters at the
    already-projected World boundary: empty structural generics and redundant text boxes disappear,
    while their children keep their relative hierarchy.  Only call-local public
    E-refs are rendered; Runtime identities and evidence lineage remain in trace.
    """

    delivered = actor_world_for_delivery(snapshot, include_images=include_images)
    verbs = {item.ref: item.verbs for item in grounding.entities}
    source_by_ref = {item.source_ref: item for item in delivered.sources}
    lines = ["compact_world format=compact_ax.v1"]
    for document in delivered.documents:
        source = source_by_ref.get(document.source_ref)
        coverage = "partial" if document.truncated else "complete"
        source_detail = ""
        if source is not None:
            source_detail = (
                f" inventory={source.inventory_coverage}"
                f" projection={source.projection_coverage}"
                f" rendering={source.rendering_coverage}"
            )
        lines.append(
            f"document {document.source_ref} modality={document.modality}"
            f" nodes={document.retained_node_count}/{document.total_node_count}"
            f" coverage={coverage}{source_detail}"
        )
        for root in document.roots:
            lines.extend(_render_node(root, verbs, depth=1, parent_label=""))

    if delivered.global_facts:
        lines.append("global_facts")
        lines.extend(
            f"  {item.subject}.{_short_field(item.field)}={_value(item.value)}"
            for item in delivered.global_facts
        )
    if delivered.facet_collections.items:
        lines.append(
            "facets"
            f" count={len(delivered.facet_collections.items)}/{delivered.facet_collections.total_count}"
            f" coverage={'partial' if delivered.facet_collections.truncated else 'complete'}"
        )
        for item in delivered.facet_collections.items:
            line = (
                f"  {item.scope_role}.{_short_field(item.field)}={_value(item.value)}"
                f" members={_value(item.member_refs)} count={item.member_count}"
                f" completeness={item.completeness}"
            )
            lines.append(line)
            for partition in item.boolean_partitions:
                lines.append(
                    f"    {_short_field(partition.field)}"
                    f" true={_value(partition.true_member_refs)}"
                    f" false={_value(partition.false_member_refs)}"
                )
    if delivered.media:
        lines.append("media")
        lines.extend(
            f"  {item.evidence_ref} kind={item.kind} availability={item.availability}"
            f" attachment={item.attachment} aligned={_value(item.aligned_node_refs)}"
            for item in delivered.media
        )
    if delivered.artifacts:
        lines.append("artifacts")
        lines.extend(f"  {_value(item)}" for item in delivered.artifacts)
    if delivered.conflicts:
        lines.append("conflicts")
        lines.extend(f"  {_value(item)}" for item in delivered.conflicts)
    if delivered.observation_capabilities:
        lines.append("observation_capabilities")
        lines.extend(f"  {_value(item)}" for item in delivered.observation_capabilities)
    if delivered.traversal is not None:
        lines.append(f"traversal {_value(delivered.traversal)}")
    return "\n".join(lines)


def _render_node(
    node: ActorWorldNodeView,
    verbs: Mapping[str, tuple[str, ...]],
    *,
    depth: int,
    parent_label: str,
) -> list[str]:
    label = node.label.strip()
    role = node.role.strip() or "unknown"
    classes = _class_tokens(node.state.get(_CLASS_FIELD))
    public_ref = node.ref if node.ref.startswith("E") else ""
    current_verbs = verbs.get(public_ref, ())
    state = _model_state(node.state, interactive=bool(current_verbs))

    skip = role == "InlineTextBox" or (role == "StaticText" and not label)
    if role == "StaticText" and label and parent_label and label in parent_label:
        skip = True
    if role.casefold() == "generic" and not public_ref and not label and not state and not node.facts and not node.relations:
        skip = True

    display_label = label
    if not display_label and public_ref and classes:
        display_label = " ".join(classes)
    display_role = "group" if role.casefold() == "generic" and public_ref else role
    current_depth = depth
    lines: list[str] = []
    if not skip:
        prefix = f"[{public_ref}] " if public_ref else ""
        line = f"{'  ' * depth}{prefix}{display_role}"
        if display_label:
            line += f" {_value(display_label)}"
        attributes = [f"{_short_field(key)}={_value(value)}" for key, value in state.items()]
        if classes and public_ref and not display_label:
            attributes.append(f"class={_value(classes)}")
        if node.marked:
            attributes.append("marked=true")
        if node.parent_outside_snapshot:
            attributes.append("parent=outside_snapshot")
        if node.state_truncated:
            attributes.append(f"state_coverage={len(node.state)}/{node.state_total_count}")
        attributes.extend(f"fact.{_short_field(item.field)}={_value(item.value)}" for item in node.facts)
        attributes.extend(
            f"relation.{_short_field(key)}={_value(value)}"
            for key, value in node.relations.items()
        )
        if current_verbs:
            attributes.append(f"verbs={_value(current_verbs)}")
        if attributes:
            line += " " + " ".join(attributes)
        lines.append(line)
        current_depth += 1

    child_parent_label = display_label or parent_label
    for child in node.children:
        lines.extend(
            _render_node(
                child,
                verbs,
                depth=current_depth,
                parent_label=child_parent_label,
            )
        )
    return lines


def _model_state(state: Mapping[str, object], *, interactive: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in state.items():
        if key == _CLASS_FIELD or key in _DROPPED_STATE_FIELDS:
            continue
        if any(key.startswith(prefix) for prefix in _DROPPED_STATE_PREFIXES):
            continue
        if key == "viewport.visible" and value is True:
            continue
        if key in {"active", "checked", "selected", "pressed", "expanded", "disabled"}:
            if value is False and not interactive:
                continue
        result[key] = value
    return result


def _class_tokens(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return ()


def _short_field(value: str) -> str:
    for prefix in ("semantic.dom.attribute.", "semantic.", "viewport."):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _value(value: object) -> str:
    return json.dumps(
        to_json_compatible(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
