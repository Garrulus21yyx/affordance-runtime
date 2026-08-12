"""Immutable unified-world and runtime-owned action-space contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.world.schema_validation import validate_parameter_schema_contract
from affordance_runtime.world.semantic_inventory import (
    SemanticInventoryStatus,
    SemanticInventorySummary,
)
from affordance_runtime.world.source_profile import ObservationSourceProfile

_PRIVATE_DESTINATION_MARKERS = ("selector", "coordinate", "bbox", "href", "http://", "https://")


class CoverageState(StrEnum):
    COMPLETE = "complete"
    NOT_ACQUIRED = "not_acquired"
    FAILED = "failed"
    TRUNCATED = "truncated"
    STALE = "stale"


class EntityInventoryStatus(StrEnum):
    UNASSESSED = "unassessed"
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class EntityInventoryIssueCode(StrEnum):
    ENTITY_CAPACITY_EXCEEDED = "inventory_capacity_exceeded"
    FACT_CAPACITY_EXCEEDED = "inventory_fact_capacity_exceeded"
    OPTION_DOMAIN_CAPACITY_EXCEEDED = "inventory_option_domain_capacity_exceeded"
    COVERAGE_UNAVAILABLE = "coverage_unavailable"


@dataclass(frozen=True)
class EntityInventorySummary:
    """Conservation metadata for the canonical public inventory of one source."""

    status: EntityInventoryStatus = EntityInventoryStatus.UNASSESSED
    entity_count: int = 0
    entity_total_count: int = 0
    fact_count: int = 0
    fact_total_count: int = 0
    relation_count: int = 0
    relation_total_count: int = 0
    option_value_count: int = 0
    option_value_total_count: int = 0
    issue_codes: tuple[EntityInventoryIssueCode, ...] = ()

    def __post_init__(self) -> None:
        counts = (
            self.entity_count,
            self.entity_total_count,
            self.fact_count,
            self.fact_total_count,
            self.relation_count,
            self.relation_total_count,
            self.option_value_count,
            self.option_value_total_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("entity inventory counts must be non-negative exact integers")
        if (
            self.entity_count > self.entity_total_count
            or self.fact_count > self.fact_total_count
            or self.relation_count > self.relation_total_count
            or self.option_value_count > self.option_value_total_count
        ):
            raise ValueError("entity inventory retained counts cannot exceed totals")
        object.__setattr__(self, "issue_codes", tuple(dict.fromkeys(self.issue_codes)))
        if any(not isinstance(code, EntityInventoryIssueCode) for code in self.issue_codes):
            raise TypeError("entity inventory issue codes must be typed")
        truncated = any(
            retained < total
            for retained, total in (
                (self.entity_count, self.entity_total_count),
                (self.fact_count, self.fact_total_count),
                (self.relation_count, self.relation_total_count),
                (self.option_value_count, self.option_value_total_count),
            )
        )
        if self.status is EntityInventoryStatus.UNASSESSED:
            if any(counts) or self.issue_codes:
                raise ValueError("unassessed entity inventory cannot carry observations")
        elif self.status is EntityInventoryStatus.COMPLETE:
            if truncated or self.issue_codes:
                raise ValueError("complete entity inventory cannot report omissions")
        elif self.status is EntityInventoryStatus.PARTIAL:
            if not truncated or not self.issue_codes:
                raise ValueError("partial entity inventory requires typed omissions")
        elif self.status is EntityInventoryStatus.UNAVAILABLE:
            if any(counts) or self.issue_codes != (EntityInventoryIssueCode.COVERAGE_UNAVAILABLE,):
                raise ValueError("unavailable entity inventory requires its typed reason only")


class ActionRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class ObservationGroundingRegion:
    """Observation-bound geometry for model annotation, never execution authority."""

    target_id: str
    bbox: tuple[int, int, int, int]
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.target_id.strip() or len(self.bbox) != 4 or not 0 <= self.confidence <= 1:
            raise ValueError("observation grounding region is invalid")
        x, y, width, height = self.bbox
        if any(type(value) is not int for value in self.bbox) or x < 0 or y < 0 or width <= 0 or height <= 0:
            raise ValueError("observation grounding bbox is invalid")
        object.__setattr__(self, "bbox", tuple(self.bbox))


@dataclass(frozen=True)
class ObservationMedia:
    media_id: str
    kind: str
    mime_type: str
    data: bytes = field(repr=False)
    grounding_regions: tuple[ObservationGroundingRegion, ...] = field(default=(), repr=False)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not self.media_id.strip()
            or len(self.media_id) > 120
            or self.kind != "screenshot"
            or self.mime_type not in {"image/png", "image/jpeg"}
            or not isinstance(self.data, bytes)
            or not self.data
            or len(self.data) > 5 * 1024 * 1024
        ):
            raise ValueError("observation media is invalid or exceeds its bound")
        object.__setattr__(self, "sha256", hashlib.sha256(self.data).hexdigest())
        regions = tuple(self.grounding_regions)
        if len(regions) > 512 or any(not isinstance(item, ObservationGroundingRegion) for item in regions):
            raise TypeError("observation grounding regions must be bounded and typed")
        if len({item.target_id for item in regions}) != len(regions):
            raise ValueError("observation grounding regions must have unique targets")
        object.__setattr__(self, "grounding_regions", regions)


@dataclass(frozen=True)
class SemanticTarget:
    target_id: str
    role: str
    label: str
    state: dict[str, Any] = field(default_factory=dict)
    relations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.role.strip():
            raise ValueError("semantic target requires identity and role")
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "relations", freeze_json(self.relations))


@dataclass(frozen=True)
class StateFact:
    fact_id: str
    subject_id: str
    predicate: str
    value: Any
    source_id: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.fact_id, self.subject_id, self.predicate, self.source_id)):
            raise ValueError("state fact identity fields cannot be blank")
        if not self.fact_id.startswith("fact:"):
            object.__setattr__(self, "fact_id", f"fact:{self.fact_id}")
        object.__setattr__(self, "value", freeze_json(self.value))


@dataclass(frozen=True)
class ObservationConflict:
    conflict_id: str
    subject_id: str
    predicate: str
    summary: str


@dataclass(frozen=True)
class EntityCorrespondence:
    """Trusted adapter-supplied source-local to canonical entity link."""

    source_target_id: str
    canonical_target_id: str
    relation: str = "explicit"

    def __post_init__(self) -> None:
        if not self.source_target_id.strip() or not self.canonical_target_id.strip():
            raise ValueError("entity correspondence requires both identities")
        if self.relation != "explicit":
            raise ValueError("only explicit correspondence is supported")


@dataclass(frozen=True)
class ActionBinding:
    binding_id: str
    world_observation_id: str
    source_observation_id: str
    source_revision: str
    target_fingerprint: str
    target_id: str
    source_target_id: str
    surface: str
    executor_id: str
    semantic_action: str
    primitive_action: str
    effect_category: str
    semantic_effects: tuple[str, ...]
    parameter_schema: dict[str, Any]
    payload: dict[str, Any]
    observation_barrier: bool = True
    expires_at_s: float = 0.0
    confidence: float = 1.0
    cost: float = 0.0
    risk: ActionRisk = ActionRisk.LOW
    destination_required: bool = False
    eligible_destination_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.binding_id,
            self.world_observation_id,
            self.source_observation_id,
            self.source_revision,
            self.target_fingerprint,
            self.target_id,
            self.source_target_id,
            self.surface,
            self.executor_id,
            self.semantic_action,
            self.primitive_action,
            self.effect_category,
        )
        if not all(value.strip() for value in required):
            raise ValueError("action binding requires world/source identity, fingerprint, and route")
        validate_parameter_schema_contract(self.parameter_schema)
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "payload", freeze_json(self.payload))
        object.__setattr__(self, "eligible_destination_ids", canonical_destination_ids(self.eligible_destination_ids))
        if self.destination_required and not self.eligible_destination_ids:
            raise ValueError("destination-required binding must offer semantic destination IDs")

    @property
    def observation_id(self) -> str:
        """Compatibility read; new code uses explicit world_observation_id."""

        return self.world_observation_id

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (self.semantic_action,)


@dataclass(frozen=True)
class SurfaceObservation:
    observation_id: str
    surface: str
    revision: str
    source_profile: ObservationSourceProfile
    targets: tuple[SemanticTarget, ...] = ()
    facts: tuple[StateFact, ...] = ()
    bindings: tuple[ActionBinding, ...] = ()
    coverage: CoverageState = CoverageState.COMPLETE
    artifacts: dict[str, Any] = field(default_factory=dict)
    semantic_inventory: SemanticInventorySummary = field(default_factory=SemanticInventorySummary.unassessed)
    media: tuple[ObservationMedia, ...] = ()
    entity_inventory: EntityInventorySummary = field(default_factory=EntityInventorySummary)
    acquisition_root_id: str = ""
    correspondences: tuple[EntityCorrespondence, ...] = ()
    visual_only_target_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.surface.strip() or not self.revision.strip():
            raise ValueError("surface observation requires identity, surface, and revision")
        if any(
            binding.source_observation_id != self.observation_id or binding.source_revision != self.revision
            for binding in self.bindings
        ):
            raise ValueError("surface binding must retain its source identity and revision")
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "artifacts", freeze_json(self.artifacts))
        if not isinstance(self.semantic_inventory, SemanticInventorySummary):
            raise TypeError("surface semantic inventory must be typed")
        object.__setattr__(self, "media", tuple(self.media))
        if len(self.media) > 4 or any(not isinstance(item, ObservationMedia) for item in self.media):
            raise TypeError("surface media must be a bounded typed tuple")
        if self.semantic_inventory.status is not SemanticInventoryStatus.UNASSESSED:
            if self.semantic_inventory.projected_target_count != len(self.targets):
                raise ValueError("assessed semantic inventory must match projected targets")
            actionable = len({binding.target_id for binding in self.bindings})
            if self.semantic_inventory.actionable_target_count != actionable:
                raise ValueError("assessed semantic inventory must match unique binding targets")
        if not isinstance(self.entity_inventory, EntityInventorySummary):
            raise TypeError("surface entity inventory summary must be typed")
        object.__setattr__(self, "correspondences", tuple(self.correspondences))
        object.__setattr__(self, "visual_only_target_ids", tuple(self.visual_only_target_ids))
        if len({item.source_target_id for item in self.correspondences}) != len(self.correspondences):
            raise ValueError("source entities may have only one explicit correspondence")
        local_ids = {item.target_id for item in self.targets}
        if any(item.source_target_id not in local_ids for item in self.correspondences):
            raise ValueError("entity correspondence must reference a source-local target")
        if (
            len(set(self.visual_only_target_ids)) != len(self.visual_only_target_ids)
            or any(item not in local_ids for item in self.visual_only_target_ids)
        ):
            raise ValueError("visual-only identity must be unique and source-local")
        corresponded = {item.source_target_id for item in self.correspondences}
        if corresponded.intersection(self.visual_only_target_ids):
            raise ValueError("a source target cannot be both corresponded and visual-only")
        if self.source_profile.modality.value != "visual" and self.visual_only_target_ids:
            raise ValueError("only a visual source may declare visual-only identities")
        if self.entity_inventory.status is not EntityInventoryStatus.UNASSESSED:
            if self.entity_inventory.entity_count != len(self.targets):
                raise ValueError("entity inventory must match retained surface targets")
            if self.entity_inventory.fact_count != len(self.facts):
                raise ValueError("entity inventory must match retained surface facts")


@dataclass(frozen=True)
class WorldObservation:
    observation_id: str
    targets: tuple[SemanticTarget, ...]
    facts: tuple[StateFact, ...]
    bindings: tuple[ActionBinding, ...]
    coverage: dict[str, CoverageState]
    conflicts: tuple[ObservationConflict, ...] = ()
    sources: tuple[SurfaceObservation, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("world observation requires non-empty identity")
        if any(binding.world_observation_id != self.observation_id for binding in self.bindings):
            raise ValueError("world binding must reference the current observation")
        target_ids = {target.target_id for target in self.targets}
        if len(target_ids) != len(self.targets):
            raise ValueError("canonical world target IDs must be unique")
        if any(binding.target_id not in target_ids for binding in self.bindings):
            raise ValueError("world bindings must reference canonical current targets")
        if any(
            destination_id not in target_ids
            for binding in self.bindings
            for destination_id in binding.eligible_destination_ids
        ):
            raise ValueError("binding destination target must exist in the current world observation")
        object.__setattr__(self, "targets", tuple(self.targets))
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "coverage", freeze_json(self.coverage))
        object.__setattr__(self, "conflicts", tuple(self.conflicts))
        object.__setattr__(self, "sources", tuple(self.sources))


@dataclass(frozen=True)
class ActionOption:
    action_id: str
    observation_id: str
    semantic_action: str
    target_id: str
    effect_category: str
    parameter_schema: dict[str, Any]
    schema_digest: str
    eligible_binding_ids: tuple[str, ...]
    description: str
    semantic_effects: tuple[str, ...] = ()
    risk: ActionRisk = ActionRisk.LOW
    destination_required: bool = False
    eligible_destination_ids: tuple[str, ...] = ()
    batchable: bool = False
    observation_barrier: bool = True

    def __post_init__(self) -> None:
        if (
            not all(
                value.strip()
                for value in (
                    self.action_id,
                    self.observation_id,
                    self.semantic_action,
                    self.target_id,
                    self.effect_category,
                    self.schema_digest,
                )
            )
            or not self.eligible_binding_ids
        ):
            raise ValueError("action option requires current semantic identity")
        validate_parameter_schema_contract(self.parameter_schema)
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "eligible_binding_ids", tuple(self.eligible_binding_ids))
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "eligible_destination_ids", canonical_destination_ids(self.eligible_destination_ids))
        if self.destination_required and not self.eligible_destination_ids:
            raise ValueError("destination-required action must offer semantic destination IDs")


@dataclass(frozen=True)
class AdmittedActionSelection:
    action_id: str
    observation_id: str
    semantic_action: str
    target_id: str
    effect_category: str
    semantic_effects: tuple[str, ...]
    schema_digest: str
    eligible_binding_ids: tuple[str, ...]
    risk: ActionRisk
    observation_barrier: bool
    parameters: dict[str, Any] = field(default_factory=dict)
    destination_id: str = ""
    destination_required: bool = False
    eligible_destination_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.action_id,
            self.observation_id,
            self.semantic_action,
            self.target_id,
            self.effect_category,
            self.schema_digest,
        )
        if not all(value.strip() for value in required) or not self.eligible_binding_ids:
            raise ValueError("admitted selection requires exact option and binding-group identity")
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "eligible_binding_ids", tuple(self.eligible_binding_ids))
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        object.__setattr__(self, "eligible_destination_ids", canonical_destination_ids(self.eligible_destination_ids))
        validate_selected_destination(
            self.destination_id,
            self.destination_required,
            self.eligible_destination_ids,
        )


@dataclass(frozen=True)
class ActionSpace:
    observation_id: str
    options: tuple[ActionOption, ...]
    action_space_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("action space requires observation identity")
        if any(option.observation_id != self.observation_id for option in self.options):
            raise ValueError("action-space option belongs to another observation")
        if len({option.action_id for option in self.options}) != len(self.options):
            raise ValueError("action ids must be unique within an action space")
        object.__setattr__(self, "options", tuple(self.options))
        semantic_membership = tuple(
            (
                option.action_id,
                option.semantic_action,
                option.target_id,
                option.effect_category,
                option.schema_digest,
                option.description,
                option.semantic_effects,
                option.risk,
                option.destination_required,
                option.eligible_destination_ids,
                option.observation_barrier,
                to_json_compatible(option.parameter_schema),
            )
            for option in self.options
        )
        encoded = json.dumps((self.observation_id, semantic_membership), sort_keys=True, separators=(",", ":"))
        object.__setattr__(self, "action_space_id", f"action-space:{hashlib.sha256(encoded.encode()).hexdigest()}")

    def find(self, action_id: str) -> ActionOption | None:
        return next((option for option in self.options if option.action_id == action_id), None)


def canonical_destination_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    destinations = tuple(values)
    if any(not item.strip() for item in destinations):
        raise ValueError("destination IDs cannot be blank")
    if len(set(destinations)) != len(destinations):
        raise ValueError("destination IDs must be unique")
    if any(_destination_is_private(item) for item in destinations):
        raise ValueError("destination contains runtime-private route identity")
    return tuple(sorted(destinations))


def validate_selected_destination(
    destination_id: str,
    destination_required: bool,
    eligible_destination_ids: tuple[str, ...],
) -> None:
    if destination_id and _destination_is_private(destination_id):
        raise ValueError("destination contains runtime-private route identity")
    if destination_required and not destination_id:
        raise ValueError("semantic destination is required")
    if destination_id and destination_id not in eligible_destination_ids:
        raise ValueError("semantic destination was not offered by the current ActionSpace")


def _destination_is_private(destination_id: str) -> bool:
    lowered = destination_id.casefold()
    return any(marker in lowered for marker in _PRIVATE_DESTINATION_MARKERS)
