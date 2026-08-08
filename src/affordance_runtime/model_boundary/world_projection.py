"""Bounded, route-free projection of authoritative world observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_boundary.budgets import BoundedSection, ContextProjectionBudget, serialized_size
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_fact_ref

_MAX_STRING = 240
_MAX_STATE_FIELDS = 8
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
class ObservationSourceSummary:
    modality: str
    assurance: str
    verification_strength: str
    acquisition_cost: str
    coverage: str
    freshness: str
    conflict_status: str


@dataclass(frozen=True)
class ObservationCapabilityView:
    modality: str
    assurance: str


@dataclass(frozen=True)
class ModelWorldView:
    targets: BoundedSection[ModelTargetView]
    facts: BoundedSection[PublicFactView]
    conflicts: BoundedSection[ConflictSummary]
    artifact_summaries: BoundedSection[str]
    sources: tuple[ObservationSourceSummary, ...] = ()
    observation_capabilities: tuple[ObservationCapabilityView, ...] = ()


def project_model_world(
    observation: WorldObservation,
    budget: ContextProjectionBudget,
    pinned_target_ids: tuple[str, ...] = (),
) -> ModelWorldView:
    pinned = set(pinned_target_ids)
    ordered_targets = tuple(item for item in observation.targets if item.target_id in pinned) + tuple(
        item for item in observation.targets if item.target_id not in pinned
    )
    targets = tuple(
        _project_target(item, budget.max_relations_per_target)
        for item in ordered_targets[: budget.max_targets]
    )
    target_ids = {item.target_id for item in targets}
    fact_counts: dict[str, int] = {}
    projected_facts: list[PublicFactView] = []
    for fact in observation.facts:
        if len(projected_facts) >= budget.max_facts:
            break
        if fact.subject_id not in target_ids:
            continue
        count = fact_counts.get(fact.subject_id, 0)
        if count >= budget.max_facts_per_target:
            continue
        projected_facts.append(
            PublicFactView(canonical_fact_ref(fact.fact_id), fact.subject_id, _text(fact.predicate), _public_value(fact.value))
        )
        fact_counts[fact.subject_id] = count + 1
    conflicts = tuple(
        ConflictSummary(item.subject_id, _text(item.predicate), _text(item.summary))
        for item in observation.conflicts[: budget.max_conflicts]
    )
    artifact_names = tuple(
        _text(str(key))
        for source in observation.sources
        for key in source.artifacts
        if not _private_key(str(key))
    )
    shown_artifacts = artifact_names[: budget.max_artifact_summaries]
    capabilities = tuple(
        sorted(_capabilities(observation))
    )
    source_summaries = tuple(
        ObservationSourceSummary(
            source.source_profile.modality,
            source.source_profile.assurance,
            source.source_profile.verification_strength,
            source.source_profile.acquisition_cost,
            observation.coverage.get(source.surface, source.coverage),
            "stale"
            if str(observation.coverage.get(source.surface, source.coverage)) == "stale"
            else "current",
            "conflicted" if observation.conflicts else "clear",
        )
        for source in observation.sources
    )
    view = ModelWorldView(
        _section(targets, len(observation.targets)),
        _section(tuple(projected_facts), len(observation.facts)),
        _section(conflicts, len(observation.conflicts)),
        _section(shown_artifacts, len(artifact_names)),
        sources=source_summaries,
        observation_capabilities=tuple(
            ObservationCapabilityView(modality, assurance) for modality, assurance in capabilities
        ),
    )
    return fit_model_world(view, budget.max_total_serialized_bytes // 2, pinned_target_ids)


def fit_model_world(
    view: ModelWorldView,
    max_bytes: int,
    pinned_target_ids: tuple[str, ...] = (),
) -> ModelWorldView:
    pinned = set(pinned_target_ids)
    while serialized_size(view) > max_bytes:
        if view.artifact_summaries.items:
            view = replace(
                view,
                artifact_summaries=_resize(view.artifact_summaries, view.artifact_summaries.items[:-1]),
            )
            continue
        if view.conflicts.items:
            view = replace(view, conflicts=_resize(view.conflicts, view.conflicts.items[:-1]))
            continue
        if view.facts.items:
            view = replace(view, facts=_resize(view.facts, view.facts.items[:-1]))
            continue
        removable = next((item for item in reversed(view.targets.items) if item.target_id not in pinned), None)
        if removable is not None:
            targets = tuple(item for item in view.targets.items if item.target_id != removable.target_id)
            visible = {item.target_id for item in targets}
            facts = tuple(item for item in view.facts.items if item.subject_id in visible)
            view = replace(view, targets=_resize(view.targets, targets), facts=_resize(view.facts, facts))
            continue
        raise ValueError("model world fixed metadata exceeds its byte budget")
    return view


def _section(items: tuple[Any, ...], total: int) -> BoundedSection[Any]:
    return BoundedSection(items, total, total > len(items))


def _resize(section: BoundedSection[Any], items: tuple[Any, ...]) -> BoundedSection[Any]:
    return BoundedSection(items, section.total_count, section.total_count > len(items))


def _project_target(target, relation_limit: int) -> ModelTargetView:
    public_state = _public_items(target.state)
    public_relations = _public_items(target.relations)
    state = dict(public_state[:_MAX_STATE_FIELDS])
    relations = dict(public_relations[:relation_limit])
    return ModelTargetView(
        target.target_id,
        _text(target.role),
        _text(target.label),
        state,
        relations,
        len(public_state),
        len(public_state) > len(state),
        len(public_relations),
        len(public_relations) > len(relations),
    )


def _public_items(value: Mapping[str, Any]) -> list[tuple[str, object]]:
    return [
        (str(key), _public_value(item))
        for key, item in value.items()
        if not _private_key(str(key))
    ]


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


def _private_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in _PRIVATE_KEYS or any(
        normalized.endswith(f"_{marker}") for marker in _PRIVATE_KEYS
    ) or any(normalized.startswith(f"{marker}_") for marker in _ROUTE_KEYS)


def _text(value: str) -> str:
    return value if len(value) <= _MAX_STRING else value[: _MAX_STRING - 1] + "…"


def _legacy_capability(source: str) -> tuple[str, str]:
    normalized = source.casefold()
    if normalized == "visual":
        return "visual", "weak"
    if normalized == "wot":
        return "environment_state", "authoritative"
    return "structural", "structural"


def _capabilities(observation: WorldObservation) -> set[tuple[str, str]]:
    if observation.sources:
        return {
            (source.source_profile.modality, source.source_profile.assurance)
            for source in observation.sources
        }
    return {
        _legacy_capability(source)
        for source, coverage in observation.coverage.items()
        if str(coverage) not in {"failed", "not_acquired", "stale"}
    }
