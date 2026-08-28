from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator
from typing_extensions import TypeAliasType

SCHEMA_VERSION = "interaction-shell.v4"
REVISION_CONVERSATION_MAX_TURNS = 6
REVISION_CONVERSATION_MAX_TEXT_BYTES = 16 * 1024


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_serialization_defaults_required=True,
    )


class ConversationTurn(StrictModel):
    turn_id: str = Field(min_length=1, max_length=128)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=8000)


class RevisionConversationContext(StrictModel):
    turns: tuple[ConversationTurn, ...] = Field(min_length=1, max_length=6)
    latest_turn_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_bounded_latest_user_turn(self):
        if len({turn.turn_id for turn in self.turns}) != len(self.turns):
            raise ValueError("revision conversation turn identities must be unique")
        latest = tuple(turn for turn in self.turns if turn.turn_id == self.latest_turn_id)
        if len(latest) != 1 or self.turns[-1] is not latest[0] or latest[0].role != "user":
            raise ValueError("revision conversation must end at one identified user turn")
        if sum(len(turn.text.encode("utf-8")) for turn in self.turns) > REVISION_CONVERSATION_MAX_TEXT_BYTES:
            raise ValueError("revision conversation exceeds its total text-byte bound")
        return self


class RunStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"
    BLOCKED = "blocked"


class ControlOwner(StrEnum):
    AGENT = "agent"
    USER = "user"


class InteractionAttribute(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=500)


class InteractionField(StrictModel):
    field_id: str = Field(min_length=1, max_length=128)
    kind: Literal["text", "integer", "decimal", "boolean", "date"]
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    required: bool = True


class InteractionOption(StrictModel):
    option_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=1000)
    media_ref: str = Field(default="", max_length=512)
    attributes: tuple[InteractionAttribute, ...] = Field(default=(), max_length=16)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=32)


class InteractionRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=1000)
    response_kind: Literal[
        "free_text",
        "single_select",
        "multi_select",
        "structured_fields",
    ]
    fields: tuple[InteractionField, ...] = Field(default=(), max_length=32)
    options: tuple[InteractionOption, ...] = Field(default=(), max_length=32)
    public_intent: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def require_response_shape(self):
        valid = (
            self.response_kind == "free_text"
            and not self.fields
            and not self.options
            or self.response_kind in {"single_select", "multi_select"}
            and not self.fields
            and bool(self.options)
            or self.response_kind == "structured_fields"
            and bool(self.fields)
            and not self.options
        )
        if not valid:
            raise ValueError("interaction request response shape is invalid")
        if len({item.field_id for item in self.fields}) != len(self.fields):
            raise ValueError("interaction field IDs must be unique")
        if len({item.option_id for item in self.options}) != len(self.options):
            raise ValueError("interaction option IDs must be unique")
        return self


class FreeTextInteractionResponse(StrictModel):
    kind: Literal["free_text"]
    request_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=8000)


class SingleSelectInteractionResponse(StrictModel):
    kind: Literal["single_select"]
    request_id: str = Field(min_length=1, max_length=128)
    option_id: str = Field(min_length=1, max_length=128)


