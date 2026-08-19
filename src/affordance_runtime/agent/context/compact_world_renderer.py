"""Compact AX-style delivery of the authoritative ActorWorldSnapshot."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from affordance_runtime.agent.context.actor_world_snapshot import (
    ActorWorldFactView,
    ActorWorldNodeView,
    ActorWorldSnapshot,
    actor_world_for_delivery,
)
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.world_region_index import WorldRegion, WorldRegionIndex
from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.world.contracts import WorldObservation

_DROPPED_STATE_PREFIXES = ("appearance.",)
_DROPPED_STATE_FIELDS = {
    "grid_coordinate_confidence",
    "grid_membership",
    "semantic.dom.tag",
    "semantic.dom.attribute.id",
    "semantic.name_status",
}
_CLASS_FIELD = "semantic.dom.attribute.class_tokens"
_MAX_REGION_DIRECTORY_ENTRIES = 64


def render_compact_actor_world(
    snapshot: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    *,
    include_images: bool,
    region_index: WorldRegionIndex | None = None,
    observation: WorldObservation | None = None,
    expanded_refs: frozenset[str] | None = None,
    selected_region_keys: frozenset[str] | None = None,
    selected_cursor: str = "",
    max_rendered_bytes: int | None = None,
    force_region_delivery: bool = False,
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
    lines = _render_documents(delivered, verbs, source_by_ref)
    rendered = "\n".join(lines)
    if not force_region_delivery and (not max_rendered_bytes or len(rendered.encode()) <= max_rendered_bytes):
        return rendered
    if region_index is None:
        raise ValueError("recoverable region delivery requires a WorldRegionIndex")
    return _render_region_delivery(
        delivered,
        verbs,
        grounding,
        region_index=region_index,
        observation=observation,
        expanded_refs=expanded_refs or frozenset(),
        selected_region_keys=selected_region_keys or frozenset(),
        selected_cursor=selected_cursor,
        max_rendered_bytes=max_rendered_bytes,
    )


def inspect_actor_world(
    snapshot: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    *,
    region_index: WorldRegionIndex,
    observation: WorldObservation,
    action: str,
    region_ref: str = "",
    query: str = "",
    cursor: str = "",
    page_size: int = 8,
) -> Mapping[str, object]:
    """Resolve one read-only folded-world inspection against the full current World."""

    if region_index.world_observation_id != observation.observation_id:
        raise ValueError("region index belongs to a previous observation")
    delivered = actor_world_for_delivery(snapshot, include_images=False)
    verbs = {item.ref: item.verbs for item in grounding.entities}
    if action == "open_region":
        try:
            region = region_index.resolve_public_ref(region_ref)
        except KeyError:
            raise ValueError("region_ref is not present in the current world")
        lines = _render_world_region(
            region,
            delivered,
            grounding,
            verbs,
            observation=observation,
            include_header=True,
        )
        if len(lines) == 1:
            lines.extend(_render_region_members_from_world(region, observation, grounding))
        content, page = _page_rendered_lines(lines, cursor)
        return {
            "action": "open_region",
            "region_ref": region.public_ref,
            "coverage": region.coverage,
            "content": content,
            "page": page,
        }
    if action == "find":
        if not query.strip():
            raise ValueError("find requires a nonblank public-text query")
        matches = _find_matches(region_index, query, observation, grounding)
        offset = _decode_simple_cursor(cursor, len(matches))
        page = matches[offset : offset + page_size]
        next_offset = offset + len(page)
        return {
            "action": "find",
            "query": query[:120],
            "matches": tuple(page),
            "total_count": len(matches),
            "page": {
                "cursor": cursor,
                "next_cursor": str(next_offset) if next_offset < len(matches) else "",
                "has_more": next_offset < len(matches),
            },
            "coverage": _index_coverage(region_index),
        }
    if action == "view_all":
        regions = tuple(region_index.regions)
        offset = _decode_simple_cursor(cursor, len(regions))
        page = regions[offset : offset + page_size]
        next_offset = offset + len(page)
        return {
            "action": "view_all",
            "regions": tuple(
                {
                    "region_ref": region.public_ref,
                    "descriptor": _region_descriptor(region),
                    "content": _page_rendered_lines(
                        _render_world_region(
                            region,
                            delivered,
                            grounding,
                            verbs,
                            observation=observation,
                            include_header=True,
                        )
                        or _render_region_members_from_world(region, observation, grounding),
                        "",
                    )[0],
                }
                for region in page
            ),
            "total_count": len(regions),
            "page": {
                "cursor": cursor,
                "next_cursor": str(next_offset) if next_offset < len(regions) else "",
                "has_more": next_offset < len(regions),
            },
            "coverage": _index_coverage(region_index),
        }
    raise ValueError("inspect_world action is unsupported")


def _render_documents(delivered, verbs, source_by_ref) -> list[str]:
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
            lines.extend(
                _render_node(
                    root,
                    verbs,
                    depth=1,
                    parent_label="",
                )
            )

    if delivered.global_facts:
        lines.append("global_facts")
        lines.extend(
            f"  {item.subject}.{_short_field(item.field)}[{item.evidence_ref}]={_value(item.value)}"
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
    return lines


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
    public_ref = node.ref if _is_model_ref(node.ref) and not (node.ref.startswith("N") and role == "StaticText") else ""
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
        attributes = []
        for key, value in state.items():
            field = _short_field(key)
            evidence_ref = node.state_evidence.get(key)
            if evidence_ref:
                field = f"{field}[{evidence_ref}]"
            attributes.append(f"{field}={_value(value)}")
        if classes and public_ref and not display_label:
            attributes.append(f"class={_value(classes)}")
        if node.marked:
            attributes.append("marked=true")
        if node.parent_outside_snapshot:
            attributes.append("parent=outside_snapshot")
        if node.state_truncated:
            attributes.append(f"state_coverage={len(node.state)}/{node.state_total_count}")
        if current_verbs:
            attributes.append(f"verbs={_value(current_verbs)}")
        elif public_ref.startswith("N"):
            attributes.append("read_only=true")
        attributes.extend(f"fact.{_short_field(item.field)}[{item.evidence_ref}]={_value(item.value)}" for item in node.facts)
        attributes.extend(
            f"relation.{_short_field(key)}={_value(value)}"
            for key, value in node.relations.items()
        )
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


def _render_region_delivery(
    delivered: ActorWorldSnapshot,
    verbs: Mapping[str, tuple[str, ...]],
    grounding: AgentGroundingIndexView,
    *,
    region_index: WorldRegionIndex,
    observation: WorldObservation | None,
    expanded_refs: frozenset[str],
    selected_region_keys: frozenset[str],
    selected_cursor: str,
    max_rendered_bytes: int,
) -> str:
    regions = region_index.regions
    selected_region_keys = selected_region_keys or _default_selected_region_keys(regions, observation)
    expanded: list[WorldRegion] = [
        region
        for region in regions
        if region.key in selected_region_keys
        or _region_public_refs(region, grounding).intersection(expanded_refs)
    ]
    if not expanded and regions:
        expanded.append(regions[0])
    directory_regions = _directory_page(regions, expanded)
    lines = [
        "compact_world format=compact_ax.v1",
        (
            "delivery=region_lens"
            " non_action_content=folded"
            " recovery=inspect_world"
            f" regions={len(regions)}"
            f" expanded={len(expanded)}"
        ),
        (
            "region_directory"
            f" shown={len(directory_regions)}/{len(regions)}"
            f" page_size={_MAX_REGION_DIRECTORY_ENTRIES}"
            + (
                f" next_cursor={_value(str(len(directory_regions)))} recovery=view_all"
                if len(directory_regions) < len(regions)
                else ""
            )
        ),
    ]
    expanded_keys = {region.key for region in expanded}
    for region in directory_regions:
        lines.append(
            "  "
            + _region_header(
                region,
                expanded=region.key in expanded_keys,
                include_recovery=True,
            )
        )
    if delivered.global_facts:
        lines.append("global_facts")
        lines.extend(
            f"  {item.subject}.{_short_field(item.field)}[{item.evidence_ref}]={_value(item.value)}"
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
    if delivered.observation_capabilities:
        lines.append("observation_capabilities")
        lines.extend(f"  {_value(item)}" for item in delivered.observation_capabilities)
    if delivered.traversal is not None:
        lines.append(f"traversal {_value(delivered.traversal)}")
    if expanded:
        lines.append("expanded_regions")
    for region in expanded:
        rendered = _render_world_region(
            region,
            delivered,
            grounding,
            verbs,
            observation=observation,
            include_header=True,
        )
        if observation is not None and len(rendered) == 1:
            rendered.extend(_render_region_members_from_world(region, observation, grounding))
        if region.key in selected_region_keys and selected_cursor:
            content, page = _page_rendered_lines(rendered, selected_cursor)
            rendered = [
                (
                    f"region_page region=[{region.public_ref}]"
                    f" cursor={_value(page['cursor'])}"
                    f" next_cursor={_value(page['next_cursor'])}"
                    f" has_more={str(page['has_more']).lower()}"
                ),
                *content.splitlines(),
            ]
        candidate = [*lines, *rendered]
        if len("\n".join(candidate).encode()) <= max_rendered_bytes or region is expanded[0]:
            lines.extend(rendered)
    return "\n".join(lines)


def _default_selected_region_keys(
    regions: tuple[WorldRegion, ...],
    observation: WorldObservation | None,
) -> frozenset[str]:
    if not regions:
        return frozenset()
    selected: list[str] = []
    target_state: dict[str, Mapping[str, object]] = {}
    if observation is not None:
        target_state = {item.target_id: item.state for item in observation.targets}
    preferred_roles = {
        "alertdialog",
        "dialog",
        "form",
        "search",
        "focused_context",
        "toolbar",
        "viewport",
    }
    for region in regions:
        role = region.role.casefold()
        has_focus_or_active = any(
            bool(target_state.get(target_id, {}).get(key))
            for target_id in region.member_target_ids
            for key in ("active", "focused", "focus")
        )
        bounded = _bounded_default_region(region)
        if bounded and (has_focus_or_active or role in preferred_roles):
            selected.append(region.key)
        if len(selected) >= 6:
            break
    selected_set = set(selected)
    for region in regions:
        if len(selected) >= 6:
            break
        if region.key in selected_set or region.role.casefold() in {"focused_context", "viewport"}:
            continue
        if _bounded_default_region(region) and region.counts.get("actions", 0):
            selected.insert(0, region.key)
            selected_set.add(region.key)
    if not selected:
        selected.append(next((region.key for region in regions if _bounded_default_region(region)), regions[0].key))
    return frozenset(selected)


def _bounded_default_region(region: WorldRegion) -> bool:
    return (
        region.counts.get("targets", len(region.member_target_ids)) <= 80
        and region.counts.get("actions", 0) <= 80
    )


def _directory_page(
    regions: tuple[WorldRegion, ...],
    expanded: list[WorldRegion],
) -> tuple[WorldRegion, ...]:
    selected = list(regions[:_MAX_REGION_DIRECTORY_ENTRIES])
    seen = {region.key for region in selected}
    for region in expanded:
        if region.key not in seen:
            selected.append(region)
            seen.add(region.key)
    return tuple(selected)


def _render_world_region(
    region: WorldRegion,
    delivered: ActorWorldSnapshot,
    grounding: AgentGroundingIndexView,
    verbs: Mapping[str, tuple[str, ...]],
    *,
    observation: WorldObservation | None,
    include_header: bool,
) -> list[str]:
    lines = []
    if include_header:
        lines.append(_region_header(region, expanded=True, include_recovery=False))
    if observation is not None:
        structured = _render_world_region_from_observation(region, observation, grounding, verbs)
        if structured:
            lines.extend(structured)
            return lines
    wanted_refs = _region_public_refs(region, grounding)
    for document in delivered.documents:
        for root in document.roots:
            sliced = _slice_region_node(root, wanted_refs)
            if sliced is not None:
                lines.extend(_render_node(sliced, verbs, depth=1, parent_label=""))
    return lines


def _region_public_refs(region: WorldRegion, grounding: AgentGroundingIndexView) -> frozenset[str]:
    return frozenset(
        grounding.target_refs[target_id]
        for target_id in region.member_target_ids
        if target_id in grounding.target_refs
    )


def _render_world_region_from_observation(
    region: WorldRegion,
    observation: WorldObservation,
    grounding: AgentGroundingIndexView,
    verbs: Mapping[str, tuple[str, ...]],
) -> list[str]:
    source = next((item for item in observation.sources if item.observation_id == region.source_id), None)
    if source is None or not source.structure:
        return []
    nodes = {item.structure_id: item for item in source.structure}
    if region.root_structure_id not in nodes:
        return []
    canonical_by_source_target = {
        item.source_target_id: item.canonical_target_id
        for item in observation.entity_source_links
        if item.source_observation_id == source.observation_id
    }
    targets = {item.target_id: item for item in observation.targets}
    facts_by_subject: dict[str, list[ActorWorldFactView]] = {}
    for fact in observation.facts:
        facts_by_subject.setdefault(fact.subject_id, []).append(
            ActorWorldFactView(fact.fact_id, fact.predicate, fact.value)
        )

    def build(structure_id: str) -> ActorWorldNodeView:
        item = nodes[structure_id]
        canonical_id = canonical_by_source_target.get(item.semantic_target_id, "")
        target = targets.get(canonical_id)
        public_ref = grounding.target_refs.get(canonical_id, "")
        children = tuple(build(child) for child in item.child_structure_ids if child in nodes)
        return ActorWorldNodeView(
            public_ref or item.structure_id,
            target.role if target is not None else item.role,
            (target.label or item.label) if target is not None else item.label,
            target.state if target is not None else item.state,
            {},
            tuple(facts_by_subject.get(canonical_id, ())),
            _non_tree_relations(target.relations, grounding.target_refs) if target is not None else {},
            (),
            False,
            children,
            item.parent_outside_structure,
            0,
            False,
        )

    return _render_node(build(region.root_structure_id), verbs, depth=1, parent_label="")


def _slice_region_node(
    node: ActorWorldNodeView,
    wanted_refs: frozenset[str],
) -> ActorWorldNodeView | None:
    children = tuple(
        child
        for child in (_slice_region_node(child, wanted_refs) for child in node.children)
        if child is not None
    )
    if node.ref in wanted_refs or children:
        return ActorWorldNodeView(
            node.ref,
            node.role,
            node.label,
            node.state,
            node.state_evidence,
            node.facts,
            node.relations,
            node.source_refs,
            node.marked,
            children,
            node.parent_outside_snapshot,
            node.state_total_count,
            node.state_truncated,
        )
    return None


def _render_region_members_from_world(
    region: WorldRegion,
    observation: WorldObservation,
    grounding: AgentGroundingIndexView,
) -> list[str]:
    refs = grounding.target_refs
    targets = {item.target_id: item for item in observation.targets}
    lines: list[str] = []
    for target_id in region.member_target_ids:
        target = targets.get(target_id)
        if target is None:
            continue
        public_ref = refs.get(target_id, "")
        prefix = f"[{public_ref}] " if _is_model_ref(public_ref) else ""
        line = f"  {prefix}{target.role} {_value(target.label)}"
        state = _model_state(target.state, interactive=public_ref.startswith("E"))
        if state:
            line += " " + " ".join(f"{_short_field(key)}={_value(value)}" for key, value in state.items())
        if public_ref.startswith("N"):
            line += " read_only=true"
        lines.append(line)
    for fact in observation.facts:
        if fact.fact_id in region.member_fact_ids:
            lines.append(f"  fact {fact.subject_id}.{_short_field(fact.predicate)}={_value(fact.value)}")
    return lines


def _non_tree_relations(relations: Mapping[str, object], target_refs: Mapping[str, str]) -> dict[str, object]:
    return {
        key: _public_relation_value(value, target_refs)
        for key, value in relations.items()
    }


def _public_relation_value(value: object, target_refs: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return target_refs.get(value, value)
    if isinstance(value, tuple | list):
        return tuple(_public_relation_value(item, target_refs) for item in value)
    if isinstance(value, Mapping):
        return {
            str(key): _public_relation_value(item, target_refs)
            for key, item in value.items()
        }
    return value


def _region_header(region: WorldRegion, *, expanded: bool, include_recovery: bool) -> str:
    line = (
        f"region [{region.public_ref}] document={region.source_id}"
        f" role={_value(region.role or 'unknown')}"
        f" label={_value(region.heading)}"
        f" targets={region.counts.get('targets', len(region.member_target_ids))}"
        f" facts={region.counts.get('facts', len(region.member_fact_ids))}"
        f" actions={region.counts.get('actions', 0)}"
        f" coverage={region.coverage}"
        f" expanded={str(expanded).lower()}"
    )
    if include_recovery and not expanded:
        line += " recovery=open_region"
    return line


def _region_descriptor(region: WorldRegion) -> Mapping[str, object]:
    return {
        "region_ref": region.public_ref,
        "document": region.source_id,
        "role": region.role or "unknown",
        "label": region.heading,
        "targets": region.counts.get("targets", len(region.member_target_ids)),
        "facts": region.counts.get("facts", len(region.member_fact_ids)),
        "actions": region.counts.get("actions", 0),
        "coverage": region.coverage,
    }


def _index_coverage(index: WorldRegionIndex) -> str:
    return "partial" if any(region.coverage != "complete" for region in index.regions) else "complete"


def _find_matches(
    index: WorldRegionIndex,
    query: str,
    observation: WorldObservation,
    grounding: AgentGroundingIndexView,
) -> tuple[Mapping[str, object], ...]:
    needle = query.casefold()[:120]
    matches: list[Mapping[str, object]] = []
    target_region = _target_region_locations(index, grounding)
    entity_by_ref = {item.ref: item for item in grounding.entities}
    for target in observation.targets:
        values = [target.role, target.label, *(str(value) for value in target.state.values())]
        if needle and needle not in " ".join(values).casefold():
            continue
        location = target_region.get(target.target_id, ("", ""))
        node_ref = location[1]
        entity = entity_by_ref.get(node_ref)
        verbs = tuple(entity.verbs) if entity is not None else ()
        matches.append({
            "region_ref": location[0],
            "node_ref": node_ref,
            "role": target.role,
            "label": target.label,
            "actionable": bool(verbs),
            "verbs": verbs,
            "action_refs": (node_ref,) if node_ref.startswith("E") and verbs else (),
            "currentness": {
                "observation_id": observation.observation_id,
                "target_id": target.target_id,
            },
            "snippet": _bounded_snippet(" ".join(values), query),
        })
    for fact in observation.facts:
        values = [fact.subject_id, fact.predicate, str(fact.value)]
        if needle and needle not in " ".join(values).casefold():
            continue
        location = target_region.get(fact.subject_id, ("", ""))
        matches.append({
            "region_ref": location[0],
            "node_ref": location[1],
            "role": "fact",
            "label": fact.predicate,
            "actionable": False,
            "verbs": (),
            "action_refs": (),
            "currentness": {
                "observation_id": observation.observation_id,
                "subject_id": fact.subject_id,
            },
            "snippet": _bounded_snippet(f"{fact.predicate} {fact.value}", query),
        })
    return tuple(matches)


def _target_region_locations(
    index: WorldRegionIndex,
    grounding: AgentGroundingIndexView,
) -> Mapping[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for region in index.regions:
        for target_id in region.member_target_ids:
            result.setdefault(target_id, (region.public_ref, grounding.target_refs.get(target_id, "")))
    return result


def _is_model_ref(value: str) -> bool:
    return (
        len(value) >= 2
        and value[0] in {"E", "N"}
        and value[1:].isdigit()
    )


def _bounded_snippet(haystack: str, query: str) -> str:
    if len(haystack) <= 240:
        return haystack
    index = haystack.casefold().find(query.casefold()[:120])
    if index < 0:
        return haystack[:239] + "…"
    start = max(0, index - 80)
    return haystack[start : start + 240]


def _decode_simple_cursor(cursor: str, total: int) -> int:
    if not cursor:
        return 0
    if not cursor.isdigit():
        raise ValueError("inspect_world cursor is invalid")
    offset = int(cursor)
    if offset < 0 or offset > total:
        raise ValueError("inspect_world cursor is outside the result")
    return offset


def _page_rendered_lines(
    lines: list[str],
    cursor: str,
    *,
    max_bytes: int = 8 * 1024,
) -> tuple[str, Mapping[str, object]]:
    offset = _decode_simple_cursor(cursor, len(lines))
    selected: list[str] = []
    size = 0
    for line in lines[offset:]:
        line_size = len((line + "\n").encode())
        if selected and size + line_size > max_bytes:
            break
        selected.append(line)
        size += line_size
    next_offset = offset + len(selected)
    return "\n".join(selected), {
        "cursor": cursor,
        "next_cursor": str(next_offset) if next_offset < len(lines) else "",
        "has_more": next_offset < len(lines),
    }


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
