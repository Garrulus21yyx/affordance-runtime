"""Parent-agent and benchmark adapters for the semantic planner boundary."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Mapping, Protocol

from affordance_runtime.generalist_planner import PlannerLimits
from affordance_runtime.planner_context import PlannerContextBuilder
from affordance_runtime.planning import PlannerProposal, PlannerProposalProvenance, PlannerProposalSource
from affordance_runtime.planning_contracts import PlannerProposalResponse, PlannerResponse
from affordance_runtime.planning_request import PlanningRequest


class ParentProposalSource(Protocol):
    def propose(
        self,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | Awaitable[Mapping[str, Any]]: ...


class PlannerContextBuilderPort(Protocol):
    def build(self, request: PlanningRequest) -> Any: ...


@dataclass(frozen=True)
class _ParentProposalResult:
    proposal: PlannerProposal
    proposal_provenance: PlannerProposalProvenance
    reason: str
    planner_context: dict[str, Any]


@dataclass
class ParentAgentPlannerAdapter:
    """Give a parent only semantic context/proposals, never primitive execution."""

    source: ParentProposalSource
    limits: PlannerLimits = field(default_factory=PlannerLimits)
    accepted_knowledge: tuple[str, ...] = ()
    context_builder: PlannerContextBuilderPort | None = None

    async def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerResponse:
        decision = await self._propose_result(request)
        return PlannerProposalResponse(
            proposal=decision.proposal,
            proposal_provenance=decision.proposal_provenance,
            reason=decision.reason,
        )

    async def _propose_result(self, request: PlanningRequest) -> _ParentProposalResult:
        context = self._context_builder().build(request)
        value = self.source.propose(context.model_dump(mode="json"))
        payload = await value if inspect.isawaitable(value) else value
        proposal = PlannerProposal.model_validate(payload)
        return _ParentProposalResult(
            proposal=proposal,
            proposal_provenance=PlannerProposalProvenance(
                source=PlannerProposalSource.PARENT_AGENT,
                producer_id=type(self.source).__name__,
                profile_id="parent-agent-adapter",
            ),
            reason=proposal.reason,
            planner_context={
                "adapter": "parent_agent",
                "task_revision": context.task_revision,
                "state_version": context.state_version,
                "snapshot_id": context.snapshot_id,
                "affordance_count": len(context.affordances),
                "granted_capabilities": list(context.granted_capabilities),
            },
        )

    def _context_builder(self) -> PlannerContextBuilderPort:
        if self.context_builder is not None:
            return self.context_builder
        return PlannerContextBuilder(
            limits=self.limits,
            accepted_knowledge=self.accepted_knowledge,
        )
