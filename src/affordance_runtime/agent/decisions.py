"""Typed policy decisions admitted only against their originating AgentContext."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, TypeAlias

from affordance_runtime.actions.paging import PUBLIC_ACTION_LABEL_MAX_CHARS
from affordance_runtime.agent.attempt_signature import PublicAttemptSignature
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
        ObservationPurpose.POINT_GROUNDING,
        ObservationPurpose.VISUAL_CHANGE,
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


class DecisionKind(StrEnum):
    """The sole formal vocabulary for policy and Runtime-local decisions."""

    SELECT_ACTION = "select_action"
    READ_REGION = "read_region"
    FIND_CONTROLS = "find_controls"
    SEARCH_PAGE_CONTENT = "search_page_content"
    SUBMIT_FINAL_RESPONSE = "submit_final_response"
    ASK_USER = "ask_user"
    ABORT = "abort"
    REQUEST_OBSERVATION = "request_observation"
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
class RequestObservation:
    kind: ClassVar[DecisionKind] = DecisionKind.REQUEST_OBSERVATION
    context_id: str
    query_id: str
    purpose: ObservationPurpose
    subject_ids: tuple[str, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    atomic_query: str = ""
    predicate: str = ""
    max_results: int = 1
    public_intent: str = ""
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        _require_bounded(self.query_id, 240, "observation query identity")
        try:
            purpose = ObservationPurpose(self.purpose)
        except ValueError as exc:
            raise ValueError("observation request requires a supported evidence purpose") from exc
        object.__setattr__(self, "purpose", purpose)
        if purpose not in _AGENT_EVIDENCE_PURPOSES:
            raise ValueError("observation purpose is not admitted for Agent requests")
        object.__setattr__(self, "subject_ids", tuple(self.subject_ids))
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        _require_collection(self.subject_ids, "observation subjects", item_limit=240)
        _require_collection(self.candidate_ids, "observation candidates", item_limit=240)
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ValueError("observation subjects cannot repeat")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("observation candidates cannot repeat")
        if len(self.atomic_query) > 500 or len(self.predicate) > 500:
            raise ValueError("observation query text exceeds its bound")
        if len(self.public_intent) > 240:
            raise ValueError("observation public intent exceeds its bound")
        if not 1 <= self.max_results <= _MAX_COLLECTION:
            raise ValueError("observation max results must be in [1, 32]")
        self._validate_purpose_shape(purpose)

    def _validate_purpose_shape(self, purpose: ObservationPurpose) -> None:
        subjects = len(self.subject_ids)
        candidates = len(self.candidate_ids)
        atomic = bool(self.atomic_query.strip())
        predicate = bool(self.predicate.strip())
        if purpose is ObservationPurpose.ENTITY_DISCOVERY:
            valid = not subjects and not candidates and atomic and not predicate
        elif purpose is ObservationPurpose.VISUAL_PROPERTY:
            valid = 1 <= subjects <= 32 and not candidates and not atomic and predicate
        elif purpose is ObservationPurpose.TARGET_DISAMBIGUATION:
            valid = not subjects and 2 <= candidates <= 32 and atomic and not predicate
        elif purpose is ObservationPurpose.POINT_GROUNDING:
            valid = not subjects and candidates <= 32 and atomic and not predicate
        elif purpose is ObservationPurpose.TEXT_IN_IMAGE:
            valid = 1 <= subjects <= 32 and not candidates and atomic and not predicate
        elif purpose is ObservationPurpose.SPATIAL_RELATIONSHIP:
            valid = 2 <= subjects <= 32 and not candidates and not atomic and predicate
        elif purpose is ObservationPurpose.VISUAL_CHANGE:
            valid = 1 <= subjects <= 32 and not candidates and not atomic and predicate
        elif purpose is ObservationPurpose.CRITERION_VERIFICATION:
            valid = 1 <= subjects <= 32 and not candidates and not atomic and not predicate
        else:
            valid = False
        if not valid:
            raise ValueError(f"observation request fields do not match purpose {purpose.value}")

    @property
    def subject_id(self) -> str:
        """Read-only compatibility projection for bounded history consumers."""

        return (self.subject_ids or self.candidate_ids or ("",))[0]

    @property
    def evidence_property(self) -> str:
        """Read-only compatibility projection; the canonical field is ``predicate``."""

        return self.predicate if self.purpose is ObservationPurpose.VISUAL_PROPERTY else ""

    @property
    def reason(self) -> str:
        """Deterministic acquisition description, never a second query authority."""

        return self.public_intent.strip() or f"agent requested {self.purpose.value} evidence"

    @property
    def cursor(self) -> str:
        """Observation queries are atomic and do not carry paging cursors."""

        return ""


@dataclass(frozen=True)
class RequestActionPage:
    kind: ClassVar[DecisionKind] = DecisionKind.FIND_CONTROLS
    context_id: str
    query: str = ""
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        if len(self.query) > PUBLIC_ACTION_LABEL_MAX_CHARS:
            raise ValueError("action page request exceeds bounded fields")


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
class ToolRejectedResult(LocalToolResult):
    kind: ClassVar[DecisionKind] = DecisionKind.TOOL_REJECTED


@dataclass(frozen=True)
class FinalResponse:
    """One bounded response submitted directly to the native evaluator path."""

    kind: ClassVar[DecisionKind] = DecisionKind.SUBMIT_FINAL_RESPONSE

    context_id: str
    content: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.content, MAX_FINAL_RESPONSE_CHARS, "final response")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        _require_collection(self.evidence_refs, "final response evidence refs", item_limit=200)
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
    | RequestObservation
    | RequestActionPage
    | AskUser
    | ReadRegionResult
    | SearchPageContentResult
    | ToolRejectedResult
    | FinalResponse
    | Wait
    | Abort
)
