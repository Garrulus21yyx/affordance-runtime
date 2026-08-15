"""Closed model-control capabilities used during Runtime composition."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class DecisionCapability(StrEnum):
    """One member of the action-policy decision algebra."""

    SELECT_ACTION = "select_action"
    REQUEST_EVIDENCE = "request_evidence"
    REQUEST_ACTION_PAGE = "request_action_page"
    ASK_USER = "ask_user"
    PROPOSE_DONE = "propose_done"
    WAIT = "wait"
    ABORT = "abort"


ALL_DECISION_CAPABILITIES = frozenset(DecisionCapability)
TOOL_ACTION_DECISION_CAPABILITIES = frozenset(
    {
        DecisionCapability.SELECT_ACTION,
        DecisionCapability.REQUEST_EVIDENCE,
        DecisionCapability.REQUEST_ACTION_PAGE,
    }
)
GROUNDED_ACTION_DECISION_CAPABILITIES = ALL_DECISION_CAPABILITIES - {
    DecisionCapability.PROPOSE_DONE,
}
STRUCTURED_PACKAGE_DECISION_CAPABILITIES = ALL_DECISION_CAPABILITIES


def normalize_decision_capabilities(
    values: object,
    *,
    field_name: str,
) -> frozenset[DecisionCapability]:
    """Reject stringly or open-ended capability declarations."""

    if isinstance(values, str):
        raise TypeError(f"{field_name} must contain typed DecisionCapability values")
    if not isinstance(values, Iterable):
        raise TypeError(f"{field_name} must be an iterable of DecisionCapability values")
    normalized = frozenset(values)
    if any(not isinstance(item, DecisionCapability) for item in normalized):
        raise TypeError(f"{field_name} must contain typed DecisionCapability values")
    return frozenset(item for item in normalized if isinstance(item, DecisionCapability))


@dataclass(frozen=True)
class UnsupportedComposition:
    """Typed, deterministic evidence for a capability-incompatible composition."""

    required_decisions: frozenset[DecisionCapability]
    supported_decisions: frozenset[DecisionCapability]
    missing_decisions: frozenset[DecisionCapability]

    def __post_init__(self) -> None:
        if self.missing_decisions != self.required_decisions - self.supported_decisions:
            raise ValueError("unsupported composition evidence is inconsistent")
        if not self.missing_decisions:
            raise ValueError("unsupported composition requires at least one missing decision")


class UnsupportedCompositionError(ValueError):
    """Raised before runtime activity when required model controls are absent."""

    def __init__(self, outcome: UnsupportedComposition) -> None:
        self.outcome = outcome
        missing = ", ".join(sorted(item.value for item in outcome.missing_decisions))
        super().__init__(f"action policy does not support required decisions: {missing}")
