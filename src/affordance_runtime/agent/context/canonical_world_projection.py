"""One immutable public ordering/ref projection over a fresh World."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from affordance_runtime.actions.capabilities import INTERACTION_CAPABILITY_REGISTRY
from affordance_runtime.actions.space_contracts import ActionSpace
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex, WorldRegion
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.evidence_refs import canonical_fact_ref, canonical_public_text_ref
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind


class PublicGroundingAmbiguousError(ValueError):
    """Typed fail-closed outcome for indistinguishable executable entities."""

    code = "public_grounding_ambiguous"


@dataclass(frozen=True)
class PublicProvenance:
    surface_kind: str
    modality: str
    source_coverage: str
    structural_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.surface_kind, self.modality, self.source_coverage)):
            raise ValueError("public provenance requires bounded source semantics")
        if self.source_coverage not in {"complete", "partial", "stale", "unavailable"}:
            raise ValueError("public provenance coverage is invalid")
        object.__setattr__(
            self,
            "structural_context",
            tuple(value[:240] for value in self.structural_context if value.strip())[:8],
        )


@dataclass(frozen=True)
class PublicTargetRecord:
    ref: str
    structural_slot: tuple[str, ...]
    role: str
    label: str
    state: Mapping[str, object]
    relations: Mapping[str, object]
    verbs: tuple[str, ...]
    provenance: PublicProvenance
    target_id: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not PublicRefCodec.accepts(self.ref, expected=self.ref[:1]) or self.ref[:1] not in {"E", "N"}:
            raise ValueError("canonical target record requires one E/N ref")
        object.__setattr__(self, "structural_slot", tuple(self.structural_slot))
        object.__setattr__(self, "state", freeze_json(dict(self.state)))
        object.__setattr__(self, "relations", freeze_json(dict(self.relations)))
        object.__setattr__(self, "verbs", tuple(self.verbs))

    @property
    def public_value(self) -> Mapping[str, object]:
        return freeze_json({
            "ref": self.ref,
            "slot": self.structural_slot,
            "role": self.role,
            "label": self.label,
            "state": self.state,
            "relations": self.relations,
            "verbs": self.verbs,
            "provenance": to_json_compatible(self.provenance),
        })


@dataclass(frozen=True)
class PublicFactRecord:
    ref: str
    subject_ref: str
    structural_slot: tuple[str, ...]
    predicate: str
    value: object
    provenance: PublicProvenance
    canonical_ref: str = field(repr=False, compare=False)
    subject_id: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        if not PublicRefCodec.accepts(self.ref, expected=PublicRefKind.FACT):
            raise ValueError("canonical fact record requires one F ref")
        object.__setattr__(self, "structural_slot", tuple(self.structural_slot))
        object.__setattr__(self, "value", freeze_json(self.value))

    @property
    def public_value(self) -> Mapping[str, object]:
        return freeze_json({
            "ref": self.ref,
            "subject_ref": self.subject_ref,
            "slot": self.structural_slot,
            "predicate": self.predicate,
            "value": self.value,
            "provenance": to_json_compatible(self.provenance),
        })


@dataclass(frozen=True)
class PublicRegionRecord:
    ref: str
    structural_slot: tuple[str, ...]
    heading: str
    role: str
    coverage: str
    provenance: PublicProvenance
    region_key: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not PublicRefCodec.accepts(self.ref, expected=PublicRefKind.REGION):
            raise ValueError("canonical region record requires one R ref")
        object.__setattr__(self, "structural_slot", tuple(self.structural_slot))

    @property
    def public_value(self) -> Mapping[str, object]:
        return freeze_json({
            "ref": self.ref,
            "slot": self.structural_slot,
            "heading": self.heading,
            "role": self.role,
            "coverage": self.coverage,
            "provenance": to_json_compatible(self.provenance),
        })


@dataclass(frozen=True)
class CanonicalPublicWorldProjection:
    """Sole public record order and E/N/F/R allocator for one fresh World."""

    projection_lineage: str = field(repr=False, compare=False)
    private_observation_id: str = field(repr=False, compare=False)
    private_action_space_id: str = field(repr=False, compare=False)
    private_index_lineage: str = field(repr=False, compare=False)
    public_document_signature: str
    ordered_target_records: tuple[PublicTargetRecord, ...]
    ordered_fact_records: tuple[PublicFactRecord, ...]
    ordered_region_records: tuple[PublicRegionRecord, ...]
    target_refs: Mapping[str, str] = field(repr=False, compare=False)
    fact_refs: Mapping[str, str] = field(repr=False, compare=False)
    private_fact_id_refs: Mapping[str, str] = field(repr=False, compare=False)
    region_refs: Mapping[str, str] = field(repr=False, compare=False)
    target_structural_slots: Mapping[str, tuple[str, ...]] = field(repr=False, compare=False)
    private_target_resolver: Mapping[str, str] = field(repr=False, compare=False)
    private_structure_refs: Mapping[tuple[str, str], str] = field(repr=False, compare=False)
    private_fact_resolver: Mapping[str, str] = field(repr=False, compare=False)
    private_region_resolver: Mapping[str, str] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.projection_lineage.startswith("projection:"):
            raise ValueError("canonical projection requires private lineage")
        if (
            not self.private_observation_id.strip()
            or not self.private_action_space_id.strip()
            or not self.private_index_lineage.startswith("index:")
        ):
            raise ValueError("canonical projection requires private currentness owners")
        if not self.public_document_signature.startswith("public-document:"):
            raise ValueError("canonical projection requires public document signature")
        for name in (
            "target_refs", "fact_refs", "private_fact_id_refs", "region_refs", "target_structural_slots",
            "private_target_resolver", "private_structure_refs", "private_fact_resolver", "private_region_resolver",
        ):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @property
    def public_refs(self) -> frozenset[str]:
        return frozenset((
            *(item.ref for item in self.ordered_target_records),
            *(item.ref for item in self.ordered_fact_records),
            *(item.ref for item in self.ordered_region_records),
        ))

    def region_record(self, region_key: str) -> PublicRegionRecord | None:
        ref = self.region_refs.get(region_key)
        return next((item for item in self.ordered_region_records if item.ref == ref), None)

    def resolve_region_ref(self, public_ref: str) -> str:
        return self.private_region_resolver[public_ref]

    def assert_current(
        self,
        observation: WorldObservation,
        index: WorldDeliveryIndex,
        action_space: ActionSpace,
    ) -> None:
        if (
            self.private_observation_id != observation.observation_id
            or self.private_action_space_id != action_space.action_space_id
            or self.private_index_lineage != _index_lineage(index)
        ):
            raise ValueError("canonical public projection inputs are not current")

    @classmethod
    def build(
        cls,
        observation: WorldObservation,
        index: WorldDeliveryIndex,
        action_space: ActionSpace,
    ) -> "CanonicalPublicWorldProjection":
        if (
            index.world_observation_id != observation.observation_id
            or action_space.observation_id != observation.observation_id
        ):
            raise ValueError("canonical public projection inputs are not current")
        target_candidates = _target_candidates(observation, index, action_space)
        _reject_ambiguous_executable_targets(target_candidates)
        target_records, target_refs, structure_refs = _allocate_targets(target_candidates)
        region_records, region_refs = _allocate_regions(observation, index)
        fact_records, fact_refs = _allocate_facts(observation, index, target_refs)
        public_digest = _digest(_public_document_payload(observation, region_records))
        private_digest = _digest((observation.observation_id, action_space.action_space_id, tuple(
            (item.target_id, item.ref) for item in target_records
        )))
        return cls(
            f"projection:{private_digest}",
            observation.observation_id,
            action_space.action_space_id,
            _index_lineage(index),
            f"public-document:{public_digest}",
            target_records,
            fact_records,
            region_records,
            target_refs,
            fact_refs,
            {
                fact.fact_id: fact_refs[canonical_fact_ref(fact.fact_id)]
                for fact in observation.facts
                if canonical_fact_ref(fact.fact_id) in fact_refs
            },
            region_refs,
            {item.target_id: item.structural_slot for item in target_records},
            {item.ref: item.target_id for item in target_records if "\0" not in item.target_id},
            structure_refs,
            {item.ref: item.canonical_ref for item in fact_records},
            {item.ref: item.region_key for item in region_records},
        )


@dataclass(frozen=True)
class _TargetCandidate:
    target_id: str
    executable: bool
    structural_slot: tuple[str, ...]
    role: str
    label: str
    state: Mapping[str, object]
    relations: Mapping[str, object]
    verbs: tuple[str, ...]
    provenance: PublicProvenance

    @property
    def order_key(self) -> str:
        geometry = self.structural_slot[-1] if self.structural_slot and self.structural_slot[-1].startswith("geometry:") else ""
        return _stable_json((
            1 if geometry in {"", "geometry:unmarked"} else 0,
            geometry,
            self.structural_slot[:-1] if geometry else self.structural_slot,
            self.role.casefold(), self.label.casefold(), self.role,
            self.label, self.state, self.relations, self.verbs, self.provenance,
        ))


def _target_candidates(observation, index, action_space) -> tuple[_TargetCandidate, ...]:
    targets = {item.target_id: item for item in observation.targets}
    offered = {
        target_id
        for option in action_space.options
        for target_id in (option.target_id, *option.eligible_destination_ids)
    }
    options: dict[str, list[object]] = defaultdict(list)
    for option in action_space.options:
        options[option.target_id].append(option)
    result = []
    for target in observation.targets:
        verbs = tuple(sorted({
            INTERACTION_CAPABILITY_REGISTRY.require(option.semantic_action).semantic_action
            for option in options.get(target.target_id, ())
        }))
        result.append(_TargetCandidate(
            target.target_id,
            target.target_id in offered,
            (*_target_slot(index, target.target_id), *_target_geometry(observation, target.target_id)),
            target.role,
            target.label,
            _public_mapping(target.state),
            _public_relations(target.relations, targets, index),
            verbs,
            _target_provenance(observation, index, target.target_id),
        ))
    for source in observation.sources:
        for node in source.structure:
            private_key = f"{source.observation_id}\0{node.structure_id}"
            result.append(_TargetCandidate(
                private_key,
                False,
                _structure_slot(source, node.structure_id),
                node.role,
                node.label,
                _public_mapping(node.state),
                {},
                (),
                _provenance(observation, None, "", [source.observation_id], structural=_structure_slot(source, node.structure_id)),
            ))
    return tuple(result)


def _reject_ambiguous_executable_targets(candidates: tuple[_TargetCandidate, ...]) -> None:
    groups: dict[str, list[_TargetCandidate]] = defaultdict(list)
    for item in candidates:
        if item.executable:
            groups[item.order_key].append(item)
    if any(len(items) > 1 for items in groups.values()):
        raise PublicGroundingAmbiguousError(PublicGroundingAmbiguousError.code)


def _allocate_targets(candidates):
    ordered = sorted(candidates, key=lambda item: item.order_key)
    executable = readonly = 0
    records = []
    refs = {}
    for item in ordered:
        if item.executable:
            executable += 1
            ref = PublicRefCodec.encode(PublicRefKind.EXECUTABLE, executable)
        else:
            readonly += 1
            ref = PublicRefCodec.encode(PublicRefKind.NODE, readonly)
        refs[item.target_id] = ref
        records.append(PublicTargetRecord(
            ref, item.structural_slot, item.role, item.label, item.state, item.relations,
            item.verbs, item.provenance, item.target_id,
        ))
    target_refs = {key: value for key, value in refs.items() if "\0" not in key}
    structure_refs = {
        tuple(key.split("\0", 1)): value for key, value in refs.items() if "\0" in key
    }
    return tuple(records), target_refs, structure_refs


def _allocate_regions(observation, index):
    candidates = sorted(index.regions, key=lambda item: _region_order_key(observation, item))
    records = []
    refs = {}
    for ordinal, region in enumerate(candidates, 1):
        ref = PublicRefCodec.encode(PublicRefKind.REGION, ordinal)
        refs[region.key] = ref
        records.append(PublicRegionRecord(
            ref,
            _region_slot(observation, region),
            region.heading,
            region.role,
            region.coverage,
            _region_provenance(observation, region),
            region.key,
        ))
    return tuple(records), refs


def _allocate_facts(observation, index, target_refs):
    candidates: list[tuple[str, str, str, tuple[str, ...], str, object, PublicProvenance]] = []
    for fact in observation.facts:
        canonical = canonical_fact_ref(fact.fact_id)
        slot = _target_slot(index, fact.subject_id)
        provenance = _fact_provenance(observation, index, fact.subject_id, fact.source_id)
        if provenance.source_coverage in {"stale", "unavailable"}:
            continue
        candidates.append((
            _stable_json((slot, fact.predicate, freeze_json(fact.value),
                          provenance)),
            canonical,
            fact.subject_id,
            slot,
            fact.predicate,
            fact.value,
            provenance,
        ))
    for target in observation.targets:
        label = target.label.strip()
        if label:
            slot = _target_slot(index, target.target_id)
            provenance = _target_provenance(observation, index, target.target_id)
            if provenance.source_coverage in {"stale", "unavailable"}:
                continue
            candidates.append((
                _stable_json((slot, "public.label", label, provenance)),
                canonical_public_text_ref(observation.observation_id, target.target_id),
                target.target_id,
                slot,
                "public.label",
                label,
                provenance,
            ))
    candidates.sort(key=lambda item: item[0])
    records = []
    refs = {}
    for ordinal, (_key, canonical, subject_id, slot, predicate, value, provenance) in enumerate(candidates, 1):
        ref = PublicRefCodec.encode(PublicRefKind.FACT, ordinal)
        refs[canonical] = ref
        records.append(PublicFactRecord(
            ref, target_refs.get(subject_id, ""), slot, predicate, value, provenance, canonical, subject_id,
        ))
    return tuple(records), refs


def _target_slot(index: WorldDeliveryIndex, target_id: str) -> tuple[str, ...]:
    context = index.functional_context_for_target(target_id)
    region = index.region_for_target(target_id)
    if context is None or region is None:
        return ()
    return (
        context.container_kind.value,
        *index.functional_path_for_target(target_id)[:8],
        region.heading,
        region.role,
        str(context.public_order),
    )


def _target_geometry(observation, target_id: str) -> tuple[str, ...]:
    boxes = tuple(sorted(
        region.bbox
        for media in observation.media
        for region in media.media.grounding_regions
        if region.target_id == target_id
    ))
    return (
        ("geometry:" + ",".join(f"{value:+012d}" for value in boxes[0])),
    ) if boxes else ("geometry:unmarked",)


def _structure_slot(source, structure_id: str) -> tuple[str, ...]:
    nodes = {item.structure_id: item for item in source.structure}
    lineage = []
    current = nodes.get(structure_id)
    seen = set()
    while current is not None and current.structure_id not in seen:
        seen.add(current.structure_id)
        lineage.append(f"{current.role}:{current.label}")
        current = nodes.get(current.parent_structure_id)
    lineage.reverse()
    if not lineage:
        return ("structure",)
    siblings = tuple(
        item for item in source.structure
        if item.parent_structure_id == nodes[structure_id].parent_structure_id
    )
    semantic = (nodes[structure_id].role, nodes[structure_id].label)
    occurrence = sum(
        (item.role, item.label) == semantic
        for item in siblings[:siblings.index(nodes[structure_id])]
    )
    return ("structure", *lineage[:-1], f"{lineage[-1]}#{occurrence}")


def _region_slot(observation, region: WorldRegion) -> tuple[str, ...]:
    manifest = next((item for item in observation.source_manifest if item.source_observation_id == region.source_id), None)
    source = (manifest.surface, manifest.modality, manifest.profile) if manifest is not None else ("world", "semantic", "")
    source_observation = next(
        (item for item in observation.sources if item.observation_id == region.source_id),
        None,
    )
    structural_path = (
        _structure_ordinal_path(source_observation, region.root_structure_id)
        if source_observation is not None
        else ()
    )
    return (*source, *structural_path, region.role, region.heading, *region.scope_path)


def _region_order_key(observation, region) -> str:
    targets = {item.target_id: item for item in observation.targets}
    facts = {item.fact_id: item for item in observation.facts}
    member_targets = tuple(sorted(
        (
            (
                targets[item].role,
                targets[item].label,
                _public_mapping(targets[item].state),
            )
            for item in region.member_target_ids
            if item in targets
        ),
        key=_stable_json,
    ))
    member_facts = tuple(sorted(
        (
            (
                facts[item].predicate,
                _public_value(facts[item].value),
            )
            for item in region.member_fact_ids
            if item in facts
        ),
        key=_stable_json,
    ))
    return _stable_json((
        _region_slot(observation, region),
        region.direct_labels,
        region.coverage,
        member_targets,
        member_facts,
    ))


def _structure_ordinal_path(source: object, structure_id: str) -> tuple[str, ...]:
    nodes = {item.structure_id: item for item in getattr(source, "structure", ())}
    if structure_id not in nodes:
        return ()
    roots = sorted(
        (item for item in nodes.values() if not item.parent_structure_id),
        key=lambda item: (item.role.casefold(), item.label.casefold(), item.role, item.label),
    )
    path = []
    current = nodes[structure_id]
    seen = set()
    while current.structure_id not in seen:
        seen.add(current.structure_id)
        if current.parent_structure_id and current.parent_structure_id in nodes:
            parent = nodes[current.parent_structure_id]
            path.append(parent.child_structure_ids.index(current.structure_id))
            current = parent
        else:
            path.append(roots.index(current))
            break
    return tuple(f"ordinal:{item}" for item in reversed(path))


def _public_relations(relations, targets, index):
    result = {}
    for key, value in relations.items():
        normalized = str(key).casefold()
        if normalized.endswith("parent_id") and isinstance(value, str):
            result[str(key).removesuffix("_id")] = _related_semantics(targets.get(value), index)
        elif normalized.endswith("child_ids") and isinstance(value, tuple | list):
            result[str(key).removesuffix("_ids")] = tuple(sorted(
                (_related_semantics(targets.get(item), index) for item in value if isinstance(item, str)),
                key=repr,
            ))
        elif not normalized.endswith("_id") and not normalized.endswith("_ids"):
            result[str(key)] = _public_value(value)
    return result


def _related_semantics(target, index):
    return (target.role, target.label, _target_slot(index, target.target_id)) if target is not None else ("unknown", "", ())


def _public_mapping(value):
    return {str(key): _public_value(item) for key, item in value.items() if not _private_key(str(key))}


def _public_value(value):
    if isinstance(value, Mapping):
        return _public_mapping(value)
    if isinstance(value, tuple | list):
        return tuple(_public_value(item) for item in value)
    return value


def _private_key(key: str) -> bool:
    lowered = key.casefold()
    return any(token in lowered for token in (
        "backend", "binding", "bbox", "capture", "coordinate", "credential", "executor",
        "fact_id", "observation_id", "selector", "source_id", "target_id", "token",
    ))


def _target_provenance(observation, index, target_id):
    links = [item.source_observation_id for item in observation.entity_source_links if item.canonical_target_id == target_id]
    return _provenance(observation, index, target_id, links)


def _fact_provenance(observation, index, subject_id, source_id):
    return _provenance(observation, index, subject_id, [source_id] if source_id else [])


def _region_provenance(observation, region):
    return _provenance(observation, None, "", [region.source_id], structural=region.scope_path)


def _provenance(observation, index, subject_id, source_ids, *, structural=()):
    manifests = {item.source_observation_id: item for item in observation.source_manifest}
    values = []
    for source_id in source_ids:
        manifest = manifests.get(source_id)
        if manifest is not None:
            values.append((manifest.surface, manifest.modality, _coverage(manifest.coverage)))
    surface, modality, coverage = min(values) if values else ("unified_world", "semantic", "complete")
    if not structural and index is not None:
        region = index.region_for_target(subject_id)
        structural = (
            *index.functional_path_for_target(subject_id)[:8],
            region.heading if region is not None else "",
            region.role if region is not None else "",
        )
    return PublicProvenance(surface, modality, coverage, tuple(item for item in structural if item))


def _coverage(value: CoverageState) -> str:
    return {
        CoverageState.COMPLETE: "complete",
        CoverageState.TRUNCATED: "partial",
        CoverageState.STALE: "stale",
    }.get(value, "unavailable")


def _stable_json(value) -> str:
    return json.dumps(to_json_compatible(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value) -> str:
    return hashlib.sha256(_stable_json(value).encode()).hexdigest()


def _index_lineage(index: WorldDeliveryIndex) -> str:
    return "index:" + _digest((
        index.world_observation_id,
        tuple(
            (
                item.key,
                item.member_target_ids,
                item.member_fact_ids,
                item.member_action_ids,
            )
            for item in index.regions
        ),
    ))


def _public_document_payload(observation, regions):
    page_semantics = tuple(sorted(
        (
            str(target.state.get("page.route", "")),
            str(target.state.get("page.title", "")),
            target.role,
        )
        for target in observation.targets
        if target.role.casefold() in {"viewport", "webarea", "rootwebarea", "document"}
    ))
    sources = tuple(sorted(
        (item.surface, item.modality, item.profile)
        for item in observation.source_manifest
    ))
    return {
        "page": page_semantics,
        "sources": sources,
        "regions": tuple(item.public_value for item in regions),
    }


__all__ = [
    "CanonicalPublicWorldProjection",
    "PublicFactRecord",
    "PublicGroundingAmbiguousError",
    "PublicProvenance",
    "PublicRegionRecord",
    "PublicTargetRecord",
]
