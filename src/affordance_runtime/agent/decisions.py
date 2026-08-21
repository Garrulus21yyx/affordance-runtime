"""Typed policy decisions admitted only against their originating AgentContext."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeAlias

from affordance_runtime.actions.relevance import ActionRelevanceRole
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.observation_needs import ObservationPurpose

_MAX_REASON = 500
_AGENT_EVIDENCE_PURPOSES = frozenset({
    ObservationPurpose.ENTITY_DISCOVERY,
    ObservationPurpose.TARGET_DISAMBIGUATION,
    ObservationPurpose.VISUAL_PROPERTY,
    ObservationPurpose.SPATIAL_RELATIONSHIP,
    ObservationPurpose.TEXT_IN_IMAGE,
    ObservationPurpose.CRITERION_VERIFICATION,
})
MAX_FINAL_RESPONSE_CHARS = 8_000
_MAX_COLLECTION = 32
_TOOL_CALL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}")


class AbortCategory(StrEnum):
    POLICY = "policy"
    SAFETY = "safety"
    UNSUPPORTED = "unsupported"
    NO_PROGRESS = "no_progress"
    USER_REQUEST = "user_request"
    INTERNAL = "internal"


class YieldSubtaskKind(StrEnum):
    OUTCOME_PROPOSED = "outcome_proposed"
    STALLED = "stalled"
    BLOCKED = "blocked"
    CAPABILITY_GAP = "capability_gap"
    NEEDS_REPLAN = "needs_replan"


class ProtocolFeedbackKind(StrEnum):
    MULTIPLE_TOOL_CALLS = "multiple_tool_calls"
    OUTPUT_TRUNCATED = "output_truncated"
    EMPTY_FINAL_CONTENT = "empty_final_content"
    JSON_INVALID = "json_invalid"


def _require_context(context_id: str) -> None:
    if not context_id.strip():
        raise ValueError("decision requires context identity")


def _require_tool_call_id(tool_call_id: str) -> None:
    if tool_call_id and _TOOL_CALL_ID.fullmatch(tool_call_id) is None:
        raise ValueError("decision tool call identity is invalid")


def _require_bounded(value: str, limit: int, field_name: str) -> None:
    if not value.strip() or len(value) > limit:
        raise ValueError(f"{field_name} must be nonblank and at most {limit} characters")


def _require_collection(values: tuple[str, ...], field_name: str, *, item_limit: int = 512) -> None:
    if len(values) > _MAX_COLLECTION or any(not item.strip() or len(item) > item_limit for item in values):
        raise ValueError(f"{field_name} exceeds structured decision bounds")


@dataclass(frozen=True)
class SelectAction:
    context_id: str
    action_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    destination_id: str = ""
    tool_call_id: str = ""
    expected_outcome: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.action_id.strip():
            raise ValueError("selection requires an offered action id")
        _require_tool_call_id(self.tool_call_id)
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        if not isinstance(self.expected_outcome, str) or len(self.expected_outcome) > 240:
            raise ValueError("selection expected outcome must be one bounded string")
        object.__setattr__(self, "expected_outcome", self.expected_outcome.strip())


@dataclass(frozen=True)
class RequestObservation:
    context_id: str
    purpose: str
    subject_id: str
    evidence_property: str
    reason: str
    cursor: str = ""
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        _require_bounded(self.subject_id, 240, "observation subject")
        if len(self.evidence_property) > 120:
            raise ValueError("observation evidence property exceeds its bound")
        _require_bounded(self.reason, _MAX_REASON, "observation reason")
        if len(self.cursor) > 512:
            raise ValueError("observation cursor exceeds its bound")
        try:
            purpose = ObservationPurpose(self.purpose)
        except ValueError as exc:
            raise ValueError("observation request requires a supported evidence purpose") from exc
        if purpose not in _AGENT_EVIDENCE_PURPOSES:
            raise ValueError("observation purpose is not admitted for Agent requests")
        if (purpose is ObservationPurpose.VISUAL_PROPERTY) != bool(self.evidence_property):
            raise ValueError("visual property requests require exactly one evidence property")


@dataclass(frozen=True)
class RequestActionPage:
    context_id: str
    query: str = ""
    target_id: str = ""
    relevance_role: str = ""
    cursor: str = ""
    tool_call_id: str = ""
    exact_target_ref: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        if len(self.query) > 120 or len(self.target_id) > 240 or len(self.cursor) > 512:
            raise ValueError("action page request exceeds bounded fields")
        if self.exact_target_ref and re.fullmatch(r"E[1-9][0-9]{0,2}", self.exact_target_ref) is None:
            raise ValueError("action page exact target ref is invalid")
        if self.relevance_role:
            ActionRelevanceRole(self.relevance_role)


@dataclass(frozen=True)
class AskUser:
    context_id: str
    question: str
    requested_fields: tuple[str, ...] = ()
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        _require_bounded(self.question, 1_000, "user question")
        object.__setattr__(self, "requested_fields", tuple(self.requested_fields))
        _require_collection(self.requested_fields, "requested fields", item_limit=120)


@dataclass(frozen=True)
class LocalToolResult:
    """One Registry-resolved local tool call and its deterministic public result."""

    context_id: str
    tool_name: str
    arguments: Mapping[str, object]
    result: Mapping[str, object]
    tool_call_id: str = ""
    working_fact: WorkingFact | None = field(default=None, repr=False, compare=False)
    delivery_lens: WorldDeliveryLens | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.tool_name) is None:
            raise ValueError("local tool result requires a valid registered name")
        if not self.result:
            raise ValueError("local tool result cannot be empty")
        object.__setattr__(self, "arguments", freeze_json(self.arguments))
        object.__setattr__(self, "result", freeze_json(self.result))
        if self.working_fact is not None and not isinstance(self.working_fact, WorkingFact):
            raise TypeError("local tool state effect must be a typed working fact")
        if self.delivery_lens is not None and not isinstance(self.delivery_lens, WorldDeliveryLens):
            raise TypeError("local tool state effect must be a typed delivery lens")


@dataclass(frozen=True)
class ProtocolFeedback:
    """No-dispatch feedback for one invalid provider action envelope."""

    context_id: str
    kind: ProtocolFeedbackKind
    call_count: int = 0
    detail: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not isinstance(self.kind, ProtocolFeedbackKind):
            object.__setattr__(self, "kind", ProtocolFeedbackKind(self.kind))
        if not 0 <= self.call_count <= 32:
            raise ValueError("protocol feedback call count is outside bounds")
        if len(self.detail) > 240:
            raise ValueError("protocol feedback detail exceeds its bound")


@dataclass(frozen=True)
class YieldSubtask:
    """Local episode exit request; never dispatches to the environment."""

    context_id: str
    kind: str
    reason: str
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        try:
            YieldSubtaskKind(self.kind)
        except ValueError as exc:
            raise ValueError("yield_subtask kind is unsupported") from exc
        _require_bounded(self.reason, _MAX_REASON, "yield reason")


@dataclass(frozen=True)
class FinalResponse:
    """Native user-facing result emitted only after Runtime-verified completion."""

    context_id: str
    content: str

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.content, MAX_FINAL_RESPONSE_CHARS, "final response")


@dataclass(frozen=True)
class Wait:
    context_id: str
    reason: str
    max_wait_ms: int
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        if not self.reason.strip() or len(self.reason) > _MAX_REASON or not 0 < self.max_wait_ms <= 60_000:
            raise ValueError("wait requires a bounded duration and reason")


@dataclass(frozen=True)
class Abort:
    context_id: str
    reason: str
    category: str
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        _require_bounded(self.reason, _MAX_REASON, "abort reason")
        try:
            AbortCategory(self.category)
        except ValueError as exc:
            raise ValueError("abort category is unsupported") from exc


AgentDecision: TypeAlias = (
    SelectAction
    | RequestObservation
    | RequestActionPage
    | AskUser
    | LocalToolResult
    | ProtocolFeedback
    | YieldSubtask
    | FinalResponse
    | Wait
    | Abort
)
