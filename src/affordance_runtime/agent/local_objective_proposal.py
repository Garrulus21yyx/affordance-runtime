"""Post-observation LocalObjective proposal boundary.

The proposal is authority-free.  AgentLoop validates its context identity and
installs the value through the existing LocalObjective lifecycle owner.  It is
not an AgentDecision and is never projected as an action tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
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


@dataclass(frozen=True)
class LocalObjectiveNotRequired:
    context_id: str

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("not-required objective outcome requires current context scope")


@dataclass(frozen=True)
class LocalObjectiveNeedsInput:
    context_id: str
    question: str
    requested_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.context_id.strip() or not self.question.strip() or len(self.question) > 1_000:
            raise ValueError("objective input request requires context and a bounded question")
        fields = tuple(self.requested_fields)
        if (
            len(fields) > 32
            or len(fields) != len(set(fields))
            or any(not item.strip() or len(item) > 120 for item in fields)
        ):
            raise ValueError("objective input request fields must be bounded and unique")
        object.__setattr__(self, "requested_fields", fields)


class LocalObjectiveUnsupportedReason(StrEnum):
    NO_RESOLVABLE_OBJECTIVE = "no_resolvable_objective"
    TASK_SEMANTICS_UNSUPPORTED = "task_semantics_unsupported"


@dataclass(frozen=True)
class LocalObjectiveUnsupported:
    context_id: str
    reason_code: LocalObjectiveUnsupportedReason
    reason: str

    def __post_init__(self) -> None:
        if not self.context_id.strip() or not self.reason.strip() or len(self.reason) > 500:
            raise ValueError("unsupported objective outcome requires context and a bounded reason")
        object.__setattr__(
            self,
            "reason_code",
            LocalObjectiveUnsupportedReason(self.reason_code),
        )


LocalObjectiveResolvedOutcome: TypeAlias = (
    LocalObjectiveProposal
    | LocalObjectiveNotRequired
    | LocalObjectiveNeedsInput
    | LocalObjectiveUnsupported
)
LocalObjectiveProposalOutcome: TypeAlias = LocalObjectiveResolvedOutcome | PolicyFailure


class LocalObjectiveProposalPort(Protocol):
    async def propose(self, context: AgentContext) -> LocalObjectiveProposalOutcome: ...
