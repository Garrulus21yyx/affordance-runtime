"""Bounded, route-free projection of authoritative world observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from affordance_runtime.agent.context.acquisition_projection import ObservationCapabilityView
from affordance_runtime.agent.context.budgets import BoundedSection, ContextProjectionBudget, serialized_size
from affordance_runtime.agent.context.canonical_world_projection import CanonicalPublicWorldProjection
from affordance_runtime.agent.context.observation_paging import (
    ObservationPager,
    ObservationTraversalStatus,
    ObservationTraversalView,
)
from affordance_runtime.agent.context.source_projection import (
    ObservationSourceSummary,
    project_observation_source,
)
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref

_MAX_STRING = 240
_MAX_STATE_FIELDS = 8
_PUBLIC_DOM_FIELDS = frozenset({
    "semantic.dom.attribute.type",
    "semantic.dom.attribute.role",
    "semantic.dom.attribute.title",
    "semantic.dom.attribute.alt",
    "semantic.dom.attribute.placeholder",
    "semantic.dom.attribute.aria-label",
    "semantic.dom.attribute.aria-description",
})
# State used to choose or avoid a currently offered semantic action must survive
# generic metadata pressure.  This is a projection priority, not a second state
# definition: values still come only from the authoritative SemanticTarget.
_ACTION_DECISION_STATE_PRIORITY = {
    key: index
    for index, key in enumerate((
        "value",
        "selected_options",
        "checked",
        "selected",
        "active",
        "expanded",
        "required",
        "option_domain",
        "grid_coordinate",
    ))
}
_TEXT_EVIDENCE_ROLE_PRIORITY = {
    "gridcell": 0,
    "cell": 0,
    "columnheader": 1,
    "rowheader": 1,
    "row": 1,
    "table": 1,
    "heading": 2,
    "statictext": 2,
    "text": 2,
    "paragraph": 3,
    "option": 4,
    "button": 5,
    "link": 5,
}
_PRIVATE_KEYS = (
    "backend",
    "bbox",
    "coordinate",
    "credential",
    "executor",
    "href",
    "method",
    "password",
    "path",
    "point",
    "secret",
    "selector",
    "token",
)
_ROUTE_KEYS = frozenset({"backend", "bbox", "coordinate", "executor", "href", "method", "path", "point", "selector"})


@dataclass(frozen=True)
class ModelTargetView:
    target_id: str
    role: str
    label: str
    state: Mapping[str, object] = field(default_factory=dict)
    relations: Mapping[str, object] = field(default_factory=dict)
    state_total_count: int = 0
    state_truncated: bool = False
    relations_total_count: int = 0
    relations_truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "relations", freeze_json(self.relations))


@dataclass(frozen=True)
class PublicFactView:
    fact_ref: str
    subject_id: str
    predicate: str
    value: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class ConflictSummary:
    subject_id: str
    predicate: str
    summary: str


@dataclass(frozen=True)
class ModelArtifactView:
    evidence_ref: str
    kind: str
    output_id: str
    summary: str


@dataclass(frozen=True)
class ModelWorldView:
    targets: BoundedSection[ModelTargetView]
    facts: BoundedSection[PublicFactView]
    conflicts: BoundedSection[ConflictSummary]
    artifact_summaries: BoundedSection[ModelArtifactView]
    sources: tuple[ObservationSourceSummary, ...] = ()
    observation_capabilities: tuple[ObservationCapabilityView, ...] = ()
    traversal: ObservationTraversalView | None = None


def project_model_world(
    observation: WorldObservation,
    budget: ContextProjectionBudget,
    pinned_target_ids: tuple[str, ...] = (),
    pinned_output_ids: tuple[str, ...] = (),
    observation_capabilities: tuple[ObservationCapabilityView, ...] = (),
    observation_cursor: str = "",
    observation_pager: ObservationPager = ObservationPager(),
    *,
    lossless_public: bool = False,
    canonical_projection: CanonicalPublicWorldProjection,
) -> ModelWorldView:
    # The normal product path has no target-count cap.  In that path this
    # projection is the lossless supported public normalization consumed by
    # ActorWorldSnapshot; model-budget folding belongs to WorldDeliveryView.
    # Explicitly bounded test/caller profiles retain the historical bounded
    # projection semantics.
    target_capacity = (
        max(1, len(observation.targets))
        if lossless_public
        else budget.observation_target_capacity(len(observation.targets))
    )
    basis = observation_pager.begin(
        canonical_projection,
        pinned_target_ids=pinned_target_ids,
        cursor=observation_cursor,
        page_size=target_capacity,
        min_exploration_slots=(
            max(1, len(observation.targets))
            if lossless_public
            else budget.observation_exploration_slots(len(observation.targets))
        ),
    )
    by_id = {item.target_id: item for item in observation.targets}
    ordered_targets = tuple(by_id[target_id] for target_id in basis.target_ids)
    targets = tuple(
        _project_target(
            item,
            None if lossless_public else budget.max_relations_per_target,
            lossless_public=lossless_public,
        )
        for item in ordered_targets
    )
    target_ids = {item.target_id for item in targets}
    pinned_targets = set(pinned_target_ids)
    fact_counts: dict[str, int] = {}
    projected_facts: list[PublicFactView] = []
    ordered_facts = tuple(
        item for item in canonical_projection.ordered_fact_records
        if item.subject_id in target_ids
    )
    ordered_facts = tuple(item for item in ordered_facts if item.subject_id in pinned_targets) + tuple(
        item for item in ordered_facts if item.subject_id not in pinned_targets
    )
    for record in ordered_facts:
        if not lossless_public and len(projected_facts) >= budget.max_facts:
            break
        count = fact_counts.get(record.subject_id, 0)
        if not lossless_public and count >= budget.max_facts_per_target:
            continue
        projected_facts.append(PublicFactView(
            record.ref,
            record.subject_id,
            record.predicate if lossless_public else _text(record.predicate),
            record.value if lossless_public else _public_value(record.value),
        ))
        fact_counts[record.subject_id] = count + 1
    conflicts = tuple(
        ConflictSummary(item.subject_id, _text(item.predicate), _text(item.summary))
        for item in observation.conflicts[: budget.max_conflicts]
    )
    artifact_values = tuple(
        ModelArtifactView(
            canonical_artifact_ref(source.observation_id, str(key)),
            _text(str(key)),
            _text(str(key)),
            _artifact_summary(str(key), source.artifacts[key]),
        )
        for source in observation.sources
        for key in source.artifacts
        if not _private_key(str(key))
    )
    pinned_outputs = set(pinned_output_ids)
    artifacts = tuple(item for item in artifact_values if item.output_id in pinned_outputs) + tuple(
        item for item in artifact_values if item.output_id not in pinned_outputs
    )
    shown_artifacts = artifacts[: budget.max_artifact_summaries]
    manifests = {item.source_observation_id: item for item in observation.source_manifest}
    source_summaries = tuple(
        project_observation_source(
            source,
            manifests[source.observation_id].coverage,
            conflicted=bool(observation.conflicts),
        )
        for source in observation.sources
    )
    provisional_traversal = observation_pager.finish(
        basis,
        tuple(item.target_id for item in targets),
    )
    view = ModelWorldView(
        _section(targets, len(observation.targets)),
        _section(tuple(projected_facts), len(ordered_facts)),
        _section(conflicts, len(observation.conflicts)),
        _section(shown_artifacts, len(artifacts)),
        sources=source_summaries,
        observation_capabilities=observation_capabilities,
        traversal=(
            None if provisional_traversal.status is ObservationTraversalStatus.COMPLETE else provisional_traversal
        ),
    )
    fit_bytes = (
        budget.max_total_serialized_bytes // 2
        if budget.max_total_serialized_bytes < 64 * 1024
        else budget.max_total_serialized_bytes * 3 // 4
    )
    fitted = (
        view
        if lossless_public
        else fit_model_world(
            view,
            fit_bytes,
            pinned_target_ids,
            pinned_output_ids,
            target_groups=_semantic_target_groups(observation),
        )
    )
    traversal = observation_pager.finish(
        basis,
        tuple(item.target_id for item in fitted.targets.items),
    )
    return replace(
        fitted,
        traversal=(None if traversal.status is ObservationTraversalStatus.COMPLETE else traversal),
    )


def fit_model_world(
    view: ModelWorldView,
    max_bytes: int,
    pinned_target_ids: tuple[str, ...] = (),
    pinned_output_ids: tuple[str, ...] = (),
    *,
    allow_target_removal: bool = True,
    target_groups: tuple[frozenset[str], ...] = (),
) -> ModelWorldView:
    pinned = set(pinned_target_ids)
    pinned_outputs = set(pinned_output_ids)
    while serialized_size(view) > max_bytes:
        removable_artifact = next(
            (item for item in reversed(view.artifact_summaries.items) if item.output_id not in pinned_outputs),
            None,
        )
        if removable_artifact is not None:
            view = replace(
                view,
                artifact_summaries=_resize(
                    view.artifact_summaries,
                    tuple(item for item in view.artifact_summaries.items if item != removable_artifact),
                ),
            )
            continue
        if view.conflicts.items:
            view = replace(view, conflicts=_resize(view.conflicts, view.conflicts.items[:-1]))
            continue
        removable_fact = next(
            (
                item
                for item in reversed(view.facts.items)
                if item.subject_id not in pinned
            ),
            None,
        )
        if removable_fact is not None:
            view = replace(
                view,
                facts=_resize(
                    view.facts,
                    tuple(item for item in view.facts.items if item != removable_fact),
                ),
            )
            continue
        removable = next(
            (item for item in reversed(view.targets.items) if allow_target_removal and item.target_id not in pinned),
            None,
        )
        if removable is not None:
            removable_ids = next(
                (group for group in target_groups if removable.target_id in group),
                frozenset({removable.target_id}),
            )
            if removable_ids & pinned:
                # A semantic group containing a pinned target is atomic.
                removable = next(
                    (
                        item
                        for item in reversed(view.targets.items)
                        if item.target_id not in pinned
                        and not any(item.target_id in group and group & pinned for group in target_groups)
                    ),
                    None,
                )
                if removable is None:
                    raise ValueError("model world pinned semantic groups exceed its byte budget")
                removable_ids = next(
                    (group for group in target_groups if removable.target_id in group),
                    frozenset({removable.target_id}),
                )
            targets = tuple(item for item in view.targets.items if item.target_id not in removable_ids)
            visible = {item.target_id for item in targets}
            facts = tuple(item for item in view.facts.items if item.subject_id in visible)
            view = replace(view, targets=_resize(view.targets, targets), facts=_resize(view.facts, facts))
            continue
        raise ValueError("model world fixed metadata exceeds its byte budget")
    return view


def _semantic_target_groups(observation: WorldObservation) -> tuple[frozenset[str], ...]:
    canonical = {
        (item.source_observation_id, item.source_target_id): item.canonical_target_id
        for item in observation.entity_source_links
    }
    groups: list[frozenset[str]] = []
    for source in observation.sources:
        by_id = {item.structure_id: item for item in source.structure}
        for parent in source.structure:
            children = [by_id[item] for item in parent.child_structure_ids if item in by_id]
            signatures: dict[tuple[object, ...], list[object]] = {}
            for child in children:
                state = dict(child.state)
                classes = state.get("semantic.dom.attribute.class_tokens", ())
                if isinstance(classes, list | tuple):
                    classes = tuple(classes)
                signature = (child.role, state.get("semantic.dom.tag", ""), classes)
                signatures.setdefault(signature, []).append(child)
            for siblings in signatures.values():
                if len(siblings) < 2:
                    continue
                for sibling in siblings:
                    pending = [sibling.structure_id]
                    target_ids: set[str] = set()
                    while pending:
                        current = by_id[pending.pop()]
                        if current.semantic_target_id:
                            target_id = canonical.get((source.observation_id, current.semantic_target_id))
                            if target_id:
                                target_ids.add(target_id)
                        pending.extend(item for item in current.child_structure_ids if item in by_id)
                    if target_ids:
                        groups.append(frozenset(target_ids))
    # Outermost repeated card/row groups subsume nested repeated control sets.
    unique = tuple(dict.fromkeys(groups))
    return tuple(group for group in unique if not any(group < other for other in unique))


def _section(items: tuple[Any, ...], total: int) -> BoundedSection[Any]:
    return BoundedSection(items, total, total > len(items))


def _artifact_summary(key: str, value: object) -> str:
    if isinstance(value, Mapping):
        summary = value.get("public_summary")
        if isinstance(summary, str) and summary.strip():
            return _text(summary)
    return _text(f"{key} artifact available")


def _resize(section: BoundedSection[Any], items: tuple[Any, ...]) -> BoundedSection[Any]:
    return BoundedSection(items, section.total_count, section.total_count > len(items))


def _project_target(
    target,
    relation_limit: int | None,
    *,
    lossless_public: bool = False,
) -> ModelTargetView:
    projector = _public_items_lossless if lossless_public else _public_items
    public_state = projector(target.state)
    public_state.sort(key=_state_projection_priority)
    public_relations = projector(target.relations)
    state = dict(public_state if relation_limit is None else public_state[:_MAX_STATE_FIELDS])
    relations = dict(public_relations if relation_limit is None else public_relations[:relation_limit])
    return ModelTargetView(
        target.target_id,
        target.role if lossless_public else _text(target.role),
        target.label if lossless_public else _text(target.label),
        state,
        relations,
        len(public_state),
        len(public_state) > len(state),
        len(public_relations),
        len(public_relations) > len(relations),
    )


def _state_projection_priority(item: tuple[str, object]) -> tuple[int, str]:
    key = item[0].casefold()
    return (_ACTION_DECISION_STATE_PRIORITY.get(key, len(_ACTION_DECISION_STATE_PRIORITY)), key)


def _public_items(value: Mapping[str, Any]) -> list[tuple[str, object]]:
    return [
        (str(key), _public_value(item))
        for key, item in value.items()
        if not _private_key(str(key)) and _public_dom_field(str(key))
    ]


def _public_items_lossless(value: Mapping[str, Any]) -> list[tuple[str, object]]:
    return [
        (str(key), _public_value_lossless(item))
        for key, item in value.items()
        if not _private_key(str(key)) and _public_dom_field(str(key))
    ]


def _public_dom_field(key: str) -> bool:
    normalized = key.casefold()
    return not normalized.startswith("semantic.dom.") or normalized in _PUBLIC_DOM_FIELDS


def _public_mapping(value: Mapping[str, Any], limit: int) -> dict[str, object]:
    return dict(_public_items(value)[:limit])


def _public_value(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if depth >= 2:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        return _public_mapping(value, _MAX_STATE_FIELDS)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_public_value(item, depth + 1) for item in list(value)[:_MAX_STATE_FIELDS]]
    return _text(str(value))


def _public_value_lossless(value: Any) -> Any:
    if isinstance(value, str) or value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _public_value_lossless(item)
            for key, item in value.items()
            if not _private_key(str(key)) and _public_dom_field(str(key))
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_public_value_lossless(item) for item in value]
    return str(value)


def _private_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    # A derived lattice coordinate is a semantic relation, not an executor
    # route or pixel coordinate.  Keep it visible while route-shaped fields
    # remain private.
    if normalized == "grid_coordinate":
        return False
    return (
        normalized in _PRIVATE_KEYS
        or any(normalized.endswith(f"_{marker}") for marker in _PRIVATE_KEYS)
        or any(normalized.startswith(f"{marker}_") for marker in _ROUTE_KEYS)
    )


def _text(value: str) -> str:
    return value if len(value) <= _MAX_STRING else value[: _MAX_STRING - 1] + "…"
