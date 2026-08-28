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


class InteractionResponseKind(StrEnum):
    FREE_TEXT = "free_text"
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    STRUCTURED_FIELDS = "structured_fields"


class InteractionFieldKind(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"


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
    public_intent: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        if not self.action_id.strip():
            raise ValueError("selection requires an offered action id")
        _require_tool_call_id(self.tool_call_id)
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        if not isinstance(self.expected_outcome, str) or len(self.expected_outcome) > 240:
            raise ValueError("selection expected outcome must be one bounded string")
        object.__setattr__(self, "expected_outcome", self.expected_outcome.strip())
        if len(self.public_intent) > 240:
            raise ValueError("selection public intent exceeds its bound")


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
    public_intent: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        if len(self.query) > PUBLIC_ACTION_LABEL_MAX_CHARS:
            raise ValueError("action page request exceeds bounded fields")
        if len(self.public_intent) > 240:
            raise ValueError("action page public intent exceeds its bound")


@dataclass(frozen=True)
class InteractionAttribute:
    label: str
    value: str

    def __post_init__(self) -> None:
        _require_bounded(self.label, 120, "interaction attribute label")
        _require_bounded(self.value, 500, "interaction attribute value")


@dataclass(frozen=True)
class InteractionOptionDraft:
    title: str
    description: str = ""
    media_ref: str = ""
    attributes: tuple[InteractionAttribute, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_bounded(self.title, 240, "interaction option title")
        if len(self.description) > 1_000 or len(self.media_ref) > 512:
            raise ValueError("interaction option presentation exceeds its bound")
        object.__setattr__(self, "attributes", tuple(self.attributes))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "uncertainties", tuple(self.uncertainties))
        if any(not isinstance(item, InteractionAttribute) for item in self.attributes):
            raise TypeError("interaction option attributes must be typed")
        if len(self.attributes) > 16:
            raise ValueError("interaction option attributes exceed their bound")
        _require_collection(self.evidence_refs, "interaction option evidence", item_limit=512)
        _require_collection(self.uncertainties, "interaction option uncertainties", item_limit=500)
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("interaction option evidence must be unique")


@dataclass(frozen=True)
class TextFieldDraft:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.TEXT
    label: str
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _validate_field_draft(self.label, self.description, self.required)


@dataclass(frozen=True)
class IntegerFieldDraft:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.INTEGER
    label: str
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _validate_field_draft(self.label, self.description, self.required)


@dataclass(frozen=True)
class DecimalFieldDraft:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.DECIMAL
    label: str
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _validate_field_draft(self.label, self.description, self.required)


@dataclass(frozen=True)
class BooleanFieldDraft:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.BOOLEAN
    label: str
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _validate_field_draft(self.label, self.description, self.required)


@dataclass(frozen=True)
class DateFieldDraft:
    kind: ClassVar[InteractionFieldKind] = InteractionFieldKind.DATE
    label: str
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        _validate_field_draft(self.label, self.description, self.required)


InteractionFieldDraft: TypeAlias = (
    TextFieldDraft | IntegerFieldDraft | DecimalFieldDraft | BooleanFieldDraft | DateFieldDraft
)


def _validate_field_draft(label: str, description: str, required: bool) -> None:
    _require_bounded(label, 120, "interaction field label")
    if len(description) > 500 or type(required) is not bool:
        raise ValueError("interaction field presentation is invalid")


@dataclass(frozen=True)
class InteractionRequestDraft:
    """Model-authored bounded content; Core assigns all public identities."""

    kind: ClassVar[DecisionKind] = DecisionKind.ASK_USER
    context_id: str
    prompt: str
    response_kind: InteractionResponseKind = InteractionResponseKind.FREE_TEXT
    field_drafts: tuple[InteractionFieldDraft, ...] = ()
    option_drafts: tuple[InteractionOptionDraft, ...] = ()
    public_intent: str = ""
    tool_call_id: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        _require_bounded(self.prompt, 1_000, "interaction prompt")
        response_kind = InteractionResponseKind(self.response_kind)
        object.__setattr__(self, "response_kind", response_kind)
        object.__setattr__(self, "field_drafts", tuple(self.field_drafts))
        object.__setattr__(self, "option_drafts", tuple(self.option_drafts))
        if any(
            not isinstance(
                item,
                TextFieldDraft
                | IntegerFieldDraft
                | DecimalFieldDraft
                | BooleanFieldDraft
                | DateFieldDraft,
            )
            for item in self.field_drafts
        ):
            raise TypeError("interaction fields must use the closed draft algebra")
        if any(not isinstance(item, InteractionOptionDraft) for item in self.option_drafts):
            raise TypeError("interaction options must be typed drafts")
        fields = len(self.field_drafts)
        options = len(self.option_drafts)
        valid = (
            response_kind is InteractionResponseKind.FREE_TEXT
            and fields == 0
            and options == 0
            or response_kind in {
                InteractionResponseKind.SINGLE_SELECT,
                InteractionResponseKind.MULTI_SELECT,
            }
            and fields == 0
            and 1 <= options <= _MAX_COLLECTION
            or response_kind is InteractionResponseKind.STRUCTURED_FIELDS
            and 1 <= fields <= _MAX_COLLECTION
            and options == 0
        )
        if not valid:
            raise ValueError("interaction request fields do not match its response kind")
        if len(self.public_intent) > 240:
            raise ValueError("interaction public intent exceeds its bound")

    @property
    def question(self) -> str:
        """Read-only compatibility projection for presentation consumers."""

        return self.prompt

    @property
    def requested_fields(self) -> tuple[str, ...]:
        """Read-only compatibility projection; field identity is assigned later."""

        return tuple(item.label for item in self.field_drafts)


class _AskUserCompatibility(type):
    """Constructor/type projection only; no live ``AskUser`` value exists."""

    def __call__(
        cls,
        context_id: str,
        question: str,
        requested_fields: tuple[str, ...] = (),
        tool_call_id: str = "",
    ) -> InteractionRequestDraft:
        fields = tuple(TextFieldDraft(item) for item in requested_fields)
        return InteractionRequestDraft(
            context_id,
            question,
            (
                InteractionResponseKind.STRUCTURED_FIELDS
                if fields
                else InteractionResponseKind.FREE_TEXT
            ),
            fields,
            tool_call_id=tool_call_id,
        )

    def __instancecheck__(cls, instance: object) -> bool:
        if isinstance(instance, InteractionRequestDraft):
            return True
        from affordance_runtime.agent.interactions import InteractionRequest

        return isinstance(instance, InteractionRequest)


class AskUser(metaclass=_AskUserCompatibility):
    """Read-only source compatibility facade for the removed live contract."""


@dataclass(frozen=True)
class PublicArtifactItemDraft:
    title: str
    summary: str = ""
    attributes: tuple[InteractionAttribute, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_bounded(self.title, 240, "artifact item title")
        if len(self.summary) > 1_000:
            raise ValueError("artifact item summary exceeds its bound")
        object.__setattr__(self, "attributes", tuple(self.attributes))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if any(not isinstance(item, InteractionAttribute) for item in self.attributes):
            raise TypeError("artifact item attributes must be typed")
        if len(self.attributes) > 16:
            raise ValueError("artifact item attributes exceed their bound")
        _require_collection(self.evidence_refs, "artifact item evidence", item_limit=512)
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("artifact item evidence must be unique")


@dataclass(frozen=True)
class PublicArtifactDraft:
    title: str
    summary: str = ""
    items: tuple[PublicArtifactItemDraft, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_bounded(self.title, 240, "artifact title")
        if len(self.summary) > 2_000:
            raise ValueError("artifact summary exceeds its bound")
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        if len(self.items) > _MAX_COLLECTION or any(
            not isinstance(item, PublicArtifactItemDraft) for item in self.items
        ):
            raise TypeError("artifact items must be bounded typed drafts")
        _require_collection(self.evidence_refs, "artifact evidence", item_limit=512)
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("artifact evidence must be unique")


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
    artifact: PublicArtifactDraft | None = None
    public_intent: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_bounded(self.content, MAX_FINAL_RESPONSE_CHARS, "final response")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        _require_collection(self.evidence_refs, "final response evidence refs", item_limit=200)
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("final response evidence citations must be unique")
        if self.artifact is not None and not isinstance(self.artifact, PublicArtifactDraft):
            raise TypeError("final response artifact must be a typed draft")
        if len(self.public_intent) > 240:
            raise ValueError("final response public intent exceeds its bound")


@dataclass(frozen=True)
class Wait:
    kind: ClassVar[DecisionKind] = DecisionKind.WAIT
    context_id: str
    reason: str
    max_wait_ms: int
    tool_call_id: str = ""
    public_intent: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        if not self.reason.strip() or len(self.reason) > _MAX_REASON or not 0 < self.max_wait_ms <= 60_000:
            raise ValueError("wait requires a bounded duration and reason")
        if len(self.public_intent) > 240:
            raise ValueError("wait public intent exceeds its bound")


@dataclass(frozen=True)
class Abort:
    kind: ClassVar[DecisionKind] = DecisionKind.ABORT
    context_id: str
    reason: str
    category: str
    tool_call_id: str = ""
    public_intent: str = ""

    def __post_init__(self) -> None:
        _require_context(self.context_id)
        _require_tool_call_id(self.tool_call_id)
        _require_bounded(self.reason, _MAX_REASON, "abort reason")
        try:
            AbortCategory(self.category)
        except ValueError as exc:
            raise ValueError("abort category is unsupported") from exc
        if len(self.public_intent) > 240:
            raise ValueError("abort public intent exceeds its bound")


AgentDecision: TypeAlias = (
    SelectAction
    | RequestObservation
    | RequestActionPage
    | InteractionRequestDraft
    | ReadRegionResult
    | SearchPageContentResult
    | ToolRejectedResult
    | FinalResponse
    | Wait
    | Abort
)
