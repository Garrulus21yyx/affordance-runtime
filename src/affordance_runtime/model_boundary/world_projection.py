"""Bounded, route-free projection of authoritative world observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_boundary.budgets import BoundedSection, ContextProjectionBudget, serialized_size
from affordance_runtime.world.contracts import WorldObservation

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


@dataclass(frozen=True)
class ModelTargetView:
    target_id: str
    role: str
    label: str
    state: Mapping[str, object] = field(default_factory=dict)
    relations: Mapping[str, object] = field(default_factory=dict)

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


def project_model_world(observation: WorldObservation, budget: ContextProjectionBudget) -> ModelWorldView:
    targets = tuple(
        ModelTargetView(
            item.target_id,
            _text(item.role),
            _text(item.label),
            _public_mapping(item.state, _MAX_STATE_FIELDS),
            _public_mapping(item.relations, budget.max_relations_per_target),
        )
        for item in observation.targets[: budget.max_targets]
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
        projected_facts.append(PublicFactView(fact.fact_id, fact.subject_id, _text(fact.predicate), _public_value(fact.value)))
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
        sorted(
            {
                _legacy_capability(source)
                for source, coverage in observation.coverage.items()
                if str(coverage) not in {"failed", "not_acquired", "stale"}
            }
        )
    )
    view = ModelWorldView(
        _section(targets, len(observation.targets)),
        _section(tuple(projected_facts), len(observation.facts)),
        _section(conflicts, len(observation.conflicts)),
        _section(shown_artifacts, len(artifact_names)),
        observation_capabilities=tuple(
            ObservationCapabilityView(modality, assurance) for modality, assurance in capabilities
        ),
    )
    return fit_model_world(view, budget.max_total_serialized_bytes // 2)


def fit_model_world(view: ModelWorldView, max_bytes: int) -> ModelWorldView:
    while serialized_size(view) > max_bytes:
        if view.targets.items:
            targets = view.targets.items[:-1]
            visible = {item.target_id for item in targets}
            facts = tuple(item for item in view.facts.items if item.subject_id in visible)
            view = replace(
                view,
                targets=_resize(view.targets, targets),
                facts=_resize(view.facts, facts),
            )
            continue
        if view.facts.items:
            view = replace(view, facts=_resize(view.facts, view.facts.items[:-1]))
            continue
        if view.conflicts.items:
            view = replace(view, conflicts=_resize(view.conflicts, view.conflicts.items[:-1]))
            continue
        if view.artifact_summaries.items:
            view = replace(
                view,
                artifact_summaries=_resize(view.artifact_summaries, view.artifact_summaries.items[:-1]),
            )
            continue
        raise ValueError("model world fixed metadata exceeds its byte budget")
    return view


def _section(items: tuple[Any, ...], total: int) -> BoundedSection[Any]:
    return BoundedSection(items, total, total > len(items))


def _resize(section: BoundedSection[Any], items: tuple[Any, ...]) -> BoundedSection[Any]:
    return BoundedSection(items, section.total_count, section.total_count > len(items))


def _public_mapping(value: Mapping[str, Any], limit: int) -> dict[str, object]:
    return {
        str(key): _public_value(item)
        for key, item in list(value.items())[:limit]
        if not _private_key(str(key))
    }


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
    return any(marker in normalized for marker in _PRIVATE_KEYS)


def _text(value: str) -> str:
    return value if len(value) <= _MAX_STRING else value[: _MAX_STRING - 1] + "…"


def _legacy_capability(source: str) -> tuple[str, str]:
    normalized = source.casefold()
    if normalized == "visual":
        return "visual", "weak"
    if normalized == "wot":
        return "environment_state", "authoritative"
    return "structural", "structural"
