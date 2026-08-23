"""Pure deterministic selection of one current private execution route."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import time

from affordance_runtime.actions.space_contracts import AdmittedActionSelection
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.world.contracts import (
    ActionBinding,
    WorldObservation,
)


class RouteSelectionCode(StrEnum):
    SELECTED = "selected"
    NO_CURRENT_ROUTE = "no_current_route"
    ROUTE_CONFLICT = "route_conflict"


@dataclass(frozen=True)
class RouteSelectionResult:
    code: RouteSelectionCode
    binding: ActionBinding | None = None

    def __post_init__(self) -> None:
        if (self.code is RouteSelectionCode.SELECTED) != isinstance(self.binding, ActionBinding):
            raise ValueError("route result must contain exactly one typed outcome")


@dataclass(frozen=True)
class RouteSelector:
    def select(
        self,
        selection: AdmittedActionSelection,
        observation: WorldObservation,
        *,
        excluded_binding_ids: frozenset[str] = frozenset(),
    ) -> RouteSelectionResult:
        candidates = tuple(
            binding
            for binding in observation.bindings
            if binding.binding_id not in excluded_binding_ids and _equivalent_current(binding, selection, observation)
        )
        ids = tuple(item.binding_id for item in candidates)
        if len(ids) != len(set(ids)):
            return RouteSelectionResult(RouteSelectionCode.ROUTE_CONFLICT)
        if not candidates:
            return RouteSelectionResult(RouteSelectionCode.NO_CURRENT_ROUTE)
        chosen = min(candidates, key=lambda item: (-item.confidence, item.cost, item.binding_id))
        return RouteSelectionResult(RouteSelectionCode.SELECTED, chosen)


def _equivalent_current(
    binding: ActionBinding,
    selection: AdmittedActionSelection,
    observation: WorldObservation,
) -> bool:
    return bool(
        binding.binding_id in selection.eligible_binding_ids
        and binding.target_id == selection.target_id
        and binding.semantic_action == selection.semantic_action
        and binding.effect_category == selection.effect_category
        and binding.semantic_effects == selection.semantic_effects
        and schema_digest(binding.parameter_schema) == selection.schema_digest
        and _risk_rank(binding.risk) <= _risk_rank(selection.risk)
        and binding.observation_barrier == selection.observation_barrier
        and binding.destination_required == selection.destination_required
        and (
            selection.destination_id in binding.eligible_destination_ids
            if selection.destination_id
            else binding.eligible_destination_ids == selection.eligible_destination_ids
        )
        and binding.verification_contract_digest == selection.verification_contract_digest
        and _binding_current(binding, observation)
    )


def _risk_rank(risk: object) -> int:
    return ("low", "medium", "high", "irreversible").index(str(risk))


def _binding_current(binding: ActionBinding, observation: WorldObservation) -> bool:
    if (
        binding.world_observation_id != observation.observation_id
        or not binding.target_fingerprint
        or (binding.expires_at_s and time() > binding.expires_at_s)
    ):
        return False
    if not observation.sources:
        return binding.source_observation_id == observation.observation_id
    source = next(
        (item for item in observation.sources if item.observation_id == binding.source_observation_id),
        None,
    )
    return bool(source and binding.surface == source.surface and binding.source_revision == source.revision)
