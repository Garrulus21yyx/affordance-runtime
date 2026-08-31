"""Immutable unified-world and runtime-owned action-space contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from affordance_runtime.actions.capabilities import (
    INTERACTION_CAPABILITY_REGISTRY,
    DestinationMode,
    InteractionCapabilityError,
    InteractionCapabilityIssueCode,
    VerificationContract,
    verification_contract_for_action,
)
from affordance_runtime.actions.effect_semantics import Reversibility
from affordance_runtime.actions.space_contracts import (
    ActionRisk,
    canonical_destination_ids,
)
from affordance_runtime.immutable import freeze_json, to_json_compatible
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.world.semantic_inventory import (
    SemanticInventoryStatus,
    SemanticInventorySummary,
)
from affordance_runtime.world.source_profile import ObservationSourceProfile


class CoverageState(StrEnum):
    COMPLETE = "complete"
    NOT_ACQUIRED = "not_acquired"
    FAILED = "failed"
    TRUNCATED = "truncated"
    STALE = "stale"


class EntityAlignmentDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONFLICTED = "conflicted"


class EntityAlignmentBasis(StrEnum):
    EXPLICIT_PROVIDER_CORRESPONDENCE = "explicit_provider_correspondence"


class EntityAllocation(StrEnum):
    EQUIVALENT = "equivalent"
    INDEPENDENT = "independent"


_ALIGNMENT_DECISION_REASONS = {
    EntityAlignmentDisposition.ACCEPTED: frozenset({"explicit_equivalence_accepted"}),
    EntityAlignmentDisposition.REJECTED: frozenset({
        "alignment_endpoint_unresolved",
        "alignment_same_source_forbidden",
        "alignment_acquisition_root_mismatch",
        "alignment_role_mismatch",
        "alignment_coordinate_space_mismatch",
    }),
    EntityAlignmentDisposition.CONFLICTED: frozenset({"alignment_component_conflicted"}),
}


class ObservationMediaVariant(StrEnum):
    RAW = "raw"
    ANNOTATED = "annotated"
    CROP = "crop"


MAX_OBSERVATION_GROUNDING_REGIONS = 512


@dataclass(frozen=True, order=True)
class SourceEntityEndpoint:
    source_observation_id: str
    source_target_id: str

    def __post_init__(self) -> None:
        if not self.source_observation_id.strip() or not self.source_target_id.strip():
            raise ValueError("source entity endpoint requires source-local identity")


@dataclass(frozen=True)
class EntityAlignmentProposal:
    proposal_id: str
    source: SourceEntityEndpoint
    candidate: SourceEntityEndpoint
    basis: EntityAlignmentBasis
    evidence_refs: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("entity alignment proposal requires identity")
        if not isinstance(self.source, SourceEntityEndpoint) or not isinstance(
            self.candidate, SourceEntityEndpoint
        ):
            raise TypeError("alignment proposal endpoints must be source-local and typed")
        if self.source == self.candidate:
            raise ValueError("alignment proposal endpoints must be distinct")
        if self.basis is not EntityAlignmentBasis.EXPLICIT_PROVIDER_CORRESPONDENCE:
            raise ValueError("unsupported entity alignment proposal basis")
        evidence = tuple(self.evidence_refs)
        if not evidence or any(not item.strip() for item in evidence):
            raise ValueError("entity alignment proposal requires evidence")
        if len(set(evidence)) != len(evidence) or not 0 <= self.confidence <= 1:
            raise ValueError("entity alignment proposal evidence or confidence is invalid")
        object.__setattr__(self, "evidence_refs", evidence)


@dataclass(frozen=True)
class EntityAlignmentDecision:
    proposal_id: str
    disposition: EntityAlignmentDisposition
    basis: EntityAlignmentBasis
    evidence_refs: tuple[str, ...]
    confidence: float
    reason_code: str

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.reason_code.strip():
            raise ValueError("entity alignment decision requires identity and reason")
        if not isinstance(self.disposition, EntityAlignmentDisposition) or not isinstance(
            self.basis, EntityAlignmentBasis
        ):
            raise TypeError("entity alignment decision disposition and basis must be typed")
        if self.reason_code not in _ALIGNMENT_DECISION_REASONS[self.disposition]:
            raise ValueError("entity alignment decision disposition and reason disagree")
        evidence = tuple(self.evidence_refs)
        if not evidence or any(not item.strip() for item in evidence):
            raise ValueError("entity alignment decision requires proposal evidence")
        if len(set(evidence)) != len(evidence) or not 0 <= self.confidence <= 1:
            raise ValueError("entity alignment decision evidence or confidence is invalid")
        object.__setattr__(self, "evidence_refs", evidence)


@dataclass(frozen=True)
class EntitySourceLink:
    source_observation_id: str
    source_target_id: str
    canonical_target_id: str
    acquisition_root_id: str
    allocation: EntityAllocation

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.source_observation_id,
                self.source_target_id,
                self.canonical_target_id,
                self.acquisition_root_id,
            )
        ):
            raise ValueError("entity source link requires complete identity")
        if not isinstance(self.allocation, EntityAllocation):
            raise TypeError("entity source link allocation must be typed")


@dataclass(frozen=True)
class SourceObservationManifest:
    source_observation_id: str
    surface: str
    modality: str
    profile: str
    acquisition_root_id: str
    coverage: CoverageState

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.source_observation_id,
                self.surface,
                self.modality,
                self.profile,
                self.acquisition_root_id,
            )
        ):
            raise ValueError("source manifest requires complete source-instance attributes")
        if not isinstance(self.coverage, CoverageState):
            raise TypeError("source manifest coverage must be typed")


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


@dataclass(frozen=True)
class ObservationGroundingRegion:
    """Observation-bound geometry for model annotation, never execution authority."""

    target_id: str
    bbox: tuple[int, int, int, int]
    confidence: float = 1.0
    coordinate_space_id: str = ""

    def __post_init__(self) -> None:
        if (
            not self.target_id.strip()
            or not self.coordinate_space_id.strip()
            or len(self.bbox) != 4
            or not 0 <= self.confidence <= 1
        ):
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
    capture_group_id: str = ""
    variant: ObservationMediaVariant = ObservationMediaVariant.RAW
    dimensions: tuple[int, int] = (0, 0)
    coordinate_space_id: str = ""
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
            or not self.capture_group_id.strip()
            or not self.coordinate_space_id.strip()
            or not isinstance(self.variant, ObservationMediaVariant)
            or len(self.dimensions) != 2
            or any(type(value) is not int or value <= 0 for value in self.dimensions)
        ):
            raise ValueError("observation media is invalid or exceeds its bound")
        object.__setattr__(self, "sha256", hashlib.sha256(self.data).hexdigest())
        regions = tuple(self.grounding_regions)
        if len(regions) > MAX_OBSERVATION_GROUNDING_REGIONS or any(
            not isinstance(item, ObservationGroundingRegion) for item in regions
        ):
            raise TypeError("observation grounding regions must be bounded and typed")
        if len({item.target_id for item in regions}) != len(regions):
            raise ValueError("observation grounding regions must have unique targets")
        if any(item.coordinate_space_id != self.coordinate_space_id for item in regions):
            raise ValueError("media grounding requires the declared coordinate space")
        object.__setattr__(self, "grounding_regions", regions)


@dataclass(frozen=True)
class CanonicalObservationMedia:
    source_observation_id: str
    media: ObservationMedia

    def __post_init__(self) -> None:
        if not self.source_observation_id.strip() or not isinstance(self.media, ObservationMedia):
            raise ValueError("canonical media requires a source instance and typed media")


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


def derived_target_state(
    target_id: str,
    facts: tuple[StateFact, ...],
    *,
    conflicted_predicates: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Project the non-conflicted canonical facts for one target into its legacy state view."""

    values: dict[str, Any] = {}
    encoded: dict[str, str] = {}
    for fact in facts:
        if fact.subject_id != target_id or fact.predicate in conflicted_predicates:
            continue
        token = json.dumps(
            to_json_compatible(fact.value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        prior = encoded.get(fact.predicate)
        if prior is not None and prior != token:
            raise ValueError("canonical state facts disagree without a typed conflict")
        encoded[fact.predicate] = token
        values.setdefault(fact.predicate, fact.value)
    return freeze_json(values)


def _validate_derived_target_states(
    targets: tuple[SemanticTarget, ...],
    facts: tuple[StateFact, ...],
    *,
    conflicts: tuple[ObservationConflict, ...] = (),
    require_complete: bool,
) -> None:
    del require_complete
    conflicts_by_target: dict[str, set[str]] = {}
    for conflict in conflicts:
        conflicts_by_target.setdefault(conflict.subject_id, set()).add(conflict.predicate)
    for target in targets:
        conflicted = frozenset(conflicts_by_target.get(target.target_id, ()))
        projected = derived_target_state(
            target.target_id,
            facts,
            conflicted_predicates=conflicted,
        )
        visible_state = {key: value for key, value in target.state.items() if key not in conflicted}
        if any(key in visible_state and visible_state[key] != value for key, value in projected.items()):
            raise ValueError("semantic target state contradicts canonical StateFact")


@dataclass(frozen=True)
class ObservationConflict:
    conflict_id: str
    subject_id: str
    predicate: str
    summary: str


@dataclass(frozen=True)
class ObservationStructureNode:
    """One public, non-authoritative node in a source structural document."""

    structure_id: str
    role: str
    label: str
    state: dict[str, Any] = field(default_factory=dict)
    parent_structure_id: str = ""
    child_structure_ids: tuple[str, ...] = ()
    semantic_target_id: str = ""
    parent_outside_structure: bool = False

    def __post_init__(self) -> None:
        if not self.structure_id.strip() or not self.role.strip():
            raise ValueError("observation structure node requires public identity and role")
        object.__setattr__(self, "state", freeze_json(self.state))
        object.__setattr__(self, "child_structure_ids", tuple(self.child_structure_ids))
        if len(set(self.child_structure_ids)) != len(self.child_structure_ids):
            raise ValueError("observation structure children must be unique")


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
    verification_contract_digest: str = ""
    verification_family: str = ""
    resource_ref: str = ""
    reversibility: Reversibility = Reversibility.UNKNOWN

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
        definition = INTERACTION_CAPABILITY_REGISTRY.require(self.semantic_action)
        INTERACTION_CAPABILITY_REGISTRY.validate_parameter_schema(
            self.semantic_action,
            self.parameter_schema,
        )
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "parameter_schema", freeze_json(self.parameter_schema))
        object.__setattr__(self, "payload", freeze_json(self.payload))
        object.__setattr__(self, "eligible_destination_ids", canonical_destination_ids(self.eligible_destination_ids))
        object.__setattr__(self, "resource_ref", self.resource_ref.strip() or self.target_id)
        if not isinstance(self.reversibility, Reversibility):
            raise TypeError("action binding reversibility must be typed")
        if self.destination_required and not self.eligible_destination_ids:
            raise ValueError("destination-required binding must offer semantic destination IDs")
        destination_mode = (
            DestinationMode.REQUIRED
            if self.destination_required
            else DestinationMode.OPTIONAL
            if self.eligible_destination_ids
            else DestinationMode.FORBIDDEN
        )
        if destination_mode is not definition.destination_mode:
            raise InteractionCapabilityError(
                InteractionCapabilityIssueCode.DESTINATION_MODE_MISMATCH,
                self.semantic_action,
            )
        if self.verification_family:
            from affordance_runtime.actions.capabilities import VerificationFamily

            if VerificationFamily(self.verification_family) not in definition.verification_families:
                raise ValueError("binding verification family is not supported by the action")
        contract = self.verification_contract
        if not self.verification_family:
            object.__setattr__(self, "verification_family", contract.family.value)
        elif self.verification_family != contract.family.value:
            raise ValueError("binding verification family does not match sealed contract")
        if not self.verification_contract_digest:
            object.__setattr__(
                self,
                "verification_contract_digest",
                contract.digest,
            )
        elif self.verification_contract_digest != contract.digest:
            raise ValueError("binding verification contract does not match sealed contract")

    @property
    def observation_id(self) -> str:
        """Compatibility read; new code uses explicit world_observation_id."""

        return self.world_observation_id

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (self.semantic_action,)

    @property
    def verification_contract(self) -> VerificationContract:
        from affordance_runtime.actions.capabilities import VerificationFamily

        return verification_contract_for_action(
            self.semantic_action,
            schema_digest(self.parameter_schema),
            self.semantic_effects,
            self.observation_barrier,
            family=VerificationFamily(self.verification_family) if self.verification_family else None,
        )


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
    alignment_proposals: tuple[EntityAlignmentProposal, ...] = ()
    visual_only_target_ids: tuple[str, ...] = ()
    structure: tuple[ObservationStructureNode, ...] = ()
    structure_total_count: int = 0

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
        if len({target.target_id for target in self.targets}) != len(self.targets):
            raise ValueError("surface semantic target IDs must be unique")
        _validate_derived_target_states(
            self.targets,
            self.facts,
            require_complete=self.coverage is CoverageState.COMPLETE,
        )
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
        object.__setattr__(self, "alignment_proposals", tuple(self.alignment_proposals))
        object.__setattr__(self, "visual_only_target_ids", tuple(self.visual_only_target_ids))
        local_ids = {item.target_id for item in self.targets}
        proposal_ids = {item.proposal_id for item in self.alignment_proposals}
        endpoint_pairs = {
            tuple(sorted((item.source, item.candidate))) for item in self.alignment_proposals
        }
        if len(proposal_ids) != len(self.alignment_proposals):
            raise ValueError("entity alignment proposal IDs must be unique within a source")
        if len(endpoint_pairs) != len(self.alignment_proposals):
            raise ValueError("entity alignment endpoint pairs must be unique within a source")
        if any(
            item.source.source_observation_id != self.observation_id
            or item.source.source_target_id not in local_ids
            for item in self.alignment_proposals
        ):
            raise ValueError("proposal source endpoint must belong to its source observation")
        if len(set(self.visual_only_target_ids)) != len(self.visual_only_target_ids) or any(
            item not in local_ids for item in self.visual_only_target_ids
        ):
            raise ValueError("visual-only identity must be unique and source-local")
        if self.source_profile.modality.value != "visual" and self.visual_only_target_ids:
            raise ValueError("only a visual source may declare visual-only identities")
        structure = tuple(self.structure)
        if any(not isinstance(item, ObservationStructureNode) for item in structure):
            raise TypeError("surface structure must be a typed tuple")
        if len({item.structure_id for item in structure}) != len(structure):
            raise ValueError("surface structure identities must be unique")
        structure_ids = {item.structure_id for item in structure}
        if any(item.semantic_target_id and item.semantic_target_id not in local_ids for item in structure):
            raise ValueError("surface structure semantic link must reference a local target")
        if any(
            (item.parent_structure_id and item.parent_structure_id not in structure_ids)
            or any(child not in structure_ids for child in item.child_structure_ids)
            for item in structure
        ):
            raise ValueError("surface structure relations must be closed over retained nodes")
        if self.structure_total_count < len(structure):
            raise ValueError("surface structure total cannot be smaller than retained nodes")
        object.__setattr__(self, "structure", structure)
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
    source_manifest: tuple[SourceObservationManifest, ...]
    conflicts: tuple[ObservationConflict, ...] = ()
    sources: tuple[SurfaceObservation, ...] = ()
    entity_alignment_decisions: tuple[EntityAlignmentDecision, ...] = ()
    entity_source_links: tuple[EntitySourceLink, ...] = ()
    media: tuple[CanonicalObservationMedia, ...] = ()

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
        object.__setattr__(self, "conflicts", tuple(self.conflicts))
        object.__setattr__(self, "sources", tuple(self.sources))
        manifests = tuple(self.source_manifest)
        decisions = tuple(self.entity_alignment_decisions)
        links = tuple(self.entity_source_links)
        media = tuple(self.media)
        if any(not isinstance(item, SourceObservationManifest) for item in manifests):
            raise TypeError("world source manifest must be typed")
        if len({item.source_observation_id for item in manifests}) != len(manifests):
            raise ValueError("world source manifest IDs must be unique")
        source_ids = {item.observation_id for item in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("world source observation IDs must be unique")
        if source_ids != {item.source_observation_id for item in manifests}:
            raise ValueError("world source manifest must cover exactly the retained sources")
        manifests_by_id = {item.source_observation_id: item for item in manifests}
        if any(
            manifests_by_id[source.observation_id]
            != SourceObservationManifest(
                source.observation_id,
                source.surface,
                str(source.source_profile.modality),
                source.source_profile.debug_source,
                source.acquisition_root_id or source.observation_id,
                source.coverage,
            )
            for source in self.sources
        ):
            raise ValueError("world source manifest attributes contradict their source instance")
        if any(not isinstance(item, EntitySourceLink) for item in links):
            raise TypeError("world entity source links must be typed")
        if any(not isinstance(item, EntityAlignmentDecision) for item in decisions):
            raise TypeError("world entity alignment decisions must be typed")
        proposals = tuple(
            proposal
            for source in self.sources
            for proposal in source.alignment_proposals
        )
        proposal_ids = [item.proposal_id for item in proposals]
        decision_ids = [item.proposal_id for item in decisions]
        if (
            len(set(proposal_ids)) != len(proposal_ids)
            or len(set(decision_ids)) != len(decision_ids)
            or set(decision_ids) != set(proposal_ids)
        ):
            raise ValueError("every proposal requires exactly one alignment decision")
        proposals_by_id = {item.proposal_id: item for item in proposals}
        if any(
            decision.basis is not proposals_by_id[decision.proposal_id].basis
            or decision.evidence_refs != proposals_by_id[decision.proposal_id].evidence_refs
            or decision.confidence != proposals_by_id[decision.proposal_id].confidence
            for decision in decisions
        ):
            raise ValueError("alignment decision must conserve proposal evidence and confidence")
        endpoints = {(item.source_observation_id, item.source_target_id) for item in links}
        expected_endpoints = {
            (source.observation_id, target.target_id)
            for source in self.sources
            for target in source.targets
        }
        if endpoints != expected_endpoints or len(endpoints) != len(links):
            raise ValueError("every retained source target requires exactly one entity source link")
        if any(item.canonical_target_id not in target_ids for item in links):
            raise ValueError("entity source link must resolve to a canonical current target")
        if {item.canonical_target_id for item in links} != target_ids:
            raise ValueError("every canonical target requires entity source link coverage")
        if len({
            (item.source_observation_id, item.canonical_target_id)
            for item in links
        }) != len(links):
            raise ValueError("source-to-canonical allocation must be injective within a source")
        if any(
            item.acquisition_root_id
            != manifests_by_id[item.source_observation_id].acquisition_root_id
            for item in links
        ):
            raise ValueError("entity source link acquisition root contradicts its source")

        typed_endpoints = {
            SourceEntityEndpoint(source_id, target_id)
            for source_id, target_id in expected_endpoints
        }
        accepted_adjacency: dict[SourceEntityEndpoint, set[SourceEntityEndpoint]] = {
            endpoint: set() for endpoint in typed_endpoints
        }
        for decision in decisions:
            if decision.disposition is not EntityAlignmentDisposition.ACCEPTED:
                continue
            proposal = proposals_by_id[decision.proposal_id]
            if proposal.source not in typed_endpoints or proposal.candidate not in typed_endpoints:
                raise ValueError("accepted alignment decision endpoints must be retained")
            accepted_adjacency[proposal.source].add(proposal.candidate)
            accepted_adjacency[proposal.candidate].add(proposal.source)

        expected_components: set[frozenset[SourceEntityEndpoint]] = set()
        remaining_endpoints = set(typed_endpoints)
        for root in sorted(typed_endpoints):
            if root not in remaining_endpoints:
                continue
            pending = [root]
            component: set[SourceEntityEndpoint] = set()
            while pending:
                endpoint = pending.pop()
                if endpoint in component:
                    continue
                component.add(endpoint)
                pending.extend(accepted_adjacency[endpoint])
            remaining_endpoints.difference_update(component)
            expected_components.add(frozenset(component))

        actual_by_canonical: dict[str, set[SourceEntityEndpoint]] = {}
        links_by_endpoint: dict[SourceEntityEndpoint, EntitySourceLink] = {}
        for link in links:
            endpoint = SourceEntityEndpoint(link.source_observation_id, link.source_target_id)
            actual_by_canonical.setdefault(link.canonical_target_id, set()).add(endpoint)
            links_by_endpoint[endpoint] = link
        actual_components = {frozenset(component) for component in actual_by_canonical.values()}
        if actual_components != expected_components:
            raise ValueError("entity source links must match accepted alignment decisions")
        for expected_component in expected_components:
            expected_allocation = (
                EntityAllocation.EQUIVALENT
                if len(expected_component) > 1
                else EntityAllocation.INDEPENDENT
            )
            component_links = tuple(links_by_endpoint[endpoint] for endpoint in expected_component)
            if any(link.allocation is not expected_allocation for link in component_links):
                raise ValueError("entity link allocation contradicts its accepted component")
            if len(expected_component) > 1:
                roots = {
                    next(
                        source.acquisition_root_id
                        for source in self.sources
                        if source.observation_id == endpoint.source_observation_id
                    )
                    for endpoint in expected_component
                }
                if "" in roots or len(roots) != 1:
                    raise ValueError("equivalent component requires one non-empty acquisition root")
        for source in self.sources:
            local_ids = {item.target_id for item in source.targets}
            if any(fact.subject_id not in local_ids for fact in source.facts):
                raise ValueError("source envelope facts must remain source-local")
            if any(
                binding.target_id not in local_ids
                or any(item not in local_ids for item in binding.eligible_destination_ids)
                for binding in source.bindings
            ):
                raise ValueError("source envelope bindings must remain source-local")
            if any(
                region.target_id not in local_ids
                for item in source.media
                for region in item.grounding_regions
            ):
                raise ValueError("source envelope media grounding must remain source-local")
        if any(not isinstance(item, CanonicalObservationMedia) for item in media):
            raise TypeError("world canonical media must be typed")
        if any(item.source_observation_id not in source_ids for item in media):
            raise ValueError("canonical media must reference a retained source instance")
        if any(
            region.target_id not in target_ids
            for item in media
            for region in item.media.grounding_regions
        ):
            raise ValueError("world media grounding must use canonical identities")
        object.__setattr__(self, "source_manifest", manifests)
        object.__setattr__(self, "entity_alignment_decisions", decisions)
        object.__setattr__(self, "entity_source_links", links)
        object.__setattr__(self, "media", media)
        _validate_derived_target_states(
            self.targets,
            self.facts,
            conflicts=self.conflicts,
            require_complete=all(item.coverage is CoverageState.COMPLETE for item in manifests),
        )
