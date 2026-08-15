"""Canonical immutable observation contracts.

This module contains Runtime observation semantics only.  It deliberately has
no dependency on planner requests, model presentation policy, acquisition
adapters, Coordinator, or StateKernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, cast

from affordance_runtime.actions.contracts import RiskLevel
from affordance_runtime.actions.grounding import GroundingCandidate, GroundingSource
from affordance_runtime.execution.context import CoordinateBinding, ExecutorCapabilityDescriptor, LiveSurfaceBinding
from affordance_runtime.immutable import FrozenDict, freeze_json
from affordance_runtime.verification.contracts import AssuranceLevel, PredicateEvidence


class CoverageCompleteness(StrEnum):
    COMPLETE = "complete"
    BOUNDED = "bounded"
    UNKNOWN = "unknown"


class CoverageStatus(StrEnum):
    OBSERVED = "observed"
    SOURCE_NOT_ACQUIRED = "source_not_acquired"
    ACQUISITION_TRUNCATED = "acquisition_truncated"
    REQUIRED_PROPERTY_UNOBSERVED = "required_property_unobserved"
    TARGET_ABSENT_COMPLETE = "target_absent_complete"
    MODEL_PRESENTATION_OMISSION = "model_presentation_omission"
    ACQUISITION_ERROR = "acquisition_error"


class CoverageTermination(StrEnum):
    EXHAUSTED = "exhausted"
    LIMIT_REACHED = "limit_reached"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ERROR = "error"
    UNKNOWN = "unknown"


class ConflictStatus(StrEnum):
    RESOLVED = "resolved"
    NO_MATERIAL_CONFLICT = "no_material_conflict"
    MATERIAL_CONFLICT = "material_conflict"
    INCONCLUSIVE = "inconclusive"


class FactStatus(StrEnum):
    ACCEPTED = "accepted"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"
    STALE = "stale"


@dataclass(frozen=True)
class SourceCoverage:
    source: GroundingSource
    capture_policy_id: str
    captured_item_count: int
    truncated: bool
    omitted_item_count_estimate: int | None
    completeness: CoverageCompleteness
    status: CoverageStatus
    required_properties: tuple[str, ...] = ()
    observed_properties: tuple[str, ...] = ()
    error_code: str = ""
    acquisition_epoch_ref: str = ""
    source_scope: str = ""
    item_limit: int | None = None
    acquisition_budget: int | None = None
    model_id: str = ""
    adapter_version: str = ""
    threshold: float | None = None
    exhaustive: bool = False
    termination_reason: CoverageTermination = CoverageTermination.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.source, GroundingSource):
            raise ValueError("coverage source must be typed")
        if not self.capture_policy_id.strip():
            raise ValueError("capture policy id cannot be blank")
        if self.captured_item_count < 0:
            raise ValueError("captured item count cannot be negative")
        if self.omitted_item_count_estimate is not None and self.omitted_item_count_estimate < 0:
            raise ValueError("omitted item estimate cannot be negative")
        if self.item_limit is not None and self.item_limit < 0:
            raise ValueError("coverage item limit cannot be negative")
        if self.acquisition_budget is not None and self.acquisition_budget < 0:
            raise ValueError("coverage acquisition budget cannot be negative")
        if self.threshold is not None and not 0 <= self.threshold <= 1:
            raise ValueError("coverage threshold must be within [0, 1]")
        if self.truncated and self.completeness == CoverageCompleteness.COMPLETE:
            raise ValueError("truncated acquisition cannot claim complete coverage")
        if self.status == CoverageStatus.ACQUISITION_TRUNCATED and not self.truncated:
            raise ValueError("truncated coverage status requires truncated acquisition")
        if self.status == CoverageStatus.TARGET_ABSENT_COMPLETE and (
            self.truncated or self.completeness != CoverageCompleteness.COMPLETE
        ):
            raise ValueError("target absence requires complete untruncated coverage")
        if self.completeness == CoverageCompleteness.COMPLETE and (
            not self.exhaustive or self.termination_reason != CoverageTermination.EXHAUSTED
        ):
            raise ValueError("complete coverage requires explicit exhaustive acquisition")
        if self.error_code and self.completeness != CoverageCompleteness.UNKNOWN:
            raise ValueError("acquisition errors cannot claim bounded or complete coverage")
        object.__setattr__(self, "required_properties", tuple(self.required_properties))
        object.__setattr__(self, "observed_properties", tuple(self.observed_properties))

    @classmethod
    def complete(
        cls,
        source: GroundingSource,
        *,
        captured_item_count: int,
        capture_policy_id: str = "complete",
        observed_properties: tuple[str, ...] = (),
        acquisition_epoch_ref: str = "test-epoch",
        source_scope: str = "full-source",
        adapter_version: str = "test-adapter@v1",
    ) -> SourceCoverage:
        return cls(
            source=source,
            capture_policy_id=capture_policy_id,
            captured_item_count=captured_item_count,
            truncated=False,
            omitted_item_count_estimate=0,
            completeness=CoverageCompleteness.COMPLETE,
            status=CoverageStatus.OBSERVED,
            observed_properties=observed_properties,
            acquisition_epoch_ref=acquisition_epoch_ref,
            source_scope=source_scope,
            adapter_version=adapter_version,
            exhaustive=True,
            termination_reason=CoverageTermination.EXHAUSTED,
        )


@dataclass(frozen=True)
class Freshness:
    observation_epoch_id: str
    environment_revision: str
    page_revision: str
    observed_at_s: float
    expires_at_s: float = 0.0


@dataclass(frozen=True)
class ActionSupport:
    action_kind: str
    candidate_ids: tuple[str, ...]
    resource_ref: str = ""
    operation_ref: str = ""
    effect_class: str = ""
    externality: str = ""
    reversibility: str = ""
    resource_sensitivity: str = ""
    source_assurance: str = ""
    risk: RiskLevel = RiskLevel.LOW
    risk_asserted: bool = False

    def __post_init__(self) -> None:
        if not self.action_kind.strip() or not self.candidate_ids:
            raise ValueError("action support requires an action and candidates")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("action support candidate ids must be unique")


@dataclass(frozen=True)
class StateFact:
    property_name: str
    value: object | None
    status: FactStatus
    assertion_refs: tuple[str, ...]
    source_values: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        if not self.property_name.strip():
            raise ValueError("fact property name cannot be blank")
        object.__setattr__(self, "value", freeze_json(self.value))
        object.__setattr__(
            self,
            "source_values",
            tuple((source, freeze_json(value)) for source, value in self.source_values),
        )


@dataclass(frozen=True)
class ObservationConflict:
    target_id: str
    property_name: str
    assertion_refs: tuple[str, ...]
    material: bool
    reason: str


@dataclass(frozen=True)
class CanonicalTarget:
    target_id: str
    role: str
    label: str
    surfaces: tuple[GroundingSource, ...]
    action_support: tuple[ActionSupport, ...]
    state_facts: tuple[StateFact, ...]
    binding_ids: tuple[str, ...]
    conflict_status: ConflictStatus
    conflicts: tuple[ObservationConflict, ...]
    source_assertion_refs: tuple[str, ...]
    freshness: Freshness

    def __post_init__(self) -> None:
        if not self.target_id.strip() or not self.role.strip():
            raise ValueError("canonical target identity and role are required")
        if len(self.binding_ids) != len(set(self.binding_ids)):
            raise ValueError("canonical binding ids must be unique")

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return tuple(item.action_kind for item in self.action_support)

    @property
    def semantic_target_id(self) -> str:
        return self.target_id

    @property
    def state(self) -> FrozenDict:
        return FrozenDict(
            {
                item.property_name: item.value
                for item in self.state_facts
                if item.status == FactStatus.ACCEPTED
            }
        )


@dataclass(frozen=True)
class UnifiedObservationTarget:
    """Small direct-construction form used by pure canonical owner tests.

    Production capture paths construct ``CanonicalTarget`` through the builder;
    this type deliberately has no planner-view conversion API.
    """

    target_id: str
    surface: str
    role: str
    label: str
    supported_actions: tuple[str, ...]
    state: FrozenDict
    confidence: float | None = None
    conflict_codes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    risk: RiskLevel = RiskLevel.LOW
    risk_asserted: bool = False
    operation_ref: str = ""
    effect_class: str = ""
    source_assurance: AssuranceLevel = AssuranceLevel.WEAK
    externality: str = ""
    reversibility: str = ""
    resource_sensitivity: str = ""

    def __init__(
        self,
        *,
        target_id: str,
        surface: str,
        role: str,
        label: str,
        supported_actions: tuple[str, ...],
        state: Mapping[str, Any],
        confidence: float | None = None,
        conflict_codes: tuple[str, ...] = (),
        source_refs: tuple[str, ...] = (),
        risk: RiskLevel = RiskLevel.LOW,
        risk_asserted: bool = False,
        operation_ref: str = "",
        effect_class: str = "",
        source_assurance: AssuranceLevel = AssuranceLevel.WEAK,
        externality: str = "",
        reversibility: str = "",
        resource_sensitivity: str = "",
    ) -> None:
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "surface", surface)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "supported_actions", tuple(supported_actions))
        object.__setattr__(self, "state", freeze_json(dict(state)))
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "conflict_codes", tuple(conflict_codes))
        object.__setattr__(self, "source_refs", tuple(source_refs))
        object.__setattr__(self, "risk", risk)
        object.__setattr__(self, "risk_asserted", risk_asserted)
        object.__setattr__(self, "operation_ref", operation_ref)
        object.__setattr__(self, "effect_class", effect_class)
        object.__setattr__(self, "source_assurance", source_assurance)
        object.__setattr__(self, "externality", externality)
        object.__setattr__(self, "reversibility", reversibility)
        object.__setattr__(self, "resource_sensitivity", resource_sensitivity)
        if not target_id.strip() or not surface.strip() or not role.strip():
            raise ValueError("direct canonical target identity is required")
        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class UnifiedObservation:
    epoch_id: str
    page_revision: str
    environment_revision: str
    observed_text: str
    targets: tuple[CanonicalTarget, ...]
    bindings: tuple[GroundingCandidate, ...]
    source_coverage: tuple[SourceCoverage, ...]
    artifact_refs: tuple[str, ...]
    captured_at_s: float
    digest: str
    acquisition_policy_id: str = "default"
    metadata: FrozenDict = field(default_factory=lambda: FrozenDict({}))
    live_surface_binding: LiveSurfaceBinding | None = None
    coordinate_binding: CoordinateBinding | None = None
    capability_descriptor: ExecutorCapabilityDescriptor | None = None
    predicate_evidence: tuple[PredicateEvidence, ...] = ()

    def __init__(
        self,
        *,
        epoch_id: str = "",
        snapshot_id: str = "",
        page_revision: str,
        environment_revision: str,
        observed_text: str,
        targets: tuple[CanonicalTarget | UnifiedObservationTarget, ...],
        bindings: tuple[GroundingCandidate, ...] = (),
        source_coverage: tuple[SourceCoverage, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        captured_at_s: float = 0.0,
        digest: str = "test-direct-canonical",
        acquisition_policy_id: str = "default",
        metadata: Mapping[str, Any] | FrozenDict | None = None,
        live_surface_binding: LiveSurfaceBinding | None = None,
        coordinate_binding: CoordinateBinding | None = None,
        capability_descriptor: ExecutorCapabilityDescriptor | None = None,
        predicate_evidence: tuple[PredicateEvidence, ...] = (),
    ) -> None:
        resolved_epoch_id = epoch_id or snapshot_id
        object.__setattr__(self, "epoch_id", resolved_epoch_id)
        object.__setattr__(self, "page_revision", page_revision)
        object.__setattr__(self, "environment_revision", environment_revision)
        object.__setattr__(self, "observed_text", observed_text)
        object.__setattr__(self, "targets", cast(tuple[CanonicalTarget, ...], tuple(targets)))
        object.__setattr__(self, "bindings", tuple(bindings))
        object.__setattr__(self, "source_coverage", tuple(source_coverage))
        object.__setattr__(self, "artifact_refs", tuple(artifact_refs))
        object.__setattr__(self, "captured_at_s", captured_at_s)
        object.__setattr__(self, "digest", digest)
        object.__setattr__(self, "acquisition_policy_id", acquisition_policy_id)
        object.__setattr__(
            self,
            "metadata",
            metadata if isinstance(metadata, FrozenDict) else FrozenDict(metadata or {}),
        )
        object.__setattr__(self, "live_surface_binding", live_surface_binding)
        object.__setattr__(self, "coordinate_binding", coordinate_binding)
        object.__setattr__(self, "capability_descriptor", capability_descriptor)
        object.__setattr__(self, "predicate_evidence", tuple(predicate_evidence))
        self.__post_init__()

    def __post_init__(self) -> None:
        for label, value in (
            ("epoch_id", self.epoch_id),
            ("page_revision", self.page_revision),
            ("environment_revision", self.environment_revision),
            ("digest", self.digest),
        ):
            if not value.strip():
                raise ValueError(f"{label} cannot be blank")
        target_ids = tuple(item.target_id for item in self.targets)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("canonical target ids must be unique")
        binding_ids = tuple(item.candidate_id for item in self.bindings)
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("canonical binding ids must be unique")

    @property
    def snapshot_id(self) -> str:
        return self.epoch_id

    @property
    def target_fingerprints(self) -> FrozenDict:
        return FrozenDict(
            {
                item.fingerprint_key or item.candidate_id: item.target_fingerprint
                for item in self.bindings
                if item.target_fingerprint
            }
        )
