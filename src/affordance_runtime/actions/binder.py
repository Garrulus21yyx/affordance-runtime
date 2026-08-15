"""Bind semantic intent to a current runtime-private surface route."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from affordance_runtime.actions.route_selector import RouteSelectionCode, RouteSelector
from affordance_runtime.actions.space_contracts import AdmittedActionSelection
from affordance_runtime.execution.contracts import ActionIntent, BoundActionRequest
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.world.contracts import (
    ActionBinding,
    WorldObservation,
)


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
        tool_call_id: str = "",
    ) -> BoundActionRequest:
        if not context_id.strip():
            raise BindingError("binding requires the accepted context identity")
        if selection.observation_id != observation.observation_id:
            raise BindingError("selected option belongs to another observation")
        route = self.route_selector.select(
            selection,
            observation,
            excluded_binding_ids=excluded_binding_ids,
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
            tool_call_id=tool_call_id,
        )

    def bind_for_execution(
        self,
        selection: AdmittedActionSelection,
        observation: WorldObservation,
        context_id: str,
        task: TaskGoal,
        *,
        selected_binding: ActionBinding | None = None,
        excluded_binding_ids: frozenset[str] = frozenset(),
        tool_call_id: str = "",
    ) -> BoundActionRequest:
        """Close the executable request, including its post-action evidence contract."""

        from affordance_runtime.evaluation.action_verification import (
            derive_action_verification_obligations,
            observation_needs_for_verification,
        )

        request = self.bind(
            selection,
            observation,
            context_id,
            selected_binding=selected_binding,
            excluded_binding_ids=excluded_binding_ids,
            tool_call_id=tool_call_id,
        )
        needs = observation_needs_for_verification(
            request.request_id,
            derive_action_verification_obligations(task, request, observation),
        )
        return replace(request, verification_needs=needs)
