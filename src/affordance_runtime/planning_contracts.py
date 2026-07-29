"""Neutral step-planning contracts shared by Coordinator and planners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Protocol

from affordance_runtime.contracts import ActionContract
from affordance_runtime.model_port import ModelCallRecord
from affordance_runtime.planning import PlannerProposal, PlannerProposalProvenance
from affordance_runtime.planning_request import PlanningRequest


@dataclass(frozen=True)
class PlannerDecision:
    """Authority-free planner output; Coordinator owns validation and commit."""

    contract: ActionContract | None = None
    proposal: PlannerProposal | None = None
    proposal_provenance: PlannerProposalProvenance | None = None
    done: bool = False
    result: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    planner_context: dict[str, Any] = field(default_factory=dict)
    model_call: ModelCallRecord | None = None


class PlannerPort(Protocol):
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerDecision | Awaitable[PlannerDecision]: ...
