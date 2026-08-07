"""Typed cross-surface grounding and route boundaries.

The planner sees semantic target ids and action kinds.  Only these runtime
types may carry source-specific handles or geometry into a selected contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import time
from typing import Any, Mapping, Protocol, TypeAlias

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.immutable import freeze_json


class CurrentObservation(Protocol):
    @property
    def environment_revision(self) -> str: ...
    @property
    def page_revision(self) -> str: ...
    @property
    def snapshot_id(self) -> str: ...
    @property
    def target_fingerprints(self) -> Mapping[str, str]: ...


class EvidenceKind(StrEnum):
    TEXTUAL = "textual"
    STRUCTURAL = "structural"
    VISUAL_APPEARANCE = "visual_appearance"
    SPATIAL = "spatial"
    DEVICE_STATE = "device_state"


class GroundingSource(StrEnum):
    DOM = "dom"
    ACCESSIBILITY = "accessibility"
    SVG = "svg"
    SOM = "som"
    VISUAL = "visual"
    WOT = "wot"
    API = "api"
    DEVICE = "device"


class AssertionResolutionStatus(StrEnum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"
    REOBSERVE = "reobserve"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class SourceAssertion:
    """One source-local claim retained with freshness and provenance."""

    assertion_id: str
    entity_key: str
    property_key: str
    value: Any
    value_type: str
    source: GroundingSource
    observation_epoch_id: str
    environment_revision: str
    page_revision: str
    parser_id: str
    schema_version: str = "1.0"
    unit: str = ""
    observed_at_s: float = field(default_factory=time)
    expires_at_s: float = 0.0
    confidence: float = 1.0
    confidence_semantics: str = "source_local"
    evidence_refs: tuple[str, ...] = ()
    material: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", freeze_json(self.value))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if not self.assertion_id or not self.entity_key or not self.property_key:
            raise ValueError("source assertion identity fields must be non-empty")
        if not self.value_type or not self.parser_id or not self.schema_version:
            raise ValueError("source assertion type, parser, and schema must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("source assertion confidence must be within [0, 1]")
        if self.confidence_semantics != "source_local":
            raise ValueError("cross-source confidence semantics are not calibrated")

    def is_current(self, observation: CurrentObservation, *, now_s: float | None = None) -> bool:
        current_time = time() if now_s is None else now_s
        return (
            (not self.environment_revision or self.environment_revision == observation.environment_revision)
            and (not self.page_revision or self.page_revision == observation.page_revision)
            and (not self.observation_epoch_id or self.observation_epoch_id == observation.snapshot_id)
            and (not self.expires_at_s or current_time <= self.expires_at_s)
        )


@dataclass(frozen=True)
class ActivePerceptionRequest:
    entity_key: str
    property_key: str
    requested_sources: tuple[GroundingSource, ...]
    reason: str
    max_observations: int = 1

    def __post_init__(self) -> None:
        if not self.entity_key or not self.property_key or not self.requested_sources:
            raise ValueError("active perception request requires a target property and source")
        if self.max_observations < 1:
            raise ValueError("active perception request must be bounded")


@dataclass(frozen=True)
class AssertionDecision:
    entity_key: str
    property_key: str
    status: AssertionResolutionStatus
    assertions: tuple[SourceAssertion, ...]
    accepted_assertion_id: str = ""
    reason: str = ""
    material: bool = True

    @property
    def accepted_assertion(self) -> SourceAssertion | None:
        return next(
            (item for item in self.assertions if item.assertion_id == self.accepted_assertion_id),
            None,
        )


@dataclass(frozen=True)
class AssertionArbitration:
    decisions: tuple[AssertionDecision, ...]
    active_perception_requests: tuple[ActivePerceptionRequest, ...] = ()


@dataclass(frozen=True)
class PerceptionRequirements:
    required_properties: frozenset[EvidenceKind] = frozenset()
    acceptable_evidence: frozenset[GroundingSource] = field(default_factory=lambda: frozenset(GroundingSource))
    preferred_sources: tuple[GroundingSource, ...] = ()
    minimum_confidence: float = 0.0
    minimum_verifier_strength: int = 0
    observation_budget: int = 1
    model_call_budget: int = 0
    latency_budget_ms: int = 5_000
    cost_budget: float = 0.0
    risk: RiskLevel = RiskLevel.LOW
    require_current_epoch: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum perception confidence must be within [0, 1]")
        if min(self.observation_budget, self.model_call_budget, self.latency_budget_ms) < 0:
            raise ValueError("perception budgets cannot be negative")
        if self.cost_budget < 0:
            raise ValueError("perception cost budget cannot be negative")


@dataclass(frozen=True)
class SourceObservation:
    source: GroundingSource
    parser_id: str
    observation_epoch_id: str
    environment_revision: str
    page_revision: str
    artifact_refs: tuple[str, ...] = ()
    latency_ms: float = 0.0
    model_cost: float = 0.0
    confidence: float = 1.0
    acquisition_exhaustive: bool = False
    source_scope: str = ""


@dataclass(frozen=True)
class DomGroundingPayload:
    backend_handle: str = ""
    selector: str = ""
    bbox_xywh: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class AccessibilityGroundingPayload:
    node_id: str
    role: str = ""
    name: str = ""


@dataclass(frozen=True)
class SvgTransform:
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    def apply(self, point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f


@dataclass(frozen=True)
class SvgGroundingPayload:
    element_id: str
    tag: str
    view_box: tuple[float, float, float, float]
    geometry_bbox_xywh: tuple[float, float, float, float]
    viewport_bbox_xywh: tuple[float, float, float, float]
    transform: SvgTransform
    backend_handle: str = ""

    @property
    def viewport_center(self) -> tuple[float, float]:
        x, y, width, height = self.viewport_bbox_xywh
        return x + width / 2, y + height / 2


@dataclass(frozen=True)
class VisualGroundingPayload:
    screenshot_ref: str
    image_size: tuple[int, int]
    point_xy: tuple[float, float] | None = None
    bbox_xywh: tuple[float, float, float, float] | None = None
    mark_id: str = ""


@dataclass(frozen=True)
class WoTGroundingPayload:
    thing_id: str
    form_index: int
    operation: str


@dataclass(frozen=True)
class ApiGroundingPayload:
    operation_id: str
    resource_id: str = ""


GroundingPayload: TypeAlias = (
    DomGroundingPayload
    | AccessibilityGroundingPayload
    | SvgGroundingPayload
    | VisualGroundingPayload
    | WoTGroundingPayload
    | ApiGroundingPayload
)


@dataclass(frozen=True)
class CandidateScopeEvidence:
    """Bounded observed relations that may support, but never grant, task scope."""

    container_context: str = ""
    group_context: str = ""
    collection_position: int | None = None

    def __post_init__(self) -> None:
        if len(self.container_context) > 160 or len(self.group_context) > 240:
            raise ValueError("candidate scope context exceeds the bounded observation contract")
        if self.collection_position is not None and self.collection_position < 1:
            raise ValueError("candidate collection position must be one-based")


@dataclass(frozen=True)
class GroundingCandidate:
    candidate_id: str
    semantic_target_id: str
    source: GroundingSource
    payload: GroundingPayload
    compatible_executor: str
    observation_epoch_id: str
    environment_revision: str
    page_revision: str
    target_fingerprint: str
    supported_actions: frozenset[str]
    evidence_kinds: frozenset[EvidenceKind]
    source_affordance_id: str = ""
    fingerprint_key: str = ""
    confidence: float = 1.0
    expires_at_s: float = 0.0
    expected_latency_ms: float = 0.0
    expected_cost: float = 0.0
    verifier_strength: int = 0
    evidence_refs: tuple[str, ...] = ()
    scope_evidence: CandidateScopeEvidence | None = None
    risk: RiskLevel = RiskLevel.LOW
    risk_asserted: bool = False
    operation_ref: str = ""
    effect_class: str = ""
    externality: str = ""
    reversibility: str = ""
    resource_sensitivity: str = ""
    authority_source_assurance: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.semantic_target_id:
            raise ValueError("grounding candidate ids must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("grounding candidate confidence must be within [0, 1]")

    def is_current(self, observation: CurrentObservation) -> bool:
        if self.environment_revision != observation.environment_revision:
            return False
        if self.page_revision and self.page_revision != observation.page_revision:
            return False
        if self.observation_epoch_id and self.observation_epoch_id != observation.snapshot_id:
            return False
        observed = observation.target_fingerprints.get(self.fingerprint_key or self.candidate_id)
        return not self.target_fingerprint or observed == self.target_fingerprint


@dataclass(frozen=True)
class UnifiedAffordance:
    semantic_target_id: str
    role: str
    label: str
    supported_actions: frozenset[str]
    accepted_state: tuple[tuple[str, str], ...] = ()
    unresolved_conflicts: tuple[str, ...] = ()
    grounding_candidates: tuple[GroundingCandidate, ...] = ()

    def __post_init__(self) -> None:
        if not self.semantic_target_id:
            raise ValueError("unified affordance requires a semantic target id")
        if any(item.semantic_target_id != self.semantic_target_id for item in self.grounding_candidates):
            raise ValueError("all grounding candidates must belong to the unified semantic target")


@dataclass(frozen=True)
class RouteGateResult:
    candidate_id: str
    passed: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteScore:
    candidate_id: str
    score: float
    confidence_component: float
    latency_component: float
    cost_component: float
    verification_component: float = 0.5


@dataclass(frozen=True)
class RoutePlan:
    semantic_target_id: str
    selected_candidate: GroundingCandidate
    viable_alternatives: tuple[GroundingCandidate, ...] = ()
    verifier_kinds: tuple[str, ...] = ()
    hard_gate_results: tuple[RouteGateResult, ...] = ()
    scores: tuple[RouteScore, ...] = ()
    decision_reason: str = ""
    environment_scope: str = "generic"
    action_kind: str = ""

    def __post_init__(self) -> None:
        candidates = (self.selected_candidate, *self.viable_alternatives)
        if any(item.semantic_target_id != self.semantic_target_id for item in candidates):
            raise ValueError("route candidates must belong to the active semantic target")
