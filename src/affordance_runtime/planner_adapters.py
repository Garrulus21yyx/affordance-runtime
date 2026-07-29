"""Parent-agent and benchmark adapters for the semantic planner boundary."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Mapping, Protocol

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.generalist_planner import PlannerLimits
from affordance_runtime.planner_context import PlannerContextBuilder
from affordance_runtime.planning import PlannerProposal, PlannerProposalProvenance, PlannerProposalSource
from affordance_runtime.planning_contracts import PlannerDecision
from affordance_runtime.planning_request import PlanningRequest
from affordance_runtime.planning_request_builder import PlanningRequestBuilder, PlanningRequestLimits
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel


class ParentProposalSource(Protocol):
    def propose(
        self,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | Awaitable[Mapping[str, Any]]: ...


class PlanningRequestBuilderPort(Protocol):
    def build(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlanningRequest: ...


class PlannerContextBuilderPort(Protocol):
    def build(
        self,
        request: PlanningRequest,
        state: StateKernel | None = None,
        snapshot: BrowserSnapshot | None = None,
    ) -> Any: ...


@dataclass
class ParentAgentPlannerAdapter:
    """Give a parent only semantic context/proposals, never primitive execution."""

    source: ParentProposalSource
    limits: PlannerLimits = field(default_factory=PlannerLimits)
    accepted_knowledge: tuple[str, ...] = ()
    planning_request_builder: PlanningRequestBuilderPort | None = None
    context_builder: PlannerContextBuilderPort | None = None

    async def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        request = self._planning_request_builder().build(envelope, state, snapshot)
        context = self._context_builder().build(request)
        value = self.source.propose(context.model_dump(mode="json"))
        payload = await value if inspect.isawaitable(value) else value
        proposal = PlannerProposal.model_validate(payload)
        return PlannerDecision(
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

    def _planning_request_builder(self) -> PlanningRequestBuilderPort:
        if self.planning_request_builder is not None:
            return self.planning_request_builder
        return PlanningRequestBuilder(
            limits=PlanningRequestLimits(
                max_steps=self.limits.max_steps,
                max_observations=self.limits.max_observations,
                max_recoveries=self.limits.max_recoveries,
                max_effectful_actions=self.limits.max_effectful_actions,
                max_affordances=self.limits.max_affordances,
                max_artifact_refs=self.limits.max_artifact_refs,
            ),
            accepted_knowledge=self.accepted_knowledge,
        )

    def _context_builder(self) -> PlannerContextBuilderPort:
        if self.context_builder is not None:
            return self.context_builder
        return PlannerContextBuilder(
            limits=self.limits,
            accepted_knowledge=self.accepted_knowledge,
        )
