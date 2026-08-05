"""Candidate typing, conservative semantic grouping, and unified routing."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from time import time
from typing import Iterable

from affordance_runtime.contracts import Affordance, Observation, Surface
from affordance_runtime.grounding import (
    ApiGroundingPayload,
    CandidateScopeEvidence,
    DomGroundingPayload,
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    PerceptionRequirements,
    RouteGateResult,
    RoutePlan,
    RouteScore,
    SvgGroundingPayload,
    SvgTransform,
    UnifiedAffordance,
    VisualGroundingPayload,
    WoTGroundingPayload,
)
from affordance_runtime.route_calibration import RouteCalibrator, RouteScope
from affordance_runtime.unified_observation import CanonicalTarget, ConflictStatus, UnifiedObservation


@dataclass(frozen=True)
class CandidateDescriptor:
    role: str
    label: str
    action: str
    container_context: str
    candidate: GroundingCandidate


def candidate_from_affordance(
    affordance: Affordance,
    observation: Observation,
    *,
    semantic_target_id: str,
    image_size: tuple[int, int] | None = None,
    compatible_executor: str = "",
) -> GroundingCandidate:
    """Translate a legacy affordance once at the typed fusion boundary."""

    candidate_id = f"candidate:{affordance.surface.value}:{affordance.id}"
    source: GroundingSource
    payload: (
        DomGroundingPayload
        | SvgGroundingPayload
        | VisualGroundingPayload
        | WoTGroundingPayload
        | ApiGroundingPayload
    )
    evidence_kinds: frozenset[EvidenceKind]
    if affordance.surface in {Surface.DOM, Surface.ACCESSIBILITY}:
        source = GroundingSource.DOM if affordance.surface == Surface.DOM else GroundingSource.ACCESSIBILITY
        bbox = _optional_box(affordance.locator.get("bbox"))
        payload = DomGroundingPayload(
            backend_handle=str(affordance.locator.get("backend_handle") or ""),
            selector=str(affordance.locator.get("selector") or ""),
            bbox_xywh=bbox,
        )
        evidence = {EvidenceKind.TEXTUAL, EvidenceKind.STRUCTURAL}
        if bbox is not None or bool(payload.backend_handle or payload.selector):
            # A current element locator is a trusted executor-local spatial
            # binding even when raw coordinates are not exposed to the planner.
            evidence.add(EvidenceKind.SPATIAL)
        evidence_kinds = frozenset(evidence)
    elif affordance.surface == Surface.SVG:
        bbox = _optional_box(affordance.locator.get("bbox"))
        if bbox is None:
            raise ValueError("SVG candidate typing requires current viewport geometry")
        source = GroundingSource.SVG
        payload = SvgGroundingPayload(
            element_id=str(
                affordance.locator.get("element_id")
                or affordance.locator.get("backend_handle")
                or affordance.id
            ),
            tag=str(affordance.locator.get("tag") or affordance.role),
            view_box=_optional_box(affordance.locator.get("view_box")) or bbox,
            geometry_bbox_xywh=(
                _optional_box(affordance.locator.get("geometry_bbox")) or bbox
            ),
            viewport_bbox_xywh=bbox,
            transform=SvgTransform(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            backend_handle=str(affordance.locator.get("backend_handle") or ""),
        )
        evidence_kinds = frozenset(
            {
                EvidenceKind.SPATIAL,
                EvidenceKind.STRUCTURAL,
                EvidenceKind.VISUAL_APPEARANCE,
                *({EvidenceKind.TEXTUAL} if affordance.label.strip() else set()),
            }
        )
    elif affordance.surface == Surface.VISUAL:
        if image_size is None:
            raise ValueError("visual candidate typing requires current image dimensions")
        source = GroundingSource.SOM if affordance.locator.get("mark_id") else GroundingSource.VISUAL
        payload = VisualGroundingPayload(
            screenshot_ref=str(affordance.locator.get("screenshot_ref") or observation.screenshot_ref),
            image_size=image_size,
            point_xy=_optional_point(affordance.locator.get("center")),
            bbox_xywh=_optional_box(affordance.locator.get("bbox")),
            mark_id=str(affordance.locator.get("mark_id") or ""),
        )
        evidence_kinds = frozenset(
            {
                EvidenceKind.VISUAL_APPEARANCE,
                EvidenceKind.SPATIAL,
                *({EvidenceKind.TEXTUAL} if affordance.label.strip() else set()),
            }
        )
    elif affordance.surface == Surface.WOT:
        source = GroundingSource.WOT
        payload = WoTGroundingPayload(
            thing_id=str(affordance.locator.get("thing_id") or ""),
            form_index=int(affordance.locator.get("form_index") or 0),
            operation=str(affordance.locator.get("operation") or affordance.action),
        )
        evidence_kinds = frozenset({EvidenceKind.DEVICE_STATE, EvidenceKind.STRUCTURAL})
    elif affordance.surface in {Surface.API, Surface.DEVICE}:
        source = (
            GroundingSource.API
            if affordance.surface == Surface.API
            else GroundingSource.DEVICE
        )
        payload = ApiGroundingPayload(
            operation_id=str(affordance.locator.get("operation_id") or affordance.action),
            resource_id=str(affordance.locator.get("resource_id") or ""),
        )
        evidence_kinds = frozenset({EvidenceKind.DEVICE_STATE, EvidenceKind.STRUCTURAL})
    else:
        raise ValueError(f"unsupported grounding surface: {affordance.surface}")
    container_context = str(affordance.state.get("container_context") or "")
    group_context = str(affordance.state.get("group_context") or "")
    raw_position = affordance.state.get("collection_position")
    collection_position = raw_position if isinstance(raw_position, int) and raw_position > 0 else None
    scope_evidence = (
        CandidateScopeEvidence(
            container_context=container_context,
            group_context=group_context,
            collection_position=collection_position,
        )
        if container_context or group_context or collection_position is not None
        else None
    )
    return GroundingCandidate(
        candidate_id=candidate_id,
        semantic_target_id=semantic_target_id,
        source=source,
        payload=payload,
        compatible_executor=(
            compatible_executor or (affordance.backend_candidates[0] if affordance.backend_candidates else source.value)
        ),
        observation_epoch_id=observation.snapshot_id,
        environment_revision=observation.environment_revision,
        page_revision=observation.page_revision,
        target_fingerprint=affordance.target_fingerprint,
        fingerprint_key=affordance.id,
        supported_actions=_semantic_actions(affordance.action),
        evidence_kinds=evidence_kinds,
        source_affordance_id=affordance.id,
        confidence=affordance.confidence,
        expires_at_s=affordance.lease.expires_at_s,
        evidence_refs=tuple(affordance.evidence),
        scope_evidence=scope_evidence,
    )


def source_affordance_for_candidate(
    candidate: GroundingCandidate,
    affordances: Iterable[Affordance],
) -> Affordance:
    """Resolve one typed candidate back to its unexposed source affordance."""

    source_id = candidate.source_affordance_id
    if source_id:
        match = next((item for item in affordances if item.id == source_id), None)
        if match is not None:
            return match
    match = next(
        (
            item
            for item in affordances
            if str(item.locator.get("grounding_candidate_id") or "") == candidate.candidate_id
        ),
        None,
    )
    if match is None:
        raise ValueError(f"source affordance is unavailable for candidate: {candidate.candidate_id}")
    return match


@dataclass(frozen=True)
class SemanticEntityResolver:
    """Merge only descriptors with compatible semantic, container, and geometry evidence."""

    def resolve(self, descriptors: Iterable[CandidateDescriptor]) -> tuple[UnifiedAffordance, ...]:
        groups: dict[tuple[str, str, str, str], list[CandidateDescriptor]] = {}
        for descriptor in descriptors:
            key = (
                _normalize(descriptor.role),
                _normalize(descriptor.label),
                _semantic_action(descriptor.action),
                _normalize(descriptor.container_context),
            )
            groups.setdefault(key, []).append(descriptor)
        unified: list[UnifiedAffordance] = []
        for key, items in groups.items():
            grouped = self._geometry_partitions(items)
            partitions = [
                (
                    key if len(grouped) == 1 else self._partition_key(key, partition_items),
                    partition_items,
                )
                for partition_items in grouped
            ]
            for partition_key, partition_items in partitions:
                semantic_target_id = _semantic_target_id(partition_key)
                candidates = tuple(
                    replace(item.candidate, semantic_target_id=semantic_target_id)
                    for item in sorted(partition_items, key=lambda item: item.candidate.candidate_id)
                )
                unified.append(
                    UnifiedAffordance(
                        semantic_target_id=semantic_target_id,
                        role=partition_items[0].role,
                        label=partition_items[0].label,
                        supported_actions=frozenset().union(*(item.supported_actions for item in candidates)),
                        grounding_candidates=candidates,
                    )
                )
        # Dict/list insertion order preserves the source observation's sibling
        # order, which is evidence required by ordinal tasks such as "3rd
        # checkbox". Semantic ids remain stable but are not an ordering signal.
        return tuple(unified)

    @staticmethod
    def _partition_key(
        key: tuple[str, str, str, str],
        items: list[CandidateDescriptor],
    ) -> tuple[str, str, str, str]:
        identities = sorted(
            item.candidate.source_affordance_id or item.candidate.candidate_id
            for item in items
        )
        return (*key[:3], f"{key[3]}|{'|'.join(identities)}")

    @staticmethod
    def _geometry_partitions(items: list[CandidateDescriptor]) -> list[list[CandidateDescriptor]]:
        source_counts: dict[GroundingSource, int] = {}
        for item in items:
            source = item.candidate.source
            source_counts[source] = source_counts.get(source, 0) + 1
        if all(count == 1 for count in source_counts.values()):
            # A unique semantic match across sources remains one target so a
            # material geometry disagreement can enter source arbitration.
            return [items]
        partitions: list[list[CandidateDescriptor]] = []
        for item in items:
            compatible = [
                partition
                for partition in partitions
                if all(existing.candidate.source != item.candidate.source for existing in partition)
                and all(
                    _geometry_compatible(existing.candidate, item.candidate)
                    for existing in partition
                )
            ]
            if len(compatible) == 1:
                compatible[0].append(item)
            else:
                # Zero matches means the geometry contradicts every known target.
                # Multiple matches are ambiguous and must not be guessed.
                partitions.append([item])
        return partitions


@dataclass(frozen=True)
class UnifiedRoutePlanner:
    confidence_weight: float = 0.6
    latency_weight: float = 0.2
    cost_weight: float = 0.2
    verification_weight: float = 0.4
    calibrator: RouteCalibrator = field(default_factory=RouteCalibrator)

    def plan(
        self,
        target: UnifiedAffordance | CanonicalTarget,
        *,
        action: str,
        requirements: PerceptionRequirements,
        observation: Observation | UnifiedObservation,
        available_executors: frozenset[str],
        bindings: tuple[GroundingCandidate, ...] = (),
        verifier_kinds: tuple[str, ...] = (),
        excluded_candidate_ids: frozenset[str] = frozenset(),
        environment_scope: str = "generic",
    ) -> RoutePlan:
        if (
            isinstance(target, UnifiedAffordance)
            and target.unresolved_conflicts
        ) or (
            isinstance(target, CanonicalTarget)
            and target.conflict_status
            in {ConflictStatus.MATERIAL_CONFLICT, ConflictStatus.INCONCLUSIVE}
        ):
            raise ValueError("cannot route a target with unresolved material conflicts")
        candidates = (
            target.grounding_candidates
            if isinstance(target, UnifiedAffordance)
            else tuple(
                item
                for item in bindings
                if item.semantic_target_id == target.target_id
            )
        )
        gates = tuple(
            self._gate(
                item,
                action=action,
                requirements=requirements,
                observation=observation,
                available_executors=available_executors,
                verifier_available=bool(verifier_kinds),
                excluded=item.candidate_id in excluded_candidate_ids,
            )
            for item in candidates
        )
        viable_ids = {item.candidate_id for item in gates if item.passed}
        viable = [item for item in candidates if item.candidate_id in viable_ids]
        if not viable:
            reasons = "; ".join(f"{item.candidate_id}: {', '.join(item.reasons)}" for item in gates)
            raise ValueError(f"no viable grounding route: {reasons}")
        scores = tuple(
            self._score(
                item,
                requirements,
                action=action,
                verifier_kinds=verifier_kinds,
                environment_scope=environment_scope,
            )
            for item in viable
        )
        score_by_id = {item.candidate_id: item.score for item in scores}
        ordered = sorted(viable, key=lambda item: (score_by_id[item.candidate_id], item.candidate_id))
        selected = ordered[0]
        return RoutePlan(
            semantic_target_id=target.semantic_target_id,
            selected_candidate=selected,
            viable_alternatives=tuple(ordered[1:]),
            verifier_kinds=verifier_kinds,
            hard_gate_results=gates,
            scores=tuple(sorted(scores, key=lambda item: (item.score, item.candidate_id))),
            decision_reason=f"selected viable candidate {selected.candidate_id} after deterministic hard gates",
            environment_scope=environment_scope,
            action_kind=action,
        )

    def _gate(
        self,
        candidate: GroundingCandidate,
        *,
        action: str,
        requirements: PerceptionRequirements,
        observation: Observation | UnifiedObservation,
        available_executors: frozenset[str],
        verifier_available: bool,
        excluded: bool,
    ) -> RouteGateResult:
        reasons: list[str] = []
        if excluded:
            reasons.append("candidate_excluded")
        if candidate.source not in requirements.acceptable_evidence:
            reasons.append("source_not_acceptable")
        if candidate.compatible_executor not in available_executors:
            reasons.append("executor_unavailable")
        if action not in candidate.supported_actions:
            reasons.append("action_unsupported")
        if not candidate.is_current(observation):
            reasons.append("candidate_stale")
        if candidate.expires_at_s and time() > candidate.expires_at_s:
            reasons.append("candidate_expired")
        if candidate.confidence < requirements.minimum_confidence:
            reasons.append("confidence_below_requirement")
        if not requirements.required_properties.issubset(candidate.evidence_kinds):
            reasons.append("required_evidence_missing")
        if candidate.verifier_strength < requirements.minimum_verifier_strength and not verifier_available:
            reasons.append("verifier_unavailable")
        return RouteGateResult(candidate.candidate_id, not reasons, tuple(reasons))

    def _score(
        self,
        candidate: GroundingCandidate,
        requirements: PerceptionRequirements,
        *,
        action: str,
        verifier_kinds: tuple[str, ...],
        environment_scope: str,
    ) -> RouteScore:
        preferred_rank = (
            requirements.preferred_sources.index(candidate.source)
            if candidate.source in requirements.preferred_sources
            else len(requirements.preferred_sources)
        )
        confidence_component = 1.0 - candidate.confidence
        latency_component = min(candidate.expected_latency_ms / max(requirements.latency_budget_ms, 1), 1.0)
        cost_denominator = requirements.cost_budget if requirements.cost_budget > 0 else 1.0
        cost_component = min(candidate.expected_cost / cost_denominator, 1.0)
        observed_failure = None
        if verifier_kinds:
            scope = RouteScope(
                environment_family=environment_scope,
                action_kind=action,
                source=candidate.source,
                executor=candidate.compatible_executor,
                verifier_kinds=verifier_kinds,
            )
            observed_failure = self.calibrator.failure_component(scope)
        verification_component = 0.5 if observed_failure is None else observed_failure
        score = (
            self.confidence_weight * confidence_component
            + self.latency_weight * latency_component
            + self.cost_weight * cost_component
            + self.verification_weight * verification_component
            + preferred_rank * 0.01
        )
        return RouteScore(
            candidate.candidate_id,
            round(score, 6),
            round(confidence_component, 6),
            round(latency_component, 6),
            round(cost_component, 6),
            round(verification_component, 6),
        )


def candidate_fingerprints(targets: Iterable[UnifiedAffordance]) -> dict[str, str]:
    return {
        candidate.fingerprint_key or candidate.candidate_id: candidate.target_fingerprint
        for target in targets
        for candidate in target.grounding_candidates
    }


def _semantic_target_id(key: tuple[str, str, str, str]) -> str:
    digest = hashlib.sha256("\0".join(key).encode()).hexdigest()[:12]
    readable = re.sub(r"[^a-z0-9]+", "-", key[1]).strip("-")[:32] or key[0] or "target"
    return f"semantic:{readable}:{digest}"


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _semantic_action(action: str) -> str:
    return {
        "activate": "activate",
        "click": "activate",
        "download": "activate",
        "invoke": "activate",
        "write_property": "activate",
        "fill": "type_text",
        "type": "type_text",
        "select": "select_option",
        "select_option": "select_option",
        "press": "press_key",
        "drag": "drag",
        "drop": "drag",
        "point_activate": "point_activate",
    }.get(action, action)


def _semantic_actions(action: str) -> frozenset[str]:
    semantic = _semantic_action(action)
    return frozenset({semantic, "focus"}) if semantic == "type_text" else frozenset({semantic})


def _candidate_bbox(candidate: GroundingCandidate) -> tuple[float, float, float, float] | None:
    payload = candidate.payload
    if isinstance(payload, DomGroundingPayload):
        return payload.bbox_xywh
    if isinstance(payload, VisualGroundingPayload):
        if payload.bbox_xywh is not None:
            return payload.bbox_xywh
        if payload.point_xy is not None:
            return payload.point_xy[0], payload.point_xy[1], 1.0, 1.0
    if hasattr(payload, "viewport_bbox_xywh"):
        value = getattr(payload, "viewport_bbox_xywh")
        return _optional_box(value)
    return None


def _geometry_compatible(first: GroundingCandidate, second: GroundingCandidate) -> bool:
    first_box = _candidate_bbox(first)
    second_box = _candidate_bbox(second)
    if first_box is None or second_box is None:
        return True
    first_x, first_y, first_width, first_height = first_box
    second_x, second_y, second_width, second_height = second_box
    overlap_width = min(first_x + first_width, second_x + second_width) - max(first_x, second_x)
    overlap_height = min(first_y + first_height, second_y + second_height) - max(first_y, second_y)
    return overlap_width > 0 and overlap_height > 0


def _optional_box(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    x, y, width, height = (float(item) for item in value)
    return (x, y, width, height) if width > 0 and height > 0 else None


def _optional_point(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    return float(value[0]), float(value[1])
