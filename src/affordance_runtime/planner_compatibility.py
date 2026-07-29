"""Compatibility seam for legacy three-argument Step Planner implementations."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Protocol, TypeAlias, cast

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel


class LegacyPlannerPort(Protocol):
    def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision | Awaitable[PlannerDecision]: ...


class RequestPlannerPort(Protocol):
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerDecision | Awaitable[PlannerDecision]: ...


PlannerCompatibilityPort: TypeAlias = RequestPlannerPort | LegacyPlannerPort


def propose_with_planner_compatibility(
    planner: PlannerCompatibilityPort,
    *,
    request: PlanningRequest | None,
    envelope: TaskEnvelope,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlannerDecision | Awaitable[PlannerDecision]:
    """Invoke the request-only planner boundary, falling back to legacy adapters.

    The fallback exists only for compatibility planners that still need raw
    snapshot/affordance objects to create legacy ActionContracts. New standard
    planners should implement ``propose(request)``.
    """

    if request is not None and _planner_accepts_request_only(planner):
        return cast(Any, planner).propose(request)
    return cast(Any, planner).propose(envelope, state, snapshot)


def propose_with_runtime_projection(
    planner: PlannerCompatibilityPort,
    *,
    envelope: TaskEnvelope,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlannerDecision | Awaitable[PlannerDecision]:
    request = None
    if envelope.task_spec is not None:
        request = PlanningRequestBuilder().build(envelope, state, snapshot)
    return propose_with_planner_compatibility(
        planner,
        request=request,
        envelope=envelope,
        state=state,
        snapshot=snapshot,
    )


def _planner_accepts_request_only(planner: PlannerCompatibilityPort) -> bool:
    signature = inspect.signature(planner.propose)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
    ]
    return len(positional) == 1
