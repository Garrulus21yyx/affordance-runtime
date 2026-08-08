"""Bind semantic intent to a current runtime-private surface route."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from time import time

from affordance_runtime.execution.contracts import ActionIntent, BoundActionRequest
from affordance_runtime.schema_digest import schema_digest
from affordance_runtime.world.contracts import ActionBinding, AdmittedActionSelection, WorldObservation


class BindingError(ValueError):
    pass


@dataclass(frozen=True)
class ActionBinder:
    def bind(
        self,
        selection: AdmittedActionSelection,
        observation: WorldObservation,
    ) -> BoundActionRequest:
        if selection.observation_id != observation.observation_id:
            raise BindingError("selected option belongs to another observation")
        bindings = [
            binding
            for binding in observation.bindings
            if binding.binding_id in selection.eligible_binding_ids
            and binding.target_id == selection.target_id
            and selection.semantic_action == binding.semantic_action
            and binding.effect_category == selection.effect_category
            and binding.semantic_effects == selection.semantic_effects
            and schema_digest(binding.parameter_schema) == selection.schema_digest
            and _risk_rank(binding.risk) <= _risk_rank(selection.risk)
            and binding.observation_barrier == selection.observation_barrier
            and _binding_current(binding, observation)
        ]
        if not bindings:
            raise BindingError("no current binding belongs to the admitted action option")
        binding = max(bindings, key=lambda item: (item.confidence, -item.cost))
        intent = ActionIntent(selection.semantic_action, selection.target_id, dict(selection.parameters))
        return BoundActionRequest(
            f"request:{uuid.uuid4().hex}",
            observation.observation_id,
            intent,
            selection,
            binding,
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
    source = next((item for item in observation.sources if item.surface == binding.surface), None)
    return bool(
        source
        and binding.source_observation_id == source.observation_id
        and binding.source_revision == source.revision
    )
