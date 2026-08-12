"""Bind semantic intent to a current runtime-private surface route."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from affordance_runtime.execution.contracts import ActionIntent, BoundActionRequest
from affordance_runtime.world.contracts import ActionBinding, AdmittedActionSelection, WorldObservation
from affordance_runtime.world.route_selector import RouteSelectionCode, RouteSelector


class BindingError(ValueError):
    pass


@dataclass(frozen=True)
class ActionBinder:
    route_selector: RouteSelector = RouteSelector()

    def bind(
        self,
        selection: AdmittedActionSelection,
        observation: WorldObservation,
        context_id: str,
        *,
        selected_binding: ActionBinding | None = None,
        excluded_binding_ids: frozenset[str] = frozenset(),
    ) -> BoundActionRequest:
        if not context_id.strip():
            raise BindingError("binding requires the accepted context identity")
        if selection.observation_id != observation.observation_id:
            raise BindingError("selected option belongs to another observation")
        route = self.route_selector.select(
            selection, observation, excluded_binding_ids=excluded_binding_ids,
        )
        binding = selected_binding or route.binding
        if route.code is not RouteSelectionCode.SELECTED or binding is None:
            raise BindingError("no current binding belongs to the admitted action option")
        if selected_binding is not None and selected_binding != route.binding:
            raise BindingError("selected binding is not the deterministic current route")
        intent = ActionIntent(
            selection.semantic_action,
            selection.target_id,
            dict(selection.parameters),
            selection.destination_id,
        )
        return BoundActionRequest(
            f"request:{uuid.uuid4().hex}",
            context_id,
            observation.observation_id,
            intent,
            selection,
            binding,
        )
