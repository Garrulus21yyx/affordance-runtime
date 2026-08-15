"""One bounded, structure-preserving epistemic snapshot for the grounded Actor."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from affordance_runtime.agent.context.budgets import BoundedSection
from affordance_runtime.agent.context.world_projection import ModelTargetView, ModelWorldView
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref

if TYPE_CHECKING:
    from affordance_runtime.agent.context.context import AgentGroundingIndexView, AgentImageInput


_MAX_FACET_COLLECTIONS = 24


@dataclass(frozen=True)
class ActorWorldFactView:
    evidence_ref: str
    field: str
    value: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class ActorWorldGlobalFactView:
    evidence_ref: str
    subject: str
    field: str
    value: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class ActorWorldNodeView:
    ref: str
    role: str
    label: str
    state: Mapping[str, object] = field(default_factory=dict)
    state_evidence: Mapping[str, str] = field(default_factory=dict)
    facts: tuple[ActorWorldFactView, ...] = ()
    relations: Mapping[str, object] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()
    marked: bool = False
    children: tuple[ActorWorldNodeView, ...] = ()
    parent_outside_snapshot: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "state_evidence", freeze_json(self.state_evidence))
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "relations", freeze_json(self.relations))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "children", tuple(self.children))


@dataclass(frozen=True)
class ActorWorldDocumentView:
    source_ref: str
    modality: str
    roots: tuple[ActorWorldNodeView, ...]
    retained_node_count: int = 0
    total_node_count: int = 0
    truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "roots", tuple(self.roots))
        if self.retained_node_count < 0 or self.total_node_count < self.retained_node_count:
            raise ValueError("Actor world document counts are invalid")
        if self.truncated != (self.total_node_count > self.retained_node_count):
            raise ValueError("Actor world document truncation is untruthful")
        if sum(1 for root in self.roots for _ in _walk_nodes(root)) != self.retained_node_count:
            raise ValueError("Actor world retained-node count does not match its forest")


@dataclass(frozen=True)
class ActorWorldSourceView:
    source_ref: str
    modality: str
    assurance: str
    freshness: str
    inventory_coverage: str
    projection_coverage: str
    rendering_coverage: str
    semantic_interpretation: str = "open_world"


@dataclass(frozen=True)
class ActorWorldMediaView:
    evidence_ref: str
    source_ref: str
    kind: str
    mime_type: str
    sha256: str
    availability: str
    attachment: str
    aligned_node_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "aligned_node_refs", tuple(self.aligned_node_refs))


@dataclass(frozen=True)
class ActorWorldBooleanPartitionView:
    field: str
    true_member_refs: tuple[str, ...]
    false_member_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "true_member_refs", tuple(self.true_member_refs))
        object.__setattr__(self, "false_member_refs", tuple(self.false_member_refs))
        if set(self.true_member_refs).intersection(self.false_member_refs):
            raise ValueError("Actor world boolean partition members must be disjoint")


@dataclass(frozen=True)
class ActorWorldFacetCollectionView:
    scope_role: str
    field: str
    value: object
    member_refs: tuple[str, ...]
    member_count: int
    completeness: str
    boolean_partitions: tuple[ActorWorldBooleanPartitionView, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))
        object.__setattr__(self, "member_refs", tuple(self.member_refs))
        object.__setattr__(self, "boolean_partitions", tuple(self.boolean_partitions))
        if self.member_count != len(self.member_refs) or len(set(self.member_refs)) != self.member_count:
            raise ValueError("Actor world facet collection members must be complete and unique")
        if self.completeness not in {"complete_for_snapshot", "partial", "unknown"}:
            raise ValueError("Actor world facet collection completeness is invalid")
        members = set(self.member_refs)
        if any(
            set(partition.true_member_refs).union(partition.false_member_refs) != members
            for partition in self.boolean_partitions
        ):
            raise ValueError("Actor world boolean partitions must cover their facet collection")


@dataclass(frozen=True)
class ActorWorldSnapshot:
    snapshot_id: str
    documents: tuple[ActorWorldDocumentView, ...]
    sources: tuple[ActorWorldSourceView, ...]
    media: tuple[ActorWorldMediaView, ...]
    global_facts: tuple[ActorWorldGlobalFactView, ...]
    facet_collections: BoundedSection[ActorWorldFacetCollectionView]
    artifacts: tuple[Mapping[str, object], ...]
    conflicts: tuple[Mapping[str, object], ...]
    observation_capabilities: tuple[Mapping[str, str], ...]
    traversal: object = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "documents", tuple(self.documents))
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "media", tuple(self.media))
        object.__setattr__(self, "global_facts", tuple(self.global_facts))
        if not isinstance(self.facet_collections, BoundedSection):
            raise TypeError("Actor world facet collections must be a bounded section")
        object.__setattr__(self, "artifacts", tuple(freeze_json(item) for item in self.artifacts))
        object.__setattr__(self, "conflicts", tuple(freeze_json(item) for item in self.conflicts))
        object.__setattr__(
            self,
            "observation_capabilities",
            tuple(freeze_json(item) for item in self.observation_capabilities),
        )
        source_refs = {item.source_ref for item in self.sources}
        if len(source_refs) != len(self.sources):
            raise ValueError("Actor world source refs must be unique")
        node_refs = [
            node.ref
            for document in self.documents
            for root in document.roots
            for node in _walk_nodes(root)
        ]
        if len(node_refs) != len(set(node_refs)):
            raise ValueError("Actor world node refs must be globally unique")
        if any(document.source_ref not in source_refs for document in self.documents):
            raise ValueError("Actor world document source is unavailable")
        if any(item.source_ref not in source_refs for item in self.media):
            raise ValueError("Actor world media source is unavailable")


def _walk_nodes(root: ActorWorldNodeView):
    yield root
    for child in root.children:
        yield from _walk_nodes(child)


def actor_world_for_delivery(
    snapshot: ActorWorldSnapshot,
    *,
    include_images: bool,
) -> ActorWorldSnapshot:
    """Reflect actual provider attachments without changing epistemic content."""

    def node(item: ActorWorldNodeView) -> ActorWorldNodeView:
        return ActorWorldNodeView(
            item.ref,
            item.role,
            item.label,
            item.state,
            item.state_evidence,
            item.facts,
            item.relations,
            item.source_refs,
            item.marked if include_images else False,
            tuple(node(child) for child in item.children),
            item.parent_outside_snapshot,
        )

    documents = tuple(
        ActorWorldDocumentView(
            item.source_ref,
            item.modality,
            tuple(node(root) for root in item.roots),
            item.retained_node_count,
            item.total_node_count,
            item.truncated,
        )
        for item in snapshot.documents
    )
    media = tuple(
        ActorWorldMediaView(
            item.evidence_ref,
            item.source_ref,
            item.kind,
            item.mime_type,
            item.sha256,
            item.availability,
            "attached" if include_images else "not_attached",
            item.aligned_node_refs,
        )
        for item in snapshot.media
    )
    return ActorWorldSnapshot(
        snapshot.snapshot_id,
        documents,
        snapshot.sources,
        media,
        snapshot.global_facts,
        snapshot.facet_collections,
        snapshot.artifacts,
        snapshot.conflicts,
        snapshot.observation_capabilities,
        snapshot.traversal,
    )


def project_actor_world_snapshot(
    observation: WorldObservation,
    world: ModelWorldView,
    grounding: AgentGroundingIndexView,
    image_inputs: tuple[AgentImageInput, ...],
    max_structure_nodes: int = 128,
) -> ActorWorldSnapshot:
    """Close one Actor view without consulting ActionSpace or ToolSpec."""

    refs = dict(grounding.target_refs)
    visible = {item.target_id: item for item in world.targets.items}
    entity_by_ref = {item.ref: item for item in grounding.entities}
    source_refs = {id(source): f"S{index}" for index, source in enumerate(observation.sources, 1)}
    memberships = _source_memberships(observation, visible, source_refs)
    primary_source = {
        target_id: memberships[target_id][0]
        for target_id in visible
        if memberships.get(target_id)
    }
    fallback_source = next(iter(source_refs.values()), "S1")
    facts_by_subject: dict[str, list[ActorWorldFactView]] = defaultdict(list)
    evidence_by_subject: dict[str, dict[str, str]] = defaultdict(dict)
    global_facts: list[ActorWorldGlobalFactView] = []
    fact_refs = {fact.fact_ref: f"F{index}" for index, fact in enumerate(world.facts.items, 1)}
    for fact in world.facts.items:
        evidence = fact_refs[fact.fact_ref]
        target = visible.get(fact.subject_id)
        if target is not None and target.state.get(fact.predicate) == fact.value:
            evidence_by_subject[fact.subject_id].setdefault(fact.predicate, evidence)
        elif target is not None:
            facts_by_subject[fact.subject_id].append(
                ActorWorldFactView(evidence, fact.predicate, fact.value)
            )
        else:
            global_facts.append(
                ActorWorldGlobalFactView(evidence, "task", fact.predicate, fact.value)
            )

    parent_by_id: dict[str, str] = {}
    explicit_children: dict[str, tuple[str, ...]] = {}
    for target in visible.values():
        parent = target.relations.get("parent_id")
        if isinstance(parent, str):
            parent_by_id[target.target_id] = parent
        children = target.relations.get("child_ids")
        if isinstance(children, Sequence) and not isinstance(children, str | bytes):
            explicit_children[target.target_id] = tuple(
                child for child in children if isinstance(child, str) and child in visible
            )
    derived_children: dict[str, list[str]] = defaultdict(list)
    for child_id, parent_id in parent_by_id.items():
        if parent_id in visible:
            derived_children[parent_id].append(child_id)
    children_by_id = {
        target_id: explicit_children.get(target_id, tuple(derived_children.get(target_id, ())))
        for target_id in visible
    }
    _validate_forest(visible, parent_by_id)

    def node(
        target_id: str,
        active: frozenset[str] = frozenset(),
        allowed: frozenset[str] | None = None,
    ) -> ActorWorldNodeView:
        if target_id in active:
            raise ValueError("Actor world structure contains a cycle")
        target = visible[target_id]
        ref = refs[target_id]
        entity = entity_by_ref[ref]
        relations = _non_tree_relations(target, refs)
        return ActorWorldNodeView(
            ref,
            target.role,
            target.label,
            target.state,
            evidence_by_subject.get(target_id, {}),
            tuple(facts_by_subject.get(target_id, ())),
            relations,
            memberships.get(target_id, (fallback_source,)),
            entity.marked,
            tuple(
                node(child_id, active | {target_id}, allowed)
                for child_id in children_by_id[target_id]
                if allowed is None or child_id in allowed
            ),
            bool(parent_by_id.get(target_id) and parent_by_id[target_id] not in visible),
        )

    roots_by_source: dict[str, list[ActorWorldNodeView]] = defaultdict(list)
    for target_id in visible:
        root_parent_id = parent_by_id.get(target_id)
        if root_parent_id in visible:
            continue
        roots_by_source[primary_source.get(target_id, fallback_source)].append(node(target_id))
    summaries = tuple(world.sources)
    sources = tuple(
        ActorWorldSourceView(
            f"S{index}",
            summary.modality,
            summary.assurance,
            summary.freshness,
            summary.entity_inventory.status,
            summary.projection_coverage,
            _rendering_coverage(observation.sources[index - 1]),
        )
        for index, summary in enumerate(summaries, 1)
    )
    if not sources:
        coverage = "truncated" if world.targets.truncated else "complete"
        sources = (ActorWorldSourceView(
            fallback_source,
            "structural",
            "unknown",
            "current",
            coverage,
            coverage,
            "not_available",
        ),)
    documents = _structure_documents(
        observation,
        sources,
        visible,
        refs,
        entity_by_ref,
        facts_by_subject,
        evidence_by_subject,
        max_structure_nodes,
    )
    if documents:
        represented = {
            item.ref
            for document in documents
            for root in document.roots
            for item in _walk_nodes(root)
        }
        missing_ids = {target_id for target_id, ref in refs.items() if ref not in represented}
        for source in sources:
            source_ids = frozenset(
                target_id
                for target_id in missing_ids
                if primary_source.get(target_id, fallback_source) == source.source_ref
            )
            if not source_ids:
                continue
            roots = tuple(
                node(target_id, allowed=source_ids)
                for target_id in visible
                if target_id in source_ids and parent_by_id.get(target_id) not in source_ids
            )
            documents = (*documents, ActorWorldDocumentView(
                source.source_ref,
                source.modality,
                roots,
                len(source_ids),
                len(source_ids),
                False,
            ))
    if not documents:
        documents = tuple(
            ActorWorldDocumentView(
                source.source_ref,
                source.modality,
                tuple(roots_by_source[source.source_ref]),
                len(visible),
                world.targets.total_count,
                world.targets.truncated,
            )
            for source in sources
            if roots_by_source.get(source.source_ref)
        )
    if not documents and visible:
        documents = (ActorWorldDocumentView(
            fallback_source,
            "structural",
            tuple(node(item) for item in visible),
            len(visible),
            world.targets.total_count,
            world.targets.truncated,
        ),)
    image_by_digest = {item.sha256: item for item in image_inputs}
    media = tuple(
        ActorWorldMediaView(
            f"M{index}",
            _media_source_ref(observation, image.evidence_ref, source_refs),
            "screenshot",
            image.mime_type,
            image.sha256,
            "current",
            "not_attached",
            _media_aligned_refs(observation, image.evidence_ref, refs),
        )
        for index, image in enumerate(image_by_digest.values(), 1)
    )
    conflicts = tuple(
        {
            "subject": refs.get(item.subject_id, ""),
            "field": item.predicate,
            "summary": item.summary,
        }
        for item in world.conflicts.items
    )
    capabilities = tuple(
        {"modality": item.modality, "assurance": item.assurance}
        for item in world.observation_capabilities
    )
    facet_collections = _facet_collections(
        visible,
        refs,
        complete_for_snapshot=(
            not world.targets.truncated
            and any(
                source.entity_inventory.status == "complete"
                and source.projection_coverage == "complete"
                and source.freshness == "current"
                for source in world.sources
            )
        ),
    )
    return ActorWorldSnapshot(
        f"snapshot:{hashlib.sha256(observation.observation_id.encode()).hexdigest()[:16]}",
        documents,
        sources,
        media,
        tuple(global_facts),
        facet_collections,
        tuple(
            {
                "evidence_ref": f"A{index}",
                "kind": item.kind,
                "output_id": item.output_id,
                "summary": item.summary,
            }
            for index, item in enumerate(world.artifact_summaries.items, 1)
        ),
        conflicts,
        capabilities,
        world.traversal,
    )


def _facet_collections(
    visible: Mapping[str, ModelTargetView],
    refs: Mapping[str, str],
    *,
    complete_for_snapshot: bool,
) -> BoundedSection[ActorWorldFacetCollectionView]:
    """Index repeated public facets without interpreting task or action semantics."""

    targets_by_role: dict[str, list[ModelTargetView]] = defaultdict(list)
    for target in visible.values():
        targets_by_role[target.role].append(target)
    collections: list[ActorWorldFacetCollectionView] = []
    for role in sorted(targets_by_role):
        role_targets = targets_by_role[role]
        shared_fields = set.intersection(*(set(item.state) for item in role_targets))
        for field_name in sorted(shared_fields):
            field_values = [item.state[field_name] for item in role_targets]
            if any(not _collection_facet_value(value) for value in field_values):
                continue
            grouped: dict[str, tuple[object, list[ModelTargetView]]] = {}
            for target, value in zip(role_targets, field_values, strict=True):
                key = repr(freeze_json(value))
                grouped.setdefault(key, (value, []))[1].append(target)
            for key in sorted(grouped):
                value, members = grouped[key]
                if len(members) < 2:
                    continue
                ordered_members = sorted(members, key=lambda item: _ref_order(refs[item.target_id]))
                member_refs = tuple(refs[item.target_id] for item in ordered_members)
                boolean_fields = sorted(set.intersection(*(set(item.state) for item in members)))
                partitions = tuple(
                    ActorWorldBooleanPartitionView(
                        boolean_field,
                        tuple(
                            refs[item.target_id]
                            for item in ordered_members
                            if item.state[boolean_field] is True
                        ),
                        tuple(
                            refs[item.target_id]
                            for item in ordered_members
                            if item.state[boolean_field] is False
                        ),
                    )
                    for boolean_field in boolean_fields
                    if all(isinstance(item.state[boolean_field], bool) for item in members)
                )
                collections.append(
                    ActorWorldFacetCollectionView(
                        role,
                        field_name,
                        value,
                        member_refs,
                        len(member_refs),
                        "complete_for_snapshot" if complete_for_snapshot else "partial",
                        partitions,
                    )
                )
    collections.sort(key=lambda item: (item.scope_role, item.field, repr(item.value)))
    shown = tuple(collections[:_MAX_FACET_COLLECTIONS])
    return BoundedSection(shown, len(collections), len(collections) > len(shown))


def _collection_facet_value(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, str | int | float)


def _ref_order(value: str) -> tuple[str, int]:
    prefix, suffix = value[:1], value[1:]
    return prefix, int(suffix) if suffix.isdigit() else 0


def _source_memberships(observation, visible, source_refs) -> dict[str, tuple[str, ...]]:
    memberships: dict[str, list[str]] = defaultdict(list)
    canonical_ids = set(visible)
    for source in observation.sources:
        source_ref = source_refs[id(source)]
        correspondence = {
            item.source_target_id: item.canonical_target_id for item in source.correspondences
        }
        for target in source.targets:
            canonical = correspondence.get(target.target_id, target.target_id)
            if canonical in canonical_ids and source_ref not in memberships[canonical]:
                memberships[canonical].append(source_ref)
    return {key: tuple(value) for key, value in memberships.items()}


def _structure_documents(
    observation,
    sources,
    visible,
    refs,
    entity_by_ref,
    facts_by_subject,
    evidence_by_subject,
    max_structure_nodes: int,
) -> tuple[ActorWorldDocumentView, ...]:
    if max_structure_nodes < 1:
        raise ValueError("Actor structure node bound must be positive")
    next_context_ref = 1
    documents: list[ActorWorldDocumentView] = []
    remaining = max_structure_nodes
    for index, source in enumerate(observation.sources):
        if not source.structure or remaining <= 0:
            continue
        source_ref = f"S{index + 1}"
        by_id = {item.structure_id: item for item in source.structure}
        required = {
            item.structure_id
            for item in source.structure
            if item.semantic_target_id in visible
        }
        for structure_id in tuple(required):
            current = by_id[structure_id]
            while current.parent_structure_id and current.parent_structure_id in by_id:
                if current.parent_structure_id in required:
                    break
                required.add(current.parent_structure_id)
                current = by_id[current.parent_structure_id]
        ordered = [item for item in source.structure if item.structure_id in required]
        ordered.extend(item for item in source.structure if item.structure_id not in required)
        retained = tuple(ordered[:remaining])
        retained_ids = {item.structure_id for item in retained}
        actor_refs: dict[str, str] = {}
        for item in retained:
            semantic_ref = refs.get(item.semantic_target_id)
            if semantic_ref is not None:
                actor_refs[item.structure_id] = semantic_ref
            else:
                actor_refs[item.structure_id] = f"N{next_context_ref}"
                next_context_ref += 1

        def node(structure_id: str, active: frozenset[str] = frozenset()) -> ActorWorldNodeView:
            if structure_id in active:
                raise ValueError("Actor source structure contains a cycle")
            item = by_id[structure_id]
            target = visible.get(item.semantic_target_id)
            target_ref = refs.get(item.semantic_target_id)
            entity = entity_by_ref.get(target_ref or "")
            children = tuple(
                node(child, active | {structure_id})
                for child in item.child_structure_ids
                if child in retained_ids
            )
            return ActorWorldNodeView(
                actor_refs[structure_id],
                target.role if target is not None else item.role,
                target.label if target is not None else item.label,
                target.state if target is not None else item.state,
                evidence_by_subject.get(item.semantic_target_id, {}),
                tuple(facts_by_subject.get(item.semantic_target_id, ())),
                _non_tree_relations(target, refs) if target is not None else {},
                (source_ref,),
                entity.marked if entity is not None else False,
                children,
                item.parent_outside_structure
                or bool(item.parent_structure_id and item.parent_structure_id not in retained_ids),
            )

        roots = tuple(
            node(item.structure_id)
            for item in retained
            if not item.parent_structure_id or item.parent_structure_id not in retained_ids
        )
        documents.append(ActorWorldDocumentView(
            source_ref,
            sources[index].modality,
            roots,
            len(retained),
            source.structure_total_count,
            len(retained) < source.structure_total_count,
        ))
        remaining -= len(retained)
    return tuple(documents)


def _non_tree_relations(target: ModelTargetView, refs: Mapping[str, str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in target.relations.items():
        if key in {"parent_id", "child_ids"}:
            continue
        projected = _relation_value(value, refs)
        if projected is not None:
            result[key] = projected
    return result


def _relation_value(value: object, refs: Mapping[str, str]) -> object | None:
    if isinstance(value, str):
        return refs.get(value, value if not value.startswith(("entity:", "target:")) else None)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        projected = tuple(item for value_item in value if (item := _relation_value(value_item, refs)) is not None)
        return projected
    if value is None or isinstance(value, bool | int | float):
        return value
    return None


def _validate_forest(visible: Mapping[str, ModelTargetView], parent_by_id: Mapping[str, str]) -> None:
    for target_id in visible:
        seen: set[str] = set()
        current = target_id
        while current in visible and current in parent_by_id:
            if current in seen:
                raise ValueError("Actor world parent relation contains a cycle")
            seen.add(current)
            current = parent_by_id[current]


def _rendering_coverage(source) -> str:
    return "current_screenshot_available" if any(item.kind == "screenshot" for item in source.media) else "not_available"


def _media_source_ref(observation, evidence_ref: str, source_refs: Mapping[int, str]) -> str:
    for source in observation.sources:
        for media in source.media:
            if canonical_artifact_ref(source.observation_id, media.media_id) == evidence_ref:
                return source_refs[id(source)]
    return ""


def _media_aligned_refs(observation, evidence_ref: str, refs: Mapping[str, str]) -> tuple[str, ...]:
    for source in observation.sources:
        for media in source.media:
            if canonical_artifact_ref(source.observation_id, media.media_id) == evidence_ref:
                return tuple(
                    refs[item.target_id]
                    for item in media.grounding_regions
                    if item.target_id in refs
                )
    return ()
