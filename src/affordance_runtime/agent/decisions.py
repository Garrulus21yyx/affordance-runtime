"""Typed policy decisions admitted only against their originating AgentContext."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, TypeAlias

from affordance_runtime.actions.relevance import ActionRelevanceRole
from affordance_runtime.agent.attempt_signature import PublicAttemptSignature
from affordance_runtime.agent.context.world_delivery_lens import WorldDeliveryLens
from affordance_runtime.agent.working_facts import WorkingFact
from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.observation_needs import ObservationPurpose

_MAX_REASON = 500
_AGENT_EVIDENCE_PURPOSES = frozenset(
    {
        ObservationPurpose.ENTITY_DISCOVERY,
        ObservationPurpose.TARGET_DISAMBIGUATION,
        ObservationPurpose.VISUAL_PROPERTY,
        ObservationPurpose.SPATIAL_RELATIONSHIP,
        ObservationPurpose.TEXT_IN_IMAGE,
        ObservationPurpose.CRITERION_VERIFICATION,
    }
)
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


class YieldMilestoneKind(StrEnum):
    OUTCOME_PROPOSED = "outcome_proposed"
    STALLED = "stalled"
    BLOCKED = "blocked"
    CAPABILITY_GAP = "capability_gap"
    NEEDS_REPLAN = "needs_replan"


class ReplanReasonCode(StrEnum):
    DELIVERY_NOT_OBSERVABLE = "delivery_not_observable"
    MILESTONE_TASK_MISMATCH = "milestone_task_mismatch"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"


class ProtocolFeedbackKind(StrEnum):
    MULTIPLE_TOOL_CALLS = "multiple_tool_calls"
    OUTPUT_TRUNCATED = "output_truncated"
    EMPTY_FINAL_CONTENT = "empty_final_content"
    JSON_INVALID = "json_invalid"


class DecisionKind(StrEnum):
    """The sole formal vocabulary for policy and Runtime-local decisions."""

    SELECT_ACTION = "select_action"
    SET_FORM_FIELDS = "set_form_fields"
    READ_REGION = "read_region"
    FIND_CONTROLS = "find_controls"
    SEARCH_PAGE_CONTENT = "search_page_content"
    PIN_FACT = "pin_fact"
    YIELD_MILESTONE = "yield_milestone"
    SUBMIT_FINAL_RESPONSE = "submit_final_response"
    ASK_USER = "ask_user"
    ABORT = "abort"
    REQUEST_OBSERVATION = "request_observation"
    PROTOCOL_FEEDBACK = "protocol_feedback"
    TOOL_REJECTED = "tool_rejected"
    WAIT = "wait"


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
    kind: ClassVar[DecisionKind] = DecisionKind.SELECT_ACTION
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
class FormFieldUpdate:
    """One privately resolved field update inside a bounded current-form command."""

    action_id: str
    operation: str
    target_ref: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.operation not in {"type_text", "select_option"}:
            raise ValueError("form field update operation is unsupported")
        if not self.action_id.strip() or re.fullmatch(r"E[1-9][0-9]{0,2}", self.target_ref) is None:
            raise ValueError("form field update requires current private action and public target ref")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))


@dataclass(frozen=True)
class SetFormFields:
    """One model call authorizing 2-4 non-submitting updates in one current form."""

    kind: ClassVar[DecisionKind] = DecisionKind.SET_FORM_FIELDS

    context_id: str
    form_key: str
    fields: tuple[FormFieldUpdate, ...]
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        fields = tuple(self.fields)
        if not self.form_key.startswith("form:") or not 2 <= len(fields) <= 4:
            raise ValueError("set_form_fields requires one current form and two to four fields")
        if len({item.target_ref for item in fields}) != len(fields):
            raise ValueError("set_form_fields cannot update one field twice")
        object.__setattr__(self, "fields", fields)


@dataclass(frozen=True)
class RequestObservation:
    kind: ClassVar[DecisionKind] = DecisionKind.REQUEST_OBSERVATION
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
    kind: ClassVar[DecisionKind] = DecisionKind.FIND_CONTROLS
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
    kind: ClassVar[DecisionKind] = DecisionKind.ASK_USER
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
    rejected_attempt_signature: PublicAttemptSignature | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if type(self) is LocalToolResult:
            raise TypeError("local tool result requires one closed semantic subtype")
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
        if self.rejected_attempt_signature is not None and not isinstance(
            self.rejected_attempt_signature, PublicAttemptSignature
        ):
            raise TypeError("local tool rejected attempt signature must be typed")


@dataclass(frozen=True)
class ReadRegionResult(LocalToolResult):
    kind: ClassVar[DecisionKind] = DecisionKind.READ_REGION


@dataclass(frozen=True)
class SearchPageContentResult(LocalToolResult):
    kind: ClassVar[DecisionKind] = DecisionKind.SEARCH_PAGE_CONTENT


@dataclass(frozen=True)
class PinFactResult(LocalToolResult):
    kind: ClassVar[DecisionKind] = DecisionKind.PIN_FACT


@dataclass(frozen=True)
class ToolRejectedResult(LocalToolResult):
    kind: ClassVar[DecisionKind] = DecisionKind.TOOL_REJECTED


@dataclass(frozen=True)
class ProtocolFeedback:
    """No-dispatch feedback for one invalid provider action envelope."""

    kind: ClassVar[DecisionKind] = DecisionKind.PROTOCOL_FEEDBACK

    context_id: str
    feedback_kind: ProtocolFeedbackKind
    call_count: int = 0
    detail: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not isinstance(self.feedback_kind, ProtocolFeedbackKind):
            object.__setattr__(self, "feedback_kind", ProtocolFeedbackKind(self.feedback_kind))
        if not 0 <= self.call_count <= 32:
            raise ValueError("protocol feedback call count is outside bounds")
        if len(self.detail) > 240:
            raise ValueError("protocol feedback detail exceeds its bound")


@dataclass(frozen=True)
class YieldMilestone:
    """Local episode exit request; never dispatches to the environment."""

    kind: ClassVar[DecisionKind] = DecisionKind.YIELD_MILESTONE

    context_id: str
    yield_kind: str
    reason: str
    tool_call_id: str = ""
    reason_code: ReplanReasonCode | None = None

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        try:
            kind = YieldMilestoneKind(self.yield_kind)
        except ValueError as exc:
            raise ValueError("yield_milestone kind is unsupported") from exc
        _require_bounded(self.reason, _MAX_REASON, "yield reason")
        if self.reason_code is not None and not isinstance(self.reason_code, ReplanReasonCode):
            object.__setattr__(self, "reason_code", ReplanReasonCode(self.reason_code))
        if (kind is YieldMilestoneKind.NEEDS_REPLAN) != (self.reason_code is not None):
            raise ValueError("needs_replan requires exactly one typed reason code")


@dataclass(frozen=True)
class FinalResponse:
    """Evidence-citing response proposal admitted before native final evaluation."""

    kind: ClassVar[DecisionKind] = DecisionKind.SUBMIT_FINAL_RESPONSE

    context_id: str
    content: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.content, MAX_FINAL_RESPONSE_CHARS, "final response")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        _require_collection(self.evidence_refs, "final response evidence refs", item_limit=200)
        if not self.evidence_refs:
            raise ValueError("final response requires current evidence citations")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("final response evidence citations must be unique")


@dataclass(frozen=True)
class Wait:
    kind: ClassVar[DecisionKind] = DecisionKind.WAIT
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
    kind: ClassVar[DecisionKind] = DecisionKind.ABORT
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
    | SetFormFields
    | RequestObservation
    | RequestActionPage
    | AskUser
    | ReadRegionResult
    | SearchPageContentResult
    | PinFactResult
    | ToolRejectedResult
    | ProtocolFeedback
    | YieldMilestone
    | FinalResponse
    | Wait
    | Abort
)
