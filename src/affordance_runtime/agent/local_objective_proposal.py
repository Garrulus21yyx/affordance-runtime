"""Post-observation LocalObjective proposal boundary.

The proposal is authority-free.  AgentLoop validates its context identity and
installs the value through the existing LocalObjective lifecycle owner.  It is
not an AgentDecision and is never projected as an action tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeAlias

from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.model_boundary.context import AgentContext
from affordance_runtime.task.local_objective import LocalObjective


@dataclass(frozen=True)
class LocalObjectiveProposal:
    context_id: str
    objective: LocalObjective

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("local objective proposal requires context identity")
        if not isinstance(self.objective, LocalObjective):
            raise TypeError("local objective proposal variant is unsupported")


LocalObjectiveProposalOutcome: TypeAlias = LocalObjectiveProposal | PolicyFailure


class LocalObjectiveProposalPort(Protocol):
    async def propose(self, context: AgentContext) -> LocalObjectiveProposalOutcome: ...