class MultiSelectInteractionResponse(StrictModel):
    kind: Literal["multi_select"]
    request_id: str = Field(min_length=1, max_length=128)
    option_ids: tuple[str, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_unique_options(self):
        if len(set(self.option_ids)) != len(self.option_ids):
            raise ValueError("multi-select option IDs must be unique")
        return self


class TextInteractionFieldValue(StrictModel):
    kind: Literal["text"]
    field_id: str = Field(min_length=1, max_length=128)
    text: str = Field(max_length=8000)


class IntegerInteractionFieldValue(StrictModel):
    kind: Literal["integer"]
    field_id: str = Field(min_length=1, max_length=128)
    integer: int


class DecimalInteractionFieldValue(StrictModel):
    kind: Literal["decimal"]
    field_id: str = Field(min_length=1, max_length=128)
    decimal_string: str = Field(min_length=1, max_length=200)


class BooleanInteractionFieldValue(StrictModel):
    kind: Literal["boolean"]
    field_id: str = Field(min_length=1, max_length=128)
    boolean: bool


class DateInteractionFieldValue(StrictModel):
    kind: Literal["date"]
    field_id: str = Field(min_length=1, max_length=128)
    iso_date: str = Field(pattern=r"\d{4}-\d{2}-\d{2}")


InteractionFieldValue = TypeAliasType(
    "InteractionFieldValue",
    Annotated[
        TextInteractionFieldValue
        | IntegerInteractionFieldValue
        | DecimalInteractionFieldValue
        | BooleanInteractionFieldValue
        | DateInteractionFieldValue,
        Field(discriminator="kind"),
    ],
)


class StructuredFieldsInteractionResponse(StrictModel):
    kind: Literal["structured_fields"]
    request_id: str = Field(min_length=1, max_length=128)
    values: tuple[InteractionFieldValue, ...] = Field(max_length=32)


InteractionResponse = TypeAliasType(
    "InteractionResponse",
    Annotated[
        FreeTextInteractionResponse
        | SingleSelectInteractionResponse
        | MultiSelectInteractionResponse
        | StructuredFieldsInteractionResponse,
        Field(discriminator="kind"),
    ],
)


class ArtifactItem(StrictModel):
    item_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=1000)
    attributes: tuple[InteractionAttribute, ...] = Field(default=(), max_length=16)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)


class ArtifactLink(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    artifact_ref: str = Field(min_length=1, max_length=512)


class PublicArtifact(StrictModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=2000)
    items: tuple[ArtifactItem, ...] = Field(default=(), max_length=32)
    links: tuple[ArtifactLink, ...] = Field(default=(), max_length=32)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)


class Completion(StrictModel):
    outcome: Literal["success", "failure", "blocked", "cancelled"]
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(max_length=4000)
    evidence_refs: tuple[str, ...] = ()
    artifact: PublicArtifact | None = None


class UnavailableSurface(StrictModel):
    status: Literal["unavailable"]
    reason_code: str = Field(min_length=1, max_length=128)


class ReadOnlySurface(StrictModel):
    status: Literal["read_only"]
    surface_kind: Literal["web", "mobile", "desktop", "generic"]
    presentation: Literal["live_media", "snapshot"]
    protected_path: str = Field(min_length=1, max_length=512)

    @field_validator("protected_path")
    @classmethod
    def require_secret_free_same_origin_path(cls, value: str) -> str:
        return _same_origin_path(value)


class InteractiveSurface(StrictModel):
    status: Literal["interactive"]
    surface_kind: Literal["web", "mobile", "desktop", "generic"]
    presentation: Literal["live_media"]
    protected_path: str = Field(min_length=1, max_length=512)
    input_mode: Literal["native"]

    @field_validator("protected_path")
    @classmethod
    def require_secret_free_same_origin_path(cls, value: str) -> str:
        return _same_origin_path(value)


SurfaceView: TypeAlias = Annotated[
    UnavailableSurface | ReadOnlySurface | InteractiveSurface,
    Field(discriminator="status"),
]


class StartTaskOffer(StrictModel):
    kind: Literal["start_task"]


class AnswerQuestionOffer(StrictModel):
    kind: Literal["answer_question"]
    request_id: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=2000)


class RespondInteractionOffer(StrictModel):
    kind: Literal["respond_interaction"]
    request: InteractionRequest


class ConfirmActionOffer(StrictModel):
    kind: Literal["confirm_action"]
    request_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)
    risk: str = Field(min_length=1, max_length=128)


class CancelTaskOffer(StrictModel):
    kind: Literal["cancel_task"]


class PauseTaskOffer(StrictModel):
    kind: Literal["pause_task"]


