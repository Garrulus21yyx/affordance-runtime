"""Change-first, reversible delivery projection over the current public World."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from affordance_runtime.actions.paging import ActionDiscoveryMatch
from affordance_runtime.agent.context.context import AgentGroundingIndexView
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.context.world_region_index import WorldDeliveryIndex
from affordance_runtime.agent.context.world_transition import (
    PublicChangeKind,
    PublicWorldDelta,
)
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
_EFFECT_PAGE_SIZE = 8
_DIRECTORY_PAGE_SIZE = 12


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
    new_items: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, InformationDeltaKind):
            raise TypeError("information delta kind must be typed")
        if not self.operation.strip() or not all(
            value.startswith("sha256:")
            for value in (self.world_digest, self.arguments_digest, self.result_digest)
        ):
            raise ValueError("information delta requires stable public identities")
        items = tuple(freeze_json(dict(item)) for item in self.new_items)
        if len(items) > _MAX_LOCAL_INFORMATION_ITEMS:
            raise ValueError("information delta exceeds its public item bound")
        if self.kind is InformationDeltaKind.NEW_INFORMATION and not items:
            raise ValueError("new information requires public items")
        if self.kind is not InformationDeltaKind.NEW_INFORMATION and items:
            raise ValueError("non-new delivery cannot carry public items")
        object.__setattr__(self, "new_items", items)

    @property
    def new_information_count(self) -> int:
        return len(self.new_items)


@dataclass(frozen=True)
class LocalDeliveryRecord:
    operation: str
    world_digest: str
    arguments_digest: str
    result_digest: str
    item_digests: tuple[str, ...]


@dataclass(frozen=True)
class DeliveryTransition:
    next_store: "ObservationDeliveryStore"
    information_delta: InformationDelta | None


@dataclass(frozen=True)
class PublicProvenance:
    """Bounded semantic provenance; source-instance identity is deliberately absent."""

    surface_kind: str
    modality: str
    source_coverage: str
    structural_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.surface_kind, self.modality, self.source_coverage)):
            raise ValueError("public provenance requires bounded source semantics")
        if self.source_coverage not in {"complete", "partial", "stale", "unavailable"}:
            raise ValueError("public provenance coverage is invalid")
        context = tuple(item[:240] for item in self.structural_context if item.strip())[:8]
        object.__setattr__(self, "structural_context", context)


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
        before: WorldObservation,
        after: WorldObservation,
        before_index: WorldDeliveryIndex,
        after_index: WorldDeliveryIndex,
    ) -> PublicEffectInventory:
        if (
            delta.before_observation_id != before.observation_id
            or delta.after_observation_id != after.observation_id
            or before_index.world_observation_id != before.observation_id
            or after_index.world_observation_id != after.observation_id
        ):
            raise ValueError("effect projection lineage is stale")
        prior = list(_public_semantic_atoms(before, before_index))
        current = list(_public_semantic_atoms(after, after_index))
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
            if before_index.document_lineage != after_index.document_lineage
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
    continuation_available: bool

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
    continuation_available: bool = False

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
    continuation_available: bool = True
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
class StoredActionQuery:
    """Runtime-private complete ordered result of one current control query."""

    query: str
    world_lineage: str
    action_space_lineage: str
    matches: tuple[ActionDiscoveryMatch, ...]

    def __post_init__(self) -> None:
        if (
            not self.query.strip()
            or not self.world_lineage.strip()
            or not self.action_space_lineage.strip()
            or any(not isinstance(item, ActionDiscoveryMatch) for item in self.matches)
        ):
            raise ValueError("stored action query requires current typed authority")
        object.__setattr__(self, "matches", tuple(self.matches))


@dataclass(frozen=True)
class ObservationDeliveryStore:
    """Own the bounded lifecycle of public information delivered to the model."""

    latest_effect: LatestEffect | None = None
    local_deliveries: tuple[LocalDeliveryRecord, ...] = ()
    active_read: WorldDeliveryLens | None = field(default=None, repr=False, compare=False)
    private_cursor_offsets: Mapping[str, tuple[str, str, str, str, int]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    action_query: StoredActionQuery | None = field(default=None, repr=False, compare=False)
    requested_continuation_scope: str | None = field(
        default=None, repr=False, compare=False, metadata={"serialize": False}
    )

    def __post_init__(self) -> None:
        records = tuple(self.local_deliveries)
        if len(records) > _MAX_LOCAL_DELIVERY_RECORDS or any(
            not isinstance(item, LocalDeliveryRecord) for item in records
        ):
            raise ValueError("local delivery lifecycle exceeds its fixed bound")
        object.__setattr__(self, "local_deliveries", records)
        if self.active_read is not None and not isinstance(self.active_read, WorldDeliveryLens):
            raise TypeError("observation delivery active read must be a private typed cursor")
        if any(
            not isinstance(scope, str)
            or not scope
            or len(value) != 5
            or type(value[-1]) is not int
            or value[-1] < 0
            for scope, value in self.private_cursor_offsets.items()
        ):
            raise ValueError("observation delivery private cursor store is invalid")
        object.__setattr__(
            self,
            "private_cursor_offsets",
            MappingProxyType(dict(self.private_cursor_offsets)),
        )
        if self.action_query is not None and not isinstance(self.action_query, StoredActionQuery):
            raise TypeError("observation delivery action query must be private typed inventory")
        if self.requested_continuation_scope is not None and not self.requested_continuation_scope.strip():
            raise ValueError("requested continuation scope must be private and nonblank")

    def with_active_read(self, lens: WorldDeliveryLens | None) -> "ObservationDeliveryStore":
        """Replace only the active local-read cursor; effects/directories survive."""

        if lens is not None and not isinstance(lens, WorldDeliveryLens):
            raise TypeError("active read replacement must be a typed private cursor")
        return ObservationDeliveryStore(
            latest_effect=self.latest_effect,
            local_deliveries=self.local_deliveries,
            active_read=lens,
            private_cursor_offsets=self.private_cursor_offsets,
            action_query=self.action_query,
            requested_continuation_scope=self.requested_continuation_scope,
        )

    def cursor_offset(
        self,
        scope: str,
        *,
        world_lineage: str,
        action_lineage: str,
        result_lineage: str,
        order_digest: str,
    ) -> int:
        value = self.private_cursor_offsets.get(scope)
        if value is None or value[:4] != (world_lineage, action_lineage, result_lineage, order_digest):
            return 0
        return value[-1]

    def with_advanced_cursor(
        self,
        scope: str,
        *,
        world_lineage: str,
        action_lineage: str,
        result_lineage: str,
        order_digest: str,
        offset: int,
    ) -> "ObservationDeliveryStore":
        if type(offset) is not int or offset < 0:
            raise ValueError("private continuation offset is invalid")
        offsets = dict(self.private_cursor_offsets)
        offsets[scope] = (
            world_lineage,
            action_lineage,
            result_lineage,
            order_digest,
            offset,
        )
        return ObservationDeliveryStore(
            latest_effect=self.latest_effect,
            local_deliveries=self.local_deliveries,
            active_read=self.active_read,
            private_cursor_offsets=offsets,
            action_query=self.action_query,
            requested_continuation_scope=scope,
        )

    def reduce(self, step: object, *, step_index: int) -> DeliveryTransition:
        committed_store = getattr(step, "next_delivery_store", None)
        if committed_store is not None and not isinstance(committed_store, ObservationDeliveryStore):
            raise TypeError("committed delivery transition must be a typed Store")
        external = committed_store or self.advance(step, step_index=step_index)
        decision = getattr(step, "decision", None)
        operation = str(getattr(decision, "tool_name", ""))
        arguments = getattr(decision, "arguments", None)
        result = getattr(decision, "result", None)
        if not operation and getattr(step, "action_page_result", None):
            operation = "find_controls"
            arguments = {
                "query": getattr(decision, "query", ""),
                "continuation_scope": getattr(decision, "continuation_scope", ""),
            }
            result = getattr(step, "action_page_result").to_public_value()
        if operation not in {"read_region", "search_page_content", "find_controls"} or not isinstance(
            result, Mapping
        ):
            return DeliveryTransition(external, None)

        world_digest = "sha256:" + getattr(step, "public_world_delta").after_world_digest
        arguments_digest = _public_digest(arguments or {})
        result_digest = _public_digest(result)
        items = _public_result_items(result)
        item_digests = tuple(_public_digest(item) for item in items)
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
            return DeliveryTransition(external, delta)

        delivered = {
            digest
            for record in external.local_deliveries
            if record.world_digest == world_digest
            for digest in record.item_digests
        }
        new_items = tuple(item for item, digest in zip(items, item_digests, strict=True) if digest not in delivered)
        if new_items:
            kind = InformationDeltaKind.NEW_INFORMATION
        elif not items:
            kind = InformationDeltaKind.NO_MATCHES
        else:
            kind = InformationDeltaKind.NO_NEW_INFORMATION
        delta = InformationDelta(
            kind,
            operation,
            world_digest,
            arguments_digest,
            result_digest,
            new_items if kind is InformationDeltaKind.NEW_INFORMATION else (),
        )
        record = LocalDeliveryRecord(operation, world_digest, arguments_digest, result_digest, item_digests)
        query_inventory = external.action_query
        discovery = getattr(step, "action_page_result", None)
        if operation == "find_controls" and discovery is not None and discovery.query:
            query_inventory = StoredActionQuery(
                discovery.query,
                discovery.private_world_lineage,
                discovery.private_action_lineage,
                discovery.private_inventory,
            )
        next_store = ObservationDeliveryStore(
            latest_effect=external.latest_effect,
            local_deliveries=(*external.local_deliveries, record)[-_MAX_LOCAL_DELIVERY_RECORDS:],
            active_read=external.active_read,
            private_cursor_offsets=external.private_cursor_offsets,
            action_query=query_inventory,
            requested_continuation_scope=(
                None if operation == "find_controls" else external.requested_continuation_scope
            ),
        )
        return DeliveryTransition(next_store, delta)

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
        before_world = getattr(step, "before_world", None)
        after_world = getattr(step, "after_world", None)
        if not isinstance(before_world, WorldObservation) or not isinstance(after_world, WorldObservation):
            raise TypeError("external GUI effect requires exact before/after Worlds")
        inventory = PublicEffectProjector().project(
            delta,
            before_world,
            after_world,
            WorldDeliveryIndex.from_observation(before_world),
            WorldDeliveryIndex.from_observation(after_world),
        )
        return ObservationDeliveryStore(
            latest_effect=LatestEffect(step_index, cause[:240], dispatch, delta, inventory),
            local_deliveries=self.local_deliveries,
        )


def _public_result_items(result: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = result.get("items", result.get("matches", ()))
    if not isinstance(raw, (tuple, list)):
        return ()
    items: list[Mapping[str, object]] = []
    for value in raw[:_MAX_LOCAL_INFORMATION_ITEMS]:
        items.append(dict(value) if isinstance(value, Mapping) else {"value": value})
    return tuple(items)


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
                len(latest.inventory.atoms) > _EFFECT_PAGE_SIZE,
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
    evidence_index,
    canonical_to_public,
    grounding,
    latest,
) -> tuple[LatestEffectValue, ...]:
    if latest is None:
        return ()
    target_refs = grounding.target_refs
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
            public_ref = target_refs.get(atom.subject_id, "")
        elif atom.current:
            record = evidence_by_subject.get((atom.subject_id, atom.predicate, _stable_value(atom.exact_value)))
            public_ref = canonical_to_public.get(record.evidence_ref, "") if record is not None else ""
        values.append(
            LatestEffectValue(
                atom.change,
                atom.predicate,
                atom.exact_value,
                public_ref,
                region.public_ref if region is not None else "",
                atom.provenance,
                atom.current,
            )
        )
    return tuple(values)


def _changed_region(index: WorldDeliveryIndex, key: str) -> ChangedRegion:
    region = index.get(key)
    version = index.version_for(key)
    assert region is not None and version is not None
    return ChangedRegion(
        key,
        region.public_ref,
        version.version,
        version.cached_outline,
        bool(region.member_structure_ids or region.member_target_ids or region.member_fact_ids),
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


def public_structural_slot(index: WorldDeliveryIndex, target_id: str) -> tuple[str, ...]:
    """Stable public slot used by effect reconciliation and ActionSpace recall join."""

    context = index.functional_context_for_target(target_id)
    region = index.region_for_target(target_id)
    if context is None or region is None:
        return ()
    return (
        context.container_kind.value,
        *(index.functional_path_for_target(target_id)[:8]),
        region.heading,
        region.role,
        str(context.public_order),
    )


def _public_semantic_atoms(
    observation: WorldObservation,
    index: WorldDeliveryIndex,
) -> tuple[PublicEffectAtom, ...]:
    manifests = {item.source_observation_id: item for item in observation.source_manifest}
    sources = {item.observation_id: item for item in observation.sources}
    source_links: dict[str, list[str]] = defaultdict(list)
    for link in observation.entity_source_links:
        source_links[link.canonical_target_id].append(link.source_observation_id)

    def provenance(subject_id: str, source_id: str = "") -> PublicProvenance:
        candidates = [source_id] if source_id else source_links.get(subject_id, [])
        public_sources = []
        for candidate in candidates:
            manifest = manifests.get(candidate)
            source = sources.get(candidate)
            if manifest is None:
                continue
            public_sources.append(
                (
                    manifest.surface,
                    manifest.modality,
                    _public_source_coverage(manifest.coverage),
                    str(getattr(source, "surface", manifest.surface)),
                )
            )
        surface, modality, coverage, _ = min(public_sources) if public_sources else (
            "unified_world",
            "semantic",
            "complete",
            "unified_world",
        )
        region = index.region_for_target(subject_id)
        structural = tuple(
            item
            for item in (
                *(index.functional_path_for_target(subject_id)[:8]),
                region.heading if region is not None else "",
                region.role if region is not None else "",
            )
            if item
        )
        return PublicProvenance(surface, modality, coverage, structural)

    targets = {item.target_id: item for item in observation.targets}
    atoms: list[PublicEffectAtom] = []
    for target in observation.targets:
        context = index.functional_context_for_target(target.target_id)
        region = index.region_for_target(target.target_id)
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
                public_structural_slot(index, target.target_id),
                target.label,
                target.role,
                region.heading if region is not None else "",
                region.role if region is not None else "",
                context.public_order if context is not None else 0,
                True,
                provenance(target.target_id),
                target.target_id,
            )
        )
    for position, fact in enumerate(observation.facts):
        target = targets.get(fact.subject_id)
        context = index.functional_context_for_target(fact.subject_id)
        region = index.region_for_fact(fact.fact_id) or index.region_for_target(fact.subject_id)
        atoms.append(
            PublicEffectAtom(
                PublicChangeKind.ADDED,
                "fact",
                fact.predicate,
                fact.value,
                public_structural_slot(index, fact.subject_id),
                target.label if target is not None else "",
                target.role if target is not None else "fact",
                region.heading if region is not None else "",
                region.role if region is not None else "",
                (context.public_order if context is not None else len(observation.targets)) + position,
                True,
                provenance(fact.subject_id, fact.source_id),
                fact.subject_id,
            )
        )
    return tuple(atoms)


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


def _public_source_coverage(coverage: CoverageState) -> str:
    if coverage is CoverageState.COMPLETE:
        return "complete"
    if coverage is CoverageState.TRUNCATED:
        return "partial"
    if coverage is CoverageState.STALE:
        return "stale"
    return "unavailable"


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
