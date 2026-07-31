"""Compatibility seam for legacy three-argument Step Planner implementations."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Protocol, TypeAlias, cast

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.planning_contracts import (
    PlannerClarificationResponse,
    PlannerDecision,
    PlannerDoneResponse,
    PlannerProposalResponse,
    PlannerResponse,
    PlannerUnsupportedResponse,
)
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder
from affordance_runtime.runtime import RunRequest
from affordance_runtime.state_kernel import StateKernel


class LegacyPlannerPort(Protocol):
    def propose(
        self,
        envelope: RunRequest,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision | Awaitable[PlannerDecision]: ...


class RequestPlannerPort(Protocol):
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerResponse | Awaitable[PlannerResponse]: ...


PlannerCompatibilityPort: TypeAlias = RequestPlannerPort | LegacyPlannerPort


def propose_with_planner_compatibility(
    planner: PlannerCompatibilityPort,
    *,
    request: PlanningRequest | None,
    envelope: RunRequest,
    state: StateKernel,
    snapshot: BrowserSnapshot,
) -> PlannerDecision | Awaitable[PlannerDecision]:
    """Invoke the request-only planner boundary, falling back to legacy adapters.

    The fallback exists only for compatibility planners that still need raw
    snapshot/affordance objects to create legacy ActionContracts. New standard
    planners should implement ``propose(request)``.
    """

    if request is not None and _planner_accepts_request_only(planner):
        return _resolve_planner_compatibility_response(cast(Any, planner).propose(request))
    return cast(Any, planner).propose(envelope, state, snapshot)


def propose_with_runtime_projection(
    planner: PlannerCompatibilityPort,
    *,
    envelope: RunRequest,
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


def planner_response_to_decision(response: PlannerResponse) -> PlannerDecision:
    if isinstance(response, PlannerProposalResponse):
        return PlannerDecision(
            proposal=response.proposal,
            proposal_provenance=response.proposal_provenance,
            reason=response.reason,
        )
    if isinstance(response, PlannerDoneResponse):
        return PlannerDecision(done=True, result=response.result, reason=response.reason)
    if isinstance(response, PlannerClarificationResponse):
        return PlannerDecision(done=False, reason=response.question)
    if isinstance(response, PlannerUnsupportedResponse):
        return PlannerDecision(
            done=False,
            reason=response.message or response.reason_code,
            planner_context={"unsupported_reason_code": response.reason_code},
        )
    raise TypeError(f"unsupported planner response: {type(response).__name__}")


def _resolve_planner_compatibility_response(
    value: PlannerResponse | Awaitable[PlannerResponse],
) -> PlannerDecision | Awaitable[PlannerDecision]:
    if inspect.isawaitable(value):
        return _await_planner_response(value)
    return planner_response_to_decision(value)


async def _await_planner_response(value: Awaitable[PlannerResponse]) -> PlannerDecision:
    return planner_response_to_decision(await value)