class ResumeTaskOffer(StrictModel):
    kind: Literal["resume_task"]


class ReviseTaskOffer(StrictModel):
    kind: Literal["revise_task"]


class TakeOverOffer(StrictModel):
    kind: Literal["take_over"]


class ReturnControlOffer(StrictModel):
    kind: Literal["return_control"]


class CloseSessionOffer(StrictModel):
    kind: Literal["close_session"]


CommandOffer = TypeAliasType(
    "CommandOffer",
    Annotated[
        StartTaskOffer
        | AnswerQuestionOffer
        | RespondInteractionOffer
        | ConfirmActionOffer
        | CancelTaskOffer
        | PauseTaskOffer
        | ResumeTaskOffer
        | ReviseTaskOffer
        | TakeOverOffer
        | ReturnControlOffer
        | CloseSessionOffer,
        Field(discriminator="kind"),
    ],
)
COMMAND_OFFER_ADAPTER = TypeAdapter(CommandOffer)


class PublicStep(StrictModel):
    step: int = Field(ge=1)
    stage: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=80)
    label: str = Field(max_length=500)
    attempt: int = Field(default=1, ge=1)
    retry_count: int = Field(default=0, ge=0)
    recovery_count: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    evidence_refs: tuple[str, ...] = ()


class ControlOutcome(StrictModel):
    command_id: str = Field(min_length=1, max_length=128)
    kind: Literal["pause", "revise", "take_over", "return_control"]
    outcome: Literal[
        "paused",
        "failed",
        "revised",
        "needs_input",
        "no_change",
        "new_task_suggested",
        "unsupported",
        "effect_reconciliation_required",
        "user_control_granted",
        "user_control_returned",
    ]
    code: str = Field(min_length=1, max_length=128)
    checkpoint_id: str | None = Field(default=None, max_length=200)
    message: str = Field(default="", max_length=2000)


class EffectReconciliation(StrictModel):
    status: Literal["pending", "compensated", "needs_input"]
    code: str = Field(min_length=1, max_length=128)
    original_effect_ref: str = Field(min_length=1, max_length=256)
    original_action: str = Field(min_length=1, max_length=256)
    resource_ref: str = Field(min_length=1, max_length=512)
    reversibility: Literal["reversible", "compensatable", "irreversible", "unknown"]
    compensation_effect_ref: str = Field(default="", max_length=256)


