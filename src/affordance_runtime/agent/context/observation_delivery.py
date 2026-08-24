"""Change-first, reversible delivery projection over the current public World."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from affordance_runtime.agent.context.canonical_world_projection import (
    CanonicalPublicWorldProjection,
    PublicProvenance,
)
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import (
    PublicChangeKind,
    PublicWorldDelta,
)
from affordance_runtime.agent.decisions import LocalToolResult
from affordance_runtime.agent.runtime_failure import RuntimeFailure
from affordance_runtime.agent.working_facts import is_public_scalar
from affordance_runtime.agent.workspace import CurrentFinding
from affordance_runtime.evaluation.evidence import WorldEvidenceIndex
from affordance_runtime.execution.contracts import DispatchStatus
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.contracts import CoverageState, WorldObservation
from affordance_runtime.world.public_refs import PublicRefCodec, PublicRefKind
from affordance_runtime.world.public_semantic_digest import public_subject_semantics

_MAX_LOCAL_DELIVERY_RECORDS = 64
_MAX_LOCAL_INFORMATION_ITEMS = 32


@dataclass(frozen=True)
class DeliveryInventorySnapshot:
    """One immutable current-turn inventory used only by the request packer."""

    scope: str
    kind: str
    world_lineage: str = field(repr=False, compare=False)
    action_lineage: str = field(repr=False, compare=False)
    result_lineage: str = field(repr=False, compare=False)
    order_digest: str = field(repr=False, compare=False)
    records: tuple[object, ...] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not all(
                value.strip()
                for value in (
                    self.scope,
                    self.kind,
                    self.world_lineage,
                    self.action_lineage,
                    self.result_lineage,
                    self.order_digest,
                )
            )
        ):
            raise ValueError("delivery inventory snapshot is invalid")
        object.__setattr__(self, "records", tuple(self.records))

    @property
    def remaining(self) -> tuple[object, ...]:
        return self.records


class InformationDeltaKind(StrEnum):
    NEW_INFORMATION = "new_information"
    NO_MATCHES = "no_matches"
    NO_NEW_INFORMATION = "no_new_information"
    EXACT_REPLAY = "exact_replay"


@dataclass(frozen=True)
class InformationDelta:
    kind: InformationDeltaKind
    operation: str
    world_digest: str
    arguments_digest: str
    result_digest: str
    inventory_digest: str = ""
    new_record_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, InformationDeltaKind):
            raise TypeError("information delta kind must be typed")
        if not self.operation.strip() or not all(
            value.startswith("sha256:")
            for value in (self.world_digest, self.arguments_digest, self.result_digest)
        ):
            raise ValueError("information delta requires stable public identities")
        digests = tuple(self.new_record_digests)
        if len(digests) > _MAX_LOCAL_INFORMATION_ITEMS or any(
            not item.startswith("sha256:") for item in digests
        ):
            raise ValueError("information delta record identities are invalid")
        if self.kind is InformationDeltaKind.NEW_INFORMATION and (
            not digests or not self.inventory_digest.startswith("sha256:")
        ):
            raise ValueError("new information requires a typed result inventory")
        if self.kind is not InformationDeltaKind.NEW_INFORMATION and digests:
            raise ValueError("non-new delivery cannot carry record identities")
        if self.inventory_digest and not self.inventory_digest.startswith("sha256:"):
            raise ValueError("information delta inventory identity is invalid")
        object.__setattr__(self, "new_record_digests", digests)

    @property
    def new_information_count(self) -> int:
        return len(self.new_record_digests)


@dataclass(frozen=True)
class LocalDeliveryRecord:
    """Bounded Monitor receipt; never a model-visible result body."""

    operation: str
    world_digest: str
    arguments_digest: str
    result_digest: str
    item_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        item_digests = tuple(self.item_digests)
        if (
            not self.operation.strip()
            or not all(
                value.startswith("sha256:")
                for value in (self.world_digest, self.arguments_digest, self.result_digest)
            )
            or len(item_digests) > _MAX_LOCAL_INFORMATION_ITEMS
            or any(not item.startswith("sha256:") for item in item_digests)
        ):
            raise ValueError("local delivery record is invalid")
        object.__setattr__(self, "item_digests", item_digests)


@dataclass(frozen=True)
class DeliveryTransition:
    next_store: "ObservationDeliveryStore"
    information_delta: InformationDelta | None
    runtime_failure: RuntimeFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.next_store, ObservationDeliveryStore):
            raise TypeError("delivery transition requires the reducer-owned next Store")
        if self.information_delta is not None and not isinstance(
            self.information_delta, InformationDelta
        ):
            raise TypeError("delivery transition information delta must be typed")
        if self.runtime_failure is not None and not isinstance(self.runtime_failure, RuntimeFailure):
            raise TypeError("delivery transition Runtime failure must be typed")


@dataclass(frozen=True)
class PublicEffectAtom:
    """One reconciled public semantic atom or ref-free removed tombstone."""

    change: PublicChangeKind
    atom_kind: str
    predicate: str
    exact_value: object
    slot_key: tuple[str, ...]
    label: str
    role: str
    region_label: str
    region_role: str
    public_order: int
    current: bool
    provenance: PublicProvenance
    subject_id: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.change, PublicChangeKind)
            or self.atom_kind not in {"target", "fact"}
            or not self.predicate.strip()
            or type(self.public_order) is not int
            or self.public_order < 0
            or self.current != (self.change is not PublicChangeKind.REMOVED)
            or not isinstance(self.provenance, PublicProvenance)
        ):
            raise ValueError("public effect atom is invalid")
        object.__setattr__(self, "exact_value", freeze_json(self.exact_value))
        object.__setattr__(self, "slot_key", tuple(self.slot_key))

    @property
    def public_value(self) -> Mapping[str, object]:
        return freeze_json(
            {
                "change": self.change.value,
                "kind": self.atom_kind,
                "predicate": self.predicate,
                "value": self.exact_value,
                "label": self.label,
                "role": self.role,
                "region": self.region_label or self.region_role,
                "current": self.current,
                "provenance": to_json_compatible(self.provenance),
            }
        )


@dataclass(frozen=True)
class PublicEffectInventory:
    """Complete reconciled effect read model retained privately by delivery."""

    transition: str
    atoms: tuple[PublicEffectAtom, ...]
    changed_target_slot_keys: tuple[tuple[str, ...], ...]
    changed_regions: tuple[tuple[str, str], ...]
    raw_delta_lineage: str = field(repr=False, compare=False)
    inventory_id: str = ""

    def __post_init__(self) -> None:
        atoms = tuple(self.atoms)
        slots = tuple(dict.fromkeys(tuple(item) for item in self.changed_target_slot_keys))
        regions = tuple(dict.fromkeys(tuple(item) for item in self.changed_regions if any(item)))
        public_payload = {
            "transition": self.transition,
            "atoms": tuple(item.public_value for item in atoms),
            "slots": slots,
            "regions": regions,
        }
        expected = "public-effect:" + hashlib.sha256(
            json.dumps(
                to_json_compatible(public_payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        if self.inventory_id and self.inventory_id != expected:
            raise ValueError("public effect identity does not bind public semantics")
        if not self.raw_delta_lineage.startswith("sha256:"):
            raise ValueError("public effect requires private raw-delta lineage")
        object.__setattr__(self, "atoms", atoms)
        object.__setattr__(self, "changed_target_slot_keys", slots)
        object.__setattr__(self, "changed_regions", regions)
        object.__setattr__(self, "inventory_id", expected)


@dataclass(frozen=True)
class PublicEffectProjector:
    """Reconcile identity delta into public semantic multiplicities."""

    def project(
        self,
        delta: PublicWorldDelta,
        before: CanonicalPublicWorldProjection,
        after: CanonicalPublicWorldProjection,
    ) -> PublicEffectInventory:
        prior = list(_public_semantic_atoms(before))
        current = list(_public_semantic_atoms(after))
        prior, current = _cancel_exact_public_multiset(prior, current)
        removed: list[PublicEffectAtom] = []
        admitted: list[PublicEffectAtom] = []
        before_slots: dict[tuple[object, ...], list[PublicEffectAtom]] = defaultdict(list)
        after_slots: dict[tuple[object, ...], list[PublicEffectAtom]] = defaultdict(list)
        for atom in prior:
            before_slots[_modification_slot(atom)].append(atom)
        for atom in current:
            after_slots[_modification_slot(atom)].append(atom)
        paired_before: set[int] = set()
        paired_after: set[int] = set()
        for key in sorted(before_slots.keys() & after_slots.keys(), key=repr):
            old_items = before_slots[key]
            new_items = after_slots[key]
            # A stable public slot is sufficient only when pairing is unambiguous.
            if not key[1] or len(old_items) != 1 or len(new_items) != 1:
                continue
            old = old_items[0]
            new = new_items[0]
            paired_before.add(id(old))
            paired_after.add(id(new))
            admitted.append(
                PublicEffectAtom(
                    PublicChangeKind.MODIFIED,
                    new.atom_kind,
                    new.predicate,
                    new.exact_value,
                    new.slot_key,
                    new.label,
                    new.role,
                    new.region_label,
                    new.region_role,
                    new.public_order,
                    True,
                    new.provenance,
                    new.subject_id,
                )
            )
        admitted.extend(
            PublicEffectAtom(
                PublicChangeKind.ADDED,
                item.atom_kind,
                item.predicate,
                item.exact_value,
                item.slot_key,
                item.label,
                item.role,
                item.region_label,
                item.region_role,
                item.public_order,
                True,
                item.provenance,
                item.subject_id,
            )
            for item in current
            if id(item) not in paired_after
        )
        removed.extend(
            PublicEffectAtom(
                PublicChangeKind.REMOVED,
                item.atom_kind,
                item.predicate,
                item.exact_value,
                item.slot_key,
                item.label,
                item.role,
                item.region_label,
                item.region_role,
                item.public_order,
                False,
                item.provenance,
            )
            for item in prior
            if id(item) not in paired_before
        )
        admitted.sort(key=_effect_atom_order)
        removed.sort(key=_effect_atom_order)
        atoms = tuple((*admitted, *removed))
        # A current fact transition is also a change to its public subject slot.
        # The ActionSpace join owns route legality; the effect inventory only
        # supplies the public structural slots whose current semantics changed.
        changed_slots = tuple(item.slot_key for item in atoms if item.current)
        regions = tuple(
            (item.region_label, item.region_role)
            for item in atoms
            if item.region_label or item.region_role
        )
        return PublicEffectInventory(
            "new_document"
            if before.public_document_signature != after.public_document_signature
            else "world_changed",
            atoms,
            changed_slots,
            regions,
            _raw_delta_lineage(delta),
        )


@dataclass(frozen=True)
class LatestEffect:
    step_index: int
    caused_by: str
    dispatch_status: DispatchStatus
    public_world_delta: PublicWorldDelta
    inventory: PublicEffectInventory

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
        if not isinstance(self.inventory, PublicEffectInventory):
            raise TypeError("latest effect requires its reconciled public inventory")
        if self.inventory.raw_delta_lineage != _raw_delta_lineage(self.public_world_delta):
            raise ValueError("latest effect inventory does not bind the raw delta")


@dataclass(frozen=True)
class LatestEffectValue:
    kind: PublicChangeKind
    predicate: str
    exact_value: object
    public_ref: str
    region_ref: str
    provenance: PublicProvenance
    current: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PublicChangeKind):
            raise ValueError("latest effect value must have a typed change")
        if not self.predicate.strip() or not isinstance(self.provenance, PublicProvenance):
            raise ValueError("latest effect value requires public semantics and provenance")
        if self.current != (self.kind is not PublicChangeKind.REMOVED):
            raise ValueError("latest effect currentness contradicts its change")
        if self.public_ref and not PublicRefCodec.accepts(self.public_ref):
            raise ValueError("latest effect value public ref is invalid")
        if self.region_ref and not PublicRefCodec.accepts(self.region_ref, expected=PublicRefKind.REGION):
            raise ValueError("latest effect value region ref is invalid")
        object.__setattr__(self, "exact_value", freeze_json(self.exact_value))


@dataclass(frozen=True)
class PublicEffectHeader:
    caused_by: str
    dispatch_status: DispatchStatus
    transition: str

    def __post_init__(self) -> None:
        if (
            not self.caused_by.strip()
            or not isinstance(self.dispatch_status, DispatchStatus)
            or self.transition not in {"world_changed", "new_document"}
        ):
            raise ValueError("public effect header is invalid")


@dataclass(frozen=True)
class ChangedRegion:
    region_key: str
    region_ref: str
    version: int
    cached_outline: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.region_key.startswith("region:")
            or not PublicRefCodec.accepts(self.region_ref, expected=PublicRefKind.REGION)
            or type(self.version) is not int
            or self.version < 1
        ):
            raise ValueError("changed region delivery is invalid")
        object.__setattr__(self, "cached_outline", tuple(self.cached_outline))


@dataclass(frozen=True)
class PageOutlineEntry:
    region_ref: str
    version: int
    outline: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not PublicRefCodec.accepts(self.region_ref, expected=PublicRefKind.REGION)
            or type(self.version) is not int
            or self.version < 1
        ):
            raise ValueError("page outline entry is invalid")
        object.__setattr__(self, "outline", tuple(self.outline))


@dataclass(frozen=True)
class RecoveryDirectoryEntry:
    region_ref: str
    version: int
    operations: tuple[str, ...] = ("read_region", "search_page_content")

    def __post_init__(self) -> None:
        if (
            not PublicRefCodec.accepts(self.region_ref, expected=PublicRefKind.REGION)
            or type(self.version) is not int
            or self.version < 1
        ):
            raise ValueError("recovery directory entry is invalid")
        operations = tuple(self.operations)
        if not operations or any(item not in {"read_region", "search_page_content"} for item in operations):
            raise ValueError("recovery directory operations are invalid")
        object.__setattr__(self, "operations", operations)


@dataclass(frozen=True)
class ObservationDelivery:
    world_observation_id: str
    effect_header: PublicEffectHeader | None
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
    """Keep only GUI-effect recall and bounded Monitor digests.

    Provider history owns completed tool call/result pairs. Local tool owners own
    result bodies and any tool-local cursor; neither is persisted here.
    """

    latest_effect: LatestEffect | None = None
    local_deliveries: tuple[LocalDeliveryRecord, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.local_deliveries)
        if len(records) > _MAX_LOCAL_DELIVERY_RECORDS or any(
            not isinstance(item, LocalDeliveryRecord) for item in records
        ):
            raise ValueError("local delivery lifecycle exceeds its fixed bound")
        object.__setattr__(self, "local_deliveries", records)

    def for_world(self, world_observation_id: str) -> "ObservationDeliveryStore":
        if not world_observation_id.strip():
            raise ValueError("current World identity is required")
        return self

    def reduce(self, step: object, *, step_index: int) -> DeliveryTransition:
        if type(step).__name__ != "StepResult":
            raise TypeError("delivery reducer requires one committed StepResult")
        after_world = getattr(step, "after_world", None)
        world_observation_id = str(getattr(after_world, "observation_id", ""))
        external = self.for_world(world_observation_id)
        external = external._apply_effect(step, step_index=step_index)
        decision = getattr(step, "decision", None)
        discovery = getattr(step, "action_page_result", None)
        if isinstance(decision, LocalToolResult):
            operation = decision.tool_name
            arguments = decision.arguments
            result = decision.result
        elif discovery is not None:
            operation = "find_controls"
            arguments = {
                "query": getattr(decision, "query", ""),
            }
            result = discovery.to_public_value()
        else:
            return DeliveryTransition(external, None, getattr(step, "runtime_failure", None))

        world_digest = "sha256:" + getattr(step, "public_world_delta").after_world_digest
        arguments_digest = _public_digest(arguments or {})
        result_digest = _public_digest(result)
        item_digests = tuple(dict.fromkeys(_public_digest(item) for item in _monitor_items(result)))[
            :_MAX_LOCAL_INFORMATION_ITEMS
        ]
        exact = next(
            (
                item for item in reversed(external.local_deliveries)
                if (item.operation, item.world_digest, item.arguments_digest, item.result_digest)
                == (operation, world_digest, arguments_digest, result_digest)
            ),
            None,
        )
        if exact is not None:
            delta = InformationDelta(
                InformationDeltaKind.EXACT_REPLAY,
                operation,
                world_digest,
                arguments_digest,
                result_digest,
            )
            return DeliveryTransition(external, delta, getattr(step, "runtime_failure", None))

        delivered = {
            digest
            for record in external.local_deliveries
            if record.world_digest == world_digest
            for digest in record.item_digests
        }
        new_digests = tuple(item for item in item_digests if item not in delivered)
        if new_digests:
            kind = InformationDeltaKind.NEW_INFORMATION
        elif not item_digests:
            kind = InformationDeltaKind.NO_MATCHES
        else:
            kind = InformationDeltaKind.NO_NEW_INFORMATION
        delta = InformationDelta(
            kind,
            operation,
            world_digest,
            arguments_digest,
            result_digest,
            _public_digest(item_digests),
            new_digests if kind is InformationDeltaKind.NEW_INFORMATION else (),
        )
        record = LocalDeliveryRecord(
            operation,
            world_digest,
            arguments_digest,
            result_digest,
            item_digests,
        )
        next_store = ObservationDeliveryStore(
            latest_effect=external.latest_effect,
            local_deliveries=(*external.local_deliveries, record)[-_MAX_LOCAL_DELIVERY_RECORDS:],
        )
        return DeliveryTransition(next_store, delta, getattr(step, "runtime_failure", None))

    def _apply_effect(self, step: object, *, step_index: int) -> "ObservationDeliveryStore":
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
        before_projection = getattr(step, "before_public_world", None)
        after_projection = getattr(step, "after_public_world", None)
        if not isinstance(before_projection, CanonicalPublicWorldProjection) or not isinstance(
            after_projection, CanonicalPublicWorldProjection
        ):
            raise TypeError("external GUI effect requires exact before/after canonical Worlds")
        inventory = PublicEffectProjector().project(
            delta,
            before_projection,
            after_projection,
        )
        return replace(
            self,
            latest_effect=LatestEffect(step_index, cause[:240], dispatch, delta, inventory),
        )


def _monitor_items(result: Mapping[str, object]) -> tuple[object, ...]:
    """Select bounded novelty atoms without retaining the result body."""

    for field_name in ("items", "matches"):
        values = result.get(field_name)
        if isinstance(values, tuple | list):
            return tuple(values)
    return (result,)


def _public_digest(value: object) -> str:
    encoded = json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def current_findings_digest(observation: WorldObservation) -> str:
    """Digest current public scalar findings without Runtime or observation identity."""

    source_coverage = {
        key: item.coverage
        for item in observation.sources
        for key in (item.observation_id, item.surface)
    }
    findings = sorted(
        (
            (
                public_subject_semantics(observation, fact.subject_id),
                fact.predicate,
                fact.value,
                source_coverage.get(fact.source_id, CoverageState.COMPLETE).value,
            )
            for fact in observation.facts
            if is_public_scalar(fact.value)
            and source_coverage.get(fact.source_id, CoverageState.COMPLETE) is not CoverageState.STALE
        ),
        key=lambda item: json.dumps(
            to_json_compatible(item),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ),
    )
    encoded = json.dumps(findings, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def project_observation_delivery(
    observation: WorldObservation,
    region_index: WorldDeliveryIndex,
    projection: CanonicalPublicWorldProjection,
    evidence_index: WorldEvidenceIndex,
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
        projection,
        evidence_index,
        changed_fact_keys,
        max_findings=max_findings,
    )
    effect_values = _latest_effect_values(
        observation,
        region_index,
        projection,
        evidence_index,
        latest,
    )
    changed_keys = tuple(
        key
        for key in (latest.public_world_delta.changed_region_keys if latest is not None else ())
        if region_index.get(key) is not None
    )
    changed_regions = tuple(_changed_region(region_index, projection, key) for key in changed_keys)
    page_outline = tuple(
        PageOutlineEntry(projection.region_refs[region.key], version.version, version.cached_outline)
        for region in region_index.regions
        if (version := region_index.version_for(region.key)) is not None
    )
    recovery = tuple(
        RecoveryDirectoryEntry(
            projection.region_refs[region.key],
            version.version,
        )
        for region in region_index.regions
        if (version := region_index.version_for(region.key)) is not None
    )
    return ObservationDelivery(
        observation.observation_id,
        (
            PublicEffectHeader(
                latest.caused_by,
                latest.dispatch_status,
                latest.inventory.transition,
            )
            if latest is not None
            else None
        ),
        effect_values,
        findings,
        changed_regions,
        page_outline,
        recovery,
    )


def _current_findings(
    observation,
    region_index,
    projection,
    evidence_index,
    changed_fact_keys,
    *,
    max_findings,
) -> tuple[CurrentFinding, ...]:
    sources = {item.observation_id: item for item in observation.sources}
    candidates: list[tuple[tuple[int, int, str], CurrentFinding]] = []
    for public_record in projection.ordered_fact_records:
        public_ref = public_record.ref
        record = evidence_index.resolve_record(public_record.canonical_ref)
        if record is None:
            continue
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
                source.surface,
                str(source.source_profile.modality),
                source.coverage.value,
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
    projection,
    evidence_index,
    latest,
) -> tuple[LatestEffectValue, ...]:
    if latest is None:
        return ()
    values: list[LatestEffectValue] = []
    evidence_by_subject = {
        (item.subject_id, item.predicate, _stable_value(item.value)): item
        for item in evidence_index.records
        if item.kind == "fact"
    }
    for atom in latest.inventory.atoms:
        region = region_index.region_for_target(atom.subject_id) if atom.current else None
        public_ref = ""
        if atom.current and atom.atom_kind == "target":
            public_ref = projection.target_refs.get(atom.subject_id, "")
        elif atom.current:
            record = evidence_by_subject.get((atom.subject_id, atom.predicate, _stable_value(atom.exact_value)))
            public_ref = projection.fact_refs.get(record.evidence_ref, "") if record is not None else ""
        values.append(
            LatestEffectValue(
                atom.change,
                atom.predicate,
                atom.exact_value,
                public_ref,
                projection.region_refs.get(region.key, "") if region is not None else "",
                atom.provenance,
                atom.current,
            )
        )
    return tuple(values)


def _changed_region(
    index: WorldDeliveryIndex,
    projection: CanonicalPublicWorldProjection,
    key: str,
) -> ChangedRegion:
    region = index.get(key)
    version = index.version_for(key)
    assert region is not None and version is not None
    return ChangedRegion(
        key,
        projection.region_refs[region.key],
        version.version,
        version.cached_outline,
    )


def _changed_fact_keys(latest: LatestEffect | None) -> frozenset[tuple[str, str, str]]:
    if latest is None:
        return frozenset()
    return frozenset(
        (item.subject_id, item.predicate, _stable_value(item.exact_value))
        for item in latest.inventory.atoms
        if item.atom_kind == "fact" and item.current
    )


def _stable_value(value: object) -> str:
    return repr(freeze_json(value))


def _public_semantic_atoms(
    projection: CanonicalPublicWorldProjection,
) -> tuple[PublicEffectAtom, ...]:
    atoms: list[PublicEffectAtom] = []
    for order, target in enumerate(projection.ordered_target_records):
        if "\0" in target.target_id:
            continue
        region_label, region_role = _slot_region(target.structural_slot)
        atoms.append(
            PublicEffectAtom(
                PublicChangeKind.ADDED,
                "target",
                "public.target",
                {
                    "label": target.label,
                    "role": target.role,
                    "state": target.state,
                    "relations": target.relations,
                },
                target.structural_slot,
                target.label,
                target.role,
                region_label,
                region_role,
                order,
                True,
                target.provenance,
                target.target_id,
            )
        )
    targets = {item.target_id: item for item in projection.ordered_target_records}
    for order, fact in enumerate(projection.ordered_fact_records, len(atoms)):
        target = targets.get(fact.subject_id)
        region_label, region_role = _slot_region(fact.structural_slot)
        atoms.append(
            PublicEffectAtom(
                PublicChangeKind.ADDED,
                "fact",
                fact.predicate,
                fact.value,
                fact.structural_slot,
                target.label if target is not None else "",
                target.role if target is not None else "fact",
                region_label,
                region_role,
                order,
                True,
                fact.provenance,
                fact.subject_id,
            )
        )
    return tuple(atoms)


def _slot_region(slot: tuple[str, ...]) -> tuple[str, str]:
    public_slot = slot[:-1] if slot and slot[-1].startswith("geometry:") else slot
    return (public_slot[-3], public_slot[-2]) if len(public_slot) >= 3 else ("", "")


def _public_atom_token(atom: PublicEffectAtom) -> str:
    return json.dumps(
        to_json_compatible(
            (
                atom.atom_kind,
                atom.slot_key,
                atom.predicate,
                atom.exact_value,
                atom.label,
                atom.role,
                atom.region_label,
                atom.region_role,
                atom.provenance,
            )
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _cancel_exact_public_multiset(
    before: list[PublicEffectAtom],
    after: list[PublicEffectAtom],
) -> tuple[list[PublicEffectAtom], list[PublicEffectAtom]]:
    remaining = Counter(_public_atom_token(item) for item in after)
    prior_residual: list[PublicEffectAtom] = []
    for item in before:
        token = _public_atom_token(item)
        if remaining[token]:
            remaining[token] -= 1
        else:
            prior_residual.append(item)
    current_residual: list[PublicEffectAtom] = []
    cancelled = Counter(_public_atom_token(item) for item in before)
    for item in after:
        token = _public_atom_token(item)
        if cancelled[token]:
            cancelled[token] -= 1
        else:
            current_residual.append(item)
    return prior_residual, current_residual


def _modification_slot(atom: PublicEffectAtom) -> tuple[object, ...]:
    return atom.atom_kind, atom.slot_key, atom.predicate


def _effect_atom_order(atom: PublicEffectAtom) -> tuple[object, ...]:
    return (
        0 if atom.current else 1,
        atom.public_order,
        atom.atom_kind,
        atom.predicate,
        _stable_value(atom.exact_value),
    )


def _raw_delta_lineage(delta: PublicWorldDelta) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(to_json_compatible(delta), sort_keys=True, default=str).encode()
    ).hexdigest()
