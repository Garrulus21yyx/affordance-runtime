"""Typed policy decisions admitted only against their originating AgentContext."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

from affordance_runtime.immutable import freeze_json


def _require_context(context_id: str) -> None:
    if not context_id.strip():
        raise ValueError("decision requires context identity")


@dataclass(frozen=True)
class SelectAction:
    context_id: str
    action_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    destination_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.action_id.strip():
            raise ValueError("selection requires an offered action id")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))


@dataclass(frozen=True)
class RequestObservation:
    context_id: str
    subject_id: str
    modality: str
    required_assurance: str
    reason: str

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not all(value.strip() for value in (self.subject_id, self.modality, self.required_assurance, self.reason)):
            raise ValueError("observation request requires subject, capability, and reason")


@dataclass(frozen=True)
class RequestActionPage:
    context_id: str
    query: str = ""
    target_id: str = ""
    relevance_role: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)


@dataclass(frozen=True)
class AskUser:
    context_id: str
    question: str
    requested_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.question.strip():
            raise ValueError("user question cannot be blank")
        object.__setattr__(self, "requested_fields", tuple(self.requested_fields))


@dataclass(frozen=True)
class ProposeDone:
    context_id: str
    claimed_criteria: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    result_summary: str
    unresolved_items: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.result_summary.strip():
            raise ValueError("completion proposal requires a summary")
        object.__setattr__(self, "claimed_criteria", tuple(self.claimed_criteria))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "unresolved_items", tuple(self.unresolved_items))


@dataclass(frozen=True)
class Wait:
    context_id: str
    reason: str
    max_wait_ms: int

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.reason.strip() or not 0 < self.max_wait_ms <= 60_000:
            raise ValueError("wait requires a bounded duration and reason")


@dataclass(frozen=True)
class Abort:
    context_id: str
    reason: str
    category: str

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.reason.strip() or not self.category.strip():
            raise ValueError("abort requires reason and category")


AgentDecision: TypeAlias = SelectAction | RequestObservation | RequestActionPage | AskUser | ProposeDone | Wait | Abort
