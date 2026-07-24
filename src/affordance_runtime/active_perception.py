"""Typed, bounded active-perception planning contracts and hard gates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Iterable
from uuid import uuid4

from pydantic import Field, model_validator

from affordance_runtime.contracts import RiskLevel
from affordance_runtime.grounding import (
    ActivePerceptionRequest,
    AssertionResolutionStatus,
    EvidenceKind,
    GroundingSource,
    PerceptionRequirements,
)
from affordance_runtime.task_intake import OperationClass, StrictModel

if TYPE_CHECKING:
    from affordance_runtime.browser_session import BrowserSnapshot


class EvidenceGapKind(StrEnum):
    MISSING_REQUIRED_EVIDENCE = "missing_required_evidence"
    STALE_EVIDENCE = "stale_evidence"
    SOURCE_CONFLICT = "source_conflict"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    AMBIGUOUS_TARGET = "ambiguous_target"
    VISUAL_PROPERTY_UNKNOWN = "visual_property_unknown"
    SPATIAL_RELATION_UNKNOWN = "spatial_relation_unknown"
    DEVICE_STATE_UNKNOWN = "device_state_unknown"
    GROUNDING_DISPROVED = "grounding_disproved"
    VERIFIER_INCONCLUSIVE = "verifier_inconclusive"
    POST_ACTION_EFFECT_UNKNOWN = "post_action_effect_unknown"


class ProbeKind(StrEnum):
    RECAPTURE_DOM = "recapture_dom"
    RECAPTURE_ACCESSIBILITY = "recapture_accessibility"
    EXTRACT_SVG_GEOMETRY = "extract_svg_geometry"
    CAPTURE_SCREENSHOT = "capture_screenshot"
    OCR_REGION = "ocr_region"
    MARK_REGION = "mark_region"
    GROUND_VISUAL_TARGET = "ground_visual_target"
    READ_DEVICE_PROPERTY = "read_device_property"
    QUERY_API_STATE = "query_api_state"
    INSPECT_RUNTIME_STATE = "inspect_runtime_state"
    WAIT_FOR_FRESH_STATE = "wait_for_fresh_state"


class ProbeAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


class PerceptionResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


class EvidenceGap(StrictModel):
    gap_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_revision: int = Field(ge=1)
    plan_version: int = Field(default=0, ge=0)
    active_subgoal_id: str = ""
    entity_key: str = Field(min_length=1)
    property_key: str = Field(min_length=1)
    gap_kind: EvidenceGapKind
    required_evidence_kind: EvidenceKind
    current_assertion_refs: tuple[str, ...] = ()
    conflicting_assertion_refs: tuple[str, ...] = ()
    current_sources: tuple[GroundingSource, ...] = ()
    preferred_sources: tuple[GroundingSource, ...] = ()
    reason: str = Field(min_length=1)
    material: bool = True
    risk_relevance: RiskLevel = RiskLevel.LOW
    blocks: bool = True
    source_event_ids: tuple[str, ...] = ()


class ProbeBudget(StrictModel):
    observations: int = Field(default=1, ge=0, le=16)
    timeout_ms: int = Field(default=5_000, ge=0, le=120_000)
    model_calls: int = Field(default=0, ge=0, le=16)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    artifacts: int = Field(default=1, ge=0, le=32)

    def includes(self, other: "ProbeBudget") -> bool:
        return (
            self.observations >= other.observations
            and self.timeout_ms >= other.timeout_ms
            and self.model_calls >= other.model_calls
            and self.estimated_cost >= other.estimated_cost
            and self.artifacts >= other.artifacts
        )


@dataclass(frozen=True)
class ProbeBudgetPolicy:
    """Intersect declared perception authority with remaining Runtime capacity."""

    def remaining_authority(
        self,
        requirements: PerceptionRequirements | None,
        *,
        remaining_observations: int,
    ) -> ProbeBudget:
        declared = requirements or PerceptionRequirements()
        observations = max(
            0,
            min(1, remaining_observations, declared.observation_budget),
        )
        return ProbeBudget(
            observations=observations,
            timeout_ms=declared.latency_budget_ms if observations else 0,
            model_calls=declared.model_call_budget if observations else 0,
            estimated_cost=declared.cost_budget if observations else 0.0,
            artifacts=1 if observations else 0,
        )


class ProbeCapability(StrictModel):
    capability_id: str = Field(min_length=1)
    source: GroundingSource
    probe_kind: ProbeKind
    supported_evidence_kinds: frozenset[EvidenceKind] = Field(min_length=1)
    supported_properties: frozenset[str] = frozenset()
    target_scope: str = "entity_property"
    expected_latency_ms: int = Field(default=0, ge=0, le=120_000)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    model_calls: int = Field(default=0, ge=0, le=16)
    freshness_semantics: str = Field(default="new_epoch", min_length=1)
    coherence_semantics: str = Field(default="single_epoch", min_length=1)
    confidence_semantics: str = "source_local"
    side_effect_class: OperationClass = OperationClass.READ_ONLY
    availability: ProbeAvailability = ProbeAvailability.AVAILABLE

    @model_validator(mode="after")
    def validate_probe_boundary(self) -> "ProbeCapability":
        if self.side_effect_class != OperationClass.READ_ONLY:
            raise ValueError("active perception capabilities must be read-only")
        if self.confidence_semantics != "source_local":
            raise ValueError("probe confidence cannot claim cross-source calibration")
        return self


class ProbeScope(StrictModel):
    entity_key: str = Field(min_length=1)
    property_key: str = Field(min_length=1)
    region_ref: str = ""


class ProbeCommand(StrictModel):
    command_id: str = Field(min_length=1)
    gap_ids: tuple[str, ...] = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    based_on_state_version: int = Field(ge=0)
    based_on_snapshot_id: str = Field(min_length=1)
    source: GroundingSource
    probe_kind: ProbeKind
    scope: ProbeScope
    expected_evidence_kind: EvidenceKind
    expected_information: str = Field(min_length=1)
    require_fresh_epoch: bool = True
    require_coherent_epoch: bool = True
    budget: ProbeBudget
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_epoch_requirements(self) -> "ProbeCommand":
        if not self.require_fresh_epoch or not self.require_coherent_epoch:
            raise ValueError("active perception must produce one fresh coherent epoch")
        if self.budget.observations != 1:
            raise ValueError("the shallow probe protocol permits exactly one observation per command")
        return self


class ProbePlan(StrictModel):
    plan_id: str = Field(min_length=1)
    based_on_state_version: int = Field(ge=0)
    based_on_snapshot_id: str = Field(min_length=1)
    gap_ids: tuple[str, ...] = Field(min_length=1)
    commands: tuple[ProbeCommand, ...] = Field(min_length=1, max_length=8)
    stop_conditions: tuple[str, ...] = Field(min_length=1)
    total_budget: ProbeBudget
    fallback: PerceptionResolutionStatus = PerceptionResolutionStatus.INCONCLUSIVE

    @model_validator(mode="after")
    def validate_plan_bindings(self) -> "ProbePlan":
        gap_ids = set(self.gap_ids)
        if len(gap_ids) != len(self.gap_ids):
            raise ValueError("probe plan gap ids must be unique")
        command_ids = [item.command_id for item in self.commands]
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("probe command ids must be unique")
        if any(
            item.based_on_state_version != self.based_on_state_version
            or item.based_on_snapshot_id != self.based_on_snapshot_id
            for item in self.commands
        ):
            raise ValueError("probe commands must bind the plan state and snapshot")
        covered = {gap_id for item in self.commands for gap_id in item.gap_ids}
        if not covered or not covered.issubset(gap_ids):
            raise ValueError("probe commands reference gaps outside the plan")
        consumed = _sum_budgets(item.budget for item in self.commands)
        if not self.total_budget.includes(consumed):
            raise ValueError("probe commands exceed the declared total budget")
        return self


class ProbeReceipt(StrictModel):
    command_id: str = Field(min_length=1)
    started_at_s: float = Field(ge=0.0)
    completed_at_s: float = Field(ge=0.0)
    observation_epoch_id: str = Field(min_length=1)
    source: GroundingSource
    success: bool
    artifact_refs: tuple[str, ...] = ()
    assertion_refs: tuple[str, ...] = ()
    error_code: str = ""
    estimated_cost: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    model_calls: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_timing(self) -> "ProbeReceipt":
        if self.completed_at_s < self.started_at_s:
            raise ValueError("probe completion cannot precede its start")
        if self.success and self.error_code:
            raise ValueError("successful probe receipt cannot carry an error")
        return self


class PerceptionResolution(StrictModel):
    status: PerceptionResolutionStatus
    based_on_snapshot_id: str = Field(min_length=1)
    observation_epoch_id: str = Field(min_length=1)
    resolved_gap_ids: tuple[str, ...] = ()
    unresolved_gap_ids: tuple[str, ...] = ()
    accepted_assertion_refs: tuple[str, ...] = ()
    probe_receipts: tuple[ProbeReceipt, ...] = ()
    reason: str = Field(min_length=1)
    blocks_effectful_action: bool = False

    @model_validator(mode="after")
    def validate_resolution(self) -> "PerceptionResolution":
        if set(self.resolved_gap_ids).intersection(self.unresolved_gap_ids):
            raise ValueError("one evidence gap cannot be both resolved and unresolved")
        if self.status == PerceptionResolutionStatus.RESOLVED and self.unresolved_gap_ids:
            raise ValueError("resolved perception cannot retain unresolved gaps")
        if self.status == PerceptionResolutionStatus.BLOCKED and not self.blocks_effectful_action:
            raise ValueError("blocked perception must block effectful action")
        return self


class ActivePerceptionDecision(StrictModel):
    gaps: tuple[EvidenceGap, ...]
    plan: ProbePlan | None = None
    resolution: PerceptionResolution | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "ActivePerceptionDecision":
        if (self.plan is None) == (self.resolution is None):
            raise ValueError("active perception decision requires exactly one plan or resolution")
        return self


@dataclass(frozen=True)
class EvidenceGapExtractor:
    """Derive explicit gaps from requirements and source arbitration output."""

    def extract(
        self,
        snapshot: "BrowserSnapshot",
        *,
        run_id: str,
        task_revision: int,
        plan_version: int = 0,
        active_subgoal_id: str = "",
    ) -> tuple[EvidenceGap, ...]:
        gaps: list[EvidenceGap] = []
        decisions = {
            (item.entity_key, item.property_key): item
            for item in snapshot.assertion_decisions
        }
        risk = (
            snapshot.perception_requirements.risk
            if snapshot.perception_requirements is not None
            else RiskLevel.LOW
        )
        for request in snapshot.active_perception_requests:
            decision = decisions.get((request.entity_key, request.property_key))
            gap_kind = _request_gap_kind(request, decision.status if decision is not None else None)
            assertion_refs = (
                tuple(item.assertion_id for item in decision.assertions)
                if decision is not None
                else ()
            )
            conflicting_refs = (
                assertion_refs if gap_kind == EvidenceGapKind.SOURCE_CONFLICT else ()
            )
            material = decision.material if decision is not None else True
            gaps.append(
                EvidenceGap(
                    gap_id=_gap_id(
                        run_id,
                        task_revision,
                        snapshot.observation.snapshot_id,
                        request.entity_key,
                        request.property_key,
                        gap_kind,
                    ),
                    run_id=run_id,
                    task_revision=task_revision,
                    plan_version=plan_version,
                    active_subgoal_id=active_subgoal_id,
                    entity_key=request.entity_key,
                    property_key=request.property_key,
                    gap_kind=gap_kind,
                    required_evidence_kind=_property_evidence_kind(request.property_key),
                    current_assertion_refs=assertion_refs,
                    conflicting_assertion_refs=conflicting_refs,
                    current_sources=(
                        tuple(dict.fromkeys(item.source for item in decision.assertions))
                        if decision is not None
                        else ()
                    ),
                    preferred_sources=request.requested_sources,
                    reason=request.reason,
                    material=material,
                    risk_relevance=risk,
                    blocks=material,
                )
            )
        requirements = snapshot.perception_requirements
        if requirements is not None:
            if not snapshot.unified_affordances:
                required_kind = (
                    EvidenceKind.VISUAL_APPEARANCE
                    if EvidenceKind.VISUAL_APPEARANCE in requirements.required_properties
                    else EvidenceKind.SPATIAL
                    if EvidenceKind.SPATIAL in requirements.required_properties
                    else EvidenceKind.STRUCTURAL
                )
                gap_kind = EvidenceGapKind.AMBIGUOUS_TARGET
                gaps.append(
                    EvidenceGap(
                        gap_id=_gap_id(
                            run_id,
                            task_revision,
                            snapshot.observation.snapshot_id,
                            "task:unresolved-target",
                            "semantic_target",
                            gap_kind,
                        ),
                        run_id=run_id,
                        task_revision=task_revision,
                        plan_version=plan_version,
                        active_subgoal_id=active_subgoal_id,
                        entity_key="task:unresolved-target",
                        property_key="semantic_target",
                        gap_kind=gap_kind,
                        required_evidence_kind=required_kind,
                        preferred_sources=(
                            requirements.preferred_sources
                            or _preferred_sources(required_kind)
                        ),
                        reason="current epoch has no actionable semantic target",
                        material=True,
                        risk_relevance=requirements.risk,
                        blocks=True,
                    )
                )
            for evidence_kind in sorted(requirements.required_properties, key=lambda item: item.value):
                if _snapshot_has_evidence(snapshot, evidence_kind):
                    continue
                gap_kind = _missing_gap_kind(evidence_kind)
                property_key = evidence_kind.value
                gaps.append(
                    EvidenceGap(
                        gap_id=_gap_id(
                            run_id,
                            task_revision,
                            snapshot.observation.snapshot_id,
                            "task:required-evidence",
                            property_key,
                            gap_kind,
                        ),
                        run_id=run_id,
                        task_revision=task_revision,
                        plan_version=plan_version,
                        active_subgoal_id=active_subgoal_id,
                        entity_key="task:required-evidence",
                        property_key=property_key,
                        gap_kind=gap_kind,
                        required_evidence_kind=evidence_kind,
                        preferred_sources=_preferred_sources(evidence_kind),
                        reason=f"required {evidence_kind.value} evidence is absent from the current epoch",
                        material=True,
                        risk_relevance=requirements.risk,
                        blocks=True,
                    )
                )
        return tuple({item.gap_id: item for item in gaps}.values())


@dataclass(frozen=True)
class ActivePerceptionController:
    """Select one minimum-cost sufficient probe without executing it."""

    def decide(
        self,
        gaps: tuple[EvidenceGap, ...],
        capabilities: tuple[ProbeCapability, ...],
        *,
        based_on_state_version: int,
        based_on_snapshot_id: str,
        budget: ProbeBudget,
        attempted_probe_fingerprints: frozenset[str] = frozenset(),
        effectful_action: bool = False,
    ) -> ActivePerceptionDecision:
        if not gaps:
            return ActivePerceptionDecision(
                gaps=(),
                resolution=PerceptionResolution(
                    status=PerceptionResolutionStatus.RESOLVED,
                    based_on_snapshot_id=based_on_snapshot_id,
                    observation_epoch_id=based_on_snapshot_id,
                    reason="current observation has no active evidence gap",
                ),
            )
        candidates: list[
            tuple[tuple[int, int, int, int, float, int, str], EvidenceGap, ProbeCapability]
        ] = []
        for gap in gaps:
            for capability in capabilities:
                if not _capability_closes_gap(capability, gap):
                    continue
                fingerprint = probe_fingerprint(capability, gap)
                if fingerprint in attempted_probe_fingerprints:
                    continue
                command_budget = _capability_budget(capability)
                if not budget.includes(command_budget):
                    continue
                source_rank = (
                    gap.preferred_sources.index(capability.source)
                    if capability.source in gap.preferred_sources
                    else len(gap.preferred_sources)
                )
                independent_rank = (
                    0
                    if gap.gap_kind != EvidenceGapKind.SOURCE_CONFLICT
                    or capability.source not in _assertion_sources(gap)
                    else 1
                )
                priority = (
                    0 if gap.blocks else 1,
                    -_risk_rank(gap.risk_relevance),
                    independent_rank,
                    source_rank,
                    capability.estimated_cost,
                    capability.expected_latency_ms + capability.model_calls * 1_000,
                    capability.capability_id,
                )
                candidates.append((priority, gap, capability))
        if not candidates:
            blocking = tuple(item.gap_id for item in gaps if item.blocks)
            status = (
                PerceptionResolutionStatus.BLOCKED
                if blocking and effectful_action
                else PerceptionResolutionStatus.INCONCLUSIVE
            )
            return ActivePerceptionDecision(
                gaps=gaps,
                resolution=PerceptionResolution(
                    status=status,
                    based_on_snapshot_id=based_on_snapshot_id,
                    observation_epoch_id=based_on_snapshot_id,
                    unresolved_gap_ids=tuple(item.gap_id for item in gaps),
                    reason="no unused read-only relevant probe fits the remaining budget",
                    blocks_effectful_action=status == PerceptionResolutionStatus.BLOCKED,
                ),
            )
        _priority, gap, capability = min(candidates, key=lambda item: item[0])
        command = ProbeCommand(
            command_id=f"probe-{uuid4().hex}",
            gap_ids=(gap.gap_id,),
            capability_id=capability.capability_id,
            based_on_state_version=based_on_state_version,
            based_on_snapshot_id=based_on_snapshot_id,
            source=capability.source,
            probe_kind=capability.probe_kind,
            scope=ProbeScope(entity_key=gap.entity_key, property_key=gap.property_key),
            expected_evidence_kind=gap.required_evidence_kind,
            expected_information=f"fresh {gap.required_evidence_kind.value} evidence for {gap.property_key}",
            budget=_capability_budget(capability),
            reason=gap.reason,
        )
        return ActivePerceptionDecision(
            gaps=gaps,
            plan=ProbePlan(
                plan_id=f"perception-plan-{uuid4().hex}",
                based_on_state_version=based_on_state_version,
                based_on_snapshot_id=based_on_snapshot_id,
                gap_ids=tuple(item.gap_id for item in gaps),
                commands=(command,),
                stop_conditions=(
                    "blocking_gap_resolved",
                    "material_conflict_survives",
                    "budget_exhausted",
                ),
                total_budget=command.budget,
                fallback=(
                    PerceptionResolutionStatus.BLOCKED
                    if effectful_action and gap.blocks
                    else PerceptionResolutionStatus.INCONCLUSIVE
                ),
            ),
        )

    def resolve(
        self,
        gaps: tuple[EvidenceGap, ...],
        snapshot: "BrowserSnapshot",
        *,
        based_on_snapshot_id: str,
        receipts: tuple[ProbeReceipt, ...],
        effectful_action: bool = False,
    ) -> PerceptionResolution:
        if snapshot.observation.snapshot_id == based_on_snapshot_id:
            unresolved_gap_ids = tuple(item.gap_id for item in gaps)
            return PerceptionResolution(
                status=(
                    PerceptionResolutionStatus.BLOCKED
                    if effectful_action and any(item.blocks for item in gaps)
                    else PerceptionResolutionStatus.INCONCLUSIVE
                ),
                based_on_snapshot_id=based_on_snapshot_id,
                observation_epoch_id=snapshot.observation.snapshot_id,
                unresolved_gap_ids=unresolved_gap_ids,
                probe_receipts=receipts,
                reason="probe did not create a fresh observation epoch",
                blocks_effectful_action=effectful_action and any(item.blocks for item in gaps),
            )
        decisions = {
            (item.entity_key, item.property_key): item
            for item in snapshot.assertion_decisions
        }
        resolved: list[str] = []
        unresolved: list[str] = []
        accepted: list[str] = []
        for gap in gaps:
            decision = decisions.get((gap.entity_key, gap.property_key))
            accepted_assertion = decision.accepted_assertion if decision is not None else None
            closed = (
                accepted_assertion is not None
                or (
                    gap.gap_kind == EvidenceGapKind.AMBIGUOUS_TARGET
                    and bool(snapshot.unified_affordances)
                )
                or (
                    gap.entity_key == "task:required-evidence"
                    and _snapshot_has_evidence(snapshot, gap.required_evidence_kind)
                )
            )
            if closed:
                resolved.append(gap.gap_id)
                if accepted_assertion is not None:
                    accepted.append(accepted_assertion.assertion_id)
            else:
                unresolved.append(gap.gap_id)
        if not unresolved:
            status = PerceptionResolutionStatus.RESOLVED
            reason = "fresh coherent evidence resolved all active gaps"
        elif effectful_action and any(item.blocks and item.gap_id in unresolved for item in gaps):
            status = PerceptionResolutionStatus.BLOCKED
            reason = "material evidence gap survives the bounded probe"
        else:
            status = PerceptionResolutionStatus.INCONCLUSIVE
            reason = "one or more evidence gaps survive the bounded probe"
        return PerceptionResolution(
            status=status,
            based_on_snapshot_id=based_on_snapshot_id,
            observation_epoch_id=snapshot.observation.snapshot_id,
            resolved_gap_ids=tuple(resolved),
            unresolved_gap_ids=tuple(unresolved),
            accepted_assertion_refs=tuple(accepted),
            probe_receipts=receipts,
            reason=reason,
            blocks_effectful_action=status == PerceptionResolutionStatus.BLOCKED,
        )


def probe_capabilities_for_requests(
    requests: tuple[ActivePerceptionRequest, ...],
) -> tuple[ProbeCapability, ...]:
    """Migration adapter from existing source requests to declared capabilities."""

    capabilities: dict[tuple[GroundingSource, str], ProbeCapability] = {}
    for request in requests:
        evidence_kind = _property_evidence_kind(request.property_key)
        for source in request.requested_sources:
            probe_kind, latency_ms, model_calls, cost = _source_probe_profile(source)
            key = source, request.property_key
            capabilities[key] = ProbeCapability(
                capability_id=f"capture:{source.value}:{request.property_key}",
                source=source,
                probe_kind=probe_kind,
                supported_evidence_kinds=frozenset({evidence_kind}),
                supported_properties=frozenset({request.property_key}),
                expected_latency_ms=latency_ms,
                estimated_cost=cost,
                model_calls=model_calls,
            )
    return tuple(capabilities.values())


def request_for_command(command: ProbeCommand) -> ActivePerceptionRequest:
    return ActivePerceptionRequest(
        entity_key=command.scope.entity_key,
        property_key=command.scope.property_key,
        requested_sources=(command.source,),
        reason=command.reason,
        max_observations=command.budget.observations,
    )


def probe_fingerprint(capability: ProbeCapability, gap: EvidenceGap) -> str:
    return "|".join(
        (
            capability.capability_id,
            capability.source.value,
            capability.probe_kind.value,
            gap.gap_id,
        )
    )


def _sum_budgets(values: Iterable[ProbeBudget]) -> ProbeBudget:
    budgets = tuple(values)
    return ProbeBudget(
        observations=sum(item.observations for item in budgets),
        timeout_ms=sum(item.timeout_ms for item in budgets),
        model_calls=sum(item.model_calls for item in budgets),
        estimated_cost=sum(item.estimated_cost for item in budgets),
        artifacts=sum(item.artifacts for item in budgets),
    )


def _capability_closes_gap(capability: ProbeCapability, gap: EvidenceGap) -> bool:
    return (
        capability.availability == ProbeAvailability.AVAILABLE
        and capability.side_effect_class == OperationClass.READ_ONLY
        and gap.required_evidence_kind in capability.supported_evidence_kinds
        and (
            not capability.supported_properties
            or gap.property_key in capability.supported_properties
        )
        and (not gap.preferred_sources or capability.source in gap.preferred_sources)
    )


def _capability_budget(capability: ProbeCapability) -> ProbeBudget:
    return ProbeBudget(
        observations=1,
        timeout_ms=max(1, capability.expected_latency_ms),
        model_calls=capability.model_calls,
        estimated_cost=capability.estimated_cost,
        artifacts=1,
    )


def _request_gap_kind(
    request: ActivePerceptionRequest,
    status: AssertionResolutionStatus | None,
) -> EvidenceGapKind:
    reason = request.reason.casefold()
    if "verifier" in reason or "verification" in reason:
        return EvidenceGapKind.VERIFIER_INCONCLUSIVE
    if "disagree" in reason or "conflict" in reason or status == AssertionResolutionStatus.CONFLICT:
        return EvidenceGapKind.SOURCE_CONFLICT
    if "stale" in reason or "expired" in reason:
        return EvidenceGapKind.STALE_EVIDENCE
    if request.entity_key == "task:unresolved-target":
        return EvidenceGapKind.AMBIGUOUS_TARGET
    evidence_kind = _property_evidence_kind(request.property_key)
    return _missing_gap_kind(evidence_kind)


def _missing_gap_kind(evidence_kind: EvidenceKind) -> EvidenceGapKind:
    return {
        EvidenceKind.VISUAL_APPEARANCE: EvidenceGapKind.VISUAL_PROPERTY_UNKNOWN,
        EvidenceKind.SPATIAL: EvidenceGapKind.SPATIAL_RELATION_UNKNOWN,
        EvidenceKind.DEVICE_STATE: EvidenceGapKind.DEVICE_STATE_UNKNOWN,
    }.get(evidence_kind, EvidenceGapKind.MISSING_REQUIRED_EVIDENCE)


def _property_evidence_kind(property_key: str) -> EvidenceKind:
    value = property_key.casefold().strip()
    if value in {"appearance", "color", "shape"}:
        return EvidenceKind.VISUAL_APPEARANCE
    if value in {"bbox", "geometry", "inside", "position", "spatial"}:
        return EvidenceKind.SPATIAL
    if value in {"device_state", "power", "sensor", "status", "temperature"}:
        return EvidenceKind.DEVICE_STATE
    if value in {"text", "textual"}:
        return EvidenceKind.TEXTUAL
    if value in {item.value for item in EvidenceKind}:
        return EvidenceKind(value)
    return EvidenceKind.STRUCTURAL


def _preferred_sources(evidence_kind: EvidenceKind) -> tuple[GroundingSource, ...]:
    return {
        EvidenceKind.TEXTUAL: (GroundingSource.DOM, GroundingSource.ACCESSIBILITY),
        EvidenceKind.STRUCTURAL: (GroundingSource.DOM, GroundingSource.ACCESSIBILITY),
        EvidenceKind.VISUAL_APPEARANCE: (
            GroundingSource.SVG,
            GroundingSource.SOM,
            GroundingSource.VISUAL,
        ),
        EvidenceKind.SPATIAL: (
            GroundingSource.SVG,
            GroundingSource.DOM,
            GroundingSource.SOM,
            GroundingSource.VISUAL,
        ),
        EvidenceKind.DEVICE_STATE: (GroundingSource.WOT, GroundingSource.API),
    }[evidence_kind]


def _snapshot_has_evidence(snapshot: "BrowserSnapshot", evidence_kind: EvidenceKind) -> bool:
    minimum_confidence = (
        snapshot.perception_requirements.minimum_confidence
        if snapshot.perception_requirements is not None
        else 0.0
    )
    conflicted_entities = {
        item.entity_key
        for item in snapshot.assertion_decisions
        if item.material and item.status == AssertionResolutionStatus.CONFLICT
    }
    return any(
        evidence_kind in candidate.evidence_kinds
        and candidate.confidence >= minimum_confidence
        and candidate.is_current(snapshot.observation)
        and target.semantic_target_id not in conflicted_entities
        and not target.unresolved_conflicts
        for target in snapshot.unified_affordances
        for candidate in target.grounding_candidates
    )


def _source_probe_profile(source: GroundingSource) -> tuple[ProbeKind, int, int, float]:
    return {
        GroundingSource.DOM: (ProbeKind.RECAPTURE_DOM, 20, 0, 0.0),
        GroundingSource.ACCESSIBILITY: (ProbeKind.RECAPTURE_ACCESSIBILITY, 30, 0, 0.0),
        GroundingSource.SVG: (ProbeKind.EXTRACT_SVG_GEOMETRY, 50, 0, 0.0),
        GroundingSource.SOM: (ProbeKind.MARK_REGION, 750, 1, 0.5),
        GroundingSource.VISUAL: (ProbeKind.GROUND_VISUAL_TARGET, 1_000, 1, 1.0),
        GroundingSource.WOT: (ProbeKind.READ_DEVICE_PROPERTY, 100, 0, 0.0),
        GroundingSource.API: (ProbeKind.QUERY_API_STATE, 100, 0, 0.0),
    }[source]


def _assertion_sources(gap: EvidenceGap) -> frozenset[GroundingSource]:
    return frozenset(gap.current_sources)


def _risk_rank(risk: RiskLevel) -> int:
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.IRREVERSIBLE: 3,
    }[risk]


def _gap_id(
    run_id: str,
    task_revision: int,
    snapshot_id: str,
    entity_key: str,
    property_key: str,
    gap_kind: EvidenceGapKind,
) -> str:
    payload = "|".join(
        (run_id, str(task_revision), snapshot_id, entity_key, property_key, gap_kind.value)
    )
    return "gap:sha256:" + hashlib.sha256(payload.encode()).hexdigest()
