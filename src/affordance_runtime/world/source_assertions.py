"""Rule-first arbitration for multi-source state assertions."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Iterable

from affordance_runtime.actions.contracts import Observation
from affordance_runtime.actions.grounding import (
    ActivePerceptionRequest,
    AssertionArbitration,
    AssertionDecision,
    AssertionResolutionStatus,
    GroundingSource,
    SourceAssertion,
    UnifiedAffordance,
)
from affordance_runtime.surfaces.dom.browser_session import BrowserSnapshot

_DOM_STATE_PROPERTIES = frozenset(
    {"checked", "enabled", "focused", "selected", "value", "visible"}
)
_DEVICE_STATE_PROPERTIES = frozenset(
    {"device_state", "power", "sensor", "status", "temperature"}
)
_VISUAL_PROPERTIES = frozenset(
    {"appearance", "bbox", "color", "geometry", "inside", "position", "shape"}
)


@dataclass(frozen=True)
class SourceAssertionArbiter:
    """Resolve claims without treating cross-source confidence as comparable."""

    minimum_confidence: float = 0.0
    max_sources_per_request: int = 2

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("assertion minimum confidence must be within [0, 1]")
        if self.max_sources_per_request < 1:
            raise ValueError("active perception must request at least one bounded source")

    def arbitrate(
        self,
        assertions: Iterable[SourceAssertion],
        observation: Observation,
        *,
        available_sources: frozenset[GroundingSource] = frozenset(),
        observation_budget: int = 1,
    ) -> AssertionArbitration:
        if observation_budget < 0:
            raise ValueError("assertion observation budget cannot be negative")
        groups: dict[tuple[str, str], list[SourceAssertion]] = {}
        for assertion in assertions:
            groups.setdefault((assertion.entity_key, assertion.property_key), []).append(assertion)

        decisions: list[AssertionDecision] = []
        requests: list[ActivePerceptionRequest] = []
        remaining_budget = observation_budget
        for (entity_key, property_key), raw_group in sorted(groups.items()):
            group = tuple(sorted(raw_group, key=lambda item: item.assertion_id))
            valid = tuple(item for item in group if self._usable(item, observation))
            material = any(item.material for item in group)
            if not valid:
                decision, request = self._unresolved(
                    entity_key,
                    property_key,
                    group,
                    material=material,
                    reason="all source assertions are stale, expired, or below confidence",
                    available_sources=available_sources,
                    remaining_budget=remaining_budget,
                    preferred_sources=self._preferred_sources(property_key),
                    conflicting=False,
                )
            else:
                decision, request = self._resolve_valid(
                    entity_key,
                    property_key,
                    group,
                    valid,
                    material=material,
                    available_sources=available_sources,
                    remaining_budget=remaining_budget,
                )
            decisions.append(decision)
            if request is not None:
                requests.append(request)
                remaining_budget -= request.max_observations
        return AssertionArbitration(tuple(decisions), tuple(requests))

    def _resolve_valid(
        self,
        entity_key: str,
        property_key: str,
        raw_group: tuple[SourceAssertion, ...],
        valid: tuple[SourceAssertion, ...],
        *,
        material: bool,
        available_sources: frozenset[GroundingSource],
        remaining_budget: int,
    ) -> tuple[AssertionDecision, ActivePerceptionRequest | None]:
        normalized = {_normalized_value(item) for item in valid}
        if len(normalized) == 1:
            accepted = self._select_without_cross_source_confidence(valid, property_key)
            return (
                AssertionDecision(
                    entity_key,
                    property_key,
                    AssertionResolutionStatus.ACCEPTED,
                    raw_group,
                    accepted_assertion_id=accepted.assertion_id,
                    reason="independent current assertions agree after normalization",
                    material=material,
                ),
                None,
            )

        preferred = self._preferred_sources(property_key)
        best_rank = min(self._source_rank(item.source, preferred) for item in valid)
        authoritative = tuple(
            item for item in valid if self._source_rank(item.source, preferred) == best_rank
        )
        authoritative_values = {_normalized_value(item) for item in authoritative}
        if preferred and len(authoritative_values) == 1:
            accepted = self._select_without_cross_source_confidence(authoritative, property_key)
            return (
                AssertionDecision(
                    entity_key,
                    property_key,
                    AssertionResolutionStatus.ACCEPTED,
                    raw_group,
                    accepted_assertion_id=accepted.assertion_id,
                    reason=f"property authority selected {accepted.source.value} evidence",
                    material=material,
                ),
                None,
            )
        return self._unresolved(
            entity_key,
            property_key,
            raw_group,
            material=material,
            reason="material current assertions disagree at the same authority level",
            available_sources=available_sources,
            remaining_budget=remaining_budget,
            preferred_sources=preferred or tuple(dict.fromkeys(item.source for item in authoritative)),
            conflicting=True,
        )

    def _unresolved(
        self,
        entity_key: str,
        property_key: str,
        assertions: tuple[SourceAssertion, ...],
        *,
        material: bool,
        reason: str,
        available_sources: frozenset[GroundingSource],
        remaining_budget: int,
        preferred_sources: tuple[GroundingSource, ...],
        conflicting: bool,
    ) -> tuple[AssertionDecision, ActivePerceptionRequest | None]:
        requested = tuple(
            source
            for source in preferred_sources
            if not available_sources or source in available_sources
        )[: self.max_sources_per_request]
        if not requested:
            requested = tuple(
                dict.fromkeys(
                    item.source
                    for item in assertions
                    if not available_sources or item.source in available_sources
                )
            )[: self.max_sources_per_request]
        if material and remaining_budget > 0 and requested:
            request = ActivePerceptionRequest(
                entity_key,
                property_key,
                requested,
                reason,
                max_observations=1,
            )
            return (
                AssertionDecision(
                    entity_key,
                    property_key,
                    AssertionResolutionStatus.REOBSERVE,
                    assertions,
                    reason=reason,
                    material=material,
                ),
                request,
            )
        status = (
            AssertionResolutionStatus.CONFLICT
            if material and assertions and conflicting
            else AssertionResolutionStatus.INCONCLUSIVE
        )
        return (
            AssertionDecision(
                entity_key,
                property_key,
                status,
                assertions,
                reason=reason,
                material=material,
            ),
            None,
        )

    def _usable(self, assertion: SourceAssertion, observation: Observation) -> bool:
        if not assertion.is_current(observation) or assertion.confidence < self.minimum_confidence:
            return False
        try:
            _normalized_value(assertion)
        except (TypeError, ValueError):
            return False
        return True

    def _select_without_cross_source_confidence(
        self,
        assertions: tuple[SourceAssertion, ...],
        property_key: str,
    ) -> SourceAssertion:
        preferred = self._preferred_sources(property_key)
        by_source: dict[GroundingSource, list[SourceAssertion]] = {}
        for assertion in assertions:
            by_source.setdefault(assertion.source, []).append(assertion)
        source = min(by_source, key=lambda item: (self._source_rank(item, preferred), item.value))
        # Confidence is compared only within the selected source's declared
        # source-local semantics, never between DOM, visual, WoT, or API.
        return min(
            by_source[source],
            key=lambda item: (-item.confidence, item.assertion_id),
        )

    @staticmethod
    def _source_rank(
        source: GroundingSource,
        preferred: tuple[GroundingSource, ...],
    ) -> int:
        if preferred in {
            (GroundingSource.WOT, GroundingSource.API),
            (GroundingSource.VISUAL, GroundingSource.SOM, GroundingSource.SVG),
        }:
            return 0 if source in preferred else 1
        return preferred.index(source) if source in preferred else len(preferred)

    @staticmethod
    def _preferred_sources(property_key: str) -> tuple[GroundingSource, ...]:
        property_name = property_key.casefold().strip()
        if property_name in _DOM_STATE_PROPERTIES:
            return (GroundingSource.DOM, GroundingSource.ACCESSIBILITY)
        if property_name in _DEVICE_STATE_PROPERTIES:
            return (GroundingSource.WOT, GroundingSource.API)
        if property_name in _VISUAL_PROPERTIES:
            return (GroundingSource.VISUAL, GroundingSource.SOM, GroundingSource.SVG)
        return ()


@dataclass(frozen=True)
class SourceAssertionOrchestrator:
    arbiter: SourceAssertionArbiter = SourceAssertionArbiter()

    def reconcile(
        self,
        targets: Iterable[UnifiedAffordance],
        assertions: Iterable[SourceAssertion],
        observation: Observation,
        *,
        available_sources: frozenset[GroundingSource] = frozenset(),
        observation_budget: int = 1,
    ) -> tuple[tuple[UnifiedAffordance, ...], AssertionArbitration]:
        arbitration = self.arbiter.arbitrate(
            assertions,
            observation,
            available_sources=available_sources,
            observation_budget=observation_budget,
        )
        decisions_by_entity: dict[str, list[AssertionDecision]] = {}
        for decision in arbitration.decisions:
            decisions_by_entity.setdefault(decision.entity_key, []).append(decision)

        reconciled: list[UnifiedAffordance] = []
        for target in targets:
            state = dict(target.accepted_state)
            conflicts = list(target.unresolved_conflicts)
            for decision in decisions_by_entity.get(target.semantic_target_id, []):
                accepted = decision.accepted_assertion
                if decision.status == AssertionResolutionStatus.ACCEPTED and accepted is not None:
                    state[decision.property_key] = _state_value(accepted.value)
                elif decision.material:
                    conflicts.append(f"{decision.property_key}:{decision.status.value}")
            reconciled.append(
                replace(
                    target,
                    accepted_state=tuple(sorted(state.items())),
                    unresolved_conflicts=tuple(dict.fromkeys(conflicts)),
                )
            )
        return tuple(reconciled), arbitration

    def reconcile_snapshot(
        self,
        snapshot: BrowserSnapshot,
        assertions: Iterable[SourceAssertion],
        *,
        available_sources: frozenset[GroundingSource] = frozenset(),
        observation_budget: int = 1,
    ) -> BrowserSnapshot:
        claims = tuple(assertions)
        targets, arbitration = self.reconcile(
            snapshot.unified_affordances,
            claims,
            snapshot.observation,
            available_sources=available_sources,
            observation_budget=observation_budget,
        )
        return replace(
            snapshot,
            unified_affordances=targets,
            source_assertions=claims,
            assertion_decisions=arbitration.decisions,
            active_perception_requests=arbitration.active_perception_requests,
        )


def _normalized_value(assertion: SourceAssertion) -> tuple[str, str, str]:
    value_type = assertion.value_type.casefold().strip()
    unit = assertion.unit.casefold().strip()
    value = assertion.value
    if value_type in {"bool", "boolean"}:
        if isinstance(value, str):
            token = value.casefold().strip()
            if token in {"1", "checked", "on", "true", "yes"}:
                normalized: Any = True
            elif token in {"0", "false", "no", "off", "unchecked"}:
                normalized = False
            else:
                raise ValueError("invalid boolean assertion")
        else:
            normalized = bool(value)
    elif value_type in {"float", "int", "number"}:
        normalized = float(value)
    elif value_type in {"str", "string", "text"}:
        normalized = " ".join(str(value).casefold().split())
    else:
        normalized = value
    return value_type, unit, json.dumps(normalized, sort_keys=True, default=str)


def _state_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)
