"""Change-first, reversible delivery projection over the current public World."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import (
    PublicChangeKind,
    PublicWorldDelta,
)
from affordance_runtime.agent.working_facts import is_public_scalar
from affordance_runtime.agent.workspace import CurrentFinding
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.contracts import CoverageState, WorldObservation


@dataclass(frozen=True)
class LatestEffect:
    step_index: int
    caused_by: str
    dispatch_status: DispatchStatus
    public_world_delta: PublicWorldDelta

    def __post_init__(self) -> None:
        if type(self.step_index) is not int or self.step_index < 1:
            raise ValueError("latest effect requires a positive committed step")
        if not self.caused_by.strip() or len(self.caused_by) > 240:
            raise ValueError("latest effect requires a bounded public cause")
        if not isinstance(self.dispatch_status, DispatchStatus):
            raise TypeError("latest effect dispatch status must be typed")
        if self.dispatch_status is DispatchStatus.NOT_SENT:
            raise ValueError("an undispatched request cannot become the latest GUI effect")
        if not isinstance(self.public_world_delta, PublicWorldDelta):
            raise TypeError("latest effect requires the authoritative public World delta")


@dataclass(frozen=True)
class LatestEffectValue:
    kind: PublicChangeKind
    predicate: str
    exact_value: object
    public_ref: str
    region_ref: str
    source_context: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PublicChangeKind) or self.kind is PublicChangeKind.REMOVED:
            raise ValueError("latest effect value must be a current addition or modification")
        if not self.predicate.strip() or not self.source_context.strip():
            raise ValueError("latest effect value requires public semantics and context")
        if self.public_ref and self.public_ref[0] not in {"E", "N", "F"}:
            raise ValueError("latest effect value public ref is invalid")
        if self.region_ref and not self.region_ref.startswith("R"):
            raise ValueError("latest effect value region ref is invalid")
        object.__setattr__(self, "exact_value", freeze_json(self.exact_value))


@dataclass(frozen=True)
class ChangedRegion:
    region_key: str
    region_ref: str
    version: int
    cached_outline: tuple[str, ...]
    member_count: int
    recovery_cursor: str = ""

    def __post_init__(self) -> None:
        if (
            not self.region_key.startswith("region:")
            or not self.region_ref.startswith("R")
            or type(self.version) is not int
            or self.version < 1
            or type(self.member_count) is not int
            or self.member_count < 0
        ):
            raise ValueError("changed region delivery is invalid")
        object.__setattr__(self, "cached_outline", tuple(self.cached_outline))


@dataclass(frozen=True)
class PageOutlineEntry:
    region_ref: str
    version: int
    outline: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.region_ref.startswith("R") or type(self.version) is not int or self.version < 1:
            raise ValueError("page outline entry is invalid")
        object.__setattr__(self, "outline", tuple(self.outline))


@dataclass(frozen=True)
class RecoveryDirectoryEntry:
    region_ref: str
    version: int
    member_count: int
    operations: tuple[str, ...] = ("read_region", "search_page_content")

    def __post_init__(self) -> None:
        if (
            not self.region_ref.startswith("R")
            or type(self.version) is not int
            or self.version < 1
            or type(self.member_count) is not int
            or self.member_count < 0
        ):
            raise ValueError("recovery directory entry is invalid")
        operations = tuple(self.operations)
        if not operations or any(item not in {"read_region", "search_page_content"} for item in operations):
            raise ValueError("recovery directory operations are invalid")
        object.__setattr__(self, "operations", operations)


@dataclass(frozen=True)
class ObservationDelivery:
    world_observation_id: str
    latest_effect: LatestEffect | None
    latest_effect_values: tuple[LatestEffectValue, ...]
    current_findings: tuple[CurrentFinding, ...]
    changed_regions: tuple[ChangedRegion, ...]
    page_outline: tuple[PageOutlineEntry, ...]
    recovery_directory: tuple[RecoveryDirectoryEntry, ...]

    def __post_init__(self) -> None:
        if not self.world_observation_id.strip():
            raise ValueError("observation delivery requires current World identity")
        for name, expected in (
            ("latest_effect_values", LatestEffectValue),
            ("current_findings", CurrentFinding),
            ("changed_regions", ChangedRegion),
            ("page_outline", PageOutlineEntry),
            ("recovery_directory", RecoveryDirectoryEntry),
        ):
            values = tuple(getattr(self, name))
            if any(not isinstance(item, expected) for item in values):
                raise TypeError(f"observation delivery {name} must be typed")
            object.__setattr__(self, name, values)


@dataclass(frozen=True)
class ObservationDeliveryStore:
    """Own only latest external GUI effect lifecycle; never current World truth."""

    latest_effect: LatestEffect | None = None

    def advance(self, step: object, *, step_index: int) -> "ObservationDeliveryStore":
        batch = getattr(step, "execution_receipts", None)
        receipts = tuple(getattr(batch, "receipts", ()))
        delta = getattr(step, "public_world_delta", None)
        if not receipts or not isinstance(delta, PublicWorldDelta):
            return self
        final = receipts[-1]
        dispatch = final.result.dispatch_status
        if dispatch is DispatchStatus.NOT_SENT:
            return self
        intent = final.request.intent
        target = next(
            (
                item
                for item in getattr(step, "before_world").targets
                if item.target_id == intent.target_id
            ),
            None,
        )
        label = target.label if target is not None and target.label.strip() else target.role if target is not None else "target"
        cause = f'{intent.semantic_action} {label!r}'
        return ObservationDeliveryStore(LatestEffect(step_index, cause[:240], dispatch, delta))


def project_observation_delivery(
    observation: WorldObservation,
    region_index: WorldDeliveryIndex,
    evidence_index: WorldEvidenceIndex,
    canonical_to_public: Mapping[str, str],
    grounding: AgentGroundingIndexView,
    store: ObservationDeliveryStore,
    *,
    max_findings: int = 12,
) -> ObservationDelivery:
    if region_index.world_observation_id != observation.observation_id:
        raise ValueError("observation delivery index belongs to another World")
    latest = store.latest_effect
    changed_fact_keys = _changed_fact_keys(latest)
    findings = _current_findings(
        observation,
        region_index,
        evidence_index,
        canonical_to_public,
        changed_fact_keys,
        max_findings=max_findings,
    )
    effect_values = _latest_effect_values(
        observation,
        region_index,
        evidence_index,
        canonical_to_public,
        grounding,
        latest,
    )
    changed_keys = tuple(
        key
        for key in (latest.public_world_delta.changed_region_keys if latest is not None else ())
        if region_index.get(key) is not None
    )
    changed_regions = tuple(_changed_region(region_index, key) for key in changed_keys)
    page_outline = tuple(
        PageOutlineEntry(region.public_ref, version.version, version.cached_outline)
        for region in region_index.regions
        if (version := region_index.version_for(region.key)) is not None
    )
    recovery = tuple(
        RecoveryDirectoryEntry(
            region.public_ref,
            version.version,
            len(region.member_structure_ids) + len(region.member_target_ids) + len(region.member_fact_ids),
        )
        for region in region_index.regions
        if (version := region_index.version_for(region.key)) is not None
    )
    return ObservationDelivery(
        observation.observation_id,
        latest,
        effect_values,
        findings,
        changed_regions,
        page_outline,
        recovery,
    )


def _current_findings(
    observation,
    region_index,
    evidence_index,
    canonical_to_public,
    changed_fact_keys,
    *,
    max_findings,
) -> tuple[CurrentFinding, ...]:
    sources = {item.observation_id: item for item in observation.sources}
    candidates: list[tuple[tuple[int, int, str], CurrentFinding]] = []
    for record in evidence_index.records:
        public_ref = canonical_to_public.get(record.evidence_ref, "")
        source = sources.get(record.source_observation_id)
        if (
            not public_ref
            or record.kind != "fact"
            or not is_public_scalar(record.value)
            or source is None
            or source.coverage is CoverageState.STALE
        ):
            continue
        region = region_index.region_for_target(record.subject_id)
        context = " / ".join(
            item
            for item in (
                region.heading if region is not None else "",
                region.role if region is not None else "",
                record.source_id,
            )
            if item
        )[:240]
        finding = CurrentFinding(
            public_ref,
            record.predicate,
            record.value,
            context or "current World",
            source.coverage,
        )
        changed = (record.subject_id, record.predicate, _stable_value(record.value)) in changed_fact_keys
        structural_priority = 0 if region is not None and region.role in {"alert", "grid", "status", "table"} else 1
        candidates.append(((0 if changed else 1, structural_priority, public_ref), finding))
    return tuple(item for _, item in sorted(candidates, key=lambda pair: pair[0])[:max_findings])


def _latest_effect_values(
    observation,
    region_index,
    evidence_index,
    canonical_to_public,
    grounding,
    latest,
) -> tuple[LatestEffectValue, ...]:
    if latest is None:
        return ()
    records = {
        (item.subject_id, item.predicate, _stable_value(item.value)): item
        for item in evidence_index.records
        if item.kind == "fact"
    }
    target_refs = grounding.target_refs
    values: list[LatestEffectValue] = []
    for change in latest.public_world_delta.fact_changes:
        if change.after is None or change.kind is PublicChangeKind.REMOVED:
            continue
        key = (change.subject_id, change.predicate, _stable_value(change.after.value))
        record = records.get(key)
        if record is None:
            continue
        region = region_index.region_for_target(change.subject_id)
        values.append(
            LatestEffectValue(
                change.kind,
                change.predicate,
                change.after.value,
                canonical_to_public.get(record.evidence_ref, ""),
                region.public_ref if region is not None else "",
                region.heading or region.role if region is not None else "current World",
            )
        )
    current_targets = {item.target_id: item for item in observation.targets}
    for change in latest.public_world_delta.target_changes:
        if change.after is None or change.target_id not in current_targets:
            continue
        target = current_targets[change.target_id]
        region = region_index.region_for_target(change.target_id)
        values.append(
            LatestEffectValue(
                change.kind,
                "public.label",
                target.label,
                target_refs.get(change.target_id, ""),
                region.public_ref if region is not None else "",
                region.heading or region.role if region is not None else "current World",
            )
        )
    return tuple(values)


def _changed_region(index: WorldDeliveryIndex, key: str) -> ChangedRegion:
    region = index.get(key)
    version = index.version_for(key)
    assert region is not None and version is not None
    member_count = len(region.member_structure_ids) + len(region.member_target_ids) + len(region.member_fact_ids)
    return ChangedRegion(
        key,
        region.public_ref,
        version.version,
        version.cached_outline,
        member_count,
        f"read_region:{region.public_ref}:0" if member_count > 20 else "",
    )


def _changed_fact_keys(latest: LatestEffect | None) -> frozenset[tuple[str, str, str]]:
    if latest is None:
        return frozenset()
    return frozenset(
        (item.subject_id, item.predicate, _stable_value(item.after.value))
        for item in latest.public_world_delta.fact_changes
        if item.after is not None and item.kind is not PublicChangeKind.REMOVED
    )


def _stable_value(value: object) -> str:
    return repr(freeze_json(value))
