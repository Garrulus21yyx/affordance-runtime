"""Parent-agent and benchmark adapters for the semantic planner boundary."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Mapping, Protocol

from affordance_runtime.browser_session import BrowserSnapshot
from affordance_runtime.coordinator import PlannerDecision
from affordance_runtime.generalist_planner import PlannerLimits, build_planner_context
from affordance_runtime.planning import PlannerProposal, PlannerProposalProvenance, PlannerProposalSource
from affordance_runtime.runtime import TaskEnvelope
from affordance_runtime.state_kernel import StateKernel


class ParentProposalSource(Protocol):
    def propose(
        self,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | Awaitable[Mapping[str, Any]]: ...


@dataclass
class ParentAgentPlannerAdapter:
    """Give a parent only semantic context/proposals, never primitive execution."""

    source: ParentProposalSource
    limits: PlannerLimits = field(default_factory=PlannerLimits)
    accepted_knowledge: tuple[str, ...] = ()

    async def propose(
        self,
        envelope: TaskEnvelope,
        state: StateKernel,
        snapshot: BrowserSnapshot,
    ) -> PlannerDecision:
        context = build_planner_context(
            envelope,
            state,
            snapshot,
            limits=self.limits,
            accepted_knowledge=self.accepted_knowledge,
        )
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
