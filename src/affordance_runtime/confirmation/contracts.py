"""Typed confirmation request and user decision contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from affordance_runtime.execution.contracts import ActionIntent
from affordance_runtime.world.contracts import ActionRisk


@dataclass(frozen=True)
class ConfirmationRequest:
    confirmation_id: str
    subject_id: str
    intent: ActionIntent = field(repr=False)
    semantic_effects: tuple[str, ...]
    risk: ActionRisk
    consequences: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.confirmation_id, self.subject_id, self.summary)):
            raise ValueError("confirmation request requires request, subject, and summary")
        object.__setattr__(self, "semantic_effects", tuple(self.semantic_effects))
        object.__setattr__(self, "consequences", tuple(self.consequences))


class ConfirmationDecisionKind(StrEnum):
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class ConfirmationDecision:
    confirmation_id: str
    subject_id: str
    decision: ConfirmationDecisionKind

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ConfirmationDecisionKind):
            raise TypeError("decision must be a ConfirmationDecisionKind")
        if not self.confirmation_id.strip() or not self.subject_id.strip():
            raise ValueError("confirmation decision requires request and subject identity")

    def matches(self, request: ConfirmationRequest) -> bool:
        return self.confirmation_id == request.confirmation_id and self.subject_id == request.subject_id