class UserTurnBlock(StrictModel):
    kind: Literal["user_turn"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    content: str = Field(min_length=1, max_length=8000)


class GoalAcceptedBlock(StrictModel):
    kind: Literal["goal_accepted"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    task_revision: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=8000)
    constraints: tuple[str, ...] = Field(default=(), max_length=32)


class AgentIntentBlock(StrictModel):
    kind: Literal["agent_intent"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    content: str = Field(min_length=1, max_length=240)


class RuntimeActivityBlock(StrictModel):
    kind: Literal["runtime_activity"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    status: Literal["started", "completed", "uncertain", "failed"]
    label: str = Field(min_length=1, max_length=500)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)


class EvidenceSummaryBlock(StrictModel):
    kind: Literal["evidence_summary"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    evidence_kind: Literal["structural", "visual", "mixed", "unknown"]
    status: Literal["observed", "partial", "unknown", "failed", "stale"]
    message: str = Field(min_length=1, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=32)


class InteractionRequestBlock(StrictModel):
    kind: Literal["interaction_request"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    request: InteractionRequest


class RevisionAppliedBlock(StrictModel):
    kind: Literal["revision_applied"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    task_revision: int = Field(ge=2)
    goal_description_changed: bool = False
    added: tuple[str, ...] = Field(default=(), max_length=32)
    removed: tuple[str, ...] = Field(default=(), max_length=32)
    retained: tuple[str, ...] = Field(default=(), max_length=32)


class ConfirmationRequiredBlock(StrictModel):
    kind: Literal["confirmation_required"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    request_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)
    risk: str = Field(min_length=1, max_length=128)


class CompletionBlock(StrictModel):
    kind: Literal["completion"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    completion: Completion


class FailureBlock(StrictModel):
    kind: Literal["failure"]
    block_id: str = Field(min_length=1, max_length=256)
    occurred_at: datetime
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)


FeedBlock = TypeAliasType(
    "FeedBlock",
    Annotated[
        UserTurnBlock
        | GoalAcceptedBlock
        | AgentIntentBlock
        | RuntimeActivityBlock
        | EvidenceSummaryBlock
        | InteractionRequestBlock
        | RevisionAppliedBlock
        | ConfirmationRequiredBlock
        | CompletionBlock
        | FailureBlock,
        Field(discriminator="kind"),
    ],
)
FEED_BLOCK_ADAPTER = TypeAdapter(FeedBlock)


class RuntimeSessionSnapshot(StrictModel):
    schema_version: Literal["interaction-shell.v4"]
    session_id: str
    task_id: str | None = None
    task_revision: int = Field(default=0, ge=0)
    task_text: str | None = Field(default=None, max_length=8000)
    run_status: RunStatus = RunStatus.IDLE
    event_epoch: str = Field(min_length=16, max_length=128)
    event_cursor: int = Field(default=0, ge=0)
    completion: Completion | None = None
    command_offers: tuple[CommandOffer, ...] = ()
    surface: SurfaceView = UnavailableSurface(
        status="unavailable",
        reason_code="surface_not_configured",
    )
    public_steps: tuple[PublicStep, ...] = ()
    feed: tuple[FeedBlock, ...] = Field(default=(), max_length=128)
    checkpoint_id: str | None = Field(default=None, max_length=200)
    resume_eligible: bool = False
    last_control_outcome: ControlOutcome | None = None
    effect_reconciliation: EffectReconciliation | None = None
    control_owner: ControlOwner = ControlOwner.AGENT
    control_lease_id: str | None = Field(default=None, min_length=16, max_length=128)
    expires_at: datetime

    @model_validator(mode="after")
    def require_owner_offer_surface_invariants(self):
        kinds = tuple(offer.kind for offer in self.command_offers)
        if len(kinds) != len(set(kinds)):
            raise ValueError("command offers must be unique by kind")
        if len({block.block_id for block in self.feed}) != len(self.feed):
            raise ValueError("feed block identities must be unique")
        if any(block.occurred_at.tzinfo is None for block in self.feed):
            raise ValueError("feed block timestamps must be timezone-aware")
        if self.control_owner is ControlOwner.AGENT:
            if self.control_lease_id is not None or isinstance(self.surface, InteractiveSurface):
                raise ValueError("Agent control cannot retain interactive surface or user lease")
        else:
            if self.run_status is not RunStatus.PAUSED or self.control_lease_id is None:
                raise ValueError("user control requires one paused opaque lease")
        if isinstance(self.surface, InteractiveSurface) and (
            self.control_owner is not ControlOwner.USER or self.control_lease_id is None
        ):
            raise ValueError("interactive surface requires exact user control lease")
        return self

    @field_validator("expires_at")
    @classmethod
    def require_aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return value


class SnapshotUpdated(StrictModel):
    schema_version: Literal["interaction-shell.v4"]
    type: Literal["snapshot.updated"]
    session_id: str
    event_epoch: str = Field(min_length=16, max_length=128)
    cursor: int = Field(ge=1)
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    snapshot: RuntimeSessionSnapshot
    feed_delta: tuple[FeedBlock, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def require_causal_snapshot(self):
        if self.snapshot.session_id != self.session_id:
            raise ValueError("event snapshot session identity mismatch")
        if self.snapshot.event_epoch != self.event_epoch or self.snapshot.event_cursor < self.cursor:
            raise ValueError("event snapshot currentness mismatch")
        if len({block.block_id for block in self.feed_delta}) != len(self.feed_delta):
            raise ValueError("event feed delta identities must be unique")
        if any(block.occurred_at != self.emitted_at for block in self.feed_delta):
            raise ValueError("event feed delta must share the source event timestamp")
        return self


ShellEvent: TypeAlias = Annotated[SnapshotUpdated, Field(discriminator="type")]
SHELL_EVENT_ADAPTER = TypeAdapter(ShellEvent)


class ShellEventEnvelope(StrictModel):
    type: Literal["CUSTOM"]
    name: Literal["snapshot.updated"]
    value: SnapshotUpdated


class CommandBase(StrictModel):
    command_id: str = Field(min_length=1, max_length=128)
    expected_task_revision: int = Field(ge=0)
    expected_run_status: RunStatus


class StartTask(CommandBase):
    kind: Literal["start_task"]
    task: str = Field(min_length=1, max_length=8000)


class AnswerQuestion(CommandBase):
    kind: Literal["answer_question"]
    request_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(min_length=1, max_length=4000)


class RespondInteraction(CommandBase):
    kind: Literal["respond_interaction"]
    request_id: str = Field(min_length=1, max_length=128)
    response: InteractionResponse

    @model_validator(mode="after")
    def require_matching_request(self):
        if self.response.request_id != self.request_id:
            raise ValueError("interaction command request identity mismatch")
        return self


class ApproveAction(CommandBase):
    kind: Literal["approve_action"]
    request_id: str = Field(min_length=1, max_length=128)


class RejectAction(CommandBase):
    kind: Literal["reject_action"]
    request_id: str = Field(min_length=1, max_length=128)


class CancelTask(CommandBase):
    kind: Literal["cancel_task"]


class PauseTask(CommandBase):
    kind: Literal["pause_task"]


class ResumeTask(CommandBase):
    kind: Literal["resume_task"]
    checkpoint_id: str = Field(min_length=1, max_length=200)


class ReviseTask(CommandBase):
    kind: Literal["revise_task"]
    expected_checkpoint_id: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=8000)
    conversation: RevisionConversationContext | None = None

    @field_validator("text")
    @classmethod
    def bound_revision_text_bytes(cls, value: str) -> str:
        if not value.strip() or len(value.encode("utf-8")) > REVISION_CONVERSATION_MAX_TEXT_BYTES:
            raise ValueError("revision text is blank or exceeds its UTF-8 byte bound")
        return value


class TakeOver(CommandBase):
    kind: Literal["take_over"]
    checkpoint_id: str = Field(min_length=1, max_length=200)


class ReturnControl(CommandBase):
    kind: Literal["return_control"]
    control_lease_id: str = Field(min_length=16, max_length=128)


class CloseSession(CommandBase):
    kind: Literal["close_session"]


ShellCommand: TypeAlias = Annotated[
    StartTask
    | AnswerQuestion
    | RespondInteraction
    | ApproveAction
    | RejectAction
    | CancelTask
    | PauseTask
    | ResumeTask
    | ReviseTask
    | TakeOver
    | ReturnControl
    | CloseSession,
    Field(discriminator="kind"),
]
SHELL_COMMAND_ADAPTER = TypeAdapter(ShellCommand)


ConflictCode: TypeAlias = Literal[
    "stale_command",
    "command_identity_reused",
    "interaction_ref_mismatch",
    "checkpoint_mismatch",
    "checkpoint_already_consumed",
    "session_closed",
    "session_state_conflict",
    "control_owner_conflict",
    "control_lease_mismatch",
]
UnsupportedCode: TypeAlias = Literal[
    "command_not_supported",
    "deployment_capability_unavailable",
]
RejectedCode: TypeAlias = Literal[
    "command_processing_failed",
    "command_persistence_failed",
    "command_projection_failed",
    "internal_contract_failure",
    "interaction_response_invalid",
]


class Accepted(StrictModel):
    kind: Literal["accepted"]
    command_id: str
    snapshot: RuntimeSessionSnapshot


class Conflict(StrictModel):
    kind: Literal["conflict"]
    command_id: str
    code: ConflictCode
    snapshot: RuntimeSessionSnapshot


class Unsupported(StrictModel):
    kind: Literal["unsupported"]
    command_id: str
    code: UnsupportedCode
    snapshot: RuntimeSessionSnapshot


class Rejected(StrictModel):
    kind: Literal["rejected"]
    command_id: str
    code: RejectedCode
    snapshot: RuntimeSessionSnapshot


CommandAdmission: TypeAlias = Annotated[
    Accepted | Conflict | Unsupported | Rejected,
    Field(discriminator="kind"),
]
COMMAND_ADMISSION_ADAPTER = TypeAdapter(CommandAdmission)


class CreateSessionRequest(StrictModel):
    ttl_seconds: int = Field(default=1800, ge=60, le=86400)


class CreateSessionResponse(StrictModel):
    session_key: str
    snapshot: RuntimeSessionSnapshot


class LiveSession(StrictModel):
    kind: Literal["live_session"]
    snapshot: RuntimeSessionSnapshot


class RecoveryRequired(StrictModel):
    kind: Literal["recovery_required"]
    checkpoint_id: str = Field(min_length=1, max_length=200)


class RecoveryUnavailable(StrictModel):
    kind: Literal["recovery_unavailable"]
    reason_code: Literal[
        "checkpoint_not_found",
        "checkpoint_consumed",
        "checkpoint_unavailable",
    ]


class RecoveryUnsupported(StrictModel):
    kind: Literal["recovery_unsupported"]
    reason_code: Literal[
        "recovery_registry_unavailable",
        "checkpoint_store_unavailable",
        "recovery_reconnector_unavailable",
    ]


class RecoveryInspectionFailed(StrictModel):
    kind: Literal["recovery_inspection_failed"]
    reason_code: Literal["checkpoint_inspection_failed"]
    retryable: bool = False


AuthenticatedSessionLookup: TypeAlias = Annotated[
    LiveSession
    | RecoveryRequired
    | RecoveryUnavailable
    | RecoveryUnsupported
    | RecoveryInspectionFailed,
    Field(discriminator="kind"),
]


class RecoverSessionRequest(StrictModel):
    checkpoint_id: str = Field(min_length=1, max_length=200)


class Recovered(StrictModel):
    kind: Literal["recovered"]
    snapshot: RuntimeSessionSnapshot


class RecoveryConflict(StrictModel):
    kind: Literal["recovery_conflict"]
    reason_code: Literal[
        "checkpoint_already_resumed",
        "checkpoint_already_revised",
        "checkpoint_mismatch",
    ]
    retryable: Literal[False] = False


class RecoveryAttemptUnavailable(StrictModel):
    kind: Literal["recovery_unavailable"]
    reason_code: Literal[
        "checkpoint_not_found",
        "checkpoint_unavailable",
        "recovery_unsupported",
        "environment_not_reconnectable",
    ]
    retryable: Literal[False] = False


class RecoveryFailed(StrictModel):
    kind: Literal["recovery_failed"]
    reason_code: Literal[
        "checkpoint_store_failed",
        "runtime_factory_failed",
        "environment_reconnect_failed",
        "session_restore_failed",
        "shell_projection_restore_failed",
    ]
    retryable: bool = False


RecoveryAttempt: TypeAlias = Annotated[
    Recovered | RecoveryConflict | RecoveryAttemptUnavailable | RecoveryFailed,
    Field(discriminator="kind"),
]


def _same_origin_path(value: str) -> str:
    if not value.startswith("/") or any(marker in value for marker in ("?", "#", "://")):
        raise ValueError("surface path must be same-origin and secret-free")
    return value
