"""公共 Session 的版本化合同。

这里只定义稳定的命令、结果、快照、事件和环境端口，不推进运行状态。
``TargetRuntimeSession`` 是状态 authority；本模块中的类型只约束边界。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, TypeAlias

from affordance_runtime.agent.interactions import (
    BooleanFieldValue,
    DateFieldValue,
    DecimalFieldValue,
    FreeTextResponse,
    IntegerFieldValue,
    InteractionField,
    InteractionOption,
    InteractionResponse,
    MultiSelectionResponse,
    PublicArtifact,
    SingleSelectionResponse,
    StructuredFieldsResponse,
    TextFieldValue,
    interaction_response_public_value,
)
from affordance_runtime.task.intake import (
    NaturalLanguageTaskRequest,
    TaskBoundary,
)
from affordance_runtime.task.revision import (
    REVISION_CONVERSATION_MAX_TEXT_BYTES,
    RevisionConversationContext,
    RevisionConversationTurn,
)
from affordance_runtime.world.environment import WorldEnvironment

from .runtime import TargetRuntime

PUBLIC_SESSION_SCHEMA_VERSION = "affordance-runtime.session.v2"
PUBLIC_SESSION_V3_SCHEMA_VERSION = "affordance-runtime.session.v3"
# Revision 命令身份是独立版本化的持久 wire fact。快照增加展示字段时，
# 不得改变既有 revision 命令 payload 的 digest，否则重放会失去幂等语义。
_PUBLIC_REVISION_COMMAND_DIGEST_VERSION = "affordance-runtime.session.v1"
PublicRevisionConversationContext = RevisionConversationContext
PublicRevisionConversationTurn = RevisionConversationTurn


class PublicSessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_USER = "waiting_user"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class PublicTaskRevisionCommand:
    """Runtime 拥有的完整 revision 命令及其规范化身份。"""

    command_id: str
    expected_task_revision: int
    expected_run_status: PublicSessionStatus
    expected_checkpoint_id: str | None
    text: str
    conversation: RevisionConversationContext

    def __post_init__(self) -> None:
        if (
            not self.command_id.strip()
            or len(self.command_id) > 128
            or type(self.expected_task_revision) is not int
            or self.expected_task_revision < 0
            or not isinstance(self.expected_run_status, PublicSessionStatus)
            or (
                self.expected_checkpoint_id is not None
                and (
                    len(self.expected_checkpoint_id) > 200
                    or not self.expected_checkpoint_id.startswith("runtime-checkpoint:")
                )
            )
            or not self.text.strip()
            or len(self.text) > 8000
            or len(self.text.encode("utf-8")) > REVISION_CONVERSATION_MAX_TEXT_BYTES
            or not isinstance(self.conversation, RevisionConversationContext)
            or self.conversation.latest_turn.text != self.text
        ):
            raise ValueError("public task revision command is invalid")

    @property
    def payload_digest(self) -> str:
        payload = {
            "expected_checkpoint_id": self.expected_checkpoint_id,
            "expected_run_status": self.expected_run_status.value,
            "expected_task_revision": self.expected_task_revision,
            "kind": "revise_task",
            "schema_version": _PUBLIC_REVISION_COMMAND_DIGEST_VERSION,
            "conversation": {
                "latest_turn_id": self.conversation.latest_turn_id,
                "turns": [
                    {
                        "role": turn.role,
                        "text": turn.text,
                        "turn_id": turn.turn_id,
                    }
                    for turn in self.conversation.turns
                ],
            },
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PublicSessionCapability(StrEnum):
    START_TASK = "start_task"
    ANSWER_QUESTION = "answer_question"
    RESPOND_INTERACTION = "respond_interaction"
    APPROVE_ACTION = "approve_action"
    REJECT_ACTION = "reject_action"
    CANCEL_TASK = "cancel_task"
    PAUSE_TASK = "pause_task"
    RESUME_TASK = "resume_task"
    REVISE_TASK = "revise_task"
    TAKE_OVER = "take_over"
    RETURN_CONTROL = "return_control"
    CLOSE_SESSION = "close_session"


class PublicSessionCommandKind(StrEnum):
    START_TASK = "start_task"
    ANSWER_QUESTION = "answer_question"
    RESPOND_INTERACTION = "respond_interaction"
    APPROVE_ACTION = "approve_action"
    REJECT_ACTION = "reject_action"
    CANCEL_TASK = "cancel_task"
    PAUSE_TASK = "pause_task"
    RESUME_TASK = "resume_task"
    REVISE_TASK = "revise_task"
    TAKE_OVER = "take_over"
    RETURN_CONTROL = "return_control"
    CLOSE_SESSION = "close_session"


@dataclass(frozen=True)
class PublicSessionCommandCapability:
    """与当前状态一致的 v3 命令能力；其中引用值仍由 Runtime 持有。"""

    kind: PublicSessionCommandKind
    interaction_ref: str | None = None
    prompt: str = ""
    summary: str = ""
    risk: str = ""

    def __post_init__(self) -> None:
        interaction_kind = self.kind in {
            PublicSessionCommandKind.ANSWER_QUESTION,
            PublicSessionCommandKind.RESPOND_INTERACTION,
            PublicSessionCommandKind.APPROVE_ACTION,
            PublicSessionCommandKind.REJECT_ACTION,
        }
        if interaction_kind != (self.interaction_ref is not None):
            raise ValueError("interaction capability ref placement is invalid")
        if self.kind in {
            PublicSessionCommandKind.ANSWER_QUESTION,
            PublicSessionCommandKind.RESPOND_INTERACTION,
        }:
            if not self.prompt or self.summary or self.risk:
                raise ValueError("answer capability presentation is invalid")
        elif self.kind in {
            PublicSessionCommandKind.APPROVE_ACTION,
            PublicSessionCommandKind.REJECT_ACTION,
        }:
            if not self.summary or not self.risk or self.prompt:
                raise ValueError("confirmation capability presentation is invalid")
        elif self.prompt or self.summary or self.risk:
            raise ValueError("non-interaction capability cannot carry presentation")


@dataclass(frozen=True)
class PublicSessionCommand:
    """v3 公共边界使用的闭合语义命令，命令含义由 Runtime 拥有。"""

    command_id: str
    kind: PublicSessionCommandKind
    expected_task_revision: int
    expected_run_status: PublicSessionStatus
    task: str = ""
    interaction_ref: str = ""
    answer: str = ""
    response: InteractionResponse | None = None
    checkpoint_id: str = ""
    control_lease_id: str = ""
    revision: PublicTaskRevisionCommand | None = None

    def __post_init__(self) -> None:
        if (
            not self.command_id.strip()
            or len(self.command_id) > 128
            or type(self.expected_task_revision) is not int
            or self.expected_task_revision < 0
            or not isinstance(self.expected_run_status, PublicSessionStatus)
        ):
            raise ValueError("public session command identity/currentness is invalid")
        if self.kind is PublicSessionCommandKind.ANSWER_QUESTION:
            object.__setattr__(self, "kind", PublicSessionCommandKind.RESPOND_INTERACTION)
        if self.kind is PublicSessionCommandKind.RESPOND_INTERACTION and self.response is None and self.answer.strip():
            object.__setattr__(self, "response", FreeTextResponse(self.interaction_ref, self.answer))
            object.__setattr__(self, "answer", "")
        required: dict[PublicSessionCommandKind, tuple[bool, ...]] = {
            PublicSessionCommandKind.START_TASK: (bool(self.task.strip()),),
            PublicSessionCommandKind.RESPOND_INTERACTION: (
                bool(self.interaction_ref.strip()),
                self.response is not None,
            ),
            PublicSessionCommandKind.APPROVE_ACTION: (bool(self.interaction_ref.strip()),),
            PublicSessionCommandKind.REJECT_ACTION: (bool(self.interaction_ref.strip()),),
            PublicSessionCommandKind.RESUME_TASK: (bool(self.checkpoint_id.strip()),),
            PublicSessionCommandKind.RETURN_CONTROL: (bool(self.control_lease_id.strip()),),
            PublicSessionCommandKind.REVISE_TASK: (self.revision is not None,),
        }
        if not all(required.get(self.kind, (True,))):
            raise ValueError("public session command payload is incomplete")
        if self.response is not None and (
            self.kind is not PublicSessionCommandKind.RESPOND_INTERACTION
            or self.response.request_id != self.interaction_ref
        ):
            raise ValueError("interaction response placement is invalid")
        if self.kind is PublicSessionCommandKind.REVISE_TASK:
            if self.revision is None or self.revision.command_id != self.command_id:
                raise ValueError("public revision command identity is invalid")
        elif self.revision is not None:
            raise ValueError("only revise_task can carry a revision command")

    @property
    def payload_digest(self) -> str:
        payload: dict[str, object] = {
            "answer": self.answer,
            "checkpoint_id": self.checkpoint_id,
            "control_lease_id": self.control_lease_id,
            "expected_run_status": self.expected_run_status.value,
            "expected_task_revision": self.expected_task_revision,
            "interaction_ref": self.interaction_ref,
            "kind": self.kind.value,
            "schema_version": PUBLIC_SESSION_V3_SCHEMA_VERSION,
            "task": self.task,
        }
        if self.response is not None:
            payload["response"] = interaction_response_public_value(self.response)
        if self.revision is not None:
            payload["revision_digest"] = self.revision.payload_digest
        canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


PublicConflictCode: TypeAlias = Literal[
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
PublicUnsupportedCode: TypeAlias = Literal["command_not_supported"]
PublicRejectedCode: TypeAlias = Literal[
    "command_processing_failed",
    "command_persistence_failed",
    "command_projection_failed",
    "internal_contract_failure",
    "interaction_response_invalid",
]


@dataclass(frozen=True)
class PublicCommandAccepted:
    kind: Literal["accepted"]
    command_id: str
    snapshot: PublicRuntimeSessionSnapshot


@dataclass(frozen=True)
class PublicCommandConflict:
    kind: Literal["conflict"]
    command_id: str
    code: PublicConflictCode
    snapshot: PublicRuntimeSessionSnapshot


@dataclass(frozen=True)
class PublicCommandUnsupported:
    kind: Literal["unsupported"]
    command_id: str
    code: PublicUnsupportedCode
    snapshot: PublicRuntimeSessionSnapshot


@dataclass(frozen=True)
class PublicCommandRejected:
    kind: Literal["rejected"]
    command_id: str
    code: PublicRejectedCode
    snapshot: PublicRuntimeSessionSnapshot


PublicCommandAdmission: TypeAlias = (
    PublicCommandAccepted | PublicCommandConflict | PublicCommandUnsupported | PublicCommandRejected
)


def public_interaction_response_from_value(
    value: Mapping[str, object],
) -> InteractionResponse:
    """只在 PublicSession 边界把闭合 wire value 转成 typed response。"""

    try:
        payload = dict(value)
        kind = str(payload["kind"])
        request_id = str(payload["request_id"])
        if kind == "free_text" and set(payload) == {"kind", "request_id", "text"}:
            return FreeTextResponse(request_id, str(payload["text"]))
        if kind == "single_select" and set(payload) == {
            "kind",
            "request_id",
            "option_id",
        }:
            return SingleSelectionResponse(request_id, str(payload["option_id"]))
        if kind == "multi_select" and set(payload) == {
            "kind",
            "request_id",
            "option_ids",
        }:
            values = payload["option_ids"]
            if not isinstance(values, list | tuple):
                raise TypeError("multi-select options must be a sequence")
            return MultiSelectionResponse(request_id, tuple(str(item) for item in values))
        if kind != "structured_fields" or set(payload) != {
            "kind",
            "request_id",
            "values",
        }:
            raise ValueError("unsupported public interaction response kind")
        raw_values = payload["values"]
        if not isinstance(raw_values, list | tuple):
            raise TypeError("structured interaction values must be a sequence")
        values = tuple(_public_interaction_field_value(item) for item in raw_values)
        return StructuredFieldsResponse(request_id, values)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("public interaction response is invalid") from exc


PUBLIC_SESSION_CAPABILITIES = frozenset(
    item for item in PublicSessionCapability if item is not PublicSessionCapability.ANSWER_QUESTION
)
BASE_PUBLIC_SESSION_CAPABILITIES = PUBLIC_SESSION_CAPABILITIES - {
    PublicSessionCapability.PAUSE_TASK,
    PublicSessionCapability.RESUME_TASK,
    PublicSessionCapability.REVISE_TASK,
    PublicSessionCapability.TAKE_OVER,
    PublicSessionCapability.RETURN_CONTROL,
}


class PublicSessionControlOwner(StrEnum):
    AGENT = "agent"
    USER = "user"


@dataclass(frozen=True)
class PublicInteractionRequest:
    request_id: str
    prompt: str
    response_kind: str
    fields: tuple[InteractionField, ...] = ()
    options: tuple[InteractionOption, ...] = ()
    public_intent: str = ""

    @property
    def interrupt_id(self) -> str:
        return self.request_id

    @property
    def requested_fields(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.fields)


@dataclass(frozen=True)
class PublicPendingConfirmation:
    interrupt_id: str
    summary: str
    risk: str


@dataclass(frozen=True)
class PublicCompletion:
    outcome: Literal["success", "failure", "blocked", "cancelled"]
    code: str
    message: str
    evidence_refs: tuple[str, ...] = ()
    artifact: PublicArtifact | None = None


@dataclass(frozen=True)
class PublicUserTurn:
    kind: Literal["user_turn"] = field(default="user_turn", init=False)
    source_id: str
    content: str

    def __post_init__(self) -> None:
        _validate_feed_text(self.source_id, self.content, 8_000)


@dataclass(frozen=True)
class PublicGoalAccepted:
    kind: Literal["goal_accepted"] = field(default="goal_accepted", init=False)
    source_id: str
    task_revision: int
    summary: str
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_feed_text(self.source_id, self.summary, 8_000)
        object.__setattr__(self, "constraints", tuple(self.constraints))
        if (
            self.task_revision < 1
            or len(self.constraints) > 32
            or any(not item.strip() or len(item) > 1_000 for item in self.constraints)
        ):
            raise ValueError("public goal feed source is invalid")


@dataclass(frozen=True)
class PublicAgentIntent:
    kind: Literal["agent_intent"] = field(default="agent_intent", init=False)
    source_id: str
    content: str

    def __post_init__(self) -> None:
        _validate_feed_text(self.source_id, self.content, 240)


@dataclass(frozen=True)
class PublicRuntimeActivity:
    kind: Literal["runtime_activity"] = field(default="runtime_activity", init=False)
    source_id: str
    status: Literal["started", "completed", "uncertain", "failed"]
    label: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_feed_text(self.source_id, self.label, 500)
        _validate_public_refs(self.evidence_refs)


@dataclass(frozen=True)
class PublicEvidenceSummary:
    kind: Literal["evidence_summary"] = field(default="evidence_summary", init=False)
    source_id: str
    evidence_kind: Literal["structural", "visual", "frame_change", "mixed", "unknown"]
    status: Literal["observed", "partial", "unknown", "failed", "stale"]
    message: str
    confidence: float | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_feed_text(self.source_id, self.message, 500)
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("public evidence confidence is invalid")
        _validate_public_refs(self.evidence_refs)


@dataclass(frozen=True)
class PublicInteractionRequested:
    kind: Literal["interaction_request"] = field(default="interaction_request", init=False)
    source_id: str
    request: PublicInteractionRequest

    def __post_init__(self) -> None:
        _validate_feed_source_id(self.source_id)
        if not isinstance(self.request, PublicInteractionRequest):
            raise TypeError("public interaction feed source must be typed")


@dataclass(frozen=True)
class PublicRevisionApplied:
    kind: Literal["revision_applied"] = field(default="revision_applied", init=False)
    source_id: str
    task_revision: int
    goal_description_changed: bool = False
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    retained: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_feed_source_id(self.source_id)
        if self.task_revision < 2 or type(self.goal_description_changed) is not bool:
            raise ValueError("public revision feed source is invalid")
        for name in ("added", "removed", "retained"):
            values = tuple(getattr(self, name))
            object.__setattr__(self, name, values)
            if len(values) > 32 or any(not item.strip() or len(item) > 1_000 for item in values):
                raise ValueError("public revision diff exceeds its bounds")


@dataclass(frozen=True)
class PublicConfirmationRequired:
    kind: Literal["confirmation_required"] = field(default="confirmation_required", init=False)
    source_id: str
    confirmation: PublicPendingConfirmation

    def __post_init__(self) -> None:
        _validate_feed_source_id(self.source_id)
        if not isinstance(self.confirmation, PublicPendingConfirmation):
            raise TypeError("public confirmation feed source must be typed")


@dataclass(frozen=True)
class PublicCompletionBlock:
    kind: Literal["completion"] = field(default="completion", init=False)
    source_id: str
    completion: PublicCompletion

    def __post_init__(self) -> None:
        _validate_feed_source_id(self.source_id)
        if not isinstance(self.completion, PublicCompletion):
            raise TypeError("public completion feed source must be typed")


@dataclass(frozen=True)
class PublicFailure:
    kind: Literal["failure"] = field(default="failure", init=False)
    source_id: str
    code: str
    message: str

    def __post_init__(self) -> None:
        _validate_feed_source_id(self.source_id)
        if not self.code.strip() or len(self.code) > 128 or not self.message.strip() or len(self.message) > 2_000:
            raise ValueError("public failure feed source is invalid")


PublicFeedSource: TypeAlias = (
    PublicUserTurn
    | PublicGoalAccepted
    | PublicAgentIntent
    | PublicRuntimeActivity
    | PublicEvidenceSummary
    | PublicInteractionRequested
    | PublicRevisionApplied
    | PublicConfirmationRequired
    | PublicCompletionBlock
    | PublicFailure
)
_PUBLIC_FEED_SOURCE_TYPES = (
    PublicUserTurn,
    PublicGoalAccepted,
    PublicAgentIntent,
    PublicRuntimeActivity,
    PublicEvidenceSummary,
    PublicInteractionRequested,
    PublicRevisionApplied,
    PublicConfirmationRequired,
    PublicCompletionBlock,
    PublicFailure,
)


@dataclass(frozen=True)
class PublicProgressStep:
    step: int
    status: str
    label: str


@dataclass(frozen=True)
class PublicControlOutcome:
    command_id: str
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
    code: str
    checkpoint_id: str | None = None
    message: str = ""


@dataclass(frozen=True)
class PublicEffectReconciliation:
    status: Literal["pending", "compensated", "needs_input"]
    code: str
    original_effect_ref: str
    original_action: str
    resource_ref: str
    reversibility: Literal["reversible", "compensatable", "irreversible", "unknown"]
    compensation_effect_ref: str = ""


@dataclass(frozen=True)
class PublicRuntimeSessionSnapshot:
    session_id: str
    expires_at: datetime
    status: PublicSessionStatus
    event_epoch: str
    event_cursor: int
    capabilities: frozenset[PublicSessionCapability] = BASE_PUBLIC_SESSION_CAPABILITIES
    command_capabilities: tuple[PublicSessionCommandCapability, ...] = ()
    task_id: str | None = None
    task_revision: int = 0
    task_text: str | None = None
    pending_interaction: PublicInteractionRequest | None = None
    pending_confirmation: PublicPendingConfirmation | None = None
    completion: PublicCompletion | None = None
    progress: tuple[PublicProgressStep, ...] = ()
    checkpoint_id: str | None = None
    resume_eligible: bool = False
    last_control_outcome: PublicControlOutcome | None = None
    effect_reconciliation: PublicEffectReconciliation | None = None
    control_owner: PublicSessionControlOwner = PublicSessionControlOwner.AGENT
    control_lease_id: str | None = None
    schema_version: str = PUBLIC_SESSION_SCHEMA_VERSION

    @property
    def pending_question(self) -> PublicInteractionRequest | None:
        """供 v4 之前 Shell adapter 使用的只读兼容投影。"""

        return self.pending_interaction


@dataclass(frozen=True)
class PublicRuntimeSessionEvent:
    session_id: str
    event_epoch: str
    cursor: int
    type: str
    snapshot: PublicRuntimeSessionSnapshot
    feed_sources: tuple[PublicFeedSource, ...] = ()
    emitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = PUBLIC_SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "feed_sources", tuple(self.feed_sources))
        expected_prefix = f"feed:{self.event_epoch}:{self.cursor}:"
        if any(
            not isinstance(source, _PUBLIC_FEED_SOURCE_TYPES) or not source.source_id.startswith(expected_prefix)
            for source in self.feed_sources
        ):
            raise ValueError("public event feed sources must match the event identity")


class PublicSessionConflict(RuntimeError):
    def __init__(self, code: str, snapshot: PublicRuntimeSessionSnapshot) -> None:
        self.code = code
        self.snapshot = snapshot
        super().__init__(code)


class PublicSessionOpenStage(StrEnum):
    RUNTIME = "runtime"
    ENVIRONMENT = "environment"
    SESSION = "session"


class PublicSessionOpenError(RuntimeError):
    """不泄露私有资源的 typed Session 构造失败。"""

    def __init__(self, stage: PublicSessionOpenStage, code: str) -> None:
        self.stage = stage
        self.code = code
        super().__init__(f"{stage.value}:{code}")


@dataclass(frozen=True)
class RuntimeEnvironmentLease:
    environment: WorldEnvironment
    cleanup: Callable[[], object] | None = None
    reconnect_reference: str = ""


class RuntimeEnvironmentFactory(Protocol):
    def __call__(self, session_id: str) -> RuntimeEnvironmentLease | Awaitable[RuntimeEnvironmentLease]: ...


class RuntimeEnvironmentReconnectFactory(Protocol):
    def __call__(
        self, session_id: str, reconnect_reference: str
    ) -> RuntimeEnvironmentLease | Awaitable[RuntimeEnvironmentLease]: ...


class TargetRuntimeFactory(Protocol):
    def __call__(self, session_id: str) -> TargetRuntime | Awaitable[TargetRuntime]: ...


class PublicTaskRequestFactory(Protocol):
    def __call__(self, session_id: str, instruction: str) -> NaturalLanguageTaskRequest: ...


def default_public_task_request(session_id: str, instruction: str) -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(session_id, instruction, TaskBoundary())


class PublicRuntimeSessionHandle(Protocol):
    async def snapshot(self) -> PublicRuntimeSessionSnapshot: ...
    async def events(self, after: int) -> tuple[PublicRuntimeSessionEvent, ...]: ...
    async def admits_surface_input(self, control_lease_id: str) -> bool: ...
    async def inspect_live_checkpoint(self, checkpoint_id: str) -> LiveCheckpointAdmission: ...
    async def start(self, instruction: str) -> PublicRuntimeSessionSnapshot: ...
    async def respond(self, response: InteractionResponse) -> PublicRuntimeSessionSnapshot: ...

    async def answer(self, interrupt_id: str, answer: str) -> PublicRuntimeSessionSnapshot: ...
    async def confirm(self, interrupt_id: str, *, approved: bool) -> PublicRuntimeSessionSnapshot: ...
    async def cancel(self, command_id: str) -> PublicRuntimeSessionSnapshot: ...
    async def pause(self, command_id: str) -> PublicRuntimeSessionSnapshot: ...
    async def resume(self, command_id: str, checkpoint_id: str) -> PublicRuntimeSessionSnapshot: ...
    async def revise(self, command: PublicTaskRevisionCommand) -> PublicRuntimeSessionSnapshot: ...
    async def take_over(
        self,
        command_id: str,
        checkpoint_id: str = "",
    ) -> PublicRuntimeSessionSnapshot: ...
    async def return_control(self, command_id: str, control_lease_id: str) -> PublicRuntimeSessionSnapshot: ...
    async def admit(self, command: PublicSessionCommand) -> PublicCommandAdmission: ...
    async def close(self) -> None: ...


class PublicRuntimeSessionFactory(Protocol):
    async def open(self, session_id: str, expires_at: datetime) -> PublicRuntimeSessionHandle: ...
    async def inspect(self, session_id: str) -> RuntimeRecoveryInspection: ...
    async def recover_typed(
        self, session_id: str, checkpoint_id: str, expires_at: datetime
    ) -> RuntimeRecoveryAttempt: ...
    async def recover(
        self, session_id: str, checkpoint_id: str, expires_at: datetime
    ) -> PublicRuntimeSessionHandle: ...


@dataclass(frozen=True)
class RecoverableCheckpoint:
    kind: Literal["recoverable_checkpoint"]
    checkpoint_id: str


@dataclass(frozen=True)
class RecoveryInspectionUnavailable:
    kind: Literal["recovery_inspection_unavailable"]
    reason_code: Literal["checkpoint_not_found", "checkpoint_consumed", "checkpoint_unavailable"]


@dataclass(frozen=True)
class RecoveryInspectionUnsupported:
    kind: Literal["recovery_inspection_unsupported"]
    reason_code: Literal["checkpoint_store_unavailable", "recovery_reconnector_unavailable"]


@dataclass(frozen=True)
class RecoveryInspectionFailed:
    kind: Literal["recovery_inspection_failed"]
    reason_code: Literal["checkpoint_inspection_failed"]
    retryable: bool = False


RuntimeRecoveryInspection: TypeAlias = (
    RecoverableCheckpoint | RecoveryInspectionUnavailable | RecoveryInspectionUnsupported | RecoveryInspectionFailed
)


class PublicRuntimeRecoveryInspector(Protocol):
    async def inspect(self, session_id: str) -> RuntimeRecoveryInspection: ...


@dataclass(frozen=True)
class RuntimeRecovered:
    kind: Literal["recovered"]
    handle: PublicRuntimeSessionHandle


@dataclass(frozen=True)
class RuntimeRecoveryConflict:
    kind: Literal["recovery_conflict"]
    reason_code: Literal[
        "checkpoint_already_resumed",
        "checkpoint_already_revised",
        "checkpoint_mismatch",
    ]


@dataclass(frozen=True)
class RuntimeRecoveryUnavailable:
    kind: Literal["recovery_unavailable"]
    reason_code: Literal[
        "checkpoint_not_found",
        "checkpoint_unavailable",
        "recovery_unsupported",
        "environment_not_reconnectable",
    ]


@dataclass(frozen=True)
class RuntimeRecoveryFailed:
    kind: Literal["recovery_failed"]
    reason_code: Literal[
        "checkpoint_store_failed",
        "runtime_factory_failed",
        "environment_reconnect_failed",
        "session_restore_failed",
    ]
    retryable: bool = False


RuntimeRecoveryAttempt: TypeAlias = (
    RuntimeRecovered | RuntimeRecoveryConflict | RuntimeRecoveryUnavailable | RuntimeRecoveryFailed
)


@dataclass(frozen=True)
class LiveCheckpointCurrent:
    kind: Literal["live_checkpoint_current"]
    snapshot: PublicRuntimeSessionSnapshot


@dataclass(frozen=True)
class LiveCheckpointConflict:
    kind: Literal["live_checkpoint_conflict"]
    reason_code: Literal["checkpoint_mismatch"]


@dataclass(frozen=True)
class LiveCheckpointUnavailable:
    kind: Literal["live_checkpoint_unavailable"]
    reason_code: Literal["checkpoint_unavailable"]


LiveCheckpointAdmission: TypeAlias = LiveCheckpointCurrent | LiveCheckpointConflict | LiveCheckpointUnavailable


def _public_interaction_field_value(
    value: object,
) -> TextFieldValue | IntegerFieldValue | DecimalFieldValue | BooleanFieldValue | DateFieldValue:
    """在公共合同 owner 内把 wire 字段值规范化为闭合类型。"""

    if not isinstance(value, Mapping):
        raise TypeError("interaction field value must be an object")
    payload = dict(value)
    kind = str(payload.get("kind", ""))
    field_id = str(payload.get("field_id", ""))
    field_name = {
        "text": "text",
        "integer": "integer",
        "decimal": "decimal_string",
        "boolean": "boolean",
        "date": "iso_date",
    }.get(kind)
    if field_name is None:
        raise ValueError("interaction field value kind is unsupported")
    if set(payload) != {"kind", "field_id", field_name}:
        raise ValueError("interaction field value shape is invalid")
    raw = payload[field_name]
    if kind == "integer" and type(raw) is not int:
        raise TypeError("integer interaction field value is invalid")
    if kind == "boolean" and type(raw) is not bool:
        raise TypeError("boolean interaction field value is invalid")
    if kind == "text":
        return TextFieldValue(field_id, str(raw))
    if kind == "integer":
        return IntegerFieldValue(field_id, raw)
    if kind == "decimal":
        return DecimalFieldValue(field_id, str(raw))
    if kind == "boolean":
        return BooleanFieldValue(field_id, raw)
    return DateFieldValue(field_id, str(raw))


def _validate_feed_source_id(source_id: str) -> None:
    """校验公共 feed 身份；投影层不得自行放宽该 wire 合同。"""

    if not source_id.startswith("feed:") or len(source_id) > 256:
        raise ValueError("public feed source identity is invalid")


def _validate_feed_text(source_id: str, content: str, limit: int) -> None:
    _validate_feed_source_id(source_id)
    if not content.strip() or len(content) > limit:
        raise ValueError("public feed source text is invalid")


def _validate_public_refs(values: tuple[str, ...]) -> None:
    if (
        len(values) > 32
        or len(set(values)) != len(values)
        or any(not item.strip() or len(item) > 512 for item in values)
    ):
        raise ValueError("public feed evidence refs are invalid")
