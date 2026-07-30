"""Neutral step-planning contracts shared by Coordinator and planners."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Protocol

from affordance_runtime.contracts import ActionContract
from affordance_runtime.immutable import freeze_json
from affordance_runtime.model_port import ModelCallRecord
from affordance_runtime.planning import PlannerProposal, PlannerProposalProvenance
from affordance_runtime.planning_request import PlanningRequest


class PlannerResponseStatus(StrEnum):
    PROPOSAL = "proposal"
    DONE = "done"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class PlannerProposalResponse:
    """Standard semantic planner response.

    This is the SAR-4 replacement contract for normal planners. It deliberately
    carries a semantic proposal, not an ActionContract.
    """

    proposal: PlannerProposal
    proposal_provenance: PlannerProposalProvenance | None = None
    reason: str = ""
    status: PlannerResponseStatus = PlannerResponseStatus.PROPOSAL

    def __post_init__(self) -> None:
        if self.status != PlannerResponseStatus.PROPOSAL:
            raise ValueError("proposal response must use proposal status")


@dataclass(frozen=True)
class PlannerDoneResponse:
    status: PlannerResponseStatus = PlannerResponseStatus.DONE
    result: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status != PlannerResponseStatus.DONE:
            raise ValueError("done response must use done status")
        object.__setattr__(self, "result", freeze_json(self.result))


@dataclass(frozen=True)
class PlannerClarificationResponse:
    question: str
    reason: str = ""
    status: PlannerResponseStatus = PlannerResponseStatus.CLARIFICATION_REQUIRED

    def __post_init__(self) -> None:
        if self.status != PlannerResponseStatus.CLARIFICATION_REQUIRED:
            raise ValueError("clarification response must use clarification status")
        if not self.question.strip():
            raise ValueError("clarification response question cannot be blank")


@dataclass(frozen=True)
class PlannerUnsupportedResponse:
    reason_code: str
    message: str = ""
    status: PlannerResponseStatus = PlannerResponseStatus.UNSUPPORTED

    def __post_init__(self) -> None:
        if self.status != PlannerResponseStatus.UNSUPPORTED:
            raise ValueError("unsupported response must use unsupported status")
        if not self.reason_code.strip():
            raise ValueError("unsupported response reason code cannot be blank")


PlannerResponse = (
    PlannerProposalResponse
    | PlannerDoneResponse
    | PlannerClarificationResponse
    | PlannerUnsupportedResponse
)


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", freeze_json(self.result))
        object.__setattr__(self, "planner_context", freeze_json(self.planner_context))


class PlannerPort(Protocol):
    def propose(
        self,
        request: PlanningRequest,
    ) -> PlannerDecision | Awaitable[PlannerDecision]: ...
