"""Change-first, reversible delivery projection over the current public World."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from affordance_runtime.actions.paging import ActionDiscoveryMatch
from affordance_runtime.agent.context.canonical_world_projection import (
    CanonicalPublicWorldProjection,
    PublicProvenance,
)
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
_MAX_LOCAL_SEARCH_FOLLOW_UP_REGIONS = _MAX_LOCAL_INFORMATION_ITEMS
_EFFECT_PAGE_SIZE = 8
_DIRECTORY_PAGE_SIZE = 12


class DeliveryContinuationOutcomeKind(StrEnum):
    READY = "ready"
    STALE = "stale"
    EXHAUSTED = "exhausted"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class DeliveryInventorySnapshot:
    """One immutable current inventory owned by the delivery Store."""

    scope: str
    kind: str
    world_lineage: str = field(repr=False, compare=False)
    action_lineage: str = field(repr=False, compare=False)
    result_lineage: str = field(repr=False, compare=False)
    order_digest: str = field(repr=False, compare=False)
    records: tuple[object, ...] = field(repr=False, compare=False)
    offset: int = field(default=0, repr=False, compare=False)

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
            or type(self.offset) is not int
            or not 0 <= self.offset <= len(self.records)
        ):
            raise ValueError("delivery inventory snapshot is invalid")
        object.__setattr__(self, "records", tuple(self.records))

    @property
    def remaining(self) -> tuple[object, ...]:
        return self.records[self.offset :]


@dataclass(frozen=True)
class DeliveryContinuationCapability:
    """Public bounded scope plus its Store-private exact transition binding."""

    scope: str
    continuation_available: bool
    admitted_count: int
    inventory_size: int
    world_lineage: str = field(repr=False, compare=False, metadata={"serialize": False})
    action_lineage: str = field(repr=False, compare=False, metadata={"serialize": False})
    result_lineage: str = field(repr=False, compare=False, metadata={"serialize": False})
    order_digest: str = field(repr=False, compare=False, metadata={"serialize": False})
    offset: int = field(repr=False, compare=False, metadata={"serialize": False})
    kind: str = field(repr=False, compare=False, metadata={"serialize": False})

    def __post_init__(self) -> None:
        if (
            not self.scope.strip()
            or not self.kind.strip()
            or type(self.admitted_count) is not int
            or type(self.inventory_size) is not int
            or type(self.offset) is not int
            or min(self.admitted_count, self.inventory_size, self.offset) < 0
            or self.offset + self.admitted_count > self.inventory_size
            or self.continuation_available
            != (self.offset + self.admitted_count < self.inventory_size)
        ):
            raise ValueError("delivery continuation capability is invalid")


@dataclass(frozen=True)
class DeliveryContinuationOutcome:
    kind: DeliveryContinuationOutcomeKind
    next_store: "ObservationDeliveryStore | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DeliveryContinuationOutcomeKind):
            raise TypeError("delivery continuation outcome must be typed")
        if (self.kind is DeliveryContinuationOutcomeKind.READY) != (self.next_store is not None):
            raise ValueError("delivery continuation outcome/store mismatch")


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
class LocalSearchHit:
    """One current public search match and its directly consumable region."""

    world_observation_id: str = field(repr=False, compare=False, metadata={"serialize": False})
    match_ref: str
    region_ref: str

    def __post_init__(self) -> None:
        if (
            not self.world_observation_id.strip()
            or not PublicRefCodec.accepts(self.match_ref)
            or PublicRefCodec.decode(self.match_ref).kind is PublicRefKind.REGION
            or not PublicRefCodec.accepts(self.region_ref, expected=PublicRefKind.REGION)
        ):
            raise ValueError("local search follow-up requires one current match and region")


@dataclass(frozen=True)
class ObservationDelivery:
    world_observation_id: str
    effect_header: PublicEffectHeader | None
    latest_effect_values: tuple[LatestEffectValue, ...]
    current_findings: tuple[CurrentFinding, ...]
    changed_regions: tuple[ChangedRegion, ...]
    page_outline: tuple[PageOutlineEntry, ...]
    recovery_directory: tuple[RecoveryDirectoryEntry, ...]
    search_follow_ups: tuple[LocalSearchHit, ...] = ()

    def __post_init__(self) -> None:
        if not self.world_observation_id.strip():
            raise ValueError("observation delivery requires current World identity")
        for name, expected in (
            ("latest_effect_values", LatestEffectValue),
            ("current_findings", CurrentFinding),
            ("changed_regions", ChangedRegion),
            ("page_outline", PageOutlineEntry),
            ("recovery_directory", RecoveryDirectoryEntry),
            ("search_follow_ups", LocalSearchHit),
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
    inventories: tuple[DeliveryInventorySnapshot, ...] = field(
        default=(), repr=False, compare=False, metadata={"serialize": False}
    )
    action_query: StoredActionQuery | None = field(default=None, repr=False, compare=False)
    search_follow_ups: tuple[LocalSearchHit, ...] = field(
        default=(), repr=False, compare=False, metadata={"serialize": False}
    )
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
        inventories = tuple(self.inventories)
        if (
            any(not isinstance(item, DeliveryInventorySnapshot) for item in inventories)
            or len({item.scope for item in inventories}) != len(inventories)
        ):
            raise ValueError("observation delivery inventories are invalid")
        object.__setattr__(self, "inventories", inventories)
        if self.action_query is not None and not isinstance(self.action_query, StoredActionQuery):
            raise TypeError("observation delivery action query must be private typed inventory")
        search_follow_ups = tuple(self.search_follow_ups)
        if (
            len(search_follow_ups) > _MAX_LOCAL_SEARCH_FOLLOW_UP_REGIONS
            or any(not isinstance(item, LocalSearchHit) for item in search_follow_ups)
            or len({item.region_ref for item in search_follow_ups}) != len(search_follow_ups)
        ):
            raise ValueError("local search follow-up inventory is invalid")
        object.__setattr__(self, "search_follow_ups", search_follow_ups)
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
            inventories=self.inventories,
            action_query=self.action_query,
            search_follow_ups=self.search_follow_ups,
            requested_continuation_scope=self.requested_continuation_scope,
        )

    def for_world(self, world_observation_id: str) -> "ObservationDeliveryStore":
        """Invalidate private local-read capabilities that do not belong to this World."""

        if not world_observation_id.strip():
            raise ValueError("current World identity is required")
        active_read = self.active_read
        if active_read is not None and active_read.world_observation_id != world_observation_id:
            active_read = None
        search_follow_ups = tuple(
            item for item in self.search_follow_ups if item.world_observation_id == world_observation_id
        )
        if active_read is self.active_read and search_follow_ups == self.search_follow_ups:
            return self
        return ObservationDeliveryStore(
            latest_effect=self.latest_effect,
            local_deliveries=self.local_deliveries,
            active_read=active_read,
            inventories=self.inventories,
            action_query=self.action_query,
            search_follow_ups=search_follow_ups,
            requested_continuation_scope=self.requested_continuation_scope,
        )

    def install_inventories(
        self,
        inventories: tuple[DeliveryInventorySnapshot, ...],
    ) -> "ObservationDeliveryStore":
        """Install fresh immutable inventories while conserving current exact offsets."""

        current = {item.scope: item for item in self.inventories}
        installed = []
        for incoming in inventories:
            prior = current.get(incoming.scope)
            same_inventory = prior is not None and (
                prior.world_lineage,
                prior.action_lineage,
                prior.result_lineage,
                prior.order_digest,
            ) == (
                incoming.world_lineage,
                incoming.action_lineage,
                incoming.result_lineage,
                incoming.order_digest,
            )
            installed.append(
                DeliveryInventorySnapshot(
                    incoming.scope,
                    incoming.kind,
                    incoming.world_lineage,
                    incoming.action_lineage,
                    incoming.result_lineage,
                    incoming.order_digest,
                    incoming.records,
                    min(prior.offset, len(incoming.records)) if same_inventory else 0,
                )
            )
        return ObservationDeliveryStore(
            latest_effect=self.latest_effect,
            local_deliveries=self.local_deliveries,
            active_read=self.active_read,
            inventories=tuple(installed),
            action_query=self.action_query,
            search_follow_ups=self.search_follow_ups,
            requested_continuation_scope=(
                self.requested_continuation_scope
                if any(item.scope == self.requested_continuation_scope for item in installed)
                else None
            ),
        )

    def inventory(self, scope: str) -> DeliveryInventorySnapshot | None:
        return next((item for item in self.inventories if item.scope == scope), None)

    def continuation_capabilities(
        self,
        admitted_counts: Mapping[str, int],
    ) -> tuple[DeliveryContinuationCapability, ...]:
        capabilities = []
        for inventory in self.inventories:
            admitted = admitted_counts.get(inventory.kind, 0)
            capability = DeliveryContinuationCapability(
                inventory.scope,
                inventory.offset + admitted < len(inventory.records),
                admitted,
                len(inventory.records),
                inventory.world_lineage,
                inventory.action_lineage,
                inventory.result_lineage,
                inventory.order_digest,
                inventory.offset,
                inventory.kind,
            )
            if capability.continuation_available:
                capabilities.append(capability)
        if self.active_read is not None and self.active_read.next_cursor:
            lens_digest = _public_digest(
                (
                    self.active_read.world_observation_id,
                    self.active_read.kind,
                    self.active_read.selected_region_key,
                    self.active_read.query,
                    self.active_read.next_cursor,
                )
            )
            capabilities.append(
                DeliveryContinuationCapability(
                    "active_read",
                    True,
                    0,
                    1,
                    self.active_read.world_observation_id,
                    "local_read",
                    lens_digest,
                    lens_digest,
                    0,
                    "active_read",
                )
            )
        return tuple(capabilities)

    def continue_delivery(
        self,
        capability: DeliveryContinuationCapability,
    ) -> DeliveryContinuationOutcome:
        if capability.scope == "active_read":
            if self.active_read is None or not self.active_read.next_cursor:
                return DeliveryContinuationOutcome(DeliveryContinuationOutcomeKind.STALE)
            return DeliveryContinuationOutcome(DeliveryContinuationOutcomeKind.READY, self)
        inventory = self.inventory(capability.scope)
        if inventory is None:
            return DeliveryContinuationOutcome(DeliveryContinuationOutcomeKind.UNSUPPORTED)
        if (
            inventory.world_lineage,
            inventory.action_lineage,
            inventory.result_lineage,
            inventory.order_digest,
            inventory.offset,
        ) != (
            capability.world_lineage,
            capability.action_lineage,
            capability.result_lineage,
            capability.order_digest,
            capability.offset,
        ):
            return DeliveryContinuationOutcome(DeliveryContinuationOutcomeKind.STALE)
        next_offset = inventory.offset + capability.admitted_count
        if next_offset >= len(inventory.records):
            return DeliveryContinuationOutcome(DeliveryContinuationOutcomeKind.EXHAUSTED)
        next_inventories = tuple(
            replace(item, offset=next_offset) if item.scope == inventory.scope else item
            for item in self.inventories
        )
        return DeliveryContinuationOutcome(
            DeliveryContinuationOutcomeKind.READY,
            ObservationDeliveryStore(
                latest_effect=self.latest_effect,
                local_deliveries=self.local_deliveries,
                active_read=self.active_read,
                inventories=next_inventories,
                action_query=self.action_query,
                search_follow_ups=self.search_follow_ups,
                requested_continuation_scope=capability.scope,
            ),
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
        if operation not in {"read_region", "search_page_content", "read_next_page", "find_controls"} or not isinstance(
            result, Mapping
        ):
            return DeliveryTransition(external, None)
        if operation == "read_next_page" and result.get("kind") not in {"Opened", "Matches", "Page"}:
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
        search_follow_ups = external.search_follow_ups
        if operation in {"search_page_content", "read_next_page"} and result.get("kind") == "Matches":
            world_observation_id = (
                external.active_read.world_observation_id
                if external.active_read is not None
                else str(getattr(getattr(step, "after_world", None), "observation_id", ""))
            )
            incoming = _local_search_hits(items, world_observation_id)
            by_region = {item.region_ref: item for item in search_follow_ups}
            for item in incoming:
                by_region.pop(item.region_ref, None)
                by_region[item.region_ref] = item
            search_follow_ups = tuple(by_region.values())[-_MAX_LOCAL_SEARCH_FOLLOW_UP_REGIONS:]
        next_store = ObservationDeliveryStore(
            latest_effect=external.latest_effect,
            local_deliveries=(*external.local_deliveries, record)[-_MAX_LOCAL_DELIVERY_RECORDS:],
            active_read=external.active_read,
            inventories=external.inventories,
            action_query=query_inventory,
            search_follow_ups=search_follow_ups,
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
        tuple(
            item for item in store.search_follow_ups
            if (
                item.world_observation_id == observation.observation_id
                and item.region_ref in projection.region_refs.values()
                and item.match_ref in projection.public_refs
            )
        ),
    )


def _local_search_hits(
    items: tuple[Mapping[str, object], ...],
    world_observation_id: str,
) -> tuple[LocalSearchHit, ...]:
    if not world_observation_id.strip():
        return ()
    hits: list[LocalSearchHit] = []
    seen_regions: set[str] = set()
    for item in items:
        region_ref = str(item.get("region_ref", ""))
        match_ref = str(item.get("match_ref") or item.get("node_ref") or item.get("evidence_ref") or "")
        if (
            region_ref in seen_regions
            or not PublicRefCodec.accepts(region_ref, expected=PublicRefKind.REGION)
            or not PublicRefCodec.accepts(match_ref)
            or PublicRefCodec.decode(match_ref).kind is PublicRefKind.REGION
        ):
            continue
        seen_regions.add(region_ref)
        hits.append(LocalSearchHit(world_observation_id, match_ref, region_ref))
    return tuple(hits[:_MAX_LOCAL_SEARCH_FOLLOW_UP_REGIONS])


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
