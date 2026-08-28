"""Versioned public session boundary over the single TargetRuntime loop."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Protocol, TypeAlias, cast

from affordance_runtime.actions.reconciliation import (
    EffectReconciliation,
    EffectReconciliationStatus,
    EffectRevisionDisposition,
    assess_effect_revision,
)
from affordance_runtime.agent.decisions import FinalResponse, RequestObservation, SelectAction
from affordance_runtime.agent.interactions import (
    BooleanFieldValue,
    DateFieldValue,
    DecimalFieldValue,
    FreeTextResponse,
    IntegerFieldValue,
    InteractionAdmissionCode,
    InteractionField,
    InteractionOption,
    InteractionRequest,
    InteractionResponse,
    MultiSelectionResponse,
    PublicArtifact,
    SingleSelectionResponse,
    StructuredFieldsResponse,
    TextFieldValue,
    admit_interaction_response,
    interaction_response_public_value,
)
from affordance_runtime.agent.observability import FanoutRunTraceSink, NullRunTraceSink
from affordance_runtime.agent.policy import PolicyFailure
from affordance_runtime.agent.run_control import (
    RunControlAdmissionKind,
    RunControlKind,
    RunControlOutcomeKind,
)
from affordance_runtime.agent.run_state import RunState, RunStatus, StepResult
from affordance_runtime.evaluation.contracts import (
    EvidenceMethod,
    LocalPostconditionStatus,
    TaskEvaluationStatus,
    TaskOutcomeKind,
)
from affordance_runtime.execution.contracts import ExecutionCompletion
from affordance_runtime.risk.contracts import RiskAssessment
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.intake import (
    NaturalLanguageTaskRequest,
    ReadyTask,
    TaskBoundary,
    TaskInputRequired,
    TaskIntakeOutcome,
    TaskPolicyRejected,
    TaskUnsupported,
)
from affordance_runtime.task.revision import (
    REVISION_CONVERSATION_MAX_TEXT_BYTES,
    RevisionConversationContext,
    RevisionConversationTurn,
    RevisionFailed,
    RevisionNeedsInput,
    RevisionNewTaskSuggested,
    RevisionNoChange,
    RevisionReady,
    RevisionUnsupported,
    revision_outcome_code,
)
from affordance_runtime.world.environment import WorldEnvironment
from affordance_runtime.world.observation_outcomes import ObservationQueryDisposition

from .checkpoint import (
    RuntimeCheckpoint,
    RuntimeCheckpointCommandOutcome,
    RuntimeCheckpointError,
    RuntimeCheckpointResumeOutcome,
    RuntimeCheckpointRevisionOutcome,
    RuntimeCheckpointStore,
)
from .runtime import TargetRuntime, TargetRuntimeRunOutcome

PUBLIC_SESSION_SCHEMA_VERSION = "affordance-runtime.session.v2"
PUBLIC_SESSION_V3_SCHEMA_VERSION = "affordance-runtime.session.v3"
# Revision command identity is an independently versioned, durable wire fact.  The
# Phase 7 snapshot projection is additive and must not change digests already
# stored for the unchanged Phase 6 revision command payload.
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
    """Complete Runtime-owned revision command and its canonical identity."""

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
    """State-correct unpublished v3 command capability and Runtime-owned refs."""

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
    """Closed Runtime-owned semantic command used by the v3 public boundary."""

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
    """Convert the closed public wire value at the PublicSession boundary."""

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
        if self.task_revision < 1 or len(self.constraints) > 32 or any(
            not item.strip() or len(item) > 1_000 for item in self.constraints
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
    evidence_kind: Literal["structural", "visual", "mixed", "unknown"]
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
        """Read-only compatibility projection for pre-v4 Shell adapters."""

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
            not isinstance(source, _PUBLIC_FEED_SOURCE_TYPES)
            or not source.source_id.startswith(expected_prefix)
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
    """Typed session-construction failure without leaking private resources."""

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


@dataclass
class TargetRuntimeSession:
    """Own the private resumable state; callers receive public values only."""

    runtime: TargetRuntime
    lease: RuntimeEnvironmentLease
    session_id: str
    expires_at: datetime
    request_factory: PublicTaskRequestFactory = default_public_task_request
    checkpoint_store: RuntimeCheckpointStore | None = None
    _event_epoch: str = field(default_factory=lambda: secrets.token_urlsafe(18), init=False, repr=False)
    _request: NaturalLanguageTaskRequest | None = field(default=None, init=False, repr=False)
    _admitted: ReadyTask | None = field(default=None, init=False, repr=False)
    _state: RunState | None = field(default=None, init=False, repr=False)
    _status: PublicSessionStatus = field(default=PublicSessionStatus.IDLE, init=False, repr=False)
    _intake_question: PublicInteractionRequest | None = field(default=None, init=False, repr=False)
    _failure: PublicCompletion | None = field(default=None, init=False, repr=False)
    _checkpoint_id: str | None = field(default=None, init=False, repr=False)
    _resume_eligible: bool = field(default=False, init=False, repr=False)
    _last_control_outcome: PublicControlOutcome | None = field(default=None, init=False, repr=False)
    _control_owner: PublicSessionControlOwner = field(
        default=PublicSessionControlOwner.AGENT,
        init=False,
        repr=False,
    )
    _control_lease_id: str | None = field(default=None, init=False, repr=False)
    _control_return_in_progress: bool = field(default=False, init=False, repr=False)
    _progress: list[PublicProgressStep] = field(default_factory=list, init=False, repr=False)
    _events: list[PublicRuntimeSessionEvent] = field(default_factory=list, init=False, repr=False)
    _active: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _cleanup_started: bool = field(default=False, init=False, repr=False)
    _command_admissions: dict[str, tuple[str, PublicCommandAdmission]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.runtime, TargetRuntime):
            raise TypeError("public Runtime session requires a TargetRuntime")
        if not isinstance(self.lease, RuntimeEnvironmentLease):
            raise TypeError("public Runtime session requires a typed environment lease")
        required_environment_methods = ("reset", "revise_task", "capture", "is_current", "execute")
        if any(not callable(getattr(self.lease.environment, method, None)) for method in required_environment_methods):
            raise TypeError("public Runtime session environment does not implement WorldEnvironment")
        if not callable(self.request_factory):
            raise TypeError("public Runtime session requires a task request factory")

    async def snapshot(self) -> PublicRuntimeSessionSnapshot:
        return self._project()

    async def admits_surface_input(self, control_lease_id: str) -> bool:
        """Own exact live lease admission without exposing control semantics to Shell."""

        return (
            not self._closed
            and self._control_owner is PublicSessionControlOwner.USER
            and self._control_lease_id is not None
            and secrets.compare_digest(self._control_lease_id, control_lease_id)
        )

    async def admit(self, command: PublicSessionCommand) -> PublicCommandAdmission:
        """Own v3 command identity, semantic admission, and closed outcome conversion."""

        existing = self._command_admissions.get(command.command_id)
        if existing is not None:
            digest, admission = existing
            if secrets.compare_digest(digest, command.payload_digest):
                return admission
            return PublicCommandConflict(
                "conflict",
                command.command_id,
                "command_identity_reused",
                self._project(),
            )
        current = self._project()
        if current.task_revision != command.expected_task_revision or current.status is not command.expected_run_status:
            return PublicCommandConflict(
                "conflict",
                command.command_id,
                "stale_command",
                current,
            )
        supported = {capability.kind for capability in current.command_capabilities}
        if command.kind not in supported:
            code: PublicConflictCode = (
                "control_owner_conflict"
                if self._control_owner is PublicSessionControlOwner.USER
                else "session_state_conflict"
            )
            return PublicCommandConflict("conflict", command.command_id, code, current)
        try:
            admission = await self._execute_admitted_command(command)
        except PublicSessionConflict as exc:
            admission = _convert_public_session_conflict(command.command_id, exc)
        except Exception:
            admission = PublicCommandRejected(
                "rejected",
                command.command_id,
                "command_processing_failed",
                self._project(),
            )
        if isinstance(admission, PublicCommandAccepted):
            self._command_admissions[command.command_id] = (command.payload_digest, admission)
        return admission

    async def _execute_admitted_command(
        self,
        command: PublicSessionCommand,
    ) -> PublicCommandAdmission:
        if command.kind is PublicSessionCommandKind.START_TASK:
            snapshot = await self.start(command.task)
        elif command.kind is PublicSessionCommandKind.RESPOND_INTERACTION:
            assert command.response is not None
            snapshot = await self.respond(command.response)
        elif command.kind is PublicSessionCommandKind.APPROVE_ACTION:
            snapshot = await self.confirm(command.interaction_ref, approved=True)
        elif command.kind is PublicSessionCommandKind.REJECT_ACTION:
            snapshot = await self.confirm(command.interaction_ref, approved=False)
        elif command.kind is PublicSessionCommandKind.CANCEL_TASK:
            snapshot = await self.cancel(command.command_id)
        elif command.kind is PublicSessionCommandKind.PAUSE_TASK:
            snapshot = await self.pause(command.command_id)
        elif command.kind is PublicSessionCommandKind.RESUME_TASK:
            snapshot = await self.resume(command.command_id, command.checkpoint_id)
        elif command.kind is PublicSessionCommandKind.REVISE_TASK:
            assert command.revision is not None
            snapshot = await self.revise(command.revision)
        elif command.kind is PublicSessionCommandKind.TAKE_OVER:
            snapshot = await self.take_over(command.command_id, command.checkpoint_id)
        elif command.kind is PublicSessionCommandKind.RETURN_CONTROL:
            snapshot = await self.return_control(command.command_id, command.control_lease_id)
        elif command.kind is PublicSessionCommandKind.CLOSE_SESSION:
            snapshot = self._project()
            await self.close()
        else:  # pragma: no cover - StrEnum closes the supported algebra
            return PublicCommandUnsupported(
                "unsupported",
                command.command_id,
                "command_not_supported",
                self._project(),
            )
        return PublicCommandAccepted("accepted", command.command_id, snapshot)

    async def events(self, after: int) -> tuple[PublicRuntimeSessionEvent, ...]:
        return tuple(event for event in self._events if event.cursor > after)

    async def inspect_live_checkpoint(self, checkpoint_id: str) -> LiveCheckpointAdmission:
        """Admit an exact live recovery ref without consulting durable projection state."""

        async with self._lock:
            snapshot = self._project()
            if self._checkpoint_id != checkpoint_id:
                return LiveCheckpointConflict("live_checkpoint_conflict", "checkpoint_mismatch")
            state = self._state
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not self._resume_eligible
                or state.durable_checkpoint_id != checkpoint_id
            ):
                return LiveCheckpointUnavailable(
                    "live_checkpoint_unavailable",
                    "checkpoint_unavailable",
                )
            return LiveCheckpointCurrent("live_checkpoint_current", snapshot)

    async def start(self, instruction: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_open()
            if self._status is not PublicSessionStatus.IDLE or self._active is not None:
                raise PublicSessionConflict("session_not_idle", self._project())
            self._request = self.request_factory(self.session_id, instruction)
            if self._request.request_id != self.session_id or self._request.revision != 1:
                raise TypeError("public task request factory must preserve session identity and initial revision")
            intake = self.runtime.admit(self._request)
            if isinstance(intake, ReadyTask):
                self._admitted = intake
            self._status = PublicSessionStatus.RUNNING
            source_factories = [
                _feed_source(lambda source_id: PublicUserTurn(source_id, instruction))
            ]
            if self._admitted is not None:
                accepted = self._admitted.task
                source_factories.append(
                    _feed_source(
                        lambda source_id: PublicGoalAccepted(
                            source_id,
                            accepted.revision,
                            accepted.instruction,
                            accepted.constraints,
                        )
                    )
                )
            self._emit(
                "RUN_STARTED",
                tuple(source_factories),
            )
            self._active = asyncio.create_task(
                self._run_start(intake),
                name=f"runtime-session:{self.session_id}",
            )
            return self._project()

    async def respond(self, response: InteractionResponse) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
            self._require_open()
            pending_step = self._state.last_step if self._state is not None else None
            pending = pending_step.decision if pending_step is not None else None
            if not isinstance(pending, InteractionRequest):
                raise PublicSessionConflict("interrupt_mismatch", self._project())
            if response.request_id != pending.request_id:
                raise PublicSessionConflict("interrupt_mismatch", self._project())
            admission = admit_interaction_response(pending, response)
            if not admission.admitted:
                raise PublicSessionConflict(
                    admission.rejection_code.value if admission.rejection_code is not None else "interaction_invalid",
                    self._project(),
                )
            if self._request is None or self._state is None:
                raise PublicSessionConflict("run_not_resumable", self._project())
            boundary = self._request.boundary
            inputs = dict(boundary.inputs)
            responses = list(inputs.get("user_responses", ()))
            responses.append(interaction_response_public_value(response))
            revised_boundary = replace(boundary, inputs={**inputs, "user_responses": responses})
            self._request = replace(
                self._request,
                boundary=revised_boundary,
                revision=self._request.revision + 1,
            )
            response_text = _interaction_response_text(pending, response)
            self._status = PublicSessionStatus.RUNNING
            self._intake_question = None
            self._emit(
                "RUN_STARTED",
                (lambda source_id: PublicUserTurn(source_id, response_text),),
            )
            self._active = asyncio.create_task(self._run_answer(), name=f"runtime-resume:{self.session_id}")
            return self._project()

    async def answer(self, interrupt_id: str, answer: str) -> PublicRuntimeSessionSnapshot:
        """Compatibility adapter into the canonical free-text response contract."""
        pending_step = self._state.last_step if self._state is not None else None
        pending = pending_step.decision if pending_step is not None else None
        if (
            isinstance(pending, InteractionRequest)
            and pending.request_id == interrupt_id
            and pending.response_kind.value == "structured_fields"
            and len(pending.fields) == 1
            and pending.fields[0].kind.value == "text"
        ):
            return await self.respond(
                StructuredFieldsResponse(
                    interrupt_id,
                    (TextFieldValue(pending.fields[0].field_id, answer),),
                )
            )
        return await self.respond(FreeTextResponse(interrupt_id, answer))

    async def confirm(self, interrupt_id: str, *, approved: bool) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
            self._require_open()
            pending = self._project().pending_confirmation
            if pending is None or pending.interrupt_id != interrupt_id:
                raise PublicSessionConflict("interrupt_mismatch", self._project())
            if self._admitted is None or self._state is None:
                raise PublicSessionConflict("run_not_resumable", self._project())
            self._status = PublicSessionStatus.RUNNING
            self._emit("RUN_STARTED")
            self._active = asyncio.create_task(
                self._run_confirmation(approved), name=f"runtime-confirm:{self.session_id}"
            )
            return self._project()

    async def cancel(self, command_id: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            state = self._state
            if (state is not None and state.terminal) or (state is None and self._active is None):
                raise PublicSessionConflict("run_not_active", self._project())
            admission = self.runtime.request_control(command_id, RunControlKind.CANCEL)
            if admission.outcome is RunControlAdmissionKind.CONFLICT:
                raise PublicSessionConflict("control_request_conflict", self._project())
            if admission.outcome is RunControlAdmissionKind.DUPLICATE:
                return self._project()
            self._emit("CONTROL_REQUESTED")
            if self._active is None:
                if state is None:
                    raise PublicSessionConflict("run_not_active", self._project())
                outcome = self.runtime.apply_waiting_control(state)
                if outcome is None or outcome.outcome is not RunControlOutcomeKind.CANCELLED:
                    raise PublicSessionConflict("control_boundary_failed", self._project())
                self._status = PublicSessionStatus.CANCELLED
                self._resume_eligible = False
                self._emit("RUN_FINISHED")
            return self._project()

    async def pause(self, command_id: str) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            if self.checkpoint_store is None:
                raise PublicSessionConflict("pause_unavailable", self._project())
            state = self._state
            if state is not None and state.status is RunStatus.PAUSED:
                existing = await self.checkpoint_store.command_outcome(self.session_id, command_id)
                if existing is not None and existing.checkpoint_id == state.durable_checkpoint_id:
                    return self._project()
                raise PublicSessionConflict("run_not_active", self._project())
            if (state is not None and state.terminal) or (state is None and self._active is None):
                raise PublicSessionConflict("run_not_active", self._project())
            admission = self.runtime.request_control(command_id, RunControlKind.PAUSE)
            if admission.outcome is RunControlAdmissionKind.CONFLICT:
                raise PublicSessionConflict("control_request_conflict", self._project())
            if admission.outcome is RunControlAdmissionKind.DUPLICATE:
                return self._project()
            self._last_control_outcome = None
            self._emit("CONTROL_REQUESTED")
            if self._active is None:
                if state is None or self._admitted is None:
                    raise PublicSessionConflict("run_not_active", self._project())
                outcome = self.runtime.apply_waiting_control(state)
                if outcome is None or outcome.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED:
                    raise PublicSessionConflict("control_boundary_failed", self._project())
                await self._settle_pause_boundary(self.runtime, self._admitted.task, state)
            return self._project()

    async def resume(
        self,
        command_id: str,
        checkpoint_id: str,
    ) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
            self._require_open()
            store = self.checkpoint_store
            if store is None:
                raise PublicSessionConflict("resume_unavailable", self._project())
            try:
                existing = await store.resume_outcome(self.session_id, command_id)
            except Exception as exc:
                raise PublicSessionConflict("resume_persistence_failed", self._project()) from exc
            if existing is not None:
                if existing.checkpoint_id == checkpoint_id:
                    return self._project()
                raise PublicSessionConflict("resume_command_conflict", self._project())
            state = self._state
            if (
                state is not None
                and state.effect_reconciliation is not None
                and state.effect_reconciliation.status is EffectReconciliationStatus.NEEDS_INPUT
            ):
                raise PublicSessionConflict(
                    state.effect_reconciliation.reason.value,
                    self._project(),
                )
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not self._resume_eligible
                or self._checkpoint_id != checkpoint_id
                or state.durable_checkpoint_id != checkpoint_id
            ):
                raise PublicSessionConflict("checkpoint_mismatch", self._project())
            try:
                await store.commit_resume(
                    RuntimeCheckpointResumeOutcome(
                        self.session_id,
                        command_id,
                        checkpoint_id,
                    )
                )
            except RuntimeCheckpointError as exc:
                raise PublicSessionConflict(exc.code, self._project()) from exc
            self.runtime.resume_control(state, command_id)
            self._resume_eligible = False
            self._status = _public_status(state.status)
            self._emit("RUN_FINISHED" if state.terminal else "RUN_RESUMED")
            if state.status is RunStatus.RUNNING:
                if self._admitted is None:
                    raise PublicSessionConflict("run_not_resumable", self._project())
                self._active = asyncio.create_task(
                    self._run_continue(),
                    name=f"runtime-checkpoint-resume:{self.session_id}",
                )
            return self._project()

    async def take_over(
        self,
        command_id: str,
        checkpoint_id: str = "",
    ) -> PublicRuntimeSessionSnapshot:
        """Reach one durable pause and grant one process-local user control lease."""

        async with self._lock:
            self._require_agent_control()
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            store = self.checkpoint_store
            if store is None:
                raise PublicSessionConflict("takeover_unavailable", self._project())
            try:
                existing = await store.resume_outcome(self.session_id, command_id)
            except Exception as exc:
                raise PublicSessionConflict("takeover_persistence_failed", self._project()) from exc
            if existing is not None:
                if existing.checkpoint_id == checkpoint_id:
                    raise PublicSessionConflict("takeover_command_consumed", self._project())
                raise PublicSessionConflict("takeover_command_conflict", self._project())
            state = self._state
            already_paused = state is not None and state.status is RunStatus.PAUSED
            if already_paused:
                if not checkpoint_id or self._checkpoint_id != checkpoint_id:
                    raise PublicSessionConflict("checkpoint_mismatch", self._project())
            else:
                if checkpoint_id:
                    raise PublicSessionConflict("checkpoint_mismatch", self._project())
                await self._ensure_durable_pause(_takeover_pause_command_id(command_id))
                state = self._state
                checkpoint_id = self._checkpoint_id or ""
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not checkpoint_id
                or self._checkpoint_id != checkpoint_id
                or state.durable_checkpoint_id != checkpoint_id
            ):
                raise PublicSessionConflict("takeover_pause_failed", self._project())
            try:
                await store.commit_resume(
                    RuntimeCheckpointResumeOutcome(
                        self.session_id,
                        command_id,
                        checkpoint_id,
                    )
                )
            except RuntimeCheckpointError as exc:
                raise PublicSessionConflict(exc.code, self._project()) from exc
            self._control_owner = PublicSessionControlOwner.USER
            self._control_lease_id = secrets.token_urlsafe(24)
            self._resume_eligible = False
            self._last_control_outcome = PublicControlOutcome(
                command_id,
                "take_over",
                "user_control_granted",
                "user_control_granted",
                checkpoint_id,
            )
            self._emit("USER_CONTROL_GRANTED")
            return self._project()

    async def return_control(
        self,
        command_id: str,
        control_lease_id: str,
    ) -> PublicRuntimeSessionSnapshot:
        """Revoke user input and resume only after a fresh owner-produced World."""

        async with self._lock:
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            if self._control_owner is not PublicSessionControlOwner.USER:
                raise PublicSessionConflict("user_control_not_active", self._project())
            if self._control_lease_id is None or not secrets.compare_digest(self._control_lease_id, control_lease_id):
                raise PublicSessionConflict("control_lease_mismatch", self._project())
            if self._active is not None or self._admitted is None or self._state is None:
                raise PublicSessionConflict("user_control_return_unavailable", self._project())
            runtime = self._runtime_with_projection()
            state = self._state
            # Revoke the user-input lease before producing the fresh World that
            # will become authoritative for Agent continuation.
            self._control_owner = PublicSessionControlOwner.AGENT
            self._control_lease_id = None
            self._control_return_in_progress = True
            self._emit("USER_CONTROL_REVOKED")
            try:
                if state.status is RunStatus.PAUSED:
                    runtime.resume_control(state, command_id)
                self._state = await runtime.refresh_after_user_control(
                    self.lease.environment,
                    self._admitted.task,
                    state,
                )
            except BaseException as exc:
                self._control_return_in_progress = False
                self._control_owner = PublicSessionControlOwner.USER
                # Capture failure restores manual control with a new epoch;
                # the revoked input lease can never become valid again.
                self._control_lease_id = secrets.token_urlsafe(24)
                code = str(getattr(exc, "reason_code", "")) or "user_control_currentness_unavailable"
                self._last_control_outcome = PublicControlOutcome(
                    command_id,
                    "return_control",
                    "failed",
                    code,
                    message="Agent control remains disabled until fresh currentness is available.",
                )
                self._emit("USER_CONTROL_RETURN_FAILED")
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise PublicSessionConflict(code, self._project()) from exc
            self._control_return_in_progress = False
            self._checkpoint_id = None
            self._resume_eligible = False
            self._status = _public_status(state.status)
            self._last_control_outcome = PublicControlOutcome(
                command_id,
                "return_control",
                "user_control_returned",
                "user_control_currentness_refreshed",
            )
            self._emit("USER_CONTROL_RETURNED")
            if state.status is RunStatus.RUNNING:
                self._active = asyncio.create_task(
                    self._run_continue(),
                    name=f"runtime-user-control-return:{self.session_id}",
                )
            return self._project()

    async def revise(self, command: PublicTaskRevisionCommand) -> PublicRuntimeSessionSnapshot:
        async with self._lock:
            self._require_agent_control()
            if self._closed:
                raise PublicSessionConflict("session_closed", self._project())
            store = self.checkpoint_store
            if store is None:
                raise PublicSessionConflict("revision_unavailable", self._project())
            admitted_at_entry = self._admitted
            state_at_entry = self._state
            command_matches_entry = (
                admitted_at_entry is not None
                and state_at_entry is not None
                and admitted_at_entry.task.revision == command.expected_task_revision
                and self._status is command.expected_run_status
            )
            checkpoint_matches_entry = self._checkpoint_id == command.expected_checkpoint_id
            try:
                existing = await store.revision_outcome(
                    self.session_id,
                    command.command_id,
                )
            except Exception as exc:
                raise PublicSessionConflict(
                    "revision_persistence_failed",
                    self._project(),
                ) from exc
            if existing is not None:
                if existing.payload_digest != command.payload_digest:
                    raise PublicSessionConflict(
                        "command_identity_reused",
                        self._project(),
                    )
                self._set_revision_outcome(
                    existing.outcome,
                    command.command_id,
                    checkpoint_id=(existing.result_checkpoint_id if existing.outcome == "revised" else None),
                    message=existing.message,
                    code=existing.result_code,
                )
                if existing.outcome == "revised":
                    return self._project()
                raise PublicSessionConflict(existing.result_code, self._project())
            if admitted_at_entry is None or state_at_entry is None:
                raise PublicSessionConflict("run_not_revisable", self._project())
            if not command_matches_entry:
                raise PublicSessionConflict("stale_command", self._project())
            if not checkpoint_matches_entry:
                raise PublicSessionConflict("checkpoint_mismatch", self._project())
            await self._ensure_revision_pause(command.command_id)
            state = self._state
            source_checkpoint_id = self._checkpoint_id
            if (
                state is None
                or state.status is not RunStatus.PAUSED
                or not source_checkpoint_id
                or state.durable_checkpoint_id != source_checkpoint_id
            ):
                raise PublicSessionConflict("revision_pause_failed", self._project())
            try:
                source_checkpoint = await store.load(
                    self.session_id,
                    source_checkpoint_id,
                )
            except Exception as exc:
                self._set_revision_outcome(
                    "revision_persistence_failed",
                    command.command_id,
                    message=type(exc).__name__,
                )
                self._emit("CONTROL_FAILED")
                raise PublicSessionConflict(
                    "revision_persistence_failed",
                    self._project(),
                ) from exc
            if source_checkpoint is None:
                self._set_revision_outcome("checkpoint_not_found", command.command_id)
                self._emit("CONTROL_FAILED")
                raise PublicSessionConflict("checkpoint_not_found", self._project())
            if (
                state.effect_reconciliation is not None
                and state.effect_reconciliation.status is not EffectReconciliationStatus.COMPENSATED
            ):
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    "effect_reconciliation_required",
                    "The current revision still has an unresolved effect reconciliation.",
                )
            early_effect = assess_effect_revision(
                execution_count=state.execution_count,
                latest_effect=state.latest_effect,
                revised_goal_satisfied=False,
            )
            if early_effect.disposition in {
                EffectRevisionDisposition.UNKNOWN,
                EffectRevisionDisposition.UNSUPPORTED,
            } and (state.execution_count != 1 or state.latest_effect is None):
                code = (
                    "effect_reconciliation_unsupported"
                    if early_effect.disposition is EffectRevisionDisposition.UNSUPPORTED
                    else "effect_reconciliation_unknown"
                )
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    code,
                    early_effect.reason.value,
                    outcome="effect_reconciliation_required",
                )
            compiled = await self.runtime.compile_task_revision(
                admitted_at_entry,
                command.conversation,
                state,
            )
            revised = compiled.intake
            if not isinstance(revised, ReadyTask):
                code, message = _revision_rejection(compiled.compiler, revised)
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    code,
                    message,
                )
            assert isinstance(revised, ReadyTask)
            current = self._admitted
            assert current is not None
            runtime = self._runtime_with_projection()
            try:
                candidate = await runtime.prepare_paused_task_revision(
                    self.lease.environment,
                    current.task,
                    revised.task,
                    state,
                )
                evaluation = candidate.current_task_evaluation
                effect_assessment = assess_effect_revision(
                    execution_count=state.execution_count,
                    latest_effect=state.latest_effect,
                    revised_goal_satisfied=(
                        evaluation is not None and evaluation.status is TaskEvaluationStatus.COMPLETE
                    ),
                )
                if effect_assessment.disposition is EffectRevisionDisposition.COMPENSATION_REQUIRED:
                    assert effect_assessment.effect is not None
                    candidate.install_effect_reconciliation(
                        EffectReconciliation(
                            effect_assessment.effect,
                            revised.task.revision,
                        )
                    )
                elif effect_assessment.disposition in {
                    EffectRevisionDisposition.NON_COMPENSABLE,
                    EffectRevisionDisposition.UNKNOWN,
                    EffectRevisionDisposition.UNSUPPORTED,
                }:
                    await self._restore_revision_source(runtime, source_checkpoint)
                    code = {
                        EffectRevisionDisposition.NON_COMPENSABLE: "effect_non_compensable",
                        EffectRevisionDisposition.UNKNOWN: "effect_reconciliation_unknown",
                        EffectRevisionDisposition.UNSUPPORTED: "effect_reconciliation_unsupported",
                    }[effect_assessment.disposition]
                    await self._reject_revision(
                        command,
                        source_checkpoint_id,
                        state.task_revision,
                        code,
                        effect_assessment.reason.value,
                        outcome="effect_reconciliation_required",
                    )
                runtime.rebind_checkpoint_history(
                    task_id=self.session_id,
                    current_revision=current.task.revision,
                    revised_revision=revised.task.revision,
                )
                checkpoint = RuntimeCheckpoint.capture(
                    session_id=self.session_id,
                    task=revised.task,
                    state=candidate,
                    model_history=await runtime.persist_checkpoint_history(),
                    environment_reference=self.lease.reconnect_reference,
                )
            except PublicSessionConflict:
                raise
            except Exception as exc:
                await self._restore_revision_source(runtime, source_checkpoint)
                await self._reject_revision(
                    command,
                    source_checkpoint_id,
                    state.task_revision,
                    "revision_failed",
                    type(exc).__name__,
                )
                raise AssertionError("revision rejection must raise") from exc
            revision_outcome = RuntimeCheckpointRevisionOutcome(
                self.session_id,
                command.command_id,
                source_checkpoint_id,
                checkpoint.checkpoint_id,
                revised.task.revision,
                "revised",
                command.payload_digest,
                "",
            )
            try:
                await store.commit_revision(checkpoint, revision_outcome)
            except Exception as exc:
                await self._restore_revision_source(runtime, source_checkpoint)
                self._set_revision_outcome(
                    "revision_persistence_failed",
                    command.command_id,
                    message=type(exc).__name__,
                )
                self._emit("CONTROL_FAILED")
                raise PublicSessionConflict(
                    "revision_persistence_failed",
                    self._project(),
                ) from exc
            candidate.commit_durable_pause(checkpoint.checkpoint_id)
            self._request = _request_from_task(revised.task)
            self._admitted = revised
            self._state = candidate
            self._status = PublicSessionStatus.PAUSED
            self._checkpoint_id = checkpoint.checkpoint_id
            self._resume_eligible = checkpoint.resume_eligible
            self._set_revision_outcome(
                "revised",
                command.command_id,
                checkpoint_id=checkpoint.checkpoint_id,
            )
            self._emit(
                "TASK_REVISED",
                (
                    lambda source_id: PublicUserTurn(source_id, command.text),
                    lambda source_id: _revision_feed_diff(
                        current.task,
                        revised.task,
                        source_id,
                    ),
                ),
            )
            return self._project()

    async def _ensure_revision_pause(self, command_id: str) -> None:
        await self._ensure_durable_pause(_revision_pause_command_id(command_id))

    async def _ensure_durable_pause(self, pause_id: str) -> None:
        state = self._state
        if state is not None and state.status is RunStatus.PAUSED:
            return
        admission = self.runtime.request_control(pause_id, RunControlKind.PAUSE)
        if admission.outcome is RunControlAdmissionKind.CONFLICT:
            raise PublicSessionConflict("control_request_conflict", self._project())
        if admission.outcome is not RunControlAdmissionKind.DUPLICATE:
            self._last_control_outcome = None
            self._emit("CONTROL_REQUESTED")
        active = self._active
        if active is None:
            if state is None or self._admitted is None:
                raise PublicSessionConflict("run_not_active", self._project())
            outcome = self.runtime.apply_waiting_control(state)
            if outcome is None or outcome.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED:
                raise PublicSessionConflict("control_boundary_failed", self._project())
            await self._settle_pause_boundary(
                self._runtime_with_projection(),
                self._admitted.task,
                state,
            )
            return
        await active

    async def _reject_revision(
        self,
        command: PublicTaskRevisionCommand,
        source_checkpoint_id: str,
        task_revision: int,
        code: str,
        message: str,
        *,
        outcome: str | None = None,
    ) -> None:
        store = self.checkpoint_store
        assert store is not None
        message = message[:2000]
        durable_outcome = outcome or code
        stored = RuntimeCheckpointRevisionOutcome(
            self.session_id,
            command.command_id,
            source_checkpoint_id,
            source_checkpoint_id,
            task_revision,
            durable_outcome,
            command.payload_digest,
            message,
            code,
        )
        try:
            await store.commit_revision(None, stored)
        except Exception as exc:
            self._set_revision_outcome(
                "revision_persistence_failed",
                command.command_id,
                message=type(exc).__name__,
            )
            self._emit("CONTROL_FAILED")
            raise PublicSessionConflict(
                "revision_persistence_failed",
                self._project(),
            ) from exc
        self._set_revision_outcome(
            durable_outcome,
            command.command_id,
            message=message,
            code=code,
        )
        self._emit(
            "TASK_REVISION_REJECTED",
            (
                lambda source_id: PublicUserTurn(source_id, command.text),
                lambda source_id: PublicRuntimeActivity(
                    source_id,
                    "failed",
                    message or "The task revision could not be applied.",
                ),
            ),
        )
        raise PublicSessionConflict(code, self._project())

    async def _restore_revision_source(
        self,
        runtime: TargetRuntime,
        checkpoint: RuntimeCheckpoint,
    ) -> None:
        task = checkpoint.restore_task()
        await runtime.restore_persisted_checkpoint_history(
            checkpoint.model_history,
            task_id=task.task_id,
            task_revision=task.revision,
        )
        await self.lease.environment.revise_task(task)
        self._state = await runtime.build_loop().restore_paused(
            self.lease.environment,
            task,
            checkpoint.restore_run_facts(),
            checkpoint.checkpoint_id,
        )
        self._request = _request_from_task(task)
        self._admitted = ReadyTask(task.task_id, task)
        self._status = PublicSessionStatus.PAUSED
        self._checkpoint_id = checkpoint.checkpoint_id
        self._resume_eligible = checkpoint.resume_eligible

    def _set_revision_outcome(
        self,
        outcome: str,
        command_id: str,
        *,
        checkpoint_id: str | None = None,
        message: str = "",
        code: str | None = None,
    ) -> None:
        public_outcome = {
            "revised": "revised",
            "revision_needs_input": "needs_input",
            "revision_no_change": "no_change",
            "revision_new_task_suggested": "new_task_suggested",
            "revision_unsupported": "unsupported",
            "revision_failed": "failed",
            "revision_persistence_failed": "failed",
            "checkpoint_not_found": "failed",
            "effect_reconciliation_required": "effect_reconciliation_required",
        }[outcome]
        self._last_control_outcome = PublicControlOutcome(
            command_id,
            "revise",
            public_outcome,  # type: ignore[arg-type]
            code or outcome,
            checkpoint_id,
            message,
        )

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            active = self._active
        if active is not None and not active.done():
            active.add_done_callback(lambda _task: asyncio.create_task(self._cleanup_once()))
            return
        await self._cleanup_once()

    async def _run_start(self, intake: TaskIntakeOutcome) -> None:
        assert self._request is not None
        session_runtime = self._runtime_with_projection()
        try:
            outcome = (
                await session_runtime.run_admitted(self.lease.environment, intake)
                if isinstance(intake, ReadyTask)
                else TargetRuntimeRunOutcome(intake)
            )
            if isinstance(outcome.intake, ReadyTask):
                self._admitted = outcome.intake
                self._state = outcome.state
                if outcome.state is not None:
                    await self._settle_pause_boundary(session_runtime, outcome.intake.task, outcome.state)
            elif isinstance(outcome.intake, TaskInputRequired):
                self._fail(outcome.intake.reason_code, outcome.intake.question)
            else:
                code = (
                    outcome.intake.reason_code
                    if isinstance(outcome.intake, TaskPolicyRejected | TaskUnsupported)
                    else "task_intake_failed"
                )
                self._fail(code)
        except BaseException as exc:
            self._fail("runtime_session_start_failed", type(exc).__name__)
        finally:
            self._active = None
            await self._cleanup_if_closed_or_terminal()

    async def _run_answer(self) -> None:
        assert self._request is not None and self._state is not None
        try:
            outcome = await self._runtime_with_projection().resume_request(
                self.lease.environment, self._state, self._request
            )
            if not isinstance(outcome.intake, ReadyTask) or outcome.state is None:
                self._fail(getattr(outcome.intake, "reason_code", "task_revision_failed"))
            else:
                self._admitted = outcome.intake
                self._state = outcome.state
                await self._settle_pause_boundary(self._runtime_with_projection(), outcome.intake.task, outcome.state)
        except BaseException as exc:
            self._fail("runtime_session_resume_failed", type(exc).__name__)
        finally:
            self._active = None
            await self._cleanup_if_closed_or_terminal()

    async def _run_confirmation(self, approved: bool) -> None:
        assert self._admitted is not None and self._state is not None
        try:
            self._state = await self._runtime_with_projection().resume_confirmation(
                self.lease.environment,
                self._admitted.task,
                self._state,
                approved=approved,
            )
            await self._settle_pause_boundary(self._runtime_with_projection(), self._admitted.task, self._state)
        except BaseException as exc:
            self._fail("runtime_session_confirmation_failed", type(exc).__name__)
        finally:
            self._active = None
            await self._cleanup_if_closed_or_terminal()

    async def _run_continue(self) -> None:
        assert self._admitted is not None and self._state is not None
        runtime = self._runtime_with_projection()
        try:
            self._state = await runtime.continue_task(
                self.lease.environment,
                self._admitted.task,
                self._state,
            )
            await self._settle_pause_boundary(
                runtime,
                self._admitted.task,
                self._state,
            )
        except BaseException as exc:
            self._fail("runtime_session_resume_failed", type(exc).__name__)
        finally:
            self._active = None
            await self._cleanup_if_closed_or_terminal()

    def _runtime_with_projection(self) -> TargetRuntime:
        projection = _SessionProjectionSink(self)
        return replace(
            self.runtime,
            trace_sink=FanoutRunTraceSink((self.runtime.trace_sink, projection)),
        )

    async def _settle_pause_boundary(
        self,
        runtime: TargetRuntime,
        task: TaskGoal,
        state: RunState,
    ) -> None:
        boundary = state.control_boundary
        if (
            boundary is None
            or boundary.kind is not RunControlKind.PAUSE
            or boundary.outcome is not RunControlOutcomeKind.PAUSE_BOUNDARY_REACHED
        ):
            return
        store = self.checkpoint_store
        if store is None:
            raise RuntimeError("Runtime reached a pause boundary without a checkpoint store")
        try:
            checkpoint = RuntimeCheckpoint.capture(
                session_id=self.session_id,
                task=task,
                state=state,
                model_history=await runtime.persist_checkpoint_history(),
                environment_reference=self.lease.reconnect_reference,
            )
            await store.commit_pause(
                checkpoint,
                RuntimeCheckpointCommandOutcome(
                    self.session_id,
                    boundary.command_id,
                    checkpoint.checkpoint_id,
                ),
            )
        except Exception:
            self._last_control_outcome = PublicControlOutcome(
                boundary.command_id,
                "pause",
                "failed",
                "pause_persistence_failed",
            )
            self._emit("CONTROL_FAILED")
            try:
                await runtime.recover_pause_persistence_failure(
                    self.lease.environment,
                    task,
                    state,
                    f"pause-persistence-failed:{boundary.command_id}",
                )
            except Exception as exc:
                self._fail(
                    "pause_persistence_failed",
                    str(getattr(exc, "reason_code", "")) or type(exc).__name__,
                )
                return
            if state.status is RunStatus.RUNNING:
                self._state = await runtime.continue_task(
                    self.lease.environment,
                    task,
                    state,
                )
            return
        state.commit_durable_pause(checkpoint.checkpoint_id)
        self._checkpoint_id = checkpoint.checkpoint_id
        self._resume_eligible = checkpoint.resume_eligible
        self._last_control_outcome = PublicControlOutcome(
            boundary.command_id,
            "pause",
            "paused",
            "pause_checkpoint_committed",
            checkpoint.checkpoint_id,
        )
        self._status = PublicSessionStatus.PAUSED
        self._emit("RUN_PAUSED")

    def _observe_started(self, task: TaskGoal, state: RunState) -> None:
        self._admitted = ReadyTask(task.task_id, task)
        self._state = state

    def _observe_step(self, step_number: int, result: StepResult) -> None:
        kind = getattr(result.decision, "kind", "progress")
        kind_value = getattr(kind, "value", str(kind))
        labels = {
            "ask_user": "Waiting for your input",
            "select_action": "Completed an interaction",
            "request_observation": "Checked the current page",
            "final_response": "Prepared the final response",
            "policy_failure": "Runtime could not continue",
        }
        self._progress.append(
            PublicProgressStep(step_number, str(result.status_after), labels.get(kind_value, "Made progress"))
        )
        self._emit("STEP_FINISHED", _step_feed_sources(result))

    def _observe_paused(self, state: RunState) -> None:
        self._state = state
        self._status = _public_status(state.status)
        completion = _completion(state, self._status)
        sources: tuple[Callable[[str], PublicFeedSource], ...] = ()
        if completion is not None:
            if completion.outcome in {"success", "cancelled"}:
                sources = (
                    lambda source_id: PublicCompletionBlock(source_id, completion),
                )
            else:
                sources = (
                    lambda source_id: PublicFailure(
                        source_id,
                        completion.code,
                        completion.message or "The Runtime could not complete the task.",
                    ),
                )
        self._emit("RUN_FINISHED", sources)

    def _observe_finished(self, state: RunState) -> None:
        self._observe_paused(state)

    def _observe_resumed(self) -> None:
        self._status = PublicSessionStatus.RUNNING

    def _observe_error(self, error: BaseException, state: RunState) -> None:
        self._state = state
        self._fail("runtime_run_failed", type(error).__name__)

    def _fail(self, code: str, message: str = "Runtime session failed.") -> None:
        if self._status is PublicSessionStatus.FAILED and self._failure is not None:
            return
        self._status = PublicSessionStatus.FAILED
        self._failure = PublicCompletion("failure", code, message)
        self._emit(
            "RUN_ERROR",
            (lambda source_id: PublicFailure(source_id, code, message),),
        )

    def _emit(
        self,
        event_type: str,
        source_factories: tuple[Callable[[str], PublicFeedSource], ...] = (),
    ) -> None:
        cursor = len(self._events) + 1
        snapshot = self._project(event_cursor=cursor)
        factories = source_factories or _control_feed_sources(event_type, self._last_control_outcome)
        sources = tuple(
            factory(f"feed:{self._event_epoch}:{cursor}:{ordinal}")
            for ordinal, factory in enumerate(factories)
        )
        self._events.append(
            PublicRuntimeSessionEvent(
                self.session_id,
                self._event_epoch,
                cursor,
                event_type,
                snapshot,
                sources,
            )
        )

    def _project(self, *, event_cursor: int | None = None) -> PublicRuntimeSessionSnapshot:
        state = self._state
        status = self._status if self._active is not None or state is None else _public_status(state.status)
        if self._control_owner is PublicSessionControlOwner.USER or self._control_return_in_progress:
            status = PublicSessionStatus.PAUSED
        pending_interaction = self._intake_question
        pending_confirmation = None
        if state is not None and state.last_step is not None:
            if (
                self._control_owner is PublicSessionControlOwner.AGENT
                and status is PublicSessionStatus.WAITING_USER
                and isinstance(state.last_step.decision, InteractionRequest)
            ):
                decision = state.last_step.decision
                pending_interaction = _public_interaction_request(decision)
            if (
                self._control_owner is PublicSessionControlOwner.AGENT
                and status is PublicSessionStatus.WAITING_CONFIRMATION
                and state.last_step.confirmation is not None
            ):
                risk = state.last_step.confirmation
                pending_confirmation = _public_confirmation(risk)
        request = self._request
        task = self._admitted.task if self._admitted is not None else None
        completion = self._failure or _completion(state, status)
        reconciliation = _public_effect_reconciliation(state.effect_reconciliation) if state is not None else None
        reconciliation_blocks_control = reconciliation is not None
        public_resume_eligible = self._resume_eligible and (
            reconciliation is None or reconciliation.status != "needs_input"
        )
        capabilities = (
            frozenset({PublicSessionCapability.CLOSE_SESSION})
            if self._control_return_in_progress
            else frozenset(
                {
                    PublicSessionCapability.CLOSE_SESSION,
                    PublicSessionCapability.RETURN_CONTROL,
                }
            )
            if self._control_owner is PublicSessionControlOwner.USER
            else (
                BASE_PUBLIC_SESSION_CAPABILITIES
                | ({PublicSessionCapability.PAUSE_TASK} if self.checkpoint_store is not None else set())
                | (
                    {PublicSessionCapability.RESUME_TASK}
                    if status is PublicSessionStatus.PAUSED and public_resume_eligible
                    else set()
                )
                | (
                    {PublicSessionCapability.REVISE_TASK}
                    if self.checkpoint_store is not None
                    and not reconciliation_blocks_control
                    and status
                    in {
                        PublicSessionStatus.RUNNING,
                        PublicSessionStatus.WAITING_USER,
                        PublicSessionStatus.WAITING_CONFIRMATION,
                        PublicSessionStatus.PAUSED,
                    }
                    else set()
                )
                | (
                    {PublicSessionCapability.TAKE_OVER}
                    if (
                        self.checkpoint_store is not None
                        and status
                        in {
                            PublicSessionStatus.RUNNING,
                            PublicSessionStatus.WAITING_USER,
                            PublicSessionStatus.WAITING_CONFIRMATION,
                            PublicSessionStatus.PAUSED,
                        }
                        and (
                            status is not PublicSessionStatus.PAUSED
                            or self._checkpoint_id is not None
                        )
                    )
                    else set()
                )
            )
        )
        return PublicRuntimeSessionSnapshot(
            self.session_id,
            self.expires_at,
            status,
            self._event_epoch,
            len(self._events) if event_cursor is None else event_cursor,
            capabilities=capabilities,
            command_capabilities=_v3_command_capabilities(
                status=status,
                checkpoint_store_available=self.checkpoint_store is not None,
                checkpoint_id=self._checkpoint_id,
                resume_eligible=public_resume_eligible,
                pending_interaction=pending_interaction,
                pending_confirmation=pending_confirmation,
                control_owner=self._control_owner,
                control_return_in_progress=self._control_return_in_progress,
                reconciliation_blocks_control=reconciliation_blocks_control,
                closed=self._closed,
            ),
            task_id=task.task_id if task is not None else (request.request_id if request else None),
            task_revision=task.revision if task is not None else (request.revision if request else 0),
            task_text=task.instruction if task is not None else (request.instruction if request else None),
            pending_interaction=pending_interaction,
            pending_confirmation=pending_confirmation,
            completion=completion,
            progress=tuple(self._progress),
            checkpoint_id=self._checkpoint_id,
            resume_eligible=public_resume_eligible,
            last_control_outcome=self._last_control_outcome,
            effect_reconciliation=reconciliation,
            control_owner=self._control_owner,
            control_lease_id=self._control_lease_id,
        )

    def _require_agent_control(self) -> None:
        if self._control_owner is not PublicSessionControlOwner.AGENT:
            raise PublicSessionConflict("user_control_active", self._project())

    def _require_open(self) -> None:
        if self._closed:
            raise PublicSessionConflict("session_closed", self._project())
        if self._active is not None:
            raise PublicSessionConflict("run_active", self._project())

    async def _cleanup_once(self) -> None:
        if self._cleanup_started:
            return
        self._cleanup_started = True
        if self.lease.cleanup is None:
            return
        result = self.lease.cleanup()
        if inspect.isawaitable(result):
            await result

    async def _cleanup_if_closed_or_terminal(self) -> None:
        if self._closed or self._status in {
            PublicSessionStatus.DONE,
            PublicSessionStatus.CANCELLED,
            PublicSessionStatus.FAILED,
            PublicSessionStatus.BLOCKED,
        }:
            await self._cleanup_once()


@dataclass(frozen=True)
class TargetRuntimeSessionFactory:
    runtime_factory: TargetRuntimeFactory
    environment_factory: RuntimeEnvironmentFactory
    request_factory: PublicTaskRequestFactory = default_public_task_request
    checkpoint_store: RuntimeCheckpointStore | None = None
    environment_reconnector: RuntimeEnvironmentReconnectFactory | None = None

    async def open(self, session_id: str, expires_at: datetime) -> TargetRuntimeSession:
        if not callable(self.request_factory):
            raise PublicSessionOpenError(PublicSessionOpenStage.SESSION, "request_factory_invalid")
        try:
            runtime = self.runtime_factory(session_id)
            if inspect.isawaitable(runtime):
                runtime = await runtime
            if not isinstance(runtime, TargetRuntime):
                raise TypeError("Runtime factory must return TargetRuntime")
        except Exception as exc:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.RUNTIME,
                "runtime_factory_failed",
            ) from exc

        lease: RuntimeEnvironmentLease | None = None
        try:
            candidate = self.environment_factory(session_id)
            if inspect.isawaitable(candidate):
                candidate = await candidate
            if not isinstance(candidate, RuntimeEnvironmentLease):
                raise TypeError("Runtime environment factory must return a typed lease")
            lease = candidate
        except Exception as exc:
            raise PublicSessionOpenError(
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_factory_failed",
            ) from exc

        return await self.open_prepared(session_id, expires_at, runtime, lease)

    async def open_prepared(
        self,
        session_id: str,
        expires_at: datetime,
        runtime: TargetRuntime,
        lease: RuntimeEnvironmentLease,
        *,
        request_factory: PublicTaskRequestFactory | None = None,
    ) -> TargetRuntimeSession:
        """Construct one session from deployment-owned resources without moving session authority."""

        selected_request_factory = request_factory or self.request_factory
        if not isinstance(runtime, TargetRuntime):
            raise PublicSessionOpenError(PublicSessionOpenStage.RUNTIME, "runtime_factory_failed")
        if not isinstance(lease, RuntimeEnvironmentLease):
            raise PublicSessionOpenError(PublicSessionOpenStage.ENVIRONMENT, "environment_factory_failed")
        if not callable(selected_request_factory):
            await _cleanup_environment_lease(lease)
            raise PublicSessionOpenError(PublicSessionOpenStage.SESSION, "request_factory_invalid")
        try:
            return TargetRuntimeSession(
                runtime,
                lease,
                session_id,
                expires_at,
                selected_request_factory,
                self.checkpoint_store,
            )
        except Exception as exc:
            await _cleanup_environment_lease(lease)
            raise PublicSessionOpenError(
                PublicSessionOpenStage.SESSION,
                "session_initialization_failed",
            ) from exc

    async def inspect(self, session_id: str) -> RuntimeRecoveryInspection:
        """Convert checkpoint truth and injected reconnectability exactly once."""

        store = self.checkpoint_store
        if store is None:
            return RecoveryInspectionUnsupported(
                "recovery_inspection_unsupported",
                "checkpoint_store_unavailable",
            )
        if self.environment_reconnector is None:
            return RecoveryInspectionUnsupported(
                "recovery_inspection_unsupported",
                "recovery_reconnector_unavailable",
            )
        try:
            checkpoint = await store.load_latest(session_id)
            if checkpoint is None:
                return RecoveryInspectionUnavailable(
                    "recovery_inspection_unavailable",
                    "checkpoint_not_found",
                )
            resume_outcome = await store.checkpoint_resume_outcome(
                session_id,
                checkpoint.checkpoint_id,
            )
            revision_outcome = await store.checkpoint_revision_outcome(
                session_id,
                checkpoint.checkpoint_id,
            )
        except Exception:
            return RecoveryInspectionFailed(
                "recovery_inspection_failed",
                "checkpoint_inspection_failed",
            )
        if resume_outcome is not None or revision_outcome is not None:
            return RecoveryInspectionUnavailable(
                "recovery_inspection_unavailable",
                "checkpoint_consumed",
            )
        if not checkpoint.resume_eligible or not checkpoint.environment_reference:
            return RecoveryInspectionUnavailable(
                "recovery_inspection_unavailable",
                "checkpoint_unavailable",
            )
        return RecoverableCheckpoint("recoverable_checkpoint", checkpoint.checkpoint_id)

    async def recover_typed(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> RuntimeRecoveryAttempt:
        store = self.checkpoint_store
        if store is None:
            return RuntimeRecoveryUnavailable(
                "recovery_unavailable",
                ("environment_not_reconnectable" if self.environment_reconnector is None else "recovery_unsupported"),
            )
        try:
            checkpoint = await store.load(session_id, checkpoint_id)
            resume_outcome = await store.checkpoint_resume_outcome(session_id, checkpoint_id)
            revision_outcome = await store.checkpoint_revision_outcome(session_id, checkpoint_id)
        except Exception:
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "checkpoint_store_failed",
            )
        if checkpoint is None:
            return RuntimeRecoveryUnavailable(
                "recovery_unavailable",
                "checkpoint_not_found",
            )
        if resume_outcome is not None:
            return RuntimeRecoveryConflict(
                "recovery_conflict",
                "checkpoint_already_resumed",
            )
        if revision_outcome is not None:
            return RuntimeRecoveryConflict(
                "recovery_conflict",
                "checkpoint_already_revised",
            )
        reconnector = self.environment_reconnector
        if not checkpoint.resume_eligible or not checkpoint.environment_reference or reconnector is None:
            return RuntimeRecoveryUnavailable(
                "recovery_unavailable",
                "environment_not_reconnectable",
            )
        try:
            runtime = self.runtime_factory(session_id)
            if inspect.isawaitable(runtime):
                runtime = await runtime
            if not isinstance(runtime, TargetRuntime):
                raise TypeError("Runtime factory must return TargetRuntime")
        except Exception:
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "runtime_factory_failed",
            )
        lease: RuntimeEnvironmentLease | None = None
        try:
            candidate = reconnector(session_id, checkpoint.environment_reference)
            if inspect.isawaitable(candidate):
                candidate = await candidate
            if not isinstance(candidate, RuntimeEnvironmentLease):
                raise TypeError("environment reconnector must return a typed lease")
            if candidate.reconnect_reference != checkpoint.environment_reference:
                raise ValueError("reconnected environment reference changed")
            lease = candidate
        except Exception:
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "environment_reconnect_failed",
            )
        try:
            task = checkpoint.restore_task()
            facts = checkpoint.restore_run_facts()
            await runtime.restore_persisted_checkpoint_history(
                checkpoint.model_history,
                task_id=task.task_id,
                task_revision=task.revision,
            )
            state = await runtime.restore_paused_checkpoint(
                lease.environment,
                task,
                facts,
                checkpoint.checkpoint_id,
            )
            session = TargetRuntimeSession(
                runtime,
                lease,
                session_id,
                expires_at,
                self.request_factory,
                store,
            )
            session._request = _request_from_task(task)
            session._admitted = ReadyTask(session_id, task)
            session._state = state
            session._status = PublicSessionStatus.PAUSED
            session._checkpoint_id = checkpoint.checkpoint_id
            session._resume_eligible = True
            session._last_control_outcome = PublicControlOutcome(
                checkpoint.pause_command_id,
                "pause",
                "paused",
                "pause_checkpoint_committed",
                checkpoint.checkpoint_id,
            )
            session._emit("SESSION_RECOVERED")
            return RuntimeRecovered("recovered", session)
        except Exception:
            await _cleanup_environment_lease(lease)
            return RuntimeRecoveryFailed(
                "recovery_failed",
                "session_restore_failed",
            )

    async def recover(
        self,
        session_id: str,
        checkpoint_id: str,
        expires_at: datetime,
    ) -> TargetRuntimeSession:
        attempt = await self.recover_typed(session_id, checkpoint_id, expires_at)
        if isinstance(attempt, RuntimeRecovered):
            return cast(TargetRuntimeSession, attempt.handle)
        if isinstance(attempt, RuntimeRecoveryConflict):
            raise PublicSessionOpenError(PublicSessionOpenStage.SESSION, attempt.reason_code)
        if isinstance(attempt, RuntimeRecoveryUnavailable):
            stage = (
                PublicSessionOpenStage.ENVIRONMENT
                if attempt.reason_code == "environment_not_reconnectable"
                else PublicSessionOpenStage.SESSION
            )
            legacy_code = (
                "checkpoint_store_unavailable" if attempt.reason_code == "recovery_unsupported" else attempt.reason_code
            )
            raise PublicSessionOpenError(stage, legacy_code)
        legacy_failure = {
            "checkpoint_store_failed": (PublicSessionOpenStage.SESSION, "checkpoint_invalid"),
            "runtime_factory_failed": (PublicSessionOpenStage.RUNTIME, "runtime_factory_failed"),
            "environment_reconnect_failed": (
                PublicSessionOpenStage.ENVIRONMENT,
                "environment_not_reconnectable",
            ),
            "session_restore_failed": (PublicSessionOpenStage.SESSION, "checkpoint_restore_failed"),
        }[attempt.reason_code]
        raise PublicSessionOpenError(*legacy_failure)


def _request_from_task(task: TaskGoal) -> NaturalLanguageTaskRequest:
    return NaturalLanguageTaskRequest(
        task.task_id,
        task.instruction,
        TaskBoundary(
            constraints=task.constraints,
            allowed_effects=task.allowed_effects,
            forbidden_effects=task.forbidden_effects,
            inputs=task.inputs,
            success_criteria=task.success_criteria,
            requested_outputs=task.requested_outputs,
            risk_profile=task.risk_profile,
            material_bindings=task.material_bindings,
            loop_budget=task.loop_budget,
            evaluation_spec=task.evaluation_spec,
        ),
        source_ref="checkpoint_restore",
        revision=task.revision,
    )


async def _cleanup_environment_lease(lease: RuntimeEnvironmentLease) -> None:
    if lease.cleanup is None:
        return
    result = lease.cleanup()
    if inspect.isawaitable(result):
        await result


def _convert_public_session_conflict(
    command_id: str,
    conflict: PublicSessionConflict,
) -> PublicCommandAdmission:
    """Exhaustively normalize legacy internal codes at the Runtime owner boundary."""

    code = conflict.code
    if code in {
        "revision_needs_input",
        "revision_no_change",
        "revision_new_task_suggested",
        "revision_unsupported",
        "revision_failed",
        "effect_reconciliation_required",
        "effect_non_compensable",
        "effect_reconciliation_unknown",
        "effect_reconciliation_unsupported",
    }:
        return PublicCommandAccepted("accepted", command_id, conflict.snapshot)
    conflict_codes: dict[str, PublicConflictCode] = {
        "stale_command": "stale_command",
        "command_identity_reused": "command_identity_reused",
        "revision_command_conflict": "command_identity_reused",
        "resume_command_conflict": "command_identity_reused",
        "takeover_command_conflict": "command_identity_reused",
        "interrupt_mismatch": "interaction_ref_mismatch",
        "checkpoint_mismatch": "checkpoint_mismatch",
        "checkpoint_already_resumed": "checkpoint_already_consumed",
        "checkpoint_already_revised": "checkpoint_already_consumed",
        "takeover_command_consumed": "checkpoint_already_consumed",
        "session_closed": "session_closed",
        "session_not_idle": "session_state_conflict",
        "run_active": "session_state_conflict",
        "run_not_active": "session_state_conflict",
        "run_not_resumable": "session_state_conflict",
        "run_not_revisable": "session_state_conflict",
        "control_request_conflict": "session_state_conflict",
        "user_control_return_unavailable": "session_state_conflict",
        "user_control_active": "control_owner_conflict",
        "user_control_not_active": "control_owner_conflict",
        "control_lease_mismatch": "control_lease_mismatch",
    }
    if code in conflict_codes:
        return PublicCommandConflict(
            "conflict",
            command_id,
            conflict_codes[code],
            conflict.snapshot,
        )
    if code in {
        "pause_unavailable",
        "resume_unavailable",
        "revision_unavailable",
        "takeover_unavailable",
    }:
        return PublicCommandUnsupported(
            "unsupported",
            command_id,
            "command_not_supported",
            conflict.snapshot,
        )
    if code in {
        "pause_persistence_failed",
        "resume_persistence_failed",
        "revision_persistence_failed",
        "takeover_persistence_failed",
        "checkpoint_not_found",
    }:
        return PublicCommandRejected(
            "rejected",
            command_id,
            "command_persistence_failed",
            conflict.snapshot,
        )
    if code in {item.value for item in InteractionAdmissionCode}:
        return PublicCommandRejected(
            "rejected",
            command_id,
            "interaction_response_invalid",
            conflict.snapshot,
        )
    if code in {
        "control_boundary_failed",
        "revision_pause_failed",
        "takeover_pause_failed",
        "user_control_currentness_unavailable",
    }:
        return PublicCommandRejected(
            "rejected",
            command_id,
            "command_processing_failed",
            conflict.snapshot,
        )
    return PublicCommandRejected(
        "rejected",
        command_id,
        "internal_contract_failure",
        conflict.snapshot,
    )


def _v3_command_capabilities(
    *,
    status: PublicSessionStatus,
    checkpoint_store_available: bool,
    checkpoint_id: str | None,
    resume_eligible: bool,
    pending_interaction: PublicInteractionRequest | None,
    pending_confirmation: PublicPendingConfirmation | None,
    control_owner: PublicSessionControlOwner,
    control_return_in_progress: bool,
    reconciliation_blocks_control: bool,
    closed: bool,
) -> tuple[PublicSessionCommandCapability, ...]:
    if closed:
        return ()
    if control_return_in_progress:
        return (PublicSessionCommandCapability(PublicSessionCommandKind.CLOSE_SESSION),)
    if control_owner is PublicSessionControlOwner.USER:
        return (
            PublicSessionCommandCapability(PublicSessionCommandKind.RETURN_CONTROL),
            PublicSessionCommandCapability(PublicSessionCommandKind.CLOSE_SESSION),
        )

    capabilities: list[PublicSessionCommandCapability] = []
    if status is PublicSessionStatus.IDLE:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.START_TASK))
    if status in {
        PublicSessionStatus.RUNNING,
        PublicSessionStatus.WAITING_USER,
        PublicSessionStatus.WAITING_CONFIRMATION,
        PublicSessionStatus.PAUSED,
    }:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.CANCEL_TASK))
    if pending_interaction is not None and status is PublicSessionStatus.WAITING_USER:
        capabilities.append(
            PublicSessionCommandCapability(
                PublicSessionCommandKind.RESPOND_INTERACTION,
                interaction_ref=pending_interaction.request_id,
                prompt=pending_interaction.prompt,
            )
        )
    if pending_confirmation is not None and status is PublicSessionStatus.WAITING_CONFIRMATION:
        for kind in (
            PublicSessionCommandKind.APPROVE_ACTION,
            PublicSessionCommandKind.REJECT_ACTION,
        ):
            capabilities.append(
                PublicSessionCommandCapability(
                    kind,
                    interaction_ref=pending_confirmation.interrupt_id,
                    summary=pending_confirmation.summary,
                    risk=pending_confirmation.risk,
                )
            )
    if checkpoint_store_available and status in {
        PublicSessionStatus.RUNNING,
        PublicSessionStatus.WAITING_USER,
        PublicSessionStatus.WAITING_CONFIRMATION,
    }:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.PAUSE_TASK))
    if (
        checkpoint_store_available
        and not reconciliation_blocks_control
        and status
        in {
            PublicSessionStatus.RUNNING,
            PublicSessionStatus.WAITING_USER,
            PublicSessionStatus.WAITING_CONFIRMATION,
            PublicSessionStatus.PAUSED,
        }
    ):
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.REVISE_TASK))
    if status is PublicSessionStatus.PAUSED and resume_eligible and checkpoint_id is not None:
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.RESUME_TASK))
    if (
        checkpoint_store_available
        and status
        in {
            PublicSessionStatus.RUNNING,
            PublicSessionStatus.WAITING_USER,
            PublicSessionStatus.WAITING_CONFIRMATION,
            PublicSessionStatus.PAUSED,
        }
        and (status is not PublicSessionStatus.PAUSED or checkpoint_id is not None)
    ):
        capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.TAKE_OVER))
    capabilities.append(PublicSessionCommandCapability(PublicSessionCommandKind.CLOSE_SESSION))
    kinds = tuple(capability.kind for capability in capabilities)
    if len(kinds) != len(set(kinds)):
        raise AssertionError("Runtime v3 command capabilities must be unique by kind")
    return tuple(capabilities)


def _revision_pause_command_id(command_id: str) -> str:
    digest = hashlib.sha256(command_id.encode()).hexdigest()[:32]
    return f"revision-pause:{digest}"


def _takeover_pause_command_id(command_id: str) -> str:
    digest = hashlib.sha256(command_id.encode()).hexdigest()[:32]
    return f"takeover-pause:{digest}"


def _public_effect_reconciliation(
    reconciliation: EffectReconciliation | None,
) -> PublicEffectReconciliation | None:
    if reconciliation is None:
        return None
    return PublicEffectReconciliation(
        cast(
            Literal["pending", "compensated", "needs_input"],
            reconciliation.status.value,
        ),
        reconciliation.reason.value,
        reconciliation.original_effect.effect_ref,
        reconciliation.original_effect.semantic_action,
        reconciliation.original_effect.resource_ref,
        cast(
            Literal["reversible", "compensatable", "irreversible", "unknown"],
            reconciliation.original_effect.reversibility.value,
        ),
        (reconciliation.compensation_effect.effect_ref if reconciliation.compensation_effect is not None else ""),
    )


def _revision_rejection(
    compiler: object,
    intake: object,
) -> tuple[str, str]:
    if isinstance(intake, TaskInputRequired):
        return "revision_needs_input", intake.question
    if isinstance(intake, TaskPolicyRejected | TaskUnsupported):
        return "revision_unsupported", intake.reason_code
    if isinstance(
        compiler,
        RevisionNeedsInput | RevisionNoChange | RevisionNewTaskSuggested | RevisionUnsupported | RevisionFailed,
    ):
        message = compiler.question if isinstance(compiler, RevisionNeedsInput) else compiler.reason
        return revision_outcome_code(compiler), message
    if isinstance(compiler, RevisionReady):
        return "revision_failed", "task_intake_failed"
    return "revision_failed", "invalid_task_revision_outcome"


@dataclass(frozen=True)
class _SessionProjectionSink(NullRunTraceSink):
    session: TargetRuntimeSession

    def run_started(self, task: object, state: object) -> None:
        if isinstance(task, TaskGoal) and isinstance(state, RunState):
            self.session._observe_started(task, state)

    def step_completed(self, step_number: int, result: object) -> None:
        if isinstance(result, StepResult):
            self.session._observe_step(step_number, result)

    def run_paused(self, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_paused(state)

    def run_finished(self, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_finished(state)

    def run_resumed(self, kind: str, details: Mapping[str, object]) -> None:
        del kind, details
        self.session._observe_resumed()

    def run_error(self, error: BaseException, state: object) -> None:
        if isinstance(state, RunState):
            self.session._observe_error(error, state)


def _feed_source(
    factory: Callable[[str], PublicFeedSource],
) -> Callable[[str], PublicFeedSource]:
    return factory


def _public_interaction_field_value(
    value: object,
) -> TextFieldValue | IntegerFieldValue | DecimalFieldValue | BooleanFieldValue | DateFieldValue:
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
    if kind == "integer" and (type(raw) is not int):
        raise TypeError("integer interaction field value is invalid")
    if kind == "boolean" and (type(raw) is not bool):
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


def _public_interaction_request(request: InteractionRequest) -> PublicInteractionRequest:
    return PublicInteractionRequest(
        request.request_id,
        request.prompt,
        request.response_kind.value,
        request.fields,
        request.options,
        request.public_intent,
    )


def _public_confirmation(risk: RiskAssessment) -> PublicPendingConfirmation:
    if not isinstance(risk, RiskAssessment):
        raise TypeError("pending confirmation requires a typed risk assessment")
    return PublicPendingConfirmation(
        f"confirmation:{risk.subject_id}",
        risk.reason,
        risk.risk.value,
    )


def _interaction_response_text(
    request: InteractionRequest,
    response: InteractionResponse,
) -> str:
    if isinstance(response, FreeTextResponse):
        return response.text
    options = {item.option_id: item.title for item in request.options}
    if isinstance(response, SingleSelectionResponse):
        return options[response.option_id]
    if isinstance(response, MultiSelectionResponse):
        return ", ".join(options[item] for item in response.option_ids)
    fields = {item.field_id: item.label for item in request.fields}
    rendered = []
    for value in response.values:
        if isinstance(value, TextFieldValue):
            public_value = value.text
        elif isinstance(value, IntegerFieldValue):
            public_value = str(value.integer)
        elif isinstance(value, DecimalFieldValue):
            public_value = value.decimal_string
        elif isinstance(value, BooleanFieldValue):
            public_value = "true" if value.boolean else "false"
        elif isinstance(value, DateFieldValue):
            public_value = value.iso_date
        else:  # pragma: no cover - InteractionResponse is a closed algebra
            raise TypeError("unsupported interaction field response")
        rendered.append(f"{fields[value.field_id]}: {public_value}")
    return "; ".join(rendered)


def _revision_feed_diff(
    before: TaskGoal,
    after: TaskGoal,
    source_id: str,
) -> PublicRevisionApplied:
    before_items = _public_goal_conditions(before)
    after_items = _public_goal_conditions(after)
    before_set = set(before_items)
    after_set = set(after_items)
    return PublicRevisionApplied(
        source_id,
        after.revision,
        before.instruction != after.instruction,
        tuple(item for item in after_items if item not in before_set),
        tuple(item for item in before_items if item not in after_set),
        tuple(item for item in after_items if item in before_set),
    )


def _public_goal_conditions(task: TaskGoal) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *task.constraints,
                *(f"Allowed effect: {item}" for item in task.allowed_effects),
                *(f"Forbidden effect: {item}" for item in task.forbidden_effects),
                *(f"Requested output: {item}" for item in task.requested_outputs),
            )
        )
    )


def _step_feed_sources(
    result: StepResult,
) -> tuple[Callable[[str], PublicFeedSource], ...]:
    sources: list[Callable[[str], PublicFeedSource]] = []
    decision = result.decision
    intent = str(getattr(decision, "public_intent", "")).strip()
    if intent:
        sources.append(_feed_source(lambda source_id: PublicAgentIntent(source_id, intent)))

    if isinstance(decision, InteractionRequest):
        request = _public_interaction_request(decision)
        sources.append(
            _feed_source(lambda source_id: PublicInteractionRequested(source_id, request))
        )
        return tuple(sources)

    if result.confirmation is not None:
        confirmation = _public_confirmation(result.confirmation)
        sources.append(
            _feed_source(
                lambda source_id: PublicConfirmationRequired(source_id, confirmation)
            )
        )
        return tuple(sources)

    if isinstance(decision, RequestObservation) and result.observation_outcome is not None:
        outcome = result.observation_outcome
        status = {
            ObservationQueryDisposition.OBSERVED: "observed",
            ObservationQueryDisposition.PARTIAL: "partial",
            ObservationQueryDisposition.UNKNOWN: "unknown",
            ObservationQueryDisposition.FAILED: "failed",
        }[outcome.disposition]
        message = {
            "observed": "Visual evidence was observed.",
            "partial": "Some visual evidence could not be confirmed.",
            "unknown": "The requested visual evidence could not be confirmed.",
            "failed": "Visual evidence acquisition failed.",
        }[status]
        refs = outcome.evidence_refs
        sources.append(
            _feed_source(
                lambda source_id: PublicEvidenceSummary(
                    source_id,
                    "visual",
                    cast(
                        Literal["observed", "partial", "unknown", "failed", "stale"],
                        status,
                    ),
                    message,
                    evidence_refs=refs,
                )
            )
        )
        return tuple(sources)

    if isinstance(decision, SelectAction):
        activity, evidence = _action_feed_sources(result)
        sources.append(activity)
        if evidence is not None:
            sources.append(evidence)
        return tuple(sources)

    if isinstance(decision, PolicyFailure):
        code = result.failure_code.value if result.failure_code is not None else decision.kind.value
        sources.append(
            _feed_source(
                lambda source_id: PublicFailure(
                    source_id,
                    code,
                    decision.reason,
                )
            )
        )
        return tuple(sources)

    kind = getattr(getattr(decision, "kind", None), "value", "")
    labels = {
        "request_action_page": "Updated the available interface actions.",
        "read_region": "Read more of the current interface.",
        "search_page_content": "Searched the current interface content.",
        "wait": "Waited for the interface to update.",
    }
    if kind in labels:
        label = labels[kind]
        sources.append(
            _feed_source(
                lambda source_id: PublicRuntimeActivity(
                    source_id,
                    "completed",
                    label,
                )
            )
        )
    return tuple(sources)


def _action_feed_sources(
    result: StepResult,
) -> tuple[
    Callable[[str], PublicFeedSource],
    Callable[[str], PublicFeedSource] | None,
]:
    outcome = result.action_outcome
    if outcome is not None:
        activity_status, message = {
            LocalPostconditionStatus.SATISFIED: (
                "completed",
                "The interface change was confirmed.",
            ),
            LocalPostconditionStatus.UNSATISFIED: (
                "failed",
                "The requested interface change was not confirmed.",
            ),
            LocalPostconditionStatus.UNKNOWN: (
                "uncertain",
                "The interface action finished, but its effect could not be confirmed.",
            ),
            LocalPostconditionStatus.NOT_APPLICABLE: (
                "completed",
                "The interface action was completed.",
            ),
        }[outcome.local_postcondition]
        refs = outcome.evidence_refs
        def activity(source_id: str) -> PublicFeedSource:
            return PublicRuntimeActivity(
                source_id,
                cast(Literal["started", "completed", "uncertain", "failed"], activity_status),
                message,
                refs,
            )

        if not refs:
            return activity, None
        evidence_kind = {
            EvidenceMethod.STRUCTURAL: "structural",
            EvidenceMethod.VISUAL_DIFF: "visual",
            EvidenceMethod.NATIVE: "structural",
            EvidenceMethod.NONE: "unknown",
        }[outcome.evidence_method]
        evidence_status = (
            "unknown"
            if outcome.local_postcondition is LocalPostconditionStatus.UNKNOWN
            else "observed"
        )
        def evidence(source_id: str) -> PublicFeedSource:
            return PublicEvidenceSummary(
                source_id,
                cast(Literal["structural", "visual", "mixed", "unknown"], evidence_kind),
                cast(Literal["observed", "partial", "unknown", "failed", "stale"], evidence_status),
                "Evidence was recorded for the interface action.",
                evidence_refs=refs,
            )

        return activity, evidence

    completion = (
        result.execution_receipts.completion
        if result.execution_receipts is not None
        else None
    )
    status, label = {
        ExecutionCompletion.COMPLETE: ("completed", "The interface action was completed."),
        ExecutionCompletion.PARTIAL: ("uncertain", "The interface action completed only partially."),
        ExecutionCompletion.UNKNOWN: ("uncertain", "The interface action result is uncertain."),
        ExecutionCompletion.CANCELLED: ("failed", "The interface action was cancelled."),
        None: ("failed", "The interface action was not executed."),
    }[completion]
    return (
        lambda source_id: PublicRuntimeActivity(
            source_id,
            status,  # type: ignore[arg-type]
            label,
        ),
        None,
    )


def _control_feed_sources(
    event_type: str,
    outcome: PublicControlOutcome | None,
) -> tuple[Callable[[str], PublicFeedSource], ...]:
    status, label = {
        "RUN_STARTED": ("started", "Runtime is continuing the task."),
        "CONTROL_REQUESTED": ("started", "A control change was requested."),
        "RUN_PAUSED": ("completed", "The task is paused."),
        "RUN_RESUMED": ("started", "The task resumed."),
        "USER_CONTROL_GRANTED": ("completed", "Control was handed to you."),
        "USER_CONTROL_REVOKED": ("started", "User control was returned for a fresh check."),
        "USER_CONTROL_RETURNED": ("completed", "The Agent has control again."),
        "USER_CONTROL_RETURN_FAILED": (
            "failed",
            "Control could not be returned because currentness was unavailable.",
        ),
        "CONTROL_FAILED": ("failed", "The requested control change failed."),
    }.get(event_type, ("", ""))
    if not status:
        return ()
    if outcome is not None and outcome.message:
        label = outcome.message
    return (
        lambda source_id: PublicRuntimeActivity(
            source_id,
            status,  # type: ignore[arg-type]
            label,
        ),
    )


def _public_status(status: RunStatus) -> PublicSessionStatus:
    return {
        RunStatus.RUNNING: PublicSessionStatus.RUNNING,
        RunStatus.PAUSED: PublicSessionStatus.PAUSED,
        RunStatus.WAITING_USER: PublicSessionStatus.WAITING_USER,
        RunStatus.WAITING_CONFIRMATION: PublicSessionStatus.WAITING_CONFIRMATION,
        RunStatus.DONE: PublicSessionStatus.DONE,
        RunStatus.BLOCKED: PublicSessionStatus.BLOCKED,
        RunStatus.CANCELLED: PublicSessionStatus.CANCELLED,
        RunStatus.FAILED: PublicSessionStatus.FAILED,
    }[status]


def _completion(state: RunState | None, status: PublicSessionStatus) -> PublicCompletion | None:
    if state is None or status not in {
        PublicSessionStatus.DONE,
        PublicSessionStatus.BLOCKED,
        PublicSessionStatus.CANCELLED,
        PublicSessionStatus.FAILED,
    }:
        return None
    if status is PublicSessionStatus.CANCELLED:
        return PublicCompletion(
            "cancelled",
            "user_cancelled",
            "Runtime cancelled the task at a safe execution boundary.",
        )
    evaluation = state.current_task_evaluation
    outcome = evaluation.outcome if evaluation is not None else None
    if evaluation is not None and outcome is not None and outcome.kind is TaskOutcomeKind.TERMINAL_SUCCESS:
        last_decision = state.last_step.decision if state.last_step is not None else None
        message = last_decision.content if isinstance(last_decision, FinalResponse) else evaluation.reason
        artifact = state.last_step.public_artifact if state.last_step is not None else None
        return PublicCompletion("success", outcome.code, message, outcome.evidence_refs, artifact)
    if evaluation is not None and outcome is not None and outcome.kind is TaskOutcomeKind.TERMINAL_FAILURE:
        return PublicCompletion("failure", outcome.code, evaluation.reason, outcome.evidence_refs)
    failure = state.runtime_failure
    if failure is not None:
        return PublicCompletion("failure", failure.code, "Runtime could not complete the task.")
    control = state.control_termination
    if control is not None:
        return PublicCompletion("blocked", str(control.kind), "Runtime stopped before completion.")
    return PublicCompletion("blocked", "runtime_blocked", evaluation.reason if evaluation else "Task blocked.")
