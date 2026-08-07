"""Bind semantic intent to a current runtime-private surface route."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from time import time

from affordance_runtime.execution.contracts import ActionIntent, BoundActionRequest
from affordance_runtime.world.contracts import WorldObservation


class BindingError(ValueError):
    pass


@dataclass(frozen=True)
class ActionBinder:
    def bind(self, intent: ActionIntent, observation: WorldObservation) -> BoundActionRequest:
        bindings = [
            binding
            for binding in observation.bindings
            if binding.target_id == intent.target_id
            and intent.semantic_action == binding.semantic_action
            and binding.world_observation_id == observation.observation_id
            and (not binding.expires_at_s or time() <= binding.expires_at_s)
        ]
        if not bindings:
            raise BindingError("no current binding supports the semantic intent")
        binding = max(bindings, key=lambda item: (item.confidence, -item.cost))
        return BoundActionRequest(f"request:{uuid.uuid4().hex}", observation.observation_id, intent, binding)
